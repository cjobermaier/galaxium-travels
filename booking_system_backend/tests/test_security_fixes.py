import sys
from pathlib import Path
from typing import ClassVar

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

import server
from schemas import (
    MAX_QUOTE_QUANTITY,
    BookingRequest,
    CreateItineraryRequest,
    CreateQuoteRequest,
)
from services import hold_rate_limit


class FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeJavaClient:
    """Stand-in for httpx.AsyncClient that records POSTs instead of calling Java."""

    posts: ClassVar[list[tuple[str, dict | None]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None, timeout=None):
        FakeJavaClient.posts.append((url, json))
        return FakeResponse({"quoteId": "Q-1", "holdId": "H-1"})


@pytest.fixture
def fake_java(monkeypatch, db_session):
    """Replace the Java HTTP client used by server.py, reset the rate limiter, and seed flight 1."""
    from models import Flight

    db_session.add(Flight(
        flight_id=1, origin="Earth", destination="Mars",
        departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
        base_price=1000, economy_seats_available=5,
        business_seats_available=3, galaxium_seats_available=1,
    ))
    db_session.commit()
    FakeJavaClient.posts = []
    monkeypatch.setattr(server.httpx, "AsyncClient", FakeJavaClient)
    hold_rate_limit.reset_hold_rate_limit()
    yield FakeJavaClient
    hold_rate_limit.reset_hold_rate_limit()


def valid_quote():
    return {
        "flightId": 1,
        "seatClass": "economy",
        "quantity": 1,
        "travelerId": 1,
        "travelerName": "Test User",
    }


class TestBookingRequestValidation:
    """BookingRequest rejects empty, oversized and non-positive values."""

    @pytest.mark.parametrize("field,value", [
        ("user_id", 0),
        ("user_id", -1),
        ("flight_id", 0),
        ("flight_id", -5),
        ("name", ""),
        ("name", "x" * 101),
    ])
    def test_invalid_values_rejected(self, field, value):
        data = {"user_id": 1, "name": "Test User", "flight_id": 1, field: value}
        with pytest.raises(ValidationError):
            BookingRequest(**data)

    def test_valid_request_accepted(self):
        request = BookingRequest(user_id=1, name="Test User", flight_id=1)
        assert request.seat_class == "economy"

    def test_book_endpoint_returns_422_for_invalid_body(self, client):
        response = client.post("/book", json={"user_id": 0, "name": "", "flight_id": -1})
        assert response.status_code == 422


class TestCreateItineraryRequestValidation:
    """CreateItineraryRequest rejects empty, oversized and non-positive values."""

    @pytest.mark.parametrize("field,value", [
        ("user_id", 0),
        ("user_id", -1),
        ("name", ""),
        ("name", "x" * 101),
    ])
    def test_invalid_values_rejected(self, field, value):
        data = {"user_id": 1, "name": "Test User", "flight_ids": [1], field: value}
        with pytest.raises(ValidationError):
            CreateItineraryRequest(**data)

    def test_valid_request_accepted(self):
        request = CreateItineraryRequest(user_id=1, name="Test User", flight_ids=[1, 2])
        assert request.flight_ids == [1, 2]

    def test_itineraries_endpoint_returns_422_for_invalid_body(self, client):
        response = client.post("/itineraries", json={"user_id": 0, "name": "", "flight_ids": [1]})
        assert response.status_code == 422


class TestCreateQuoteValidation:
    """POST /quotes validates its body before proxying to the Java service."""

    def test_valid_quote_is_forwarded(self, client, fake_java):
        response = client.post("/quotes", json=valid_quote())
        assert response.status_code == 200
        assert len(fake_java.posts) == 1
        assert fake_java.posts[0][1] == valid_quote()

    def test_unknown_price_field_rejected_and_not_forwarded(self, client, fake_java):
        body = {**valid_quote(), "pricePerSeat": 1, "totalPrice": 1}
        response = client.post("/quotes", json=body)
        assert response.status_code == 422
        assert fake_java.posts == []

    @pytest.mark.parametrize("field,value", [
        ("flightId", 0),
        ("seatClass", "first"),
        ("quantity", 0),
        ("quantity", -3),
        ("quantity", MAX_QUOTE_QUANTITY + 1),
        ("travelerId", 0),
        ("travelerName", ""),
        ("travelerName", "x" * 101),
    ])
    def test_invalid_field_rejected_and_not_forwarded(self, client, fake_java, field, value):
        response = client.post("/quotes", json={**valid_quote(), field: value})
        assert response.status_code == 422
        assert fake_java.posts == []

    def test_missing_field_rejected(self, client, fake_java):
        body = valid_quote()
        del body["quantity"]
        response = client.post("/quotes", json=body)
        assert response.status_code == 422
        assert fake_java.posts == []

    def test_schema_accepts_max_quantity(self):
        quote = CreateQuoteRequest(**{**valid_quote(), "quantity": MAX_QUOTE_QUANTITY})
        assert quote.quantity == MAX_QUOTE_QUANTITY


class TestHoldRateLimit:
    """POST /quotes/{quote_id}/holds is limited per client."""

    def test_holds_allowed_up_to_limit_then_429(self, client, fake_java, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "HOLD_RATE_LIMIT", 2)

        assert client.post("/quotes/Q-1/holds").status_code == 200
        assert client.post("/quotes/Q-1/holds").status_code == 200

        response = client.post("/quotes/Q-1/holds")
        assert response.status_code == 429
        assert response.json()["detail"]["error_code"] == "RATE_LIMITED"
        # The rejected request never reached the Java service.
        assert len(fake_java.posts) == 2

    def test_limit_expires_after_window(self, client, fake_java, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "HOLD_RATE_LIMIT", 1)
        now = [1000.0]
        monkeypatch.setattr(hold_rate_limit.time, "monotonic", lambda: now[0])

        assert client.post("/quotes/Q-1/holds").status_code == 200
        assert client.post("/quotes/Q-1/holds").status_code == 429

        now[0] += hold_rate_limit.HOLD_RATE_WINDOW_SECONDS
        assert client.post("/quotes/Q-1/holds").status_code == 200

    def test_limit_is_tracked_per_client(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "HOLD_RATE_LIMIT", 1)
        hold_rate_limit.reset_hold_rate_limit()

        assert hold_rate_limit.check_hold_rate_limit("10.0.0.1") is None
        assert hold_rate_limit.check_hold_rate_limit("10.0.0.1") is not None
        assert hold_rate_limit.check_hold_rate_limit("10.0.0.2") is None
        hold_rate_limit.reset_hold_rate_limit()


def add_flights(db_session, count):
    """Insert `count` flights with increasing prices and departure dates."""
    from models import Flight

    db_session.add_all([
        Flight(
            origin="Earth",
            destination="Mars",
            departure_time=f"2099-01-{i + 1:02d} 09:00",
            arrival_time=f"2099-01-{i + 1:02d} 17:00",
            base_price=1000 + i,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1,
        )
        for i in range(count)
    ])
    db_session.commit()


class TestFlightsQueryBounds:
    """GET /flights rejects out-of-range filters and malformed dates with 422."""

    @pytest.mark.parametrize("query", [
        "min_price=-1",
        "max_price=-1",
        "min_price=2000000000",
        "max_price=2000000000",
        "min_duration=-1",
        "max_duration=-1",
        "max_duration=999999",
        "min_seats_available=-1",
        "min_seats_available=999999999",
        "departure_date_from=not-a-date",
        "departure_date_to=2099-01-01';DROP",
        "departure_date_from=" + "2099-01-01" + "x" * 50,
    ])
    def test_out_of_range_values_rejected(self, client, query):
        assert client.get(f"/flights?{query}").status_code == 422

    def test_in_range_values_accepted(self, client, db_session):
        add_flights(db_session, 1)
        response = client.get(
            "/flights?min_price=0&max_price=5000&min_duration=0&max_duration=24"
            "&min_seats_available=1&departure_date_from=2099-01-01"
            "&departure_date_to=2099-12-31T00:00:00"
        )
        assert response.status_code == 200
        assert len(response.json()) == 1


class TestFlightsPagination:
    """GET /flights returns at most `limit` flights and supports `offset`."""

    def test_default_limit_caps_results(self, client, db_session):
        add_flights(db_session, server.DEFAULT_FLIGHTS_LIMIT + 5)
        response = client.get("/flights")
        assert response.status_code == 200
        assert len(response.json()) == server.DEFAULT_FLIGHTS_LIMIT

    def test_limit_and_offset(self, client, db_session):
        add_flights(db_session, 10)
        response = client.get("/flights?sort_by=base_price&sort_order=asc&limit=3&offset=2")
        assert response.status_code == 200
        assert [f["base_price"] for f in response.json()] == [1002, 1003, 1004]

    def test_offset_past_end_returns_empty(self, client, db_session):
        add_flights(db_session, 3)
        assert client.get("/flights?offset=10").json() == []

    @pytest.mark.parametrize("query", [
        "limit=0",
        "limit=-1",
        f"limit={server.MAX_FLIGHTS_LIMIT + 1}",
        "offset=-1",
    ])
    def test_invalid_pagination_rejected(self, client, query):
        assert client.get(f"/flights?{query}").status_code == 422


class TestQuoteRateLimit:
    """POST /quotes is limited per client, separately from hold creation."""

    def test_quotes_allowed_up_to_limit_then_429(self, client, fake_java, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 2)

        assert client.post("/quotes", json=valid_quote()).status_code == 200
        assert client.post("/quotes", json=valid_quote()).status_code == 200

        response = client.post("/quotes", json=valid_quote())
        assert response.status_code == 429
        assert response.json()["detail"]["error_code"] == "RATE_LIMITED"
        # The rejected request never reached the Java service.
        assert len(fake_java.posts) == 2

    def test_quote_limit_does_not_consume_hold_budget(self, client, fake_java, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 1)
        monkeypatch.setattr(hold_rate_limit, "HOLD_RATE_LIMIT", 1)

        assert client.post("/quotes", json=valid_quote()).status_code == 200
        assert client.post("/quotes", json=valid_quote()).status_code == 429
        # Holds have their own counter and are still allowed.
        assert client.post("/quotes/Q-1/holds").status_code == 200

    def test_quote_limit_expires_after_window(self, client, fake_java, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 1)
        now = [1000.0]
        monkeypatch.setattr(hold_rate_limit.time, "monotonic", lambda: now[0])

        assert client.post("/quotes", json=valid_quote()).status_code == 200
        assert client.post("/quotes", json=valid_quote()).status_code == 429

        now[0] += hold_rate_limit.HOLD_RATE_WINDOW_SECONDS
        assert client.post("/quotes", json=valid_quote()).status_code == 200

    def test_quote_limit_is_tracked_per_client(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 1)
        hold_rate_limit.reset_hold_rate_limit()

        assert hold_rate_limit.check_quote_rate_limit("10.0.0.1") is None
        assert hold_rate_limit.check_quote_rate_limit("10.0.0.1") is not None
        assert hold_rate_limit.check_quote_rate_limit("10.0.0.2") is None
        hold_rate_limit.reset_hold_rate_limit()

    def test_invalid_quote_does_not_count_against_limit(self, client, fake_java, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 1)

        assert client.post("/quotes", json={**valid_quote(), "quantity": 0}).status_code == 422
        assert client.post("/quotes", json=valid_quote()).status_code == 200


class TestRateLimitClientIdentity:
    """Rate-limit key uses the real client behind trusted proxies, never a spoofable header."""

    def test_peer_used_when_no_trusted_proxy(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 0)
        assert hold_rate_limit.resolve_client_id("10.0.0.9", "1.2.3.4") == "10.0.0.9"

    def test_unknown_when_no_peer_and_no_trusted_proxy(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 0)
        assert hold_rate_limit.resolve_client_id(None, None) == "unknown"

    def test_forwarded_for_used_behind_one_trusted_proxy(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 1)
        assert hold_rate_limit.resolve_client_id("10.0.0.9", "1.2.3.4") == "1.2.3.4"

    def test_spoofed_leftmost_entries_ignored(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 1)
        # Client sent "6.6.6.6"; the trusted proxy appended the real address.
        assert hold_rate_limit.resolve_client_id("10.0.0.9", "6.6.6.6, 1.2.3.4") == "1.2.3.4"

    def test_two_trusted_proxies_take_second_from_right(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 2)
        assert (
            hold_rate_limit.resolve_client_id("10.0.0.9", "6.6.6.6, 1.2.3.4, 10.1.1.1")
            == "1.2.3.4"
        )

    def test_falls_back_to_peer_when_header_missing_or_short(self, monkeypatch):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 2)
        assert hold_rate_limit.resolve_client_id("10.0.0.9", None) == "10.0.0.9"
        assert hold_rate_limit.resolve_client_id("10.0.0.9", "1.2.3.4") == "10.0.0.9"

    def test_clients_behind_proxy_get_separate_buckets(
        self, client, fake_java, monkeypatch
    ):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 1)
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 1)

        a = {"X-Forwarded-For": "1.1.1.1"}
        b = {"X-Forwarded-For": "2.2.2.2"}
        assert client.post("/quotes", json=valid_quote(), headers=a).status_code == 200
        assert client.post("/quotes", json=valid_quote(), headers=a).status_code == 429
        # A different real client is not locked out by the first one.
        assert client.post("/quotes", json=valid_quote(), headers=b).status_code == 200

    def test_forwarded_header_ignored_without_trusted_proxy(
        self, client, fake_java, monkeypatch
    ):
        monkeypatch.setattr(hold_rate_limit, "TRUSTED_PROXY_COUNT", 0)
        monkeypatch.setattr(hold_rate_limit, "QUOTE_RATE_LIMIT", 1)

        assert client.post(
            "/quotes", json=valid_quote(), headers={"X-Forwarded-For": "1.1.1.1"}
        ).status_code == 200
        # Rotating the header does not evade the limit.
        assert client.post(
            "/quotes", json=valid_quote(), headers={"X-Forwarded-For": "2.2.2.2"}
        ).status_code == 429


