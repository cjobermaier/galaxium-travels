import os
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mcp import FastApiMCP
from sqlalchemy.orm import Session

from db import get_db, init_db
from schemas import (
    BookingOut,
    BookingRequest,
    CreateItineraryRequest,
    CreateQuoteRequest,
    ErrorResponse,
    FlightOut,
    ItineraryOut,
    ItinerarySearchResult,
    UserOut,
    UserRegistration,
)
from seed import seed
from services import booking, flight, hold_rate_limit, itinerary, itinerary_search, user

# Load environment variables from .env file
load_dotenv()

# Bounds for GET /flights query parameters
MAX_PRICE_FILTER = 1_000_000_000
MAX_DURATION_FILTER_HOURS = 10_000
MAX_SEATS_FILTER = 10_000
DEFAULT_FLIGHTS_LIMIT = 100
MAX_FLIGHTS_LIMIT = 500
MAX_FLIGHTS_OFFSET = 100_000
# Bounds for GET /itineraries/search query parameters
MAX_BODY_NAME_LENGTH = 50
ITINERARY_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
DATE_FILTER_PATTERN = r"^\d{4}-\d{2}-\d{2}([T ].*)?$"


# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()

    should_seed = os.getenv("SEED_DEMO_DATA", "true").lower() in {"1", "true", "yes", "on"}
    if should_seed:
        seed()

    yield
    # Shutdown (nothing to do)


# ==================== FASTAPI APP (REST + Swagger UI) ====================

app = FastAPI(
    title="Galaxium Booking System",
    description="API for booking interplanetary flights. Swagger UI available at /docs",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/api"  # Add this for ALB routing
)

# Get allowed origins from environment
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "OK"}


@app.get("/flights", response_model=list[FlightOut], tags=["Flights"])
def get_flights(
    # Basic filters from main branch
    origin: str | None = None,
    destination: str | None = None,
    departure_date_from: str | None = Query(None, pattern=DATE_FILTER_PATTERN, max_length=40),
    departure_date_to: str | None = Query(None, pattern=DATE_FILTER_PATTERN, max_length=40),
    min_price: int | None = Query(None, ge=0, le=MAX_PRICE_FILTER),
    max_price: int | None = Query(None, ge=0, le=MAX_PRICE_FILTER),
    has_economy: bool | None = None,
    has_business: bool | None = None,
    has_galaxium: bool | None = None,
    sort: str | None = None,
    order: str | None = 'asc',
    # Phase 1: Core Filters from feature branch
    sort_by: str | None = None,
    sort_order: str | None = None,
    seat_class: str | None = None,
    # Phase 2: Additional Filters from feature branch
    departure_time_period: str | None = None,
    min_duration: int | None = Query(None, ge=0, le=MAX_DURATION_FILTER_HOURS),
    max_duration: int | None = Query(None, ge=0, le=MAX_DURATION_FILTER_HOURS),
    min_seats_available: int | None = Query(None, ge=0, le=MAX_SEATS_FILTER),
    # Phase 3: Popular Routes from feature branch
    route_category: str | None = None,
    # Pagination
    limit: int = Query(DEFAULT_FLIGHTS_LIMIT, ge=1, le=MAX_FLIGHTS_LIMIT),
    offset: int = Query(0, ge=0, le=MAX_FLIGHTS_OFFSET),
    db: Session = Depends(get_db)
):
    """List all available flights with optional filtering and sorting.
    
    All query parameters are optional for backward compatibility.
    
    **Basic Filters:**
    - origin: Filter by origin (case-insensitive partial match)
    - destination: Filter by destination (case-insensitive partial match)
    - departure_date_from: Filter flights departing on or after this date (ISO format)
    - departure_date_to: Filter flights departing on or before this date (ISO format)
    - min_price: Minimum price (checks economy price)
    - max_price: Maximum price (checks economy price)
    - has_economy: Only flights with economy seats available
    - has_business: Only flights with business seats available
    - has_galaxium: Only flights with galaxium seats available
    - sort: Sort by 'price', 'departure_time', or 'duration'
    - order: Sort order 'asc' or 'desc' (default: asc)
    
    **Phase 1 - Core Filters:**
    - sort_by: Field to sort by (departure_time, base_price, duration, seats_available)
    - sort_order: Sort direction (asc, desc)
    - seat_class: Filter by seat class availability (economy, business, galaxium)
    
    **Phase 2 - Additional Filters:**
    - departure_time_period: Time of day (morning, afternoon, evening, night)
    - min_duration: Minimum flight duration in hours
    - max_duration: Maximum flight duration in hours
    - min_seats_available: Minimum total seats available
    
    **Phase 3 - Popular Routes:**
    - route_category: Route category (inner_planets, outer_planets, moons)

    **Pagination:**
    - limit: Maximum flights to return (1-500, default 100)
    - offset: Number of flights to skip (default 0)

    Out-of-range numeric filters and malformed dates are rejected with 422.
    """
    return flight.list_flights(
        db=db,
        origin=origin,
        destination=destination,
        departure_date_from=departure_date_from,
        departure_date_to=departure_date_to,
        min_price=min_price,
        max_price=max_price,
        has_economy=has_economy,
        has_business=has_business,
        has_galaxium=has_galaxium,
        sort=sort,
        order=order,
        sort_by=sort_by,
        sort_order=sort_order,
        seat_class=seat_class,
        departure_time_period=departure_time_period,
        min_duration=min_duration,
        max_duration=max_duration,
        min_seats_available=min_seats_available,
        route_category=route_category,
        limit=limit,
        offset=offset
    )


