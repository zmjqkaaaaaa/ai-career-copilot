from collections import OrderedDict
import hmac
from math import ceil
from threading import Lock
from time import monotonic

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.errors import ApiError
from app.models.operations import AuthRateWindow


def too_many(retry_after):
    raise ApiError(429, "RATE_LIMITED", "请求过多，请稍后再试", {"Retry-After": str(retry_after)})

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
                too_many(self.window)
            expires, count = existing or (now + self.window, 0)
            if count >= maximum:
                too_many(ceil(expires - now))
            self.entries[key] = (expires, count + 1)


class SharedAuthRateLimiter:
    def __init__(self, factory, secret: str, window_seconds: int = 60):
        self.factory = factory
        self.secret = secret.encode()
        self.window = window_seconds

    def check(self, request: Request, action: str, maximum: int) -> None:
        host = request.client.host if request.client else "unknown"
        key = hmac.digest(self.secret, f"auth-rate:{action}:{host}".encode(), "sha256").hex()
        try:
            with self.factory.begin() as db:
                now = int(db.scalar(select(func.unix_timestamp())))
                start = now - now % self.window
                expires = start + self.window
                statement = insert(AuthRateWindow).values(fingerprint=key, window_start=start, expires_at=expires, hits=1)
                db.execute(statement.on_duplicate_key_update(hits=func.least(AuthRateWindow.hits + 1, maximum + 1)))
                hits = db.scalar(select(AuthRateWindow.hits).where(
                    AuthRateWindow.fingerprint == key, AuthRateWindow.window_start == start))
        except SQLAlchemyError:
            raise ApiError(503, "AUTH_RATE_UNAVAILABLE", "暂时无法进行身份验证，请稍后再试") from None
        if hits > maximum:
            too_many(expires - now)


def clear_expired_windows(factory):
    with factory.begin() as db:
        return db.execute(delete(AuthRateWindow).where(AuthRateWindow.expires_at <= func.unix_timestamp())
                          .with_dialect_options(mysql_limit=500)).rowcount
