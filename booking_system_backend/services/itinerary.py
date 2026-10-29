import os
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session, selectinload

from models import Booking, Flight, Itinerary, ItineraryLeg, User
from schemas import ErrorResponse, ItineraryLegOut, ItineraryOut
from services import booking
from services.flight import _flight_to_out

JAVA_SERVICE_URL = os.getenv("JAVA_SERVICE_URL", "http://localhost:8080")
JAVA_TIMEOUT = 30.0
HOLD_DURATION_MINUTES = int(os.getenv("HOLD_DURATION_MINUTES", "15"))
MAX_HELD_ITINERARIES = 3


def _itinerary_to_out(itinerary: Itinerary) -> ItineraryOut:
    """Convert an Itinerary ORM object (with legs and flights loaded) to ItineraryOut."""
    legs = sorted(itinerary.legs, key=lambda leg: leg.leg_order)
    return ItineraryOut(
        itinerary_id=itinerary.itinerary_id,
        user_id=itinerary.user_id,
        status=itinerary.status,
        created_at=itinerary.created_at,
        legs=[
            ItineraryLegOut(
                leg_id=leg.leg_id,
                flight_id=leg.flight_id,
                leg_order=leg.leg_order,
                flight=_flight_to_out(leg.flight),
                booking_id=leg.booking_id,
                hold_id=leg.hold_id,
            )
            for leg in legs
        ],
        total_price=sum(leg.flight.base_price for leg in legs),
    )


async def _release_hold(client: httpx.AsyncClient, hold_id: str) -> None:
    """Release a hold in the Java service, ignoring failures (best-effort cleanup)."""
    try:
        response = await client.post(
            f"{JAVA_SERVICE_URL}/api/v1/holds/{hold_id}/release", timeout=JAVA_TIMEOUT
        )
        response.raise_for_status()
    except httpx.HTTPError:
        pass


async def create_itinerary(
    db: Session, user_id: int, name: str, flight_ids: list[int]
) -> ItineraryOut | ErrorResponse:
    """Hold one economy seat on every flight of an itinerary, all-or-nothing.

    Quotes and holds are created through the Java hold service. If any hold
    fails, the holds already obtained are released (in reverse order), a
    `failed` itinerary is recorded, and a HOLD_FAILED error is returned.
    """
    cutoff = (datetime.now(tz=UTC) - timedelta(minutes=HOLD_DURATION_MINUTES)).isoformat()
    active_holds = (
        db.query(Itinerary)
        .filter(
            Itinerary.user_id == user_id,
            Itinerary.status == "held",
            Itinerary.created_at >= cutoff,
        )
        .count()
    )
    if active_holds >= MAX_HELD_ITINERARIES:
        return ErrorResponse(
            error="Too many active holds",
            error_code="TOO_MANY_HOLDS",
            details=(
                f"You already have {active_holds} itinerary hold(s) active. "
                f"Holds expire after {HOLD_DURATION_MINUTES} minutes. "
                "Please confirm or wait for existing holds to expire before creating a new one."
            ),
        )

    if len(set(flight_ids)) != len(flight_ids):
        return ErrorResponse(
            error="Duplicate legs",
            error_code="DUPLICATE_LEGS",
            details="The same flight_id appears more than once in the itinerary.",
        )

    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return ErrorResponse(
            error="User not found",
            error_code="USER_NOT_FOUND",
            details=f"User with ID {user_id} is not registered in our system.",
        )
    if user.name != name:
        return ErrorResponse(
            error="Name mismatch",
            error_code="NAME_MISMATCH",
            details=f"User ID {user_id} exists but the name '{name}' does not match the registered name '{user.name}'.",
        )

    flights: list[Flight] = []
    for flight_id in flight_ids:
        flight = db.query(Flight).filter(Flight.flight_id == flight_id).first()
        if not flight:
            return ErrorResponse(
                error="Flight not found",
                error_code="FLIGHT_NOT_FOUND",
                details=f"The specified flight_id {flight_id} does not exist in our system.",
            )
        if flight.economy_seats_available < 1:
            return ErrorResponse(
                error="No economy seats available",
                error_code="NO_SEATS_AVAILABLE",
                details=f"Flight {flight_id} has no available economy seats.",
            )
        flights.append(flight)

    hold_ids: list[str] = []
    failure: str | None = None
    async with httpx.AsyncClient() as client:
        for flight in flights:
            try:
                quote_response = await client.post(
                    f"{JAVA_SERVICE_URL}/api/v1/quotes",
                    json={
                        "flightId": flight.flight_id,
                        "seatClass": "economy",
                        "quantity": 1,
                        "travelerId": user_id,
                        "travelerName": name,
                    },
                    timeout=JAVA_TIMEOUT,
                )
                quote_response.raise_for_status()
                quote_id = quote_response.json()["quoteId"]
                hold_response = await client.post(
                    f"{JAVA_SERVICE_URL}/api/v1/quotes/{quote_id}/holds",
                    timeout=JAVA_TIMEOUT,
                )
                hold_response.raise_for_status()
                hold_ids.append(hold_response.json()["holdId"])
            except (httpx.HTTPError, KeyError, ValueError) as e:
                failure = f"Could not hold flight {flight.flight_id}: {e!s}"
                break

        if failure is not None:
            for hold_id in reversed(hold_ids):
                await _release_hold(client, hold_id)

    itinerary = Itinerary(
        user_id=user_id,
        status="held" if failure is None else "failed",
        created_at=datetime.now(tz=UTC).isoformat(),
    )
    db.add(itinerary)
    db.flush()
    for order, flight in enumerate(flights, start=1):
        db.add(ItineraryLeg(
            itinerary_id=itinerary.itinerary_id,
            flight_id=flight.flight_id,
            hold_id=hold_ids[order - 1] if failure is None else None,
            leg_order=order,
        ))
    db.commit()

    if failure is not None:
        return ErrorResponse(
            error="Failed to hold all legs",
            error_code="HOLD_FAILED",
            details=f"{failure}. Any holds already obtained were released.",
        )

    db.refresh(itinerary)
    return _itinerary_to_out(itinerary)