@app.post("/book", response_model=BookingOut, tags=["Bookings"])
def book_flight_endpoint(request: BookingRequest, db: Session = Depends(get_db)):
    """Book a seat on a specific flight for a user in the specified seat class.

    Requires user_id, name, and flight_id.
    Optional seat_class: 'economy' (default), 'business', or 'galaxium'.
    Decrements available seats for the selected class if successful.
    Returns booking details. Raises 404 if the flight or user is not found,
    409 if there is a name mismatch or no seats available.
    """
    result = booking.book_flight(db, request.user_id, request.name, request.flight_id, request.seat_class)
    if isinstance(result, ErrorResponse):
        status = 404 if result.error_code in ("FLIGHT_NOT_FOUND", "USER_NOT_FOUND") else 409
        raise HTTPException(status_code=status, detail=result.model_dump())
    return result


@app.get("/bookings/{user_id}", response_model=list[BookingOut], tags=["Bookings"])
def get_user_bookings(user_id: int, db: Session = Depends(get_db)):
    """Retrieve all bookings for a specific user by user_id."""
    return booking.get_bookings(db, user_id)


@app.post("/cancel/{booking_id}", response_model=BookingOut, tags=["Bookings"])
def cancel_booking_endpoint(booking_id: int, db: Session = Depends(get_db)):
    """Cancel an existing booking by its booking_id.

    Increments available seats for the flight if successful.
    Raises 404 if the booking is not found, 409 if already cancelled.
    """
    result = booking.cancel_booking(db, booking_id)
    if isinstance(result, ErrorResponse):
        status = 404 if result.error_code == "BOOKING_NOT_FOUND" else 409
        raise HTTPException(status_code=status, detail=result.model_dump())
    return result


@app.post("/register", response_model=UserOut, tags=["Users"])
def register_user_endpoint(request: UserRegistration, db: Session = Depends(get_db)):
    """Register a new user with a name and unique email.

    Raises 409 if the email is already registered, 422 if the email format is invalid.
    """
    result = user.register_user(db, request.name, request.email)
    if isinstance(result, ErrorResponse):
        status = 409 if result.error_code == "EMAIL_EXISTS" else 422
        raise HTTPException(status_code=status, detail=result.model_dump())
    return result


