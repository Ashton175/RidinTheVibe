from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return password_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Check a plaintext password against its bcrypt hash."""
    return password_context.verify(password, hashed_password)


def create_access_token(
    *,
    user_id: int,
    role: str,
    organization_id: int,
    site_id: int | None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT with the user's identity and authorization scope."""
    expires_at = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    return jwt.encode(
        {
            "sub": str(user_id),
            "user_id": user_id,
            "role": role,
            "organization_id": organization_id,
            "site_id": site_id,
            "exp": expires_at,
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT, raising InvalidTokenError if invalid or expired."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


__all__ = [
    "InvalidTokenError",
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
