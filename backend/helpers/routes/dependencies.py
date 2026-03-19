"""FastAPI dependencies for auth-protected routes."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from helpers.routes.auth import validate_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    token: str | None = Query(default=None),
) -> dict:
    """Validate a JWT access token from either source:

    - ``Authorization: Bearer <token>`` header  (standard REST / fetch calls)
    - ``?token=<token>`` query parameter         (SSE via EventSource, which
      cannot set custom headers in browsers)

    Raises 401 if no token is provided or the token is invalid/expired.
    This is the single auth dependency used by every protected endpoint.
    """
    raw_token: str | None = None

    if creds and creds.credentials:
        raw_token = creds.credentials
    elif token:
        raw_token = token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — provide a Bearer token or ?token= query param",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return validate_access_token(raw_token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired — use /auth/refresh",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )
