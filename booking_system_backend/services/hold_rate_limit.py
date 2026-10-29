import os
import time
from collections import deque

from schemas import ErrorResponse

HOLD_RATE_LIMIT = int(os.getenv("HOLD_RATE_LIMIT_PER_MINUTE", "20"))
QUOTE_RATE_LIMIT = int(os.getenv("QUOTE_RATE_LIMIT_PER_MINUTE", "20"))
HOLD_RATE_WINDOW_SECONDS = 60.0
# Number of trusted reverse proxies in front of the app. 0 means the TCP peer is the client.
# X-Forwarded-For is only honored when this is > 0, since clients can spoof it otherwise.
TRUSTED_PROXY_COUNT = int(os.getenv("TRUSTED_PROXY_COUNT", "0"))

# "scope:client" -> monotonic timestamps of attempts inside the window
_attempts: dict[str, deque[float]] = {}


def resolve_client_id(peer_host: str | None, forwarded_for: str | None) -> str:
    """Return the rate-limit key for a request.

    With TRUSTED_PROXY_COUNT == 0 the TCP peer address is used. Otherwise the client
    address is the TRUSTED_PROXY_COUNT-th entry from the right of X-Forwarded-For, which
    is the last value appended by a trusted proxy and cannot be spoofed by the client.
    Falls back to the peer address (or "unknown") if the header is missing or too short.
    """
    fallback = peer_host or "unknown"
    if TRUSTED_PROXY_COUNT <= 0 or not forwarded_for:
        return fallback
    hops = [h.strip() for h in forwarded_for.split(",") if h.strip()]
    if len(hops) < TRUSTED_PROXY_COUNT:
        return fallback
    return hops[-TRUSTED_PROXY_COUNT]


def reset_hold_rate_limit() -> None:
    """Clear all recorded quote and hold attempts (used by tests)."""
    _attempts.clear()


def _check(scope: str, client_id: str, limit: int, noun: str) -> ErrorResponse | None:
    """Record an attempt for a client in a scope and enforce its per-minute limit."""
    now = time.monotonic()
    attempts = _attempts.setdefault(f"{scope}:{client_id}", deque())
    while attempts and now - attempts[0] >= HOLD_RATE_WINDOW_SECONDS:
        attempts.popleft()

    if len(attempts) >= limit:
        return ErrorResponse(
            error=f"Too many {noun} requests",
            error_code="RATE_LIMITED",
            details=f"At most {limit} {noun}s can be created per minute. Please wait before trying again.",
        )

    attempts.append(now)
    return None


def check_hold_rate_limit(client_id: str) -> ErrorResponse | None:
    """Record a hold creation attempt for a client and enforce the per-minute limit.

    Returns None when the attempt is allowed, or a RATE_LIMITED ErrorResponse when the
    client has already made HOLD_RATE_LIMIT attempts in the last minute.
    """
    return _check("hold", client_id, HOLD_RATE_LIMIT, "hold")


def check_quote_rate_limit(client_id: str) -> ErrorResponse | None:
    """Record a quote creation attempt for a client and enforce the per-minute limit.

    Quotes are counted separately from holds. Returns None when allowed, or a
    RATE_LIMITED ErrorResponse after QUOTE_RATE_LIMIT attempts in the last minute.
    """
    return _check("quote", client_id, QUOTE_RATE_LIMIT, "quote")
