from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

import jwt
from jwt.exceptions import PyJWTError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
TOKEN_REFRESH_HEADER = "X-Access-Token"
TOKEN_VERSION_CLAIM = "tv"


class TokenPayload(NamedTuple):
    subject: str
    token_version: int


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(
    subject: str | int,
    token_version: int = 0,
    expires_delta: timedelta | None = None,
) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        TOKEN_VERSION_CLAIM: token_version,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenPayload | None:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        subject = payload.get("sub")
        if subject is None:
            return None
        token_version = payload.get(TOKEN_VERSION_CLAIM, 0)
        return TokenPayload(subject=str(subject), token_version=int(token_version))
    except PyJWTError:
        return None

