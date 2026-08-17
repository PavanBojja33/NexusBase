"""
app/routes/auth.py
───────────────────
HTTP routes for user authentication: register, login, and profile retrieval.

Design conventions followed here:
  - `response_model` is set on every route.  FastAPI serialises the response
    through the schema, which strips any field not in `UserOut` (including
    `hashed_password`) before it hits the wire.  This is a safety net on top
    of the service layer's deliberate omission.
  - Routes contain zero business logic — they delegate entirely to
    `auth_service` and return the result.  This keeps routes thin and
    testable in isolation.
  - Summaries and descriptions are written for the project report audience:
    they appear verbatim in the Swagger UI at /docs.
  - HTTP status codes follow REST conventions:
      201 Created  → new resource created (register)
      200 OK       → read or action with returned data (login, me)
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr, Field

from app.dependencies.auth import get_current_user
from app.models.user import UserCreate, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ── Inline request/response schemas ───────────────────────────────────────────

class LoginRequest(BaseModel):
    """Credentials accepted by POST /auth/login.

    Deliberately separate from `UserCreate` — login does not require `name`,
    and keeping schemas distinct prevents accidental field coupling between
    registration and authentication logic.
    """

    email: Annotated[EmailStr, Field(examples=["alice@example.com"])]
    password: Annotated[str, Field(min_length=1, examples=["supersecret"])]


class TokenResponse(BaseModel):
    """Response envelope returned by POST /auth/login."""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Register ───────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Creates a new user account with the **employee** role. "
        "Returns the created user profile — password hash is never included "
        "in the response.\n\n"
        "**Duplicate email** → 409 Conflict.\n\n"
        "---\n"
        # ⚠️  MODULE 3 TODO — RBAC lock-down ⚠️
        # This endpoint is intentionally OPEN in Module 2.
        # In Module 3 (RBAC), restrict this route so that only a
        # `super_admin` JWT can call it.  For now, anyone can self-register,
        # which is acceptable for the initial development phase but MUST be
        # changed before the system is considered production-ready.
        "**⚠ Note (Module 3):** This endpoint will be restricted to "
        "`super_admin` role once RBAC is implemented."
    ),
)
async def register(payload: UserCreate) -> UserOut:
    """Register a new user and return their profile.

    Args:
        payload: Registration form data — name, email, password.

    Returns:
        201 Created with the new user's `UserOut` profile.

    Raises:
        422 Unprocessable Entity: If required fields are missing or email is invalid.
        409 Conflict: If the email address is already registered.
    """
    return await auth_service.register_user(payload)


# ── Login ──────────────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in and obtain a JWT",
    description=(
        "Authenticates a user by email and password. "
        "On success, returns a signed JWT access token and the user profile.\n\n"
        "**Wrong email or wrong password** → both return 401 with the same "
        "generic `'Invalid credentials'` message.  This prevents user-enumeration "
        "attacks (an attacker cannot tell whether the email exists)."
    ),
)
async def login(payload: LoginRequest) -> TokenResponse:
    """Authenticate and return a JWT access token.

    Args:
        payload: Login credentials — email and password.

    Returns:
        200 OK with `{access_token, token_type, user}`.

    Raises:
        401 Unauthorized: If the email is not registered or the password is wrong.
                          Both cases return the same error message intentionally.
    """
    user_out, token = await auth_service.authenticate_user(
        payload.email, payload.password
    )
    return TokenResponse(access_token=token, token_type="bearer", user=user_out)


# ── Me ─────────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserOut,
    summary="Get the current authenticated user",
    description=(
        "Returns the profile of the user identified by the Bearer token in "
        "the `Authorization` header.\n\n"
        "If the token is missing, malformed, expired, or the corresponding "
        "user no longer exists in the database, the endpoint returns **401**."
    ),
)
async def me(current_user: UserOut = Depends(get_current_user)) -> UserOut:
    """Return the profile of the currently authenticated user.

    Args:
        current_user: Injected by `get_current_user` — the validated user
                      loaded from the database.

    Returns:
        200 OK with the user's `UserOut` profile (no password field).

    Raises:
        401 Unauthorized: If the Bearer token is missing, invalid, or expired.
    """
    return current_user
