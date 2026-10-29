import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Booking, Flight, Itinerary, ItineraryLeg, User
from schemas import ErrorResponse
from services import booking, flight, itinerary, user


class TestFlightService:
    """Test flight service functions."""

    def test_list_flights_empty(self, db_session):
        """Test listing flights when database is empty."""
        result = flight.list_flights(db_session)
        assert result == []

    def test_list_flights_with_data(self, db_session):
        """Test listing flights with data in database."""
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session)
        assert len(result) == 1
        assert result[0].origin == "Earth"
        assert result[0].destination == "Mars"

    def test_list_flights_sort_by_price_asc(self, db_session):
        """Test sorting flights by price ascending."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=2000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, sort_by="base_price", sort_order="asc")
        assert len(result) == 2
        assert result[0].base_price == 1000
        assert result[1].base_price == 2000

    def test_list_flights_sort_by_price_desc(self, db_session):
        """Test sorting flights by price descending."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=2000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, sort_by="base_price", sort_order="desc")
        assert len(result) == 2
        assert result[0].base_price == 2000
        assert result[1].base_price == 1000

    def test_list_flights_filter_by_date_range(self, db_session):
        """Test filtering flights by date range."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-15 09:00", arrival_time="2099-01-15 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, departure_date_from="2099-01-10", departure_date_to="2099-01-20")
        assert len(result) == 1
        assert result[0].destination == "Venus"

    def test_list_flights_filter_by_price_range(self, db_session):
        """Test filtering flights by price range."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=500, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=1500, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Jupiter",
            departure_time="2099-01-03 09:00", arrival_time="2099-01-03 17:00",
            base_price=2500, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, min_price=1000, max_price=2000)
        assert len(result) == 1
        assert result[0].base_price == 1500

    def test_list_flights_filter_by_seat_class(self, db_session):
        """Test filtering flights by seat class availability."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=0, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=0, galaxium_seats_available=0
        ))
        db_session.commit()

        result = flight.list_flights(db_session, seat_class="economy")
        assert len(result) == 1
        assert result[0].destination == "Venus"

    def test_list_flights_filter_by_time_period(self, db_session):
        """Test filtering flights by time of day."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 08:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-01 14:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, departure_time_period="morning")
        assert len(result) == 1
        assert result[0].destination == "Mars"

    def test_list_flights_filter_by_duration(self, db_session):
        """Test filtering flights by duration."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 13:00",  # 4 hours
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Jupiter",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 21:00",  # 12 hours
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, min_duration=5, max_duration=15)
        assert len(result) == 1
        assert result[0].destination == "Jupiter"

    def test_list_flights_filter_by_min_seats(self, db_session):
        """Test filtering flights by minimum seats available."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=1, business_seats_available=1, galaxium_seats_available=0
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=2
        ))
        db_session.commit()

        result = flight.list_flights(db_session, min_seats_available=5)
        assert len(result) == 1
        assert result[0].destination == "Venus"

    def test_list_flights_filter_by_route_category(self, db_session):
        """Test filtering flights by route category."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Jupiter",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(db_session, route_category="inner_planets")
        assert len(result) == 1
        assert result[0].destination == "Mars"

    def test_list_flights_combined_filters(self, db_session):
        """Test combining multiple filters."""
        db_session.add(Flight(
            origin="Earth", destination="Mars",
            departure_time="2099-01-01 09:00", arrival_time="2099-01-01 17:00",
            base_price=1000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.add(Flight(
            origin="Earth", destination="Venus",
            departure_time="2099-01-02 09:00", arrival_time="2099-01-02 17:00",
            base_price=2000, economy_seats_available=5, business_seats_available=3, galaxium_seats_available=1
        ))
        db_session.commit()

        result = flight.list_flights(
            db_session,
            sort_by="base_price",
            sort_order="asc",
            min_price=500,
            max_price=1500,
            seat_class="economy"
        )
        assert len(result) == 1
        assert result[0].destination == "Mars"


class TestUserService:
    """Test user service functions."""

    def test_register_user_success(self, db_session):
        """Test successful user registration."""
        result = user.register_user(db_session, "Test User", "test@example.com")
        assert result.name == "Test User"
        assert result.email == "test@example.com"
        assert result.user_id > 0

    def test_register_user_duplicate_email(self, db_session):
        """Test registration with duplicate email."""
        user.register_user(db_session, "User 1", "test@example.com")
        result = user.register_user(db_session, "User 2", "test@example.com")

        assert isinstance(result, ErrorResponse)
        assert result.error_code == "EMAIL_EXISTS"

    def test_get_user_success(self, db_session):
        """Test successful user retrieval."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.commit()

        result = user.get_user(db_session, "Test User", "test@example.com")
        assert result.name == "Test User"
        assert result.email == "test@example.com"

    def test_get_user_not_found(self, db_session):
        """Test user retrieval when not found."""
        result = user.get_user(db_session, "NonExistent", "none@example.com")
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "USER_NOT_FOUND"


