# Conversation transcript: security-critic review and fixes

Repository: galaxium-travels (branch `course/m01-start`)

Tool calls (file reads, edits, test runs) are summarized in italics. User messages and assistant replies are reproduced as given.

---

## 1. Create the agent file

**User:** create a nlank file .bob/agents/security-critic.md

*Assistant created an empty `.bob/agents/security-critic.md`.*

**Assistant:** I created the blank file at `.bob/agents/security-critic.md`.

*The file was then filled in externally with this definition:*

```markdown
---
name: security-critic
description: Reviews changed backend code for security flaws against OWASP ASVS. Read-only.
tools:
  - read
---
You are an application security reviewer. You did not write this code, and you have not seen the reasoning behind it.

Check the files you are given for:
1. Request fields a client controls that affect prices, holds, or other server-owned values
2. Missing limits that let one user exhaust shared resources
3. Input that is accepted without validation

The app has no authentication yet. Don't report missing authentication or authorization.

Report findings in a table with columns: Severity, File, Lines, ASVS control, Description.
Use severity levels HIGH, MEDIUM, LOW. If you find nothing, say so. Don't invent findings.
Do not suggest code. Describe issues only.
```

---

## 2. Review round 1

**User:** Spawn a security critic subagent. Have it review @booking_system_backend/schemas.py, @booking_system_backend/server.py, and the itinerary service module in booking_system_backend/services/.

*Assistant read the agent definition, located `services/itinerary.py`, and spawned a read-only subagent.*

**Subagent report:**

| Severity | File | Lines | ASVS control | Description |
|---|---|---|---|---|
| HIGH | server.py | 288-303 | 4.1.4, 6.3.5 | `/internal/bookings/from-hold` accepts an unvalidated `dict`. |
| HIGH | server.py | 308-321 | 4.1.4 | `/quotes` accepts an unvalidated `dict` and proxies it to the Java service. |
| MEDIUM | schemas.py | 51-55 | 4.1.4 | `BookingRequest` fields have no validation constraints. |
| MEDIUM | schemas.py | 107-110 | 4.1.4 | `CreateItineraryRequest.user_id` and `name` have no constraints. |
| MEDIUM | server.py | 339-351 | 5.3.2 | `/quotes/{quote_id}/holds` has no rate limit. |
| LOW | server.py | 73-152 | 4.1.4 | `/flights` numeric filters have no bounds. |

**Assistant summary:** Presented the table, noted that `itinerary.py` had no findings of its own, that `itinerary_search.py` was not included, and that the subagent's line numbers and ASVS IDs were not independently verified.

---

## 3. Fix round 1

**User:** Fix the HIGH and MEDIUM findings the security-critic subagent reported. Don't change the confirm endpoint or /internal/bookings/from-hold. Add a test for each fix.

*Changes:*
- `schemas.py`: `BookingRequest` and `CreateItineraryRequest` gained bounds (`user_id`/`flight_id` >= 1, `name` 1-100 chars). New `CreateQuoteRequest` (camelCase, `extra='forbid'`, seat class literal, quantity 1-10, bounded IDs/name) and `MAX_QUOTE_QUANTITY = 10`.
- `server.py`: `/quotes` now takes `CreateQuoteRequest` and forwards only validated fields; `/quotes/{id}/holds` is rate limited (429).
- New `services/hold_rate_limit.py`: in-memory per-client-IP limiter, 20/min, `HOLD_RATE_LIMIT_PER_MINUTE`.
- New `tests/test_security_fixes.py`.

*Validation: 132 backend tests passed; ruff clean on touched files (4 pre-existing ruff errors remain in other files).*

**Assistant summary:** Fixed the two HIGH and three MEDIUM findings except `/internal/bookings/from-hold`, which was explicitly excluded. Noted the quote-quantity cap of 10 was my own choice, that the limiter is in-memory and keyed on client IP, and that e2e tests were not run.

---

## 4. Review round 2

**User:** Spawn a security critic subagent. Have it review @booking_system_backend/schemas.py, @booking_system_backend/server.py, and the itinerary service module in booking_system_backend/services/.

**Subagent report:**

| Severity | File | Lines | Description |
|---|---|---|---|
| HIGH | server.py | 289-300 | `create_booking_from_hold` takes an untyped dict. |
| HIGH | services/flight.py | 107-111 | Price filters accept any integer. |
| MEDIUM | services/flight.py | 166-172 | `min_seats_available` has no validation. |
| MEDIUM | services/flight.py | 55-57, 94-97 | Duration filters have no bounds. |
| MEDIUM | services/flight.py | 54, 101-104 | Date filters are unvalidated strings "concatenated into SQL". |
| MEDIUM | server.py | 74-154 | `GET /flights` has no pagination or result limit. |
| LOW | schemas.py | 54-58, 110-113 | Callers supply `user_id`. |

**Assistant assessment (after checking the code):**
- `from-hold`: same as before, left alone as instructed.
- Price filters: overrated; they only change the result set, LOW at most.
- Seat and duration filters: overrated, same reasoning.
- Date filters: the "SQL injection" claim is inaccurate; the queries use bound parameters. A malformed date is a validation gap only.
- `GET /flights` without a result limit: valid.
- `user_id` finding: mostly out of scope (authentication).
- The subagent also reviewed `services/flight.py`, which was outside its brief, and applied ASVS 5.1.1 indiscriminately.

