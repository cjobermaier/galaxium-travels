# Trust Boundary Audit — Itinerary Endpoints

**Scope:** `POST /itineraries`, `POST /itineraries/{itinerary_id}/confirm`  
**Files:** `booking_system_backend/server.py`, `booking_system_backend/schemas.py`,
`booking_system_backend/services/itinerary.py`  
**Standard:** OWASP ASVS 4.0

---

## Phase 1 — Trust Boundary Map

### POST /itineraries

Client controls the entire JSON body via `CreateItineraryRequest`:

| Field | Type | Server action |
|---|---|---|
| `user_id` | int | Looked up in DB; used as `travelerId` in Java quote payload |
| `name` | str | Compared against DB user name; used as `travelerName` in Java quote payload |
| `flight_ids` | list[int] (1–3) | Each ID looked up in DB; a hold is placed on each flight |

`seat_class` is **not** a client field — the service hard-codes `"economy"` for every leg
(`itinerary.py` line 106).

### POST /itineraries/{itinerary_id}/confirm

Client controls only the URL path parameter:

| Field | Type | Server action |
|---|---|---|
| `itinerary_id` | int (path) | Looked up in DB; status checked; Java confirm called per leg |

No request body is accepted.

---

## Phase 2 — Control Checks

| Control | Result | Notes |
|---|---|---|
| V5.1.2 — Mass parameter assignment | **FAIL** | `/internal/bookings/from-hold` accepts `dict` — see F-1 |
| V5.1.3 — Input validated against allow list | **FAIL** | `name` and `user_id` are not sanitised — see F-2; `seat_class` injected from Java response without validation — see F-3 |
| V11.1.4 — Business limits on inventory | **FAIL** | No per-user cap on held itineraries — see F-4 |
| V11.1.5 — Business logic limits against price abuse | **FAIL** | Seat class is fixed to `economy` for itineraries; however, the internal endpoint accepts a client-supplied `seatClass` string directly — see F-3 |

---

## Phase 3 — Findings

### F-1 — Mass Assignment on Internal Booking Endpoint

- **Rule:** V5.1.2
- **Severity:** High
- **File/line:** `server.py:286`
- **Issue:** `create_booking_from_hold` accepts the request body as `dict`, so any extra
  fields the caller sends are silently ignored only by accident — there is no schema
  enforcing the exact allowed fields, and a caller could probe or confuse the handler.
- **Fix:** Replace the `dict` parameter with a typed Pydantic model
  (e.g. `HoldCallbackRequest`) that declares exactly the four expected fields:
  `travelerId`, `travelerName`, `flightId`, and `seatClass`.

---

### F-2 — `name` Field Has No Length or Character Constraint

- **Rule:** V5.1.3
- **Severity:** Medium
- **File/line:** `schemas.py:109`
- **Issue:** `CreateItineraryRequest.name` is declared as `str` with no minimum or
  maximum length and no character-set constraint; an arbitrarily large or specially
  crafted string is forwarded verbatim into the Java quote payload
  (`itinerary.py:109`) and into error messages.
- **Fix:** Add `Field(min_length=1, max_length=120)` (or an equivalent
  `Annotated[str, StringConstraints(...)]`) to `CreateItineraryRequest.name`.

---

### F-3 — `seatClass` from Java Response Passed to `book_flight` Without Validation

- **Rule:** V5.1.3, V11.1.5
- **Severity:** High
- **File/line:** `server.py:297`
- **Issue:** The internal callback endpoint reads `hold_data["seatClass"]` straight from
  the caller's JSON and passes it to `booking.book_flight` as the `seat_class`
  argument with no validation against the allowed literal set
  (`'economy' | 'business' | 'galaxium'`). A caller that can reach the internal
  endpoint can supply `"galaxium"` and obtain a premium booking at economy price.
- **Fix:** Validate the value against the `SeatClass` literal (or a strict allow-list
  check) before passing it to `book_flight`; using the typed Pydantic model from F-1
  and declaring `seat_class: SeatClass` on it achieves this automatically.

---

### F-4 — No Per-User Cap on Concurrent Held Itineraries

- **Rule:** V11.1.4
- **Severity:** Medium
- **File/line:** `services/itinerary.py:50` (`create_itinerary`)
- **Issue:** `create_itinerary` places a Java inventory hold for each requested flight
  without checking how many itineraries the same `user_id` already has in `"held"`
  status; a single user can hold an unlimited number of seats across the entire
  inventory.
- **Fix:** Before placing any holds, query the `Itinerary` table for the number of rows
  where `user_id == user_id AND status == "held"` and return a
  `TOO_MANY_HOLDS` error if it meets or exceeds a configurable threshold (e.g. 5).

---

## Summary

| ID | ASVS | Severity | Location |
|---|---|---|---|
| F-1 | V5.1.2 | High | `server.py:286` |
| F-2 | V5.1.3 | Medium | `schemas.py:109` |
| F-3 | V5.1.3 / V11.1.5 | High | `server.py:297` |
| F-4 | V11.1.4 | Medium | `services/itinerary.py:50` |