@app.get("/user", response_model=UserOut, tags=["Users"])
def get_user_endpoint(name: str, email: str, db: Session = Depends(get_db)):
    """Get user by name and email.

    Raises 404 if no user matches the provided name and email,
    422 if the email format is invalid.
    """
    result = user.get_user(db, name, email)
    if isinstance(result, ErrorResponse):
        status = 404 if result.error_code == "USER_NOT_FOUND" else 422
        raise HTTPException(status_code=status, detail=result.model_dump())
    return result


# ==================== ITINERARIES ====================

@app.get("/itineraries/search", response_model=list[ItinerarySearchResult], tags=["Itineraries"])
def search_itineraries_endpoint(
    origin: str = Query(max_length=MAX_BODY_NAME_LENGTH),
    destination: str = Query(max_length=MAX_BODY_NAME_LENGTH),
    date: str = Query(pattern=ITINERARY_DATE_PATTERN, max_length=10),
    db: Session = Depends(get_db),
):
    """Search 1-3 leg itineraries between two bodies for a departure date (YYYY-MM-DD).

    Layovers must be 2-72 hours. Results are sorted by total travel time, then price.
    Raises 422 if the date is invalid.
    """
    result = itinerary_search.search_itineraries(db, origin, destination, date)
    if isinstance(result, ErrorResponse):
        raise HTTPException(status_code=422, detail=result.model_dump())
    return result


@app.post("/itineraries", response_model=ItineraryOut, tags=["Itineraries"])
async def create_itinerary_endpoint(request: CreateItineraryRequest, db: Session = Depends(get_db)):
    """Hold every leg of an itinerary through the Java hold service, all-or-nothing.

    Raises 404 if the user or a flight is not found, 409 for duplicate legs, name
    mismatch, or no seats, and 502 (HOLD_FAILED) if any hold fails.
    """
    result = await itinerary.create_itinerary(db, request.user_id, request.name, request.flight_ids)
    if isinstance(result, ErrorResponse):
        if result.error_code == "HOLD_FAILED":
            status = 502
        elif result.error_code in ("FLIGHT_NOT_FOUND", "USER_NOT_FOUND"):
            status = 404
        elif result.error_code == "TOO_MANY_HOLDS":
            status = 429
        else:
            status = 409
        raise HTTPException(status_code=status, detail=result.model_dump())
    return result


@app.post("/itineraries/{itinerary_id}/confirm", response_model=ItineraryOut, tags=["Itineraries"])
async def confirm_itinerary_endpoint(itinerary_id: int, db: Session = Depends(get_db)):
    """Confirm all holds of an itinerary leg by leg.

    Raises 404 if the itinerary is not found, 409 if it is not in held status,
    and 502 (CONFIRM_FAILED) if any leg fails to confirm.
    """
    result = await itinerary.confirm_itinerary(db, itinerary_id)
    if isinstance(result, ErrorResponse):
        if result.error_code == "CONFIRM_FAILED":
            status = 502
        elif result.error_code == "ITINERARY_NOT_FOUND":
            status = 404
        else:
            status = 409
        raise HTTPException(status_code=status, detail=result.model_dump())
    return result


@app.get("/users/{user_id}/itineraries", response_model=list[ItineraryOut], tags=["Itineraries"])
def get_user_itineraries_endpoint(user_id: int, db: Session = Depends(get_db)):
    """List a user's itineraries with their legs, newest first."""
    return itinerary.get_user_itineraries(db, user_id)


# ==================== JAVA SERVICE INTEGRATION ====================

JAVA_SERVICE_URL = os.getenv("JAVA_SERVICE_URL", "http://localhost:8080")


@app.post("/internal/bookings/from-hold", response_model=BookingOut, tags=["Internal"])
def create_booking_from_hold(hold_data: dict, db: Session = Depends(get_db)):
    """Internal endpoint for Java hold service to create bookings.

    This endpoint is called by the Java inventory hold service when confirming a hold.
    Returns HTTP 400 on booking failure so the Java service can detect and propagate the error.
    """
    result = booking.book_flight(
        db,
        user_id=hold_data["travelerId"],
        name=hold_data["travelerName"],
        flight_id=hold_data["flightId"],
        seat_class=hold_data["seatClass"]
    )
    if isinstance(result, ErrorResponse):
        raise HTTPException(status_code=400, detail=result.model_dump())
    return result


