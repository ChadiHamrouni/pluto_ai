"""Authentication endpoints: login, refresh, verify."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from helpers.core.logger import get_logger
from helpers.routes.auth import authenticate_user, refresh_access_token, validate_access_token

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenVerifyRequest(BaseModel):
    token: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with username/password, receive access + refresh tokens."""
    result = authenticate_user(body.username, body.password)
    if result is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        return refresh_access_token(body.refresh_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token expired — login again")
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid refresh token: {exc}")


@router.post("/verify")
async def verify(body: TokenVerifyRequest):
    """Check whether an access token is still valid."""
    try:
        payload = validate_access_token(body.token)
        return {"valid": True, "subject": payload["sub"], "expires": payload["exp"]}
    except jwt.ExpiredSignatureError:
        return {"valid": False, "reason": "expired"}
    except jwt.InvalidTokenError as exc:
        return {"valid": False, "reason": str(exc)}
