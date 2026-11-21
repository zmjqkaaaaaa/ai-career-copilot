from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

password_hasher = PasswordHash.recommended()
dummy_hash = password_hasher.hash("placeholder used for password timing")
cookie_name = "career_access"
issuer = "career-copilot"

def issue_token(user_id: int, audience: str, settings: Settings) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "iss": issuer, "aud": audience, "iat": now,
         "exp": now + timedelta(minutes=settings.jwt_minutes)},
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )

def token_user_id(token: str, audience: str, settings: Settings) -> int:
    payload = jwt.decode(
        token, settings.jwt_secret.get_secret_value(), algorithms=["HS256"],
        audience=audience, issuer=issuer, options={"require": ["sub", "iat", "exp"]},
    )
    subject = payload["sub"]
    if not subject.isascii() or not subject.isdecimal() or len(subject) > 10 or not 0 < int(subject) <= 2147483647:
        raise jwt.InvalidTokenError("Invalid user ID")
    return int(subject)
