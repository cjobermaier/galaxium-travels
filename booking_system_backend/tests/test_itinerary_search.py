import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Flight
from schemas import ErrorResponse
from services.itinerary_search import is_valid_connection, search_itineraries


def make_flight(flight_id, origin, destination, departure, arrival, base_price=1000):
    """Build an in-memory Flight (no database involved)."""
    return Flight(
        flight_id=flight_id,
        origin=origin,
        destination=destination,
        departure_time=departure,
        arrival_time=arrival,
        base_price=base_price,
        economy_seats_available=5,
        business_seats_available=3,
        galaxium_seats_available=1,
    )


def make_db(flights):
    """Return a mock session whose query(Flight).all() yields the given flights."""
    db = MagicMock()
    db.query.return_value.all.return_value = flights
    return db


def flight_ids(result):
    """Return the leg flight_ids of every itinerary in a search result."""
    return [[leg.flight_id for leg in r.legs] for r in result]


class TestIsValidConnection:
    """Test is_valid_connection layover and location rules."""

    @staticmethod
    def _pair(arrival, departure):
        arriving = make_flight(1, "Earth", "Mars", "2099-01-01 00:00", arrival)
        departing = make_flight(2, "Mars", "Venus", departure, "2099-02-01 00:00")
        return arriving, departing

    def test_layover_exactly_2_hours_is_valid(self):
        """Test a layover of exactly 2 hours is accepted."""
        arriving, departing = self._pair("2099-01-01 10:00", "2099-01-01 12:00")
        assert is_valid_connection(arriving, departing) is True

    def test_layover_exactly_72_hours_is_valid(self):
        """Test a layover of exactly 72 hours is accepted."""
        arriving, departing = self._pair("2099-01-01 10:00", "2099-01-04 10:00")
        assert is_valid_connection(arriving, departing) is True

    def test_layover_1h59m_is_invalid(self):
        """Test a layover of 1 hour 59 minutes is rejected."""
        arriving, departing = self._pair("2099-01-01 10:00", "2099-01-01 11:59")
        assert is_valid_connection(arriving, departing) is False

    def test_layover_72h01m_is_invalid(self):
        """Test a layover of 72 hours 1 minute is rejected."""
        arriving, departing = self._pair("2099-01-01 10:00", "2099-01-04 10:01")
        assert is_valid_connection(arriving, departing) is False

    def test_departure_before_arrival_is_invalid(self):
        """Test a negative layover is rejected."""
        arriving, departing = self._pair("2099-01-01 10:00", "2099-01-01 09:00")
        assert is_valid_connection(arriving, departing) is False

    def test_mismatched_location_is_invalid(self):
        """Test flights that do not meet at the same body are rejected."""
        arriving = make_flight(1, "Earth", "Mars", "2099-01-01 00:00", "2099-01-01 10:00")
        departing = make_flight(2, "Venus", "Mercury", "2099-01-01 14:00", "2099-01-01 20:00")
        assert is_valid_connection(arriving, departing) is False

    def test_location_match_is_case_insensitive(self):
        """Test origin/destination matching ignores case."""
        arriving = make_flight(1, "Earth", "MARS", "2099-01-01 00:00", "2099-01-01 10:00")
        departing = make_flight(2, "mars", "Venus", "2099-01-01 14:00", "2099-01-01 20:00")
        assert is_valid_connection(arriving, departing) is True

    def test_mixed_timestamp_formats(self):
        """Test ISO 'T...Z' and 'YYYY-MM-DD HH:MM' formats can be compared."""
        arriving = make_flight(1, "Earth", "Mars", "2099-01-01T00:00:00Z", "2099-01-01T10:00:00Z")
        departing = make_flight(2, "Mars", "Venus", "2099-01-01 12:00", "2099-01-01 20:00")
        assert is_valid_connection(arriving, departing) is True

        too_soon = make_flight(3, "Mars", "Venus", "2099-01-01 11:59", "2099-01-01 20:00")
        assert is_valid_connection(arriving, too_soon) is False

    def test_unparseable_timestamp_raises(self):
        """Test an unsupported timestamp format raises ValueError."""
        arriving = make_flight(1, "Earth", "Mars", "2099-01-01 00:00", "not-a-date")
        departing = make_flight(2, "Mars", "Venus", "2099-01-01 14:00", "2099-01-01 20:00")
        with pytest.raises(ValueError):
            is_valid_connection(arriving, departing)