class TestQuoteSeatAvailability:
    """POST /quotes rejects quantities above the seats actually available."""

    def test_quantity_above_available_rejected_and_not_forwarded(self, client, fake_java):
        # Flight 1 has 5 economy seats.
        response = client.post("/quotes", json={**valid_quote(), "quantity": 6})
        assert response.status_code == 409
        assert response.json()["detail"]["error_code"] == "NO_SEATS_AVAILABLE"
        assert fake_java.posts == []

    def test_quantity_equal_to_available_accepted(self, client, fake_java):
        response = client.post("/quotes", json={**valid_quote(), "quantity": 5})
        assert response.status_code == 200
        assert len(fake_java.posts) == 1

    def test_seat_class_is_checked_separately(self, client, fake_java):
        # Flight 1 has only 1 galaxium seat.
        body = {**valid_quote(), "seatClass": "galaxium", "quantity": 2}
        assert client.post("/quotes", json=body).status_code == 409
        assert fake_java.posts == []

    def test_unknown_flight_returns_404_and_not_forwarded(self, client, fake_java):
        response = client.post("/quotes", json={**valid_quote(), "flightId": 999})
        assert response.status_code == 404
        assert response.json()["detail"]["error_code"] == "FLIGHT_NOT_FOUND"
        assert fake_java.posts == []


