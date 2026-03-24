"""Authentication endpoints: login, refresh, verify."""

from __future__ import annotations

import jwt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from helpers.core.logger import get_logger
from helpers.routes.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    verify_token,
)

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


class VerifyRequest(BaseModel):
    token: str


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate with username + password and receive JWT tokens."""
    if not authenticate_user(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    logger.info("User '%s' logged in", body.username)
    return TokenResponse(
        access_token=create_access_token(body.username),
        refresh_token=create_refresh_token(body.username),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    """Exchange a valid refresh token for a new access + refresh token pair."""
    try:
        username = verify_token(body.refresh_token, expected_type="refresh")
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )
    return TokenResponse(
        access_token=create_access_token(username),
        refresh_token=create_refresh_token(username),
    )


@router.post("/verify")
async def verify(body: VerifyRequest):
    """Check whether an access token is still valid."""
    try:
        username = verify_token(body.token, expected_type="access")
        return {"valid": True, "username": username}
    except jwt.InvalidTokenError:
        return {"valid": False, "username": None}
