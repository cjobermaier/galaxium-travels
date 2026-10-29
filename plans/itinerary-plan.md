# Multi-Leg Itinerary Plan

## Overview

Add multi-leg itinerary support to Galaxium Travels so a traveller can search for routes of 1–3 legs, book all legs atomically through the Java hold service, and review booked trips on a new `/trips` page.

The work is split into two sequential sub-tasks:

1. **Backend** — new DB tables, schemas, services, and routes
2. **Frontend** — new `/trips` page, `Trips` nav link, API client additions

Key constraints carried through both sub-tasks:

- `parse_time(value)` and `is_valid_connection(arriving, departing)` are written by the developer in `booking_system_backend/services/itinerary_search.py` during sub-task 1 step 5. The plan only adds `search_itineraries` to that same file alongside those functions; it does not stub or rewrite them.
- `bookings.itinerary_id` is added with `ALTER TABLE` in `init_db()`, not by deleting the database.
- The `Book trip` button on the frontend holds **and** confirms in one click. There is no separate confirm endpoint exposed on the frontend.
- Each leg's `booking_id` (from `externalBookingReference` after confirm) is stored on `ItineraryLeg` so that a failed confirm can cancel the already-created bookings.

---

## Sub-task 1 — Backend

**Status:** [x] done

### Intent

Deliver all Python-side changes needed to search, hold, confirm, and list multi-leg itineraries. No frontend changes.

### Expected Outcomes

- `GET /itineraries/search?origin=&destination=&date=` returns routes of 1–3 legs, sorted by total travel time then total price, with layovers 2–72 h.
- Searching Earth → Europa on 2099-02-01 returns one three-leg result (Flights A → B → C from AC4).
- Searching Earth → Mars on 2099-03-01 returns a two-leg result via Moon.
- `POST /itineraries` holds every leg through the Java hold service all-or-nothing; returns `HOLD_FAILED` + HTTP 502 if any hold fails, releasing earlier holds first.
- `POST /itineraries/{itinerary_id}/confirm` confirms all holds leg by leg; the Java service calls `/internal/bookings/from-hold` to create each `Booking` and returns `booking_id` in `externalBookingReference`; the service stores that on the leg and must not call `/book` again.
- `GET /users/{user_id}/itineraries` returns the user's itineraries with legs.
- `itineraries`, `itinerary_legs` tables exist in the DB. `bookings.itinerary_id` column exists (nullable). Existing databases keep working via `ALTER TABLE` in `init_db()`.
- All service functions follow the `result | ErrorResponse` pattern from `booking_system_backend/services/booking.py`.
- `ruff check .` passes with no new errors.
- Existing backend tests pass unchanged.

### Todo List

1. **Extend `booking_system_backend/seed.py`** — add the four AC4 flights on 2099-02-01 and the two AC5 flights (Earth → Moon and Moon → Mars) on 2099-03-01. Use the same seat-distribution helper already in the file. Keep seeds idempotent (the existing user-count guard already handles that).

2. **Add new SQLAlchemy models in `booking_system_backend/models.py`**:
   - `Itinerary` table: `itinerary_id` (PK), `user_id` (FK → users), `status` (String: `held` | `confirmed` | `failed`), `created_at` (String).
   - `ItineraryLeg` table: `leg_id` (PK), `itinerary_id` (FK → itineraries), `flight_id` (FK → flights), `booking_id` (FK → bookings, nullable), `hold_id` (String, nullable), `leg_order` (Integer).
   - Add nullable `itinerary_id` column to `Booking` in the model declaration. Do **not** include it in a `create_all`-managed constraint, because `create_all` on a fresh DB will create the column automatically while `init_db()` handles it with `ALTER TABLE` on existing DBs.

3. **Update `init_db()` in `booking_system_backend/db.py`** — after `Base.metadata.create_all(bind=engine)`, execute `ALTER TABLE bookings ADD COLUMN itinerary_id INTEGER REFERENCES itineraries(itinerary_id)` via SQLAlchemy `text()` and `engine.connect()`. Wrap the execute in a try/except that silently ignores the "duplicate column" (or equivalent) database error so `init_db()` is safe to run on both a fresh DB and an existing one. The two new tables (`itineraries`, `itinerary_legs`) are created by `create_all` and need no `ALTER`.