# ==================== JAVA SERVICE PROXY ENDPOINTS ====================

def _client_id(request: Request) -> str:
    """Return the rate-limit key for a request, honoring X-Forwarded-For only for trusted proxies."""
    return hold_rate_limit.resolve_client_id(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
    )


@app.post("/quotes", tags=["Quotes"])
async def create_quote(
    quote_data: CreateQuoteRequest, request: Request, db: Session = Depends(get_db)
):
    """Proxy endpoint to create a quote in the Java hold service.

    The body is validated and unknown fields are rejected (422), so a client cannot
    inject server-owned values such as a price. Rate limited per client; raises 429
    when the limit is exceeded. Raises 404 if the flight does not exist and 409 if it
    has fewer seats of the requested class than the requested quantity.
    """
    client_id = _client_id(request)
    limited = hold_rate_limit.check_quote_rate_limit(client_id)
    if isinstance(limited, ErrorResponse):
        raise HTTPException(status_code=429, detail=limited.model_dump())
    unavailable = flight.check_seat_availability(
        db, quote_data.flightId, quote_data.seatClass, quote_data.quantity
    )
    if isinstance(unavailable, ErrorResponse):
        status = 404 if unavailable.error_code == "FLIGHT_NOT_FOUND" else 409
        raise HTTPException(status_code=status, detail=unavailable.model_dump())
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{JAVA_SERVICE_URL}/api/v1/quotes",
                json=quote_data.model_dump(),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            return {"error": f"Failed to create quote: {e!s}"}


@app.get("/quotes/{quote_id}", tags=["Quotes"])
async def get_quote(quote_id: str):
    """Proxy endpoint to get a quote from the Java hold service."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{JAVA_SERVICE_URL}/api/v1/quotes/{quote_id}",
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            return {"error": f"Failed to get quote: {e!s}"}


@app.post("/quotes/{quote_id}/holds", tags=["Holds"])
async def create_hold(quote_id: str, request: Request):
    """Proxy endpoint to create a hold from a quote in the Java hold service.

    Rate limited per client; raises 429 when the limit is exceeded.
    """
    client_id = _client_id(request)
    limited = hold_rate_limit.check_hold_rate_limit(client_id)
    if isinstance(limited, ErrorResponse):
        raise HTTPException(status_code=429, detail=limited.model_dump())
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{JAVA_SERVICE_URL}/api/v1/quotes/{quote_id}/holds",
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            return {"error": f"Failed to create hold: {e!s}"}


@app.get("/holds/{hold_id}", tags=["Holds"])
async def get_hold(hold_id: str):
    """Proxy endpoint to get a hold from the Java hold service."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{JAVA_SERVICE_URL}/api/v1/holds/{hold_id}",
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            return {"error": f"Failed to get hold: {e!s}"}


@app.post("/holds/{hold_id}/confirm", tags=["Holds"])
async def confirm_hold(hold_id: str):
    """Proxy endpoint to confirm a hold in the Java hold service."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{JAVA_SERVICE_URL}/api/v1/holds/{hold_id}/confirm",
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            return {"error": f"Failed to confirm hold: {e!s}"}


@app.post("/holds/{hold_id}/release", tags=["Holds"])
async def release_hold(hold_id: str):
    """Proxy endpoint to release a hold in the Java hold service."""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{JAVA_SERVICE_URL}/api/v1/holds/{hold_id}/release",
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            return {"error": f"Failed to release hold: {e!s}"}


# ==================== MCP SERVER (for AI agents) ====================
# Auto-generates MCP tools from all FastAPI routes above — no duplication needed.

mcp = FastApiMCP(app)
mcp.mount_http()


# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
