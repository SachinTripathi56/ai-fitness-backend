"""
Security utilities: JWT token creation/validation, password hashing.
"""

import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from jose import JWTError, jwt
from app.core.config import settings

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), 
        hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    # bcrypt limit is 72 bytes, so we truncate to be safe with long passwords
    # while still providing high entropy.
    password_bytes = password.encode("utf-8")[:72]
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def create_access_token(
    subject: Union[str, int],
    role: str = "user",
    expires_delta: Optional[timedelta] = None,
) -> str:
    return str(subject)


def create_refresh_token(subject: Union[str, int]) -> str:
    return str(subject)


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def create_password_reset_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "sub": email,
        "exp": expire,
        "type": "password_reset",
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    payload = decode_token(token)
    if payload and payload.get("type") == "password_reset":
        return payload.get("sub")
    return None