4. **Add new Pydantic schemas in `booking_system_backend/schemas.py`**:
   - `ItineraryLegOut` — `leg_id`, `flight_id`, `leg_order`, `flight` (FlightOut), `booking_id` (nullable), `hold_id` (nullable).
   - `ItineraryOut` — `itinerary_id`, `user_id`, `status`, `created_at`, `legs` (list of `ItineraryLegOut`), `total_price` (sum of economy prices).
   - `ItinerarySearchResult` — a list of `legs` (list of `FlightOut`) with computed `total_price` and `total_duration_minutes`.
   - `CreateItineraryRequest` — `user_id`, `name`, `flight_ids` (list of int, 1–3 items).

5. **Add `search_itineraries` to `booking_system_backend/services/itinerary_search.py`** — the file already contains `parse_time` and `is_valid_connection` written by the developer; only add `search_itineraries(db, origin, destination, date)` below them:
   - Call `parse_time` to normalise departure/arrival strings when comparing times.
   - Call `is_valid_connection(arriving, departing)` to filter candidate next legs.
   - Load all flights departing on or after `date 00:00` and before `date+1 00:00` from the DB (no seat filter — search does not check seats per A3).
   - Build routes BFS-style up to 3 legs: for each candidate prefix, extend with any flight whose origin matches the current endpoint, whose departure is after the current arrival, and for which `is_valid_connection(arriving, departing)` returns `True`.
   - Collect routes that end at `destination`.
   - Sort by `total_duration_minutes` ascending, then `total_price` ascending.
   - Return `list[ItinerarySearchResult]`.

6. **Create `booking_system_backend/services/itinerary.py`** — implement three service functions following the `result | ErrorResponse` pattern:

   a. `create_itinerary(db, user_id, name, flight_ids) -> ItineraryOut | ErrorResponse`:
      - Reject duplicate `flight_ids` with `error_code="DUPLICATE_LEGS"`.
      - Validate user exists and name matches (reuse the pattern from `booking.py`).
      - Validate each `flight_id` exists and has economy seats ≥ 1.
      - For each leg in order: POST `{flightId, seatClass: "economy", quantity: 1, travelerId: user_id, travelerName: name}` to `{JAVA_SERVICE_URL}/api/v1/quotes`, then POST to `.../holds`. Use `httpx.AsyncClient` directly — do not call the Python proxy routes.
      - If any hold fails: release all successfully obtained holds (POST `.../release`) in reverse order, set itinerary status to `failed`, and return `ErrorResponse(error_code="HOLD_FAILED", ...)` with the intent to raise HTTP 502 in the route handler.
      - On full success: persist `Itinerary` (status=`held`) and one `ItineraryLeg` per flight with the returned `hold_id`, commit.
      - Return `ItineraryOut`.

   b. `confirm_itinerary(db, itinerary_id) -> ItineraryOut | ErrorResponse`:
      - Verify itinerary exists and status is `held`.
      - Iterate over legs in `leg_order` order. For each leg: POST `{JAVA_SERVICE_URL}/api/v1/holds/{hold_id}/confirm`. Java calls `/internal/bookings/from-hold`, which creates the `Booking` and returns `booking_id` as a string in `externalBookingReference`. Parse it to int and store it on `ItineraryLeg.booking_id` immediately (so subsequent cleanup can find it).
      - **If any leg's confirm call fails** (HTTP error, Java unavailable, or `CONFIRMATION_FAILED` status in the response):
        - Cancel the bookings of every leg already confirmed: call `cancel_booking(db, leg.booking_id)` from `services/booking.py` for each leg whose `booking_id` is set.
        - Release the holds of every remaining leg (those whose confirm was not yet attempted): POST `{JAVA_SERVICE_URL}/api/v1/holds/{hold_id}/release` for each.
        - Mark itinerary status as `failed`, commit.
        - Return `ErrorResponse(error_code="CONFIRM_FAILED", ...)` — the route handler raises HTTP 502.
      - On full success: update itinerary status to `confirmed`, commit.
      - Return `ItineraryOut`.

   c. `get_user_itineraries(db, user_id) -> list[ItineraryOut]`:
      - Query `Itinerary` rows by `user_id`, ordered by `created_at` descending.
      - Eager-load legs and their flights.
      - Return list of `ItineraryOut`.