class TestSearchItineraries:
    """Test search_itineraries (behind GET /itineraries/search)."""

    def test_direct_route(self):
        """Test a single-leg route is returned with correct totals."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00", 1000),
        ])

        result = search_itineraries(db, "Earth", "Mars", "2099-01-01")

        assert flight_ids(result) == [[1]]
        assert result[0].total_price == 1000
        assert result[0].total_duration_minutes == 480

    def test_two_leg_route(self):
        """Test a valid two-leg route is returned with summed price and duration."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00", 1000),
            make_flight(2, "Mars", "Venus", "2099-01-01 20:00", "2099-01-02 04:00", 500),
        ])

        result = search_itineraries(db, "Earth", "Venus", "2099-01-01")

        assert flight_ids(result) == [[1, 2]]
        assert result[0].total_price == 1500
        # 09:00 -> 04:00 next day = 19 hours
        assert result[0].total_duration_minutes == 19 * 60

    def test_layover_exactly_2_hours_included(self):
        """Test a two-leg route with a 2 hour layover is included."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00"),
            make_flight(2, "Mars", "Venus", "2099-01-01 19:00", "2099-01-02 03:00"),
        ])
        assert flight_ids(search_itineraries(db, "Earth", "Venus", "2099-01-01")) == [[1, 2]]

    def test_layover_exactly_72_hours_included(self):
        """Test a two-leg route with a 72 hour layover is included."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00"),
            make_flight(2, "Mars", "Venus", "2099-01-04 17:00", "2099-01-05 01:00"),
        ])
        assert flight_ids(search_itineraries(db, "Earth", "Venus", "2099-01-01")) == [[1, 2]]

    def test_layover_1h59m_excluded(self):
        """Test a two-leg route with a 1h59m layover is excluded."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00"),
            make_flight(2, "Mars", "Venus", "2099-01-01 18:59", "2099-01-02 03:00"),
        ])
        assert search_itineraries(db, "Earth", "Venus", "2099-01-01") == []

    def test_layover_72h01m_excluded(self):
        """Test a two-leg route with a 72h01m layover is excluded."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00"),
            make_flight(2, "Mars", "Venus", "2099-01-04 17:01", "2099-01-05 01:00"),
        ])
        assert search_itineraries(db, "Earth", "Venus", "2099-01-01") == []

    def test_four_leg_route_excluded(self):
        """Test routes needing more than three legs are not returned."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 12:00"),
            make_flight(2, "Mars", "Venus", "2099-01-01 15:00", "2099-01-01 18:00"),
            make_flight(3, "Venus", "Mercury", "2099-01-01 21:00", "2099-01-02 00:00"),
            make_flight(4, "Mercury", "Jupiter", "2099-01-02 03:00", "2099-01-02 06:00"),
        ])
        assert search_itineraries(db, "Earth", "Jupiter", "2099-01-01") == []
        # The three-leg prefix is still reachable
        assert flight_ids(search_itineraries(db, "Earth", "Mercury", "2099-01-01")) == [[1, 2, 3]]

    def test_mixed_timestamp_formats(self):
        """Test a route whose legs use different timestamp formats is found."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-02-01T09:00:00Z", "2099-02-01T17:00:00Z"),
            make_flight(2, "Mars", "Venus", "2099-02-01 20:00", "2099-02-02 04:00"),
        ])

        result = search_itineraries(db, "Earth", "Venus", "2099-02-01")

        assert flight_ids(result) == [[1, 2]]
        assert result[0].total_duration_minutes == 19 * 60

    def test_sorted_by_duration_then_price(self):
        """Test results are ordered by total duration, then total price."""
        db = make_db([
            # Slow direct (10h, 100)
            make_flight(1, "Earth", "Venus", "2099-01-01 08:00", "2099-01-01 18:00", 100),
            # Fast direct, expensive (4h, 900)
            make_flight(2, "Earth", "Venus", "2099-01-01 08:00", "2099-01-01 12:00", 900),
            # Fast direct, cheap (4h, 300)
            make_flight(3, "Earth", "Venus", "2099-01-01 09:00", "2099-01-01 13:00", 300),
            # Two-leg (08:00 -> 20:00 = 12h, 200)
            make_flight(4, "Earth", "Mars", "2099-01-01 08:00", "2099-01-01 10:00", 100),
            make_flight(5, "Mars", "Venus", "2099-01-01 12:00", "2099-01-01 20:00", 100),
        ])

        result = search_itineraries(db, "Earth", "Venus", "2099-01-01")

        assert flight_ids(result) == [[3], [2], [1], [4, 5]]
        durations = [r.total_duration_minutes for r in result]
        assert durations == sorted(durations)

    def test_case_insensitive_origin_and_destination(self):
        """Test origin and destination matching ignores case and whitespace."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00"),
        ])
        assert flight_ids(search_itineraries(db, " earth ", "MARS", "2099-01-01")) == [[1]]

    def test_first_leg_must_depart_on_date(self):
        """Test first legs departing on other dates are not used."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-02 09:00", "2099-01-02 17:00"),
        ])
        assert search_itineraries(db, "Earth", "Mars", "2099-01-01") == []

    def test_no_route_returns_empty_list(self):
        """Test an unreachable destination yields an empty list."""
        db = make_db([
            make_flight(1, "Earth", "Mars", "2099-01-01 09:00", "2099-01-01 17:00"),
        ])
        assert search_itineraries(db, "Earth", "Neptune", "2099-01-01") == []

    def test_invalid_date_returns_error_response(self):
        """Test a malformed date returns an ErrorResponse instead of raising."""
        result = search_itineraries(make_db([]), "Earth", "Mars", "01/01/2099")
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "INVALID_DATE"
