# Multi-leg itinerary user stories

**Feature:** Multi-leg itineraries — up to three connected economy-class flights booked as a single atomic transaction, with layovers between 2 and 72 hours.

**Out of scope:** changing or cancelling a booked trip; seat classes other than economy.

---

## Assumption log

> Assumptions made where the request left details open. Challenge any of these before implementation begins.

| # | Assumption |
|---|------------|
| A1 | "Up to three flights" means 1-, 2-, and 3-leg itineraries are all valid. A direct flight is a one-leg itinerary and is unaffected by this feature. |
| A2 | The layover window (2–72 h) is measured from the *arrival time* of the inbound leg to the *departure time* of the outbound leg at the same body. |
| A3 | Seat availability is checked and decremented for every leg at booking time, not at search time. |
| A4 | The seeded flight schedule does not contain a connectable Earth → Mars → Jupiter → Europa route on 2099-02-01. The seed must be extended with four flights on that date whose layovers fall within 2–72 h (see US-01 criterion AC4 for the required schedule). |
| A5 | A "trip" is the new aggregate entity. It has its own `trip_id` and references an ordered list of `booking_id` values, one per leg. |
| A6 | "My Trips" replaces or supplements "My Bookings" in the UI. Individual leg bookings created by a trip are not shown separately in My Trips. |
| A7 | Total trip price shown to the traveler is the sum of the economy price of every leg. |

---

## US-01 — Search for a multi-leg itinerary

**As a** traveler,
**I want to** search for a multi-leg itinerary by entering an origin, a destination, and a departure date,
**so that** I can see every connected route — including ones that require one or two stops — without manually piecing together individual flights.

### Acceptance criteria

**AC1 — Direct and connecting results are returned together**
Given a traveler is logged in,
When they search for flights from Earth to Mars departing on 2099-01-01,
Then the results include the direct Earth → Mars flight (flight_id 1 in the seeded schedule) as a one-leg itinerary alongside any valid connecting routes.

**AC2 — Layovers outside the 2–72 h window are excluded**
Given a traveler searches for a route between two bodies,
When the only connecting path has a layover shorter than 2 hours or longer than 72 hours at an intermediate stop,
Then that connecting path does not appear in the results.

**AC3 — Routes with more than three legs are excluded**
Given a traveler searches for a route between two bodies,
When the only connecting path requires four or more flights,
Then that path does not appear in the results.

**AC4 — Three-leg route appears for Earth to Europa on 2099-02-01**
Given the seeded flight schedule includes the following four flights on 2099-02-01:
- Flight A: Earth → Mars, departs 08:00, arrives 16:00
- Flight B: Mars → Jupiter, departs 18:00, arrives 2099-02-02 04:00 (layover at Mars: 2 h ✓)
- Flight C: Jupiter → Europa, departs 2099-02-02 10:00, arrives 2099-02-02 14:00 (layover at Jupiter: 6 h ✓)
- Flight D: Earth → Moon, departs 08:00, arrives 12:00 (unrelated flight, present to confirm it is not included in this result)

When a traveler searches Earth to Europa on 2099-02-01,
Then the results include a three-leg route via Mars and Jupiter composed of Flights A, B, and C in that order.

**AC5 — No results state is shown when no valid route exists**
Given a traveler searches for a route between two bodies with no direct or connecting flights that satisfy the layover window,
When the search completes,
Then the results page shows a message indicating no itineraries were found for those inputs, and no flight cards are displayed.

---

## US-02 — View itinerary details before booking

**As a** traveler,
**I want to** see the full leg-by-leg schedule and total price of a multi-leg itinerary before I commit,
**so that** I can confirm the layover times and total cost are acceptable to me.

### Acceptance criteria

**AC1 — All legs are shown in order**
Given a traveler selects a two-leg itinerary (Earth → Mars, Mars → Jupiter),
When the itinerary detail view opens,
Then both legs are listed in departure-time order, each showing origin, destination, departure time, arrival time, and economy price.

