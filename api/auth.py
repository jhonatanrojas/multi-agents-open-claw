"""Authentication router - handles login/logout/session endpoints."""
import os
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    message: str
    expires_in: int


@router.post("/login", response_model=LoginResponse)
async def login(request: Request, payload: LoginRequest, response: Response):
    """
    Authenticate with username/password and set a session cookie.

    Credentials are read from environment variables:
    - DASHBOARD_ADMIN_USER (default: admin)
    - DASHBOARD_ADMIN_PASSWORD (default: admin123)

    The API key from DASHBOARD_API_KEY is still used for backend validation.
    """
    from dashboard_api import _API_KEY, _create_session

    ADMIN_USER = os.environ.get("DASHBOARD_ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("DASHBOARD_ADMIN_PASSWORD", "admin123")

    if not _API_KEY:
        return LoginResponse(ok=True, message="Auth disabled", expires_in=0)

    if payload.username != ADMIN_USER or payload.password != ADMIN_PASSWORD:
        response.status_code = 401
        return LoginResponse(ok=False, message="Credenciales inválidas", expires_in=0)

    session_token = _create_session()

    # Set HttpOnly cookie
    is_https = request.headers.get("X-Forwarded-Proto") == "https" or request.url.scheme == "https"
    response.set_cookie(
        key="dashboard_session",
        value=session_token,
        httponly=True,
        secure=is_https,
        samesite="lax" if not is_https else "strict",
        max_age=86400,  # 24 hours
    )
    return LoginResponse(ok=True, message="Sesión iniciada", expires_in=86400)


@router.post("/logout")
async def logout(response: Response):
    """Clear the session cookie."""
    response.delete_cookie(key="dashboard_session")
    return {"ok": True}


@router.get("/session")
async def get_session(request: Request):
    """Check if the current session is valid."""
    from dashboard_api import _validate_session, _API_KEY

    if not _API_KEY:
        return {"authenticated": True, "reason": "auth_disabled"}

    session_token = request.cookies.get("dashboard_session")
    is_valid = _validate_session(session_token)
    return {"authenticated": is_valid}