class TestItinerarySearchQueryBounds:
    """GET /itineraries/search validates origin, destination and date."""

    def test_valid_query_accepted(self, client):
        response = client.get(
            "/itineraries/search?origin=Earth&destination=Mars&date=2099-02-01"
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.parametrize("query", [
        "origin=" + "x" * 51 + "&destination=Mars&date=2099-02-01",
        "origin=Earth&destination=" + "x" * 51 + "&date=2099-02-01",
        "origin=Earth&destination=Mars&date=" + "2099-02-01" + "x" * 500,
        "origin=Earth&destination=Mars&date=not-a-date",
        "origin=Earth&destination=Mars&date=2099-02-01T00:00",
        "origin=Earth&destination=Mars",
    ])
    def test_invalid_query_rejected(self, client, query):
        assert client.get(f"/itineraries/search?{query}").status_code == 422


class TestFlightsOffsetUpperBound:
    """GET /flights rejects offsets above MAX_FLIGHTS_OFFSET."""

    def test_offset_above_max_rejected(self, client):
        assert client.get(f"/flights?offset={server.MAX_FLIGHTS_OFFSET + 1}").status_code == 422

    def test_offset_at_max_accepted(self, client):
        response = client.get(f"/flights?offset={server.MAX_FLIGHTS_OFFSET}")
        assert response.status_code == 200
        assert response.json() == []

