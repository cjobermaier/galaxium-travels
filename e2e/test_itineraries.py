"""
Itinerary lifecycle — multi-leg bookings are all-or-nothing.

Drives the Python backend's public API. Confirming an itinerary makes the Java
hold service confirm each leg's hold (which calls back into Python to create the
real booking), so a sold-out leg exercises the cross-service rollback path.
"""

from helpers import seats_available


def _find_route_flights(client, origin, destination, date):
    """Return the flight_ids of the first itinerary found by /itineraries/search."""
    r = client.get(
        "/itineraries/search",
        params={"origin": origin, "destination": destination, "date": date},
    )
    r.raise_for_status()
    results = r.json()
    assert results, f"no itinerary found {origin} -> {destination} on {date}"
    return [leg["flight_id"] for leg in results[0]["legs"]]


def test_failed_leg_rolls_back_whole_itinerary(client, traveler):
    """A sold-out second leg makes confirm fail and undoes the first leg's booking."""
    first_leg, second_leg = _find_route_flights(client, "Earth", "Mars", "2099-03-01")

    r = client.post(
        "/itineraries",
        json={
            "user_id": traveler["user_id"],
            "name": traveler["name"],
            "flight_ids": [first_leg, second_leg],
        },
    )
    assert r.status_code == 200, r.text
    itinerary = r.json()
    assert itinerary["status"] == "held"
    itinerary_id = itinerary["itinerary_id"]

    # Sell out the second leg's economy class through the plain booking endpoint.
    # Holds reserve nothing in Python, so these bookings succeed despite our hold.
    while seats_available(client, second_leg, "economy") > 0:
        r = client.post(
            "/book",
            json={
                "user_id": traveler["user_id"],
                "name": traveler["name"],
                "flight_id": second_leg,
                "seat_class": "economy",
            },
        )
        assert r.status_code == 200, r.text
    assert seats_available(client, second_leg, "economy") == 0

    first_leg_before = seats_available(client, first_leg, "economy")

    r = client.post(f"/itineraries/{itinerary_id}/confirm")
    assert r.status_code == 502, r.text
    assert r.json()["detail"]["error_code"] == "CONFIRM_FAILED"

    # The first leg was confirmed (seat taken) then cancelled — net zero change.
    assert seats_available(client, first_leg, "economy") == first_leg_before

    r = client.get(f"/users/{traveler['user_id']}/itineraries")
    r.raise_for_status()
    stored = next(i for i in r.json() if i["itinerary_id"] == itinerary_id)
    assert stored["status"] == "failed"
