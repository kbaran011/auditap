"""
Rate limiting middleware — OWASP API Security: limit abuse and brute force.

Enforces both IP-based and user-based (X-API-Key) limits so that:
- A single IP cannot exhaust capacity (IP-based).
- A single API key cannot exceed its quota from many IPs (user-based).

Returns 429 Too Many Requests with Retry-After when either limit is exceeded.
"""
import time
import logging
from collections import defaultdict
from typing import Callable, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)

# Default thresholds: sensible for a typical API (OWASP recommendation: limit by identity + IP)
DEFAULT_REQUESTS_PER_MINUTE_IP = 100
DEFAULT_REQUESTS_PER_MINUTE_USER = 100
WINDOW_SECONDS = 60


class InMemoryRateLimitStore:
    """
    In-memory store for rate limit counters.
    Keys are (identifier, window_start). Counts reset each window.
    For production at scale, replace with Redis.
    """

    def __init__(self, window_seconds: int = WINDOW_SECONDS):
        self._counts: dict[tuple[str, int], int] = defaultdict(int)
        self._window = window_seconds

    def _window_start(self) -> int:
        return int(time.time() // self._window) * self._window

    def increment(self, key: str) -> int:
        """Increment count for key in current window; return new count."""
        w = self._window_start()
        self._counts[(key, w)] += 1
        return self._counts[(key, w)]

    def get_count(self, key: str) -> int:
        """Return current count for key in current window."""
        w = self._window_start()
        return self._counts.get((key, w), 0)

    def cleanup_old(self):
        """Drop entries from previous windows to avoid unbounded growth."""
        w = self._window_start()
        to_drop = [k for k in self._counts if k[1] < w]
        for k in to_drop:
            del self._counts[k]


# Module-level store so the same instance is used across requests
_store: Optional[InMemoryRateLimitStore] = None


def get_store() -> InMemoryRateLimitStore:
    global _store
    if _store is None:
        _store = InMemoryRateLimitStore()
    return _store


def get_client_ip(request: Request) -> str:
    """Resolve client IP, respecting X-Forwarded-For when behind a proxy (e.g. load balancer)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # First element is the client IP (appendees are proxies)
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "0.0.0.0"


def get_api_key_from_request(request: Request) -> Optional[str]:
    """Extract X-API-Key from request if present; used for user-based rate limiting."""
    return request.headers.get("x-api-key") or request.headers.get("X-API-Key")


def _rate_limit_response(retry_after_seconds: int = 60) -> Response:
    """Return 429 Too Many Requests with JSON body and Retry-After header (OWASP best practice)."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please retry after the time indicated in Retry-After.",
            "retry_after_seconds": retry_after_seconds,
        },
        headers={"Retry-After": str(retry_after_seconds)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Applies IP-based and (when present) user-based rate limits.
    Exempts health check and static assets to avoid blocking monitoring.
    """

    def __init__(
        self,
        app,
        requests_per_minute_ip: int = DEFAULT_REQUESTS_PER_MINUTE_IP,
        requests_per_minute_user: int = DEFAULT_REQUESTS_PER_MINUTE_USER,
        exempt_paths: Optional[list[str]] = None,
    ):
        super().__init__(app)
        self.rpm_ip = requests_per_minute_ip
        self.rpm_user = requests_per_minute_user
        self.exempt = set(exempt_paths or ["/health", "/"])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        # Exempt health and landing so load balancers and users are not blocked
        if any(path == p or path.startswith(p + "/") for p in self.exempt):
            return await call_next(request)

        store = get_store()
        store.cleanup_old()

        client_ip = get_client_ip(request)
        ip_key = f"ip:{client_ip}"
        ip_count = store.increment(ip_key)
        if ip_count > self.rpm_ip:
            logger.warning("Rate limit exceeded for IP %s", client_ip)
            return _rate_limit_response(retry_after_seconds=WINDOW_SECONDS)

        api_key = get_api_key_from_request(request)
        if api_key:
            user_key = f"key:{api_key}"
            user_count = store.increment(user_key)
            if user_count > self.rpm_user:
                logger.warning("Rate limit exceeded for API key (user-based)")
                return _rate_limit_response(retry_after_seconds=WINDOW_SECONDS)

        return await call_next(request)