---

## 5. Fix round 2

**User:** Fix the HIGH and MEDIUM findings the security-critic subagent reported. Don't change the confirm endpoint or /internal/bookings/from-hold. Add a test for each fix.

*Changes:*
- `server.py`: `GET /flights` bounds: prices 0-1,000,000,000; durations 0-10,000 hours; `min_seats_available` 0-10,000; dates must match `YYYY-MM-DD` with an optional `T`/space suffix, max 40 chars; new `limit` (1-500, default 100) and `offset` (>= 0).
- `services/flight.py`: `list_flights` accepts `limit`/`offset`, applied after filtering and sorting.
- `tests/test_security_fixes.py`: `TestFlightsQueryBounds`, `TestFlightsPagination`.

*Validation: 152 tests passed; ruff clean on touched files. Seeded flights: 16.*

**Assistant summary:** Fixed the price/seat/duration/date bounds and added pagination. Noted the default limit of 100, that the frontend sends no `limit`, that the filter inputs can still send negatives (now a 422), and that e2e tests were not run.

---

## 6. Review round 3

**User:** Spawn a security critic subagent. Have it review @booking_system_backend/schemas.py, @booking_system_backend/server.py, and the itinerary service module in booking_system_backend/services/.

*The subagent was explicitly restricted to those three files this time.*

**Subagent table:**

| Severity | File | Lines | ASVS control | Description |
|---|---|---|---|---|
| MEDIUM | schemas.py, itinerary.py | 113; 37, 62-70 | 4.1.2 | Up to 3 itineraries x 3 legs = 9 simultaneous seat holds per user. |
| MEDIUM | server.py, itinerary.py | 307-323; 52-176 | 2.1.1 | Client supplies `user_id` and `name` with no binding to the requester. |
| MEDIUM | server.py | 328-345 | 4.1.2 | `/quotes` has no rate limiting. |
| LOW | server.py | 348-427 | 5.1.1 | `quote_id` and `hold_id` path parameters have no format validation. |

**Assistant assessment (after checking the code):**
- `/quotes` rate limit: valid; the limiter covered only `/quotes/{id}/holds`.
- Nine-seat hold cap: weak; `MAX_HELD_ITINERARIES = 3` is deliberate, and bypassing it means registering more users (an authentication gap).
- Client-supplied `user_id`/`name`: out of scope (authentication); ASVS 2.1.1 was also the wrong control.
- Path-parameter IDs: low value; the Java service rejects unknown IDs.
- The subagent's prose also claimed that `quantity` controls pricing and that the itinerary search date is unvalidated. Both are wrong: the Java service calculates the price server-side, and `itinerary_search.py` parses the date and returns `INVALID_DATE`.

---

## 7. Fix round 3

**User:** Fix the HIGH and MEDIUM findings the security-critic subagent reported. Don't change the confirm endpoint or /internal/bookings/from-hold. Add a test for each fix.

*Changes:*
- `services/hold_rate_limit.py`: refactored into a shared `_check` helper with separate scopes. Added `check_quote_rate_limit` and `QUOTE_RATE_LIMIT` (`QUOTE_RATE_LIMIT_PER_MINUTE`, default 20).
- `server.py`: `POST /quotes` now returns 429 `RATE_LIMITED` once the per-client limit is exceeded, before calling the Java service.
- `tests/test_security_fixes.py`: `TestQuoteRateLimit` (limit then 429, separate from holds, window expiry, per-client tracking, validation failures not counted).

*Validation: 157 backend tests passed; ruff clean on touched files.*

**Assistant summary:** Added the quote rate limit, the only finding in that review that held up. Left the nine-seat cap, the client-supplied identity finding, and the LOW path-parameter finding alone, with reasons. Noted the limiter is in-memory, single-process, and IP-keyed, and that e2e tests were not run.

---

## 8. Save the conversation

**User:** Save this whole conversation in a file

*This file was created at `docs/security-review-conversation.md`.*

---

## Final state

Files added or changed during this conversation:

| File | Change |
|---|---|
| `.bob/agents/security-critic.md` | Created (blank, then filled in externally) |
| `booking_system_backend/schemas.py` | Field bounds; `CreateQuoteRequest`; `MAX_QUOTE_QUANTITY` |
| `booking_system_backend/server.py` | Typed `/quotes`; quote and hold rate limits; `/flights` bounds and pagination |
| `booking_system_backend/services/flight.py` | `limit` / `offset` support |
| `booking_system_backend/services/hold_rate_limit.py` | New in-memory per-client limiter (holds and quotes) |
| `booking_system_backend/tests/test_security_fixes.py` | New tests for every fix (157 backend tests passing in total) |
| `docs/security-review-conversation.md` | This transcript |

Deliberately left unchanged: `/internal/bookings/from-hold` and the itinerary confirm endpoint.

Known limitations: the rate limiter is in-memory and per process, so it is not shared across workers and depends on the client IP seen by the server. Authentication-related findings were out of scope by the agent's brief. E2E tests were not run.