class TestBookingService:
    """Test booking service functions."""

    def test_book_flight_success(self, db_session):
        """Test successful flight booking."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        user_obj = db_session.query(User).first()
        flight_obj = db_session.query(Flight).first()

        result = booking.book_flight(db_session, user_obj.user_id, "Test User", flight_obj.flight_id)
        assert result.status == "booked"
        assert result.user_id == user_obj.user_id
        assert result.flight_id == flight_obj.flight_id

        # Verify seat was decremented
        db_session.refresh(flight_obj)
        assert flight_obj.economy_seats_available == 4

    def test_book_flight_not_found(self, db_session):
        """Test booking non-existent flight."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.commit()
        user_obj = db_session.query(User).first()

        result = booking.book_flight(db_session, user_obj.user_id, "Test User", 999)
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "FLIGHT_NOT_FOUND"

    def test_book_flight_no_seats(self, db_session):
        """Test booking when no seats available."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=0,
            business_seats_available=0,
            galaxium_seats_available=0
        ))
        db_session.commit()

        user_obj = db_session.query(User).first()
        flight_obj = db_session.query(Flight).first()

        result = booking.book_flight(db_session, user_obj.user_id, "Test User", flight_obj.flight_id)
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "NO_SEATS_AVAILABLE"

    def test_book_flight_user_not_found(self, db_session):
        """Test booking with non-existent user."""
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()
        flight_obj = db_session.query(Flight).first()

        result = booking.book_flight(db_session, 999, "Fake User", flight_obj.flight_id)
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "USER_NOT_FOUND"

    def test_book_flight_name_mismatch(self, db_session):
        """Test booking with wrong name for user ID."""
        db_session.add(User(name="Real Name", email="test@example.com"))
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        user_obj = db_session.query(User).first()
        flight_obj = db_session.query(Flight).first()

        result = booking.book_flight(db_session, user_obj.user_id, "Wrong Name", flight_obj.flight_id)
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "NAME_MISMATCH"

    def test_cancel_booking_success(self, db_session):
        """Test successful booking cancellation."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=4,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        user_obj = db_session.query(User).first()
        flight_obj = db_session.query(Flight).first()

        db_session.add(Booking(
            user_id=user_obj.user_id,
            flight_id=flight_obj.flight_id,
            status="booked",
            booking_time="2099-01-01 10:00",
            seat_class="economy",
            price_paid=1000000
        ))
        db_session.commit()

        booking_obj = db_session.query(Booking).first()
        result = booking.cancel_booking(db_session, booking_obj.booking_id)

        assert result.status == "cancelled"

        # Verify seat was restored
        db_session.refresh(flight_obj)
        assert flight_obj.economy_seats_available == 5

    def test_cancel_booking_not_found(self, db_session):
        """Test cancelling non-existent booking."""
        result = booking.cancel_booking(db_session, 999)
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "BOOKING_NOT_FOUND"

    def test_cancel_booking_already_cancelled(self, db_session):
        """Test cancelling already cancelled booking."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        user_obj = db_session.query(User).first()
        flight_obj = db_session.query(Flight).first()

        db_session.add(Booking(
            user_id=user_obj.user_id,
            flight_id=flight_obj.flight_id,
            status="cancelled",
            booking_time="2099-01-01 10:00",
            seat_class="economy",
            price_paid=1000000
        ))
        db_session.commit()

        booking_obj = db_session.query(Booking).first()
        result = booking.cancel_booking(db_session, booking_obj.booking_id)

        assert isinstance(result, ErrorResponse)
        assert result.error_code == "ALREADY_CANCELLED"

    def test_get_bookings_success(self, db_session):
        """Test getting user bookings."""
        db_session.add(User(name="Test User", email="test@example.com"))
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2099-01-01 09:00",
            arrival_time="2099-01-01 17:00",
            base_price=1000000,
            economy_seats_available=5,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        user_obj = db_session.query(User).first()
        flight_obj = db_session.query(Flight).first()

        db_session.add(Booking(
            user_id=user_obj.user_id,
            flight_id=flight_obj.flight_id,
            status="booked",
            booking_time="2099-01-01 10:00",
            seat_class="economy",
            price_paid=1000000
        ))
        db_session.commit()

        result = booking.get_bookings(db_session, user_obj.user_id)
        assert len(result) == 1
        assert result[0].status == "booked"

    def test_get_bookings_empty(self, db_session):
        """Test getting bookings when user has none."""
        result = booking.get_bookings(db_session, 999)
        assert result == []



class TestFlightFiltering:
    """Test flight filtering and sorting functionality."""

    def setup_method(self):
        """Setup test flights with various attributes."""

    def test_filter_by_origin(self, db_session):
        """Test filtering flights by origin (case-insensitive partial match)."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Moon",
                destination="Mars",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 18:00",
                base_price=800000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Venus",
                destination="Earth",
                departure_time="2026-03-03 11:00",
                arrival_time="2026-03-03 19:00",
                base_price=1200000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test exact match
        results = flight.list_flights(db_session, origin="Earth")
        assert len(results) == 1
        assert results[0].origin == "Earth"

        # Test case-insensitive
        results = flight.list_flights(db_session, origin="earth")
        assert len(results) == 1
        assert results[0].origin == "Earth"

        # Test partial match
        results = flight.list_flights(db_session, origin="ar")
        assert len(results) == 1
        assert "ar" in results[0].origin.lower()

    def test_filter_by_destination(self, db_session):
        """Test filtering flights by destination."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Venus",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 18:00",
                base_price=1100000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        results = flight.list_flights(db_session, destination="Mars")
        assert len(results) == 1
        assert results[0].destination == "Mars"

    def test_filter_by_date_range(self, db_session):
        """Test filtering flights by departure date range."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Venus",
                departure_time="2026-03-15 10:00",
                arrival_time="2026-03-15 18:00",
                base_price=1100000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Jupiter",
                departure_time="2026-04-01 11:00",
                arrival_time="2026-04-01 19:00",
                base_price=2000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test from date
        results = flight.list_flights(db_session, departure_date_from="2026-03-15")
        assert len(results) == 2
        assert all(r.departure_time >= "2026-03-15" for r in results)

        # Test to date
        results = flight.list_flights(db_session, departure_date_to="2026-03-15")
        assert len(results) == 2
        assert all(r.departure_time <= "2026-03-15 23:59" for r in results)

        # Test date range
        results = flight.list_flights(
            db_session,
            departure_date_from="2026-03-10",
            departure_date_to="2026-03-20"
        )
        assert len(results) == 1
        assert results[0].departure_time.startswith("2026-03-15")

    def test_filter_by_price_range(self, db_session):
        """Test filtering flights by price range."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Moon",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=500000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 18:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Jupiter",
                departure_time="2026-03-03 11:00",
                arrival_time="2026-03-03 19:00",
                base_price=2000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test min price
        results = flight.list_flights(db_session, min_price=1000000)
        assert len(results) == 2
        assert all(r.base_price >= 1000000 for r in results)

        # Test max price
        results = flight.list_flights(db_session, max_price=1000000)
        assert len(results) == 2
        assert all(r.base_price <= 1000000 for r in results)

        # Test price range
        results = flight.list_flights(db_session, min_price=800000, max_price=1500000)
        assert len(results) == 1
        assert results[0].base_price == 1000000

    def test_filter_by_seat_availability(self, db_session):
        """Test filtering flights by seat class availability."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=5,
                business_seats_available=0,
                galaxium_seats_available=0
            ),
            Flight(
                origin="Earth",
                destination="Venus",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 18:00",
                base_price=1100000,
                economy_seats_available=0,
                business_seats_available=3,
                galaxium_seats_available=0
            ),
            Flight(
                origin="Earth",
                destination="Jupiter",
                departure_time="2026-03-03 11:00",
                arrival_time="2026-03-03 19:00",
                base_price=2000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test economy seats
        results = flight.list_flights(db_session, has_economy=True)
        assert len(results) == 2
        assert all(r.economy_seats_available > 0 for r in results)

        # Test business seats
        results = flight.list_flights(db_session, has_business=True)
        assert len(results) == 2
        assert all(r.business_seats_available > 0 for r in results)

        # Test galaxium seats
        results = flight.list_flights(db_session, has_galaxium=True)
        assert len(results) == 1
        assert all(r.galaxium_seats_available > 0 for r in results)

        # Test multiple seat classes
        results = flight.list_flights(db_session, has_economy=True, has_business=True)
        assert len(results) == 1
        assert results[0].economy_seats_available > 0
        assert results[0].business_seats_available > 0

    def test_sort_by_price(self, db_session):
        """Test sorting flights by price."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Moon",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 18:00",
                base_price=500000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Jupiter",
                departure_time="2026-03-03 11:00",
                arrival_time="2026-03-03 19:00",
                base_price=2000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test ascending
        results = flight.list_flights(db_session, sort="price", order="asc")
        prices = [r.base_price for r in results]
        assert prices == sorted(prices)
        assert prices[0] == 500000

        # Test descending
        results = flight.list_flights(db_session, sort="price", order="desc")
        prices = [r.base_price for r in results]
        assert prices == sorted(prices, reverse=True)
        assert prices[0] == 2000000

    def test_sort_by_departure_time(self, db_session):
        """Test sorting flights by departure time."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-15 09:00",
                arrival_time="2026-03-15 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Venus",
                departure_time="2026-03-01 10:00",
                arrival_time="2026-03-01 18:00",
                base_price=1100000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Jupiter",
                departure_time="2026-03-30 11:00",
                arrival_time="2026-03-30 19:00",
                base_price=2000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test ascending
        results = flight.list_flights(db_session, sort="departure_time", order="asc")
        times = [r.departure_time for r in results]
        assert times == sorted(times)

        # Test descending
        results = flight.list_flights(db_session, sort="departure_time", order="desc")
        times = [r.departure_time for r in results]
        assert times == sorted(times, reverse=True)

    def test_sort_by_duration(self, db_session):
        """Test sorting flights by duration."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",  # 8 hours
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Moon",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 14:00",  # 4 hours
                base_price=500000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Jupiter",
                departure_time="2026-03-03 11:00",
                arrival_time="2026-03-04 11:00",  # 24 hours
                base_price=2000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Test ascending
        results = flight.list_flights(db_session, sort="duration", order="asc")
        assert results[0].destination == "Moon"  # Shortest
        assert results[2].destination == "Jupiter"  # Longest

        # Test descending
        results = flight.list_flights(db_session, sort="duration", order="desc")
        assert results[0].destination == "Jupiter"  # Longest
        assert results[2].destination == "Moon"  # Shortest

    def test_combined_filters(self, db_session):
        """Test combining multiple filters."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Earth",
                destination="Venus",
                departure_time="2026-03-15 10:00",
                arrival_time="2026-03-15 18:00",
                base_price=1100000,
                economy_seats_available=6,
                business_seats_available=0,
                galaxium_seats_available=0
            ),
            Flight(
                origin="Moon",
                destination="Mars",
                departure_time="2026-03-20 11:00",
                arrival_time="2026-03-20 19:00",
                base_price=800000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        # Combine origin, destination, date range, and seat availability
        results = flight.list_flights(
            db_session,
            origin="Earth",
            destination="Mars",
            departure_date_from="2026-03-01",
            departure_date_to="2026-03-10",
            has_business=True
        )
        assert len(results) == 1
        assert results[0].origin == "Earth"
        assert results[0].destination == "Mars"
        assert results[0].business_seats_available > 0

    def test_no_filters_returns_all(self, db_session):
        """Test that no filters returns all flights."""
        db_session.add_all([
            Flight(
                origin="Earth",
                destination="Mars",
                departure_time="2026-03-01 09:00",
                arrival_time="2026-03-01 17:00",
                base_price=1000000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            ),
            Flight(
                origin="Moon",
                destination="Venus",
                departure_time="2026-03-02 10:00",
                arrival_time="2026-03-02 18:00",
                base_price=1100000,
                economy_seats_available=6,
                business_seats_available=3,
                galaxium_seats_available=1
            )
        ])
        db_session.commit()

        results = flight.list_flights(db_session)
        assert len(results) == 2

    def test_filters_return_empty_when_no_match(self, db_session):
        """Test that filters return empty list when no flights match."""
        db_session.add(Flight(
            origin="Earth",
            destination="Mars",
            departure_time="2026-03-01 09:00",
            arrival_time="2026-03-01 17:00",
            base_price=1000000,
            economy_seats_available=6,
            business_seats_available=3,
            galaxium_seats_available=1
        ))
        db_session.commit()

        results = flight.list_flights(db_session, origin="Pluto")
        assert len(results) == 0

        results = flight.list_flights(db_session, min_price=10000000)
        assert len(results) == 0


class TestItineraryService:
    """Test itinerary service functions."""

    @pytest.mark.asyncio
    async def test_confirm_itinerary_partial_failure(self, db_session, monkeypatch):
        """A failed second-leg confirm cancels leg 1's booking and releases leg 2's hold."""
        db_session.add(User(user_id=1, name="Alice", email="alice@example.com"))
        for flight_id, origin, destination in ((1, "Earth", "Mars"), (2, "Mars", "Jupiter")):
            db_session.add(Flight(
                flight_id=flight_id, origin=origin, destination=destination,
                departure_time="2099-02-01 08:00", arrival_time="2099-02-01 16:00",
                base_price=1000, economy_seats_available=5,
                business_seats_available=3, galaxium_seats_available=1,
            ))
        db_session.add(Itinerary(
            itinerary_id=1, user_id=1, status="held", created_at="2099-01-01T00:00:00+00:00"
        ))
        db_session.add_all([
            ItineraryLeg(itinerary_id=1, flight_id=1, hold_id="H-001", leg_order=1),
            ItineraryLeg(itinerary_id=1, flight_id=2, hold_id="H-002", leg_order=2),
        ])
        db_session.commit()

        posted_urls = []

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kwargs):
                posted_urls.append(url)
                if url.endswith("/holds/H-002/confirm"):
                    raise httpx.HTTPStatusError(
                        "boom", request=MagicMock(), response=MagicMock(status_code=500)
                    )
                response = MagicMock()
                response.raise_for_status.return_value = None
                if url.endswith("/holds/H-001/confirm"):
                    response.json.return_value = {
                        "status": "CONFIRMED", "externalBookingReference": "99"
                    }
                else:
                    response.json.return_value = {"status": "RELEASED"}
                return response

        cancelled = []
        monkeypatch.setattr(itinerary.httpx, "AsyncClient", FakeClient)
        monkeypatch.setattr(
            booking, "cancel_booking", lambda db, booking_id: cancelled.append(booking_id)
        )

        result = await itinerary.confirm_itinerary(db_session, 1)

        assert isinstance(result, ErrorResponse)
        assert result.error_code == "CONFIRM_FAILED"
        db_session.expire_all()
        assert db_session.query(Itinerary).filter_by(itinerary_id=1).one().status == "failed"
        assert cancelled == [99]
        assert any(url.endswith("/holds/H-002/release") for url in posted_urls)
        assert not any(url.endswith("/holds/H-001/release") for url in posted_urls)


