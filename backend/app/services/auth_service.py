from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import dummy_hash, password_hasher
from app.models.user import User
from app.schemas.auth import RegisterRequest

def register(db: Session, data: RegisterRequest) -> User:
    email = data.email.casefold()
    if len(email) > 254:
        raise ApiError(422, "VALIDATION_ERROR", "邮箱长度不能超过 254 个字符")
    user = User(email=email, username=data.username, password_hash=password_hasher.hash(data.password))
    db.add(user)
    try:
        db.flush()
        db.refresh(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if exc.orig.args[0] == 1062:
            raise ApiError(409, "EMAIL_EXISTS", "该邮箱已注册") from None
        raise
    return user

def authenticate(db: Session, email: str, password: str) -> User:
    if len(email) > 254 or len(password) > 128:
        raise ApiError(401, "INVALID_CREDENTIALS", "邮箱或密码错误", {"WWW-Authenticate": "Bearer"})
    user = db.scalar(select(User).where(User.email == email.strip().casefold()))
    if not password_hasher.verify(password, user.password_hash if user else dummy_hash) or not user or not user.is_active:
        raise ApiError(401, "INVALID_CREDENTIALS", "邮箱或密码错误", {"WWW-Authenticate": "Bearer"})
    return user
