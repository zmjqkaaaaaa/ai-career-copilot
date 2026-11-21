from collections import OrderedDict
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import Request

from app.core.errors import ApiError

class AuthRateLimiter:
    def __init__(self, window_seconds: int = 60):
        self.window = window_seconds
        self.entries: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()
        self.lock = Lock()

    def check(self, request: Request, action: str, maximum: int) -> None:
        key = (action, request.client.host if request.client else "unknown")
        with self.lock:
            now = monotonic()
            while self.entries and next(iter(self.entries.values()))[0] <= now:
                self.entries.popitem(last=False)
            existing = self.entries.get(key)
            if existing is None and len(self.entries) >= 4096:
                raise ApiError(429, "RATE_LIMITED", "请求过多，请稍后再试", {"Retry-After": str(self.window)})
            expires, count = existing or (now + self.window, 0)
            if count >= maximum:
                raise ApiError(429, "RATE_LIMITED", "请求过多，请稍后再试", {"Retry-After": str(ceil(expires - now))})
            self.entries[key] = (expires, count + 1)