**AC2 — Layover duration is displayed at each intermediate stop**
Given a traveler is viewing a three-leg itinerary,
When the detail view renders,
Then the layover duration (in hours and minutes) is shown between Leg 1 and Leg 2, and between Leg 2 and Leg 3.

**AC3 — Total price is the sum of economy prices for all legs**
Given a three-leg itinerary where Leg 1 costs 1,000,000 credits, Leg 2 costs 2,500,000 credits, and Leg 3 costs 2,000,000 credits,
When the detail view renders,
Then the total price displayed is 5,500,000 credits.

**AC4 — Seats available per leg are shown**
Given a traveler is viewing an itinerary,
When the detail view renders,
Then each leg shows the number of economy seats currently available, and a leg with zero economy seats available is marked as sold out.

---

## US-03 — Book a multi-leg itinerary atomically

**As a** traveler,
**I want to** book all legs of a multi-leg itinerary in a single action,
**so that** I never end up with only part of my journey booked if one leg has no seats.

### Acceptance criteria

**AC1 — All legs book or none do**
Given a traveler attempts to book a three-leg itinerary where Leg 1 has seats available, Leg 2 has seats available, but Leg 3 has 0 economy seats available,
When they submit the booking,
Then no booking is created for any leg, the seat counts on Leg 1 and Leg 2 are unchanged, and the traveler sees an error message identifying which leg has no availability.

**AC2 — A successful booking creates one trip record and one booking per leg**
Given a traveler books a valid two-leg itinerary (Earth → Mars, Mars → Jupiter) with economy seats available on both legs,
When the booking is confirmed,
Then a single trip record is created with a unique `trip_id`, two `Booking` records are created (one per leg, both with `status: "booked"`), and the trip record references both booking IDs.

**AC3 — Economy seat counts are decremented for every leg**
Given a traveler books a valid three-leg itinerary,
When the booking is confirmed,
Then the `economy_seats_available` count on each of the three flights is decremented by exactly 1.

**AC4 — A traveler cannot book the same leg twice in one trip**
Given a traveler attempts to create a trip where the same `flight_id` appears more than once in the leg list,
When they submit the booking,
Then the request is rejected with an error indicating duplicate legs, and no booking is created.

---

## US-04 — View my booked trips

**As a** traveler,
**I want to** see all my booked trips in a "My Trips" list,
**so that** I can review my upcoming multi-leg journeys in one place.

### Acceptance criteria

**AC1 — My Trips shows trips in reverse chronological booking order**
Given a traveler has three booked trips with booking times T1 < T2 < T3,
When they open My Trips,
Then the trips are listed with the most recently booked trip (T3) at the top.

**AC2 — Each trip card summarises the full route**
Given a traveler has a booked three-leg trip (Earth → Mars → Jupiter → Europa),
When they view My Trips,
Then that trip's card shows the origin of the first leg (Earth), the destination of the last leg (Europa), the departure time of the first leg, the arrival time of the last leg, and the total price paid.

**AC3 — Each trip card expands to show individual legs**
Given a traveler taps or clicks a trip card in My Trips,
When the card expands,
Then each leg is listed with its flight number, origin, destination, departure time, and arrival time.

**AC4 — A traveler with no booked trips sees an empty state**
Given a newly registered traveler has made no bookings,
When they open My Trips,
Then the page shows an empty-state message such as "No trips booked yet" and no trip cards are displayed.

**AC5 — Only the authenticated traveler's trips are shown**
Given traveler Alice and traveler Bob each have booked trips,
When Alice views My Trips,
Then only Alice's trips are shown and none of Bob's trips appear.

---

## Story map

```
Search itinerary   →   View itinerary details   →   Book itinerary   →   View My Trips
    (US-01)                  (US-02)                   (US-03)              (US-04)
```
