"""JWT token creation and verification, password hashing utilities.

Secrets are read from environment variables (loaded from .env via python-dotenv):
    AUTH_USERNAME       — the single-user username
    AUTH_PASSWORD_HASH  — bcrypt hash of the password
    AUTH_SECRET_KEY     — HS256 signing key (auto-generated on first run if missing)

Non-secret config (algorithm, token expiry) comes from config.json ``auth`` section.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import jwt
from dotenv import load_dotenv, set_key

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

# Ensure .env is loaded (python-dotenv)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)


def _auth_cfg() -> dict:
    """Non-secret auth config from config.json."""
    return load_config().get("auth", {})


# ── Password helpers ────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Check *plain* against a bcrypt *hashed* value."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ── Secret retrieval from environment ───────────────────────────────────────

def _secret_key() -> str:
    """Get the JWT signing key from AUTH_SECRET_KEY env var.

    If not set, generates one and persists it to .env so it survives restarts.
    """
    key = os.environ.get("AUTH_SECRET_KEY", "")
    if not key:
        key = secrets.token_urlsafe(32)
        logger.info("No AUTH_SECRET_KEY found — generated and saved to .env")
        if _env_path.exists():
            set_key(str(_env_path), "AUTH_SECRET_KEY", key)
        os.environ["AUTH_SECRET_KEY"] = key
    return key


def _get_username() -> str:
    return os.environ.get("AUTH_USERNAME", "")


def _get_password_hash() -> str:
    return os.environ.get("AUTH_PASSWORD_HASH", "")


def _algorithm() -> str:
    return _auth_cfg().get("algorithm", "HS256")


# ── Token helpers ───────────────────────────────────────────────────────────

def create_access_token(subject: str) -> str:
    """Create a short-lived access token."""
    expires_minutes = _auth_cfg().get("access_token_expires_minutes", 15)
    exp = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"sub": subject, "exp": exp, "type": "access"}
    return jwt.encode(payload, _secret_key(), algorithm=_algorithm())


def create_refresh_token(subject: str) -> str:
    """Create a long-lived refresh token."""
    expires_days = _auth_cfg().get("refresh_token_expires_days", 7)
    exp = datetime.now(timezone.utc) + timedelta(days=expires_days)
    payload = {"sub": subject, "exp": exp, "type": "refresh"}
    return jwt.encode(payload, _secret_key(), algorithm=_algorithm())


def verify_token(token: str, expected_type: str = "access") -> str:
    """Decode and validate a JWT. Returns the subject (username).

    Raises ``jwt.InvalidTokenError`` (or subclass) on any failure.
    """
    payload = jwt.decode(token, _secret_key(), algorithms=[_algorithm()])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Expected token type '{expected_type}', got '{payload.get('type')}'"
        )
    sub: str | None = payload.get("sub")
    if not sub:
        raise jwt.InvalidTokenError("Token has no subject")
    return sub


# ── Credential check ───────────────────────────────────────────────────────

def authenticate_user(username: str, password: str) -> bool:
    """Return True if *username* and *password* match the configured credentials."""
    expected_user = _get_username()
    if not expected_user or username != expected_user:
        return False
    stored_hash = _get_password_hash()
    if not stored_hash:
        return False
    return verify_password(password, stored_hash)
