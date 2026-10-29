from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import Flight
from schemas import ErrorResponse, ItinerarySearchResult
from services.flight import _flight_to_out as flight_to_out

DATETIME_FORMATS = ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M"]


def parse_time(value: str) -> datetime:
    """Parse a datetime string in either ISO 8601 UTC or space-separated format.

    Accepts formats:
        - "2099-02-01T09:00:00Z"
        - "2099-02-01 09:00"

    Returns:
        datetime: The parsed datetime object.

    Raises:
        ValueError: If the string does not match any supported format.
    """
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unable to parse datetime string: {value!r}")


def is_valid_connection(arriving: Flight, departing: Flight) -> bool:
    """Check whether two flights form a valid connection.

    A connection is valid when:
        - departing.origin matches arriving.destination (case-insensitive).
        - departing.departure_time is between 2 and 72 hours (inclusive) after
          arriving.arrival_time.

    Args:
        arriving: The inbound flight.
        departing: The outbound/connecting flight.

    Returns:
        bool: True if the connection is valid, False otherwise.
    """
    if arriving.destination.lower() != departing.origin.lower():
        return False

    arrival_dt = parse_time(arriving.arrival_time)
    departure_dt = parse_time(departing.departure_time)

    layover = departure_dt - arrival_dt
    min_layover_hours = 2
    max_layover_hours = 72
    total_seconds = layover.total_seconds()
    return (
        min_layover_hours * 3600 <= total_seconds <= max_layover_hours * 3600
    )


MAX_LEGS = 3


def search_itineraries(
    db: Session, origin: str, destination: str, date: str
) -> list[ItinerarySearchResult] | ErrorResponse:
    """Search for 1-3 leg itineraries from origin to destination.

    The first leg must depart on `date` (YYYY-MM-DD); later legs may depart on
    following days as long as each layover is valid per `is_valid_connection`.
    Seat availability is not checked here. Results are sorted by total travel
    time, then total economy price.

    Args:
        db: Database session.
        origin: Origin body (case-insensitive).
        destination: Destination body (case-insensitive).
        date: Departure date of the first leg, formatted YYYY-MM-DD.

    Returns:
        A list of ItinerarySearchResult, or an ErrorResponse if `date` is invalid.
    """
    try:
        day_start = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return ErrorResponse(
            error="Invalid date",
            error_code="INVALID_DATE",
            details=f"Date '{date}' is not valid. Use the format YYYY-MM-DD.",
        )
    day_end = day_start + timedelta(days=1)

    flights = [
        f for f in db.query(Flight).all()
        if parse_time(f.departure_time) >= day_start
    ]
    origin_key = origin.strip().lower()
    destination_key = destination.strip().lower()

    # Breadth-first expansion of route prefixes, starting with first legs
    # that depart on the requested date.
    frontier: list[list[Flight]] = [
        [f] for f in flights
        if f.origin.lower() == origin_key and parse_time(f.departure_time) < day_end
    ]
    routes: list[list[Flight]] = []
    for _ in range(MAX_LEGS):
        next_frontier: list[list[Flight]] = []
        for prefix in frontier:
            last = prefix[-1]
            if last.destination.lower() == destination_key:
                routes.append(prefix)
                continue
            if len(prefix) == MAX_LEGS:
                continue
            last_arrival = parse_time(last.arrival_time)
            for candidate in flights:
                if (
                    parse_time(candidate.departure_time) > last_arrival
                    and is_valid_connection(last, candidate)
                ):
                    next_frontier.append([*prefix, candidate])
        frontier = next_frontier

    results = [
        ItinerarySearchResult(
            legs=[flight_to_out(f) for f in route],
            total_price=sum(f.base_price for f in route),
            total_duration_minutes=int(
                (
                    parse_time(route[-1].arrival_time)
                    - parse_time(route[0].departure_time)
                ).total_seconds() // 60
            ),
        )
        for route in routes
    ]
    results.sort(key=lambda r: (r.total_duration_minutes, r.total_price))
    return results
