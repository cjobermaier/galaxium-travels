from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Seat class type definition
SeatClass = Literal['economy', 'business', 'galaxium']

# Maximum seats a single quote may request
MAX_QUOTE_QUANTITY = 10


class FlightQueryParams(BaseModel):
    """Query parameters for filtering and sorting flights."""
    # Location filters (case-insensitive partial match)
    origin: str | None = None
    destination: str | None = None
    
    # Date range filters (format: YYYY-MM-DD)
    departure_date_from: str | None = None
    departure_date_to: str | None = None
    
    # Price range filters
    min_price: int | None = None
    max_price: int | None = None
    
    # Seat availability filters (at least 1 seat available)
    has_economy: bool | None = None
    has_business: bool | None = None
    has_galaxium: bool | None = None
    
    # Sorting
    sort: Literal['price', 'departure_time', 'duration'] | None = None
    order: Literal['asc', 'desc'] | None = 'asc'


class FlightOut(BaseModel):
    flight_id: int
    origin: str
    destination: str
    departure_time: str  # Format: YYYY-MM-DD HH:MM
    arrival_time: str    # Format: YYYY-MM-DD HH:MM
    base_price: int  # Economy price (1x)
    economy_seats_available: int
    business_seats_available: int
    galaxium_seats_available: int
    # Computed prices for all classes
    economy_price: int
    business_price: int
    galaxium_price: int

    model_config = ConfigDict(from_attributes=True)


class BookingRequest(BaseModel):
    user_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    flight_id: int = Field(ge=1)
    seat_class: SeatClass = 'economy'  # Default to economy


class BookingOut(BaseModel):
    booking_id: int
    user_id: int
    flight_id: int
    status: str
    booking_time: str
    seat_class: str
    price_paid: int

    model_config = ConfigDict(from_attributes=True)


class UserRegistration(BaseModel):
    name: str
    email: str


class UserOut(BaseModel):
    user_id: int
    name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class ItineraryLegOut(BaseModel):
    leg_id: int
    flight_id: int
    leg_order: int
    flight: FlightOut
    booking_id: int | None = None
    hold_id: str | None = None


class ItineraryOut(BaseModel):
    itinerary_id: int
    user_id: int
    status: str  # held | confirmed | failed
    created_at: str
    legs: list[ItineraryLegOut]
    total_price: int  # Sum of economy prices of all legs


class ItinerarySearchResult(BaseModel):
    legs: list[FlightOut]
    total_price: int  # Sum of economy prices of all legs
    total_duration_minutes: int  # First departure to last arrival


class CreateItineraryRequest(BaseModel):
    user_id: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=100)
    flight_ids: list[int] = Field(min_length=1, max_length=3)


class CreateQuoteRequest(BaseModel):
    """Body for POST /quotes; field names match the Java hold service API (camelCase).

    Unknown fields (for example a client-supplied price) are rejected.
    """
    model_config = ConfigDict(extra='forbid')

    flightId: int = Field(ge=1)
    seatClass: SeatClass
    quantity: int = Field(ge=1, le=MAX_QUOTE_QUANTITY)
    travelerId: int = Field(ge=1)
    travelerName: str = Field(min_length=1, max_length=100)


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    error_code: str
    details: str | None = None