async def confirm_itinerary(db: Session, itinerary_id: int) -> ItineraryOut | ErrorResponse:
    """Confirm every hold of a held itinerary, leg by leg.

    The Java service creates each Booking via the Python `/internal/bookings/from-hold`
    endpoint and returns its id as `externalBookingReference`; that id is stored on the
    leg. If any leg fails, bookings already created are cancelled, the holds of all legs
    without a booking are released, the itinerary is marked `failed`, and CONFIRM_FAILED
    is returned.
    """
    itinerary = db.query(Itinerary).filter(Itinerary.itinerary_id == itinerary_id).first()
    if not itinerary:
        return ErrorResponse(
            error="Itinerary not found",
            error_code="ITINERARY_NOT_FOUND",
            details=f"Itinerary with ID {itinerary_id} does not exist.",
        )
    if itinerary.status != "held":
        return ErrorResponse(
            error="Itinerary is not in held status",
            error_code="INVALID_ITINERARY_STATUS",
            details=f"Itinerary {itinerary_id} has status '{itinerary.status}' and cannot be confirmed.",
        )

    legs = sorted(itinerary.legs, key=lambda leg: leg.leg_order)
    failure: str | None = None
    async with httpx.AsyncClient() as client:
        for leg in legs:
            try:
                response = await client.post(
                    f"{JAVA_SERVICE_URL}/api/v1/holds/{leg.hold_id}/confirm",
                    timeout=JAVA_TIMEOUT,
                )
                response.raise_for_status()
                data = response.json()
                if data.get("status") != "CONFIRMED":
                    raise ValueError(f"hold status is {data.get('status')}")
                leg.booking_id = int(data["externalBookingReference"])
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
                failure = f"Could not confirm leg {leg.leg_order} (hold {leg.hold_id}): {e!s}"
                break
            # Persist immediately so cleanup can find the booking.
            linked = db.query(Booking).filter(Booking.booking_id == leg.booking_id).first()
            if linked:
                linked.itinerary_id = itinerary_id
            db.commit()

        if failure is not None:
            for leg in legs:
                if leg.booking_id is not None:
                    booking.cancel_booking(db, leg.booking_id)
                elif leg.hold_id:
                    await _release_hold(client, leg.hold_id)

    if failure is not None:
        itinerary.status = "failed"
        db.commit()
        return ErrorResponse(
            error="Failed to confirm all legs",
            error_code="CONFIRM_FAILED",
            details=f"{failure}. Confirmed legs were cancelled and remaining holds released.",
        )

    itinerary.status = "confirmed"
    db.commit()
    db.refresh(itinerary)
    return _itinerary_to_out(itinerary)


def get_user_itineraries(db: Session, user_id: int) -> list[ItineraryOut]:
    """Return a user's itineraries (with legs and flights), newest first."""
    itineraries = (
        db.query(Itinerary)
        .options(selectinload(Itinerary.legs).selectinload(ItineraryLeg.flight))
        .filter(Itinerary.user_id == user_id)
        .order_by(Itinerary.created_at.desc())
        .all()
    )
    return [_itinerary_to_out(i) for i in itineraries]