7. **Add new routes in `booking_system_backend/server.py`**:
   - `GET /itineraries/search` — query params `origin`, `destination`, `date`. Calls `search_itineraries`. Returns `list[ItinerarySearchResult]`.
   - `POST /itineraries` — body `CreateItineraryRequest`. Calls `create_itinerary`. Returns `ItineraryOut` or raises HTTP 502 on `HOLD_FAILED`.
   - `POST /itineraries/{itinerary_id}/confirm` — calls `confirm_itinerary`. Returns `ItineraryOut` or raises HTTP 502 on `CONFIRM_FAILED`. (Used internally by the frontend `Book trip` handler; not a user-facing separate step.)
   - `GET /users/{user_id}/itineraries` — calls `get_user_itineraries`. Returns `list[ItineraryOut]`.

8. **Add a service-level test in `booking_system_backend/tests/test_services.py`** for the partial-confirm failure path:

   `test_confirm_itinerary_partial_failure` — verifies that when the second leg's Java confirm call fails in a two-leg itinerary, `confirm_itinerary` returns an `ErrorResponse` with `error_code="CONFIRM_FAILED"`, the itinerary status is `failed`, the first leg's already-created booking is cancelled, and the second leg's hold is released.

   Setup:
   - Insert a `User`, two `Flight` rows, and an `Itinerary` with status `held`, plus two `ItineraryLeg` rows with `hold_id` values `"H-001"` and `"H-002"` and `leg_order` 1 and 2.
   - Patch `httpx.AsyncClient` (or the relevant module-level attribute in `services/itinerary.py`) so that:
     - `POST .../holds/H-001/confirm` returns a successful response (`status: "CONFIRMED"`, `externalBookingReference: "99"`).
     - `POST .../holds/H-002/confirm` raises `httpx.HTTPStatusError` (simulating a Java 5xx).
     - `POST .../holds/H-002/release` returns a successful response.
   - Also patch `services.booking.cancel_booking` to record that it was called.

   Assertions:
   - Return value is an `ErrorResponse` with `error_code="CONFIRM_FAILED"`.
   - The db itinerary row has `status == "failed"`.
   - `cancel_booking` was called once with the booking_id from leg 1 (`99`).
   - The release call for `H-002` was made.

   Follow the existing test style in [`booking_system_backend/tests/test_services.py`](../booking_system_backend/tests/test_services.py) and use the `db_session` fixture from [`booking_system_backend/tests/conftest.py`](../booking_system_backend/tests/conftest.py).

### Relevant Context

- Service pattern: [`booking_system_backend/services/booking.py`](../booking_system_backend/services/booking.py) — return `result | ErrorResponse`, check `isinstance(result, ErrorResponse)` in the route.
- Models: [`booking_system_backend/models.py`](../booking_system_backend/models.py) — `Base`, `Flight`, `Booking`, `User`.
- DB init: [`booking_system_backend/db.py`](../booking_system_backend/db.py) — `init_db()` calls `Base.metadata.create_all`.
- Schemas: [`booking_system_backend/schemas.py`](../booking_system_backend/schemas.py) — `FlightOut`, `BookingOut`, `ErrorResponse`.
- Java hold service URLs: `POST /api/v1/quotes`, `POST /api/v1/quotes/{quoteId}/holds`, `POST /api/v1/holds/{holdId}/confirm`, `POST /api/v1/holds/{holdId}/release`. Base URL from `JAVA_SERVICE_URL` env var (default `http://localhost:8080`).
- Java confirm flow: confirming a hold triggers Java → Python `/internal/bookings/from-hold`; the resulting `booking_id` appears in the confirm response as `externalBookingReference`. Do not call `/book` again.
- Seed data: [`booking_system_backend/seed.py`](../booking_system_backend/seed.py) — add to the `flight_data` list; existing user-count guard keeps seeds idempotent.
- `ruff` ignores `B008` (FastAPI `Depends`). Run `ruff check .` from `booking_system_backend/`.

---

## Sub-task 2 — Frontend

**Status:** [x] done

### Intent

Add a `/trips` page where a signed-in traveller can search for multi-leg itineraries, book in one click, and review their booked trips. Also add a `Trips` nav link in the header.

### Expected Outcomes

- `/trips` route exists in `App.tsx`.
- `Trips` nav link appears in the header next to `Flights` (visible to all; redirects unauthenticated users to identify before booking).
- The search form accepts origin, destination, and date; submits to `GET /itineraries/search` via the api client.
- Results are rendered as a trip timeline per itinerary: each leg shows origin → destination, departure/arrival times, economy price; layovers show duration between legs.
- A `Book trip` button on each result calls `POST /itineraries` then `POST /itineraries/{id}/confirm` in sequence (one click, no separate confirm step). Requires the user to be identified first; if not, shows the `UserIdentification` modal.
- A `My trips` section below the search results shows the signed-in user's confirmed itineraries from `GET /users/{user_id}/itineraries`. Each trip card shows first-leg origin, last-leg destination, first departure, last arrival, total price, and expands to show individual legs.
- Empty-state messages for no search results and no booked trips.
- `npm run lint` and `npm run build` pass with no new errors.

