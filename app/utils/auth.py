"""This file contains the authentication utilities for the application."""

import re
from datetime import (
    UTC,
    datetime,
    timedelta,
)
from typing import Optional

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import settings
from app.core.logging import logger
from app.schemas.auth import Token
from app.utils.sanitization import sanitize_string


def create_access_token(
    user_id: str, session_id: Optional[str] = None, expires_delta: Optional[timedelta] = None
) -> Token:
    """Create a new access token.

    Args:
        user_id: The user ID (stored in the JWT ``sub`` claim).
        session_id: Optional session ID (stored in the ``sid`` claim).
        expires_delta: Optional expiration time delta.

    Returns:
        Token: The generated access token.
    """
    now = datetime.now(UTC)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(days=settings.JWT_ACCESS_TOKEN_EXPIRE_DAYS)

    jti_slug = session_id if session_id else user_id
    to_encode: dict = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
        "jti": sanitize_string(f"{jti_slug}-{now.timestamp()}"),
    }
    if session_id:
        to_encode["sid"] = session_id

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

    logger.info("token_created", user_id=user_id, session_id=session_id, expires_at=expire.isoformat())

    return Token(access_token=encoded_jwt, expires_at=expire)


def verify_token(token: str) -> Optional[dict]:
    """Verify a JWT token and return the decoded payload.

    Args:
        token: The JWT token to verify.

    Returns:
        Optional[dict]: The decoded JWT payload if valid, ``None`` otherwise.
        The payload contains at least ``sub`` (user_id) and optionally ``sid`` (session_id).

    Raises:
        ValueError: If the token format is invalid
    """
    if not token or not isinstance(token, str):
        logger.warning("token_invalid_format")
        raise ValueError("Token must be a non-empty string")

    # Basic format validation before attempting decode
    # JWT tokens consist of 3 base64url-encoded segments separated by dots
    if not re.match(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$", token):
        logger.warning("token_suspicious_format")
        raise ValueError("Token format is invalid - expected JWT format")

    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            logger.warning("token_missing_sub")
            return None

        logger.info("token_verified", user_id=user_id, session_id=payload.get("sid"))
        return payload

    except InvalidTokenError as e:
        logger.error("token_verification_failed", error=str(e))
        return None
