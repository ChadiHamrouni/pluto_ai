"""JWT authentication: token creation, validation, and refresh."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _auth_cfg() -> dict:
    return load_config().get("auth", {})


def _secret_key() -> str:
    key = _auth_cfg().get("secret_key", "")
    if not key:
        raise ValueError("auth.secret_key is not set in config.json")
    return key


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

def create_access_token(subject: str, extra: dict | None = None) -> str:
    """Create a short-lived access token."""
    cfg = _auth_cfg()
    expires_minutes = cfg.get("access_token_expires_minutes", 15)

    payload = {
        "sub": subject,
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
        "jti": secrets.token_hex(16),
    }
    if extra:
        payload.update(extra)

    token = jwt.encode(payload, _secret_key(), algorithm="HS256")
    logger.debug("Created access token for %s (expires in %dm)", subject, expires_minutes)
    return token


def create_refresh_token(subject: str) -> str:
    """Create a longer-lived refresh token."""
    cfg = _auth_cfg()
    expires_days = cfg.get("refresh_token_expires_days", 7)

    payload = {
        "sub": subject,
        "type": "refresh",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(days=expires_days),
        "jti": secrets.token_hex(16),
    }

    token = jwt.encode(payload, _secret_key(), algorithm="HS256")
    logger.debug("Created refresh token for %s (expires in %dd)", subject, expires_days)
    return token


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------

def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Raises jwt.ExpiredSignatureError if expired.
    Raises jwt.InvalidTokenError for any other issue.
    """
    return jwt.decode(token, _secret_key(), algorithms=["HS256"])


def validate_access_token(token: str) -> dict:
    """Decode token and verify it's an access token."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Not an access token")
    return payload


def validate_refresh_token(token: str) -> dict:
    """Decode token and verify it's a refresh token."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise jwt.InvalidTokenError("Not a refresh token")
    return payload


# ---------------------------------------------------------------------------
# Refresh flow
# ---------------------------------------------------------------------------

def refresh_access_token(refresh_token: str) -> dict:
    """
    Given a valid refresh token, return a new access + refresh token pair.

    Returns {"access_token": ..., "refresh_token": ..., "token_type": "bearer"}.
    """
    payload = validate_refresh_token(refresh_token)
    subject = payload["sub"]

    return {
        "access_token": create_access_token(subject),
        "refresh_token": create_refresh_token(subject),
        "token_type": "bearer",
    }


# ---------------------------------------------------------------------------
# User authentication (simple single-user for now)
# ---------------------------------------------------------------------------

def authenticate_user(username: str, password: str) -> dict | None:
    """
    Validate credentials against config.

    Returns {"access_token": ..., "refresh_token": ..., "token_type": "bearer"}
    or None if invalid.
    """
    cfg = _auth_cfg()
    stored_username = cfg.get("username", "")
    stored_hash = cfg.get("password_hash", "")

    if not stored_username or not stored_hash:
        logger.error("Auth credentials not configured in config.json")
        return None

    if not hmac.compare_digest(username, stored_username):
        return None

    if not verify_password(password, stored_hash):
        return None

    logger.info("User '%s' authenticated successfully", username)
    return {
        "access_token": create_access_token(username),
        "refresh_token": create_refresh_token(username),
        "token_type": "bearer",
    }