class TestItineraryCreateLimits:
    """Tests for POST /itineraries business-limit controls (F-2 and F-4 from audit)."""

    # ------------------------------------------------------------------
    # Fix 1 — flight_ids list length (schema-level, tested via REST client)
    # ------------------------------------------------------------------

    def test_zero_flight_ids_rejected_422(self, client):
        """An empty flight_ids list is rejected by Pydantic before hitting the service."""
        resp = client.post(
            "/itineraries",
            json={"user_id": 1, "name": "Alice", "flight_ids": []},
        )
        assert resp.status_code == 422

    def test_four_flight_ids_rejected_422(self, client):
        """A list of 4 flight IDs exceeds max_length=3 and is rejected with 422."""
        resp = client.post(
            "/itineraries",
            json={"user_id": 1, "name": "Alice", "flight_ids": [1, 2, 3, 4]},
        )
        assert resp.status_code == 422

    def test_one_flight_id_passes_schema(self, client, db_session):
        """A single flight_id satisfies min_length=1 and reaches the service layer."""
        # Service will return USER_NOT_FOUND (409), proving schema validation passed.
        resp = client.post(
            "/itineraries",
            json={"user_id": 999, "name": "Nobody", "flight_ids": [1]},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_code"] == "USER_NOT_FOUND"

    def test_three_flight_ids_passes_schema(self, client, db_session):
        """Three flight_ids satisfies max_length=3 and reaches the service layer."""
        resp = client.post(
            "/itineraries",
            json={"user_id": 999, "name": "Nobody", "flight_ids": [1, 2, 3]},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error_code"] == "USER_NOT_FOUND"

    # ------------------------------------------------------------------
    # Fix 2 — per-user hold cap (service-layer, tested directly)
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_too_many_holds_returns_error(self, db_session, monkeypatch):
        """User with 3 active held itineraries within the hold window is rejected."""
        import services.itinerary as svc

        db_session.add(User(user_id=10, name="Bob", email="bob@example.com"))
        db_session.add(Flight(
            flight_id=10, origin="Earth", destination="Mars",
            departure_time="2099-06-01 10:00", arrival_time="2099-06-01 18:00",
            base_price=500, economy_seats_available=10,
            business_seats_available=3, galaxium_seats_available=1,
        ))
        db_session.commit()

        # Insert 3 held itineraries all created "now" (well within the window).
        now = datetime.now(tz=UTC).isoformat()
        for _ in range(3):
            db_session.add(Itinerary(user_id=10, status="held", created_at=now))
        db_session.commit()

        result = await svc.create_itinerary(db_session, 10, "Bob", [10])

        assert isinstance(result, ErrorResponse)
        assert result.error_code == "TOO_MANY_HOLDS"

    @pytest.mark.asyncio
    async def test_expired_holds_do_not_count(self, db_session, monkeypatch):
        """Held itineraries older than HOLD_DURATION_MINUTES are not counted."""
        import services.itinerary as svc

        db_session.add(User(user_id=11, name="Carol", email="carol@example.com"))
        db_session.add(Flight(
            flight_id=11, origin="Earth", destination="Venus",
            departure_time="2099-06-02 10:00", arrival_time="2099-06-02 18:00",
            base_price=500, economy_seats_available=10,
            business_seats_available=3, galaxium_seats_available=1,
        ))
        db_session.commit()

        # 3 itineraries created 20 minutes ago — beyond the default 15-minute window.
        stale = (datetime.now(tz=UTC) - timedelta(minutes=20)).isoformat()
        for _ in range(3):
            db_session.add(Itinerary(user_id=11, status="held", created_at=stale))
        db_session.commit()

        # Patch httpx so the service doesn't try to reach the Java service.
        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kwargs):
                raise httpx.HTTPError("no java service in tests")

        monkeypatch.setattr(svc.httpx, "AsyncClient", FakeClient)

        result = await svc.create_itinerary(db_session, 11, "Carol", [11])

        # Not rejected by the cap — reaches the Java call and fails with HOLD_FAILED.
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "HOLD_FAILED"

    @pytest.mark.asyncio
    async def test_too_many_holds_http_429(self, client, db_session):
        """POST /itineraries returns 429 when the per-user hold cap is reached."""
        db_session.add(User(user_id=20, name="Dave", email="dave@example.com"))
        db_session.commit()

        now = datetime.now(tz=UTC).isoformat()
        for _ in range(3):
            db_session.add(Itinerary(user_id=20, status="held", created_at=now))
        db_session.commit()

        resp = client.post(
            "/itineraries",
            json={"user_id": 20, "name": "Dave", "flight_ids": [1]},
        )
        assert resp.status_code == 429
        assert resp.json()["detail"]["error_code"] == "TOO_MANY_HOLDS"

    @pytest.mark.asyncio
    async def test_confirmed_itineraries_do_not_count(self, db_session, monkeypatch):
        """Only 'held' itineraries count toward the cap; confirmed ones do not."""
        import services.itinerary as svc

        db_session.add(User(user_id=12, name="Eve", email="eve@example.com"))
        db_session.add(Flight(
            flight_id=12, origin="Mars", destination="Jupiter",
            departure_time="2099-06-03 10:00", arrival_time="2099-06-04 06:00",
            base_price=800, economy_seats_available=10,
            business_seats_available=3, galaxium_seats_available=1,
        ))
        db_session.commit()

        now = datetime.now(tz=UTC).isoformat()
        # 3 confirmed itineraries — these must NOT block a new hold.
        for _ in range(3):
            db_session.add(Itinerary(user_id=12, status="confirmed", created_at=now))
        db_session.commit()

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, **kwargs):
                raise httpx.HTTPError("no java service in tests")

        monkeypatch.setattr(svc.httpx, "AsyncClient", FakeClient)

        result = await svc.create_itinerary(db_session, 12, "Eve", [12])

        # Cap not triggered — reaches Java call and fails with HOLD_FAILED.
        assert isinstance(result, ErrorResponse)
        assert result.error_code == "HOLD_FAILED"
