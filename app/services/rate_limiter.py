import time
from collections import defaultdict
from threading import Lock
from typing import Dict, List
from fastapi import Request, HTTPException, status
from app.config import get_settings

settings = get_settings()


def get_client_ip(request: Request) -> str:
    """Extract client IP, taking X-Forwarded-For into account for Render/proxies."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # First IP in comma-separated list is the original client IP
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class InMemoryRateLimiter:
    """Thread-safe in-memory sliding window rate limiter."""
    def __init__(self):
        self._records: Dict[str, List[float]] = defaultdict(list)
        self._lock = Lock()

    def check_rate_limit(self, key: str, max_requests: int, window_seconds: int = 3600) -> None:
        """
        Check if the request limit for the given key is exceeded.
        Raises HTTPException(429) if exceeded.
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Filter out timestamps older than the sliding window
            timestamps = [t for t in self._records[key] if t > cutoff]

            if len(timestamps) >= max_requests:
                earliest = timestamps[0]
                retry_after = max(1, int(earliest + window_seconds - now))
                self._records[key] = timestamps
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: maximum {max_requests} requests per hour allowed for your IP.",
                    headers={"Retry-After": str(retry_after)}
                )

            timestamps.append(now)
            self._records[key] = timestamps

    def reset(self) -> None:
        """Clear all rate limit records (used in test fixtures)."""
        with self._lock:
            self._records.clear()


limiter = InMemoryRateLimiter()


def rate_limit_repos(request: Request):
    """Rate limit dependency for POST /repos."""
    client_ip = get_client_ip(request)
    limiter.check_rate_limit(
        key=f"repos:{client_ip}",
        max_requests=settings.RATE_LIMIT_REPOS_PER_HOUR,
        window_seconds=3600
    )


def rate_limit_ask(request: Request):
    """Rate limit dependency for POST /repos/{id}/ask."""
    client_ip = get_client_ip(request)
    limiter.check_rate_limit(
        key=f"ask:{client_ip}",
        max_requests=settings.RATE_LIMIT_ASK_PER_HOUR,
        window_seconds=3600
    )