### Todo List

1. **Add new TypeScript types in `booking_system_frontend/src/types/index.ts`**:
   - `ItineraryLeg` — `leg_id`, `flight_id`, `leg_order`, `flight` (Flight), `booking_id` (number | null), `hold_id` (string | null).
   - `Itinerary` — `itinerary_id`, `user_id`, `status` (`'held' | 'confirmed' | 'failed'`), `created_at`, `legs` (ItineraryLeg[]), `total_price`.
   - `ItinerarySearchResult` — `legs` (Flight[]), `total_price`, `total_duration_minutes`.
   - `CreateItineraryRequest` — `user_id`, `name`, `flight_ids` (number[]).

2. **Add new API functions in `booking_system_frontend/src/services/api.ts`**:
   - `searchItineraries(origin, destination, date)` → `ItinerarySearchResult[]` — `GET /itineraries/search`.
   - `createItinerary(data: CreateItineraryRequest)` → `Itinerary | ErrorResponse` — `POST /itineraries`.
   - `confirmItinerary(itineraryId: number)` → `Itinerary | ErrorResponse` — `POST /itineraries/{itinerary_id}/confirm`.
   - `getUserItineraries(userId: number)` → `Itinerary[]` — `GET /users/{user_id}/itineraries`.

3. **Create `booking_system_frontend/src/components/trips/TripTimeline.tsx`** — receives a single `ItinerarySearchResult` and renders:
   - Each leg as a row: origin → destination, departure time, arrival time, economy price.
   - Between consecutive legs: a layover badge showing the layover duration in hours and minutes.
   - A total price row at the bottom.
   - A `Book trip` button that calls the `onBook` callback prop.

4. **Create `booking_system_frontend/src/components/trips/TripCard.tsx`** — receives a single `Itinerary` and renders:
   - Collapsed view: first-leg origin → last-leg destination, first departure, last arrival, total price paid, `status` badge.
   - Expanded view (toggle on click): each leg listed with flight_id, origin, destination, departure, arrival.

5. **Create `booking_system_frontend/src/pages/Trips.tsx`**:
   - Search form: `origin`, `destination`, `date` inputs + a `Search` button.
   - On submit: call `searchItineraries`; show `LoadingSpinner` while loading; show results as `TripTimeline` cards; show an empty-state message when results are empty.
   - `Book trip` handler: if no user, show `UserIdentification` modal; once user is known, call `createItinerary` then immediately `confirmItinerary` in the same handler — one click, no separate confirm step in the UI. On success show a toast and refresh My trips. On error (including `HOLD_FAILED`) show a toast with the error message.
   - `My trips` section (only when user is signed in): call `getUserItineraries` on mount and after a successful booking; render `TripCard` components; show empty state if none.

6. **Register the route and nav link**:
   - Add `<Route path="/trips" element={<Trips />} />` in `booking_system_frontend/src/App.tsx`.
   - Add a `Trips` `<Link>` in both the desktop and mobile nav blocks in `booking_system_frontend/src/components/layout/Header.tsx`, immediately after the existing `Flights` link. Apply the same active-state class pattern already used for `Flights`.

### Relevant Context

- Existing page pattern: [`booking_system_frontend/src/pages/Flights.tsx`](../booking_system_frontend/src/pages/Flights.tsx) — search form, loading/error/empty states, booking modal flow.
- Header nav pattern: [`booking_system_frontend/src/components/layout/Header.tsx`](../booking_system_frontend/src/components/layout/Header.tsx) — `isActive()` helper, desktop + mobile nav blocks.
- API client: [`booking_system_frontend/src/services/api.ts`](../booking_system_frontend/src/services/api.ts) — single axios instance, `isErrorResponse()` helper.
- Types: [`booking_system_frontend/src/types/index.ts`](../booking_system_frontend/src/types/index.ts).
- App routing: [`booking_system_frontend/src/App.tsx`](../booking_system_frontend/src/App.tsx).
- Reuse `UserIdentification` modal, `LoadingSpinner`, `Button`, `Card`, `toast` patterns already present in the project.
- Tailwind classes follow the existing `glass-card`, `cosmic-gradient`, `star-white` design tokens.
