"""
app/dependencies/auth.py
─────────────────────────
FastAPI dependency for authenticating the current request.

`get_current_user` is the single reusable guard imported by every protected
route across ALL future modules.  Its design is intentionally minimal and
dependency-injection-friendly:

  - It extracts the token from the `Authorization: Bearer <token>` header.
  - It decodes the token via `security.decode_access_token`, which raises
    `ApiError(401)` if the token is invalid or expired.
  - It loads the live user document from MongoDB via the repository.
    This extra DB round-trip is important: if a user is deleted or suspended
    after their token was issued, the middleware catches it immediately rather
    than serving stale data from the JWT payload alone.
  - It returns `UserOut`, the public schema — not the raw dict.  This means
    downstream routes receive a properly typed, password-free object.

Future modules (RBAC, Knowledge Spaces) will inject additional dependencies
ON TOP of `get_current_user`, e.g.:
    `Depends(require_role("space_admin"))` which itself calls `get_current_user`.
Never modify this function to add role checks — keep it pure authentication.
"""

from fastapi import Header
from typing import Annotated

from app.core.exceptions import ApiError
from app.core.security import decode_access_token
from app.models.user import UserOut
from app.repositories import user_repository


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> UserOut:
    """Validate the Bearer token and return the authenticated user.

    FastAPI automatically injects this function via `Depends(get_current_user)`
    in any route that declares it as a dependency.

    Args:
        authorization: The raw value of the `Authorization` HTTP header,
                       automatically injected by FastAPI from the request.
                       Expected format: `Bearer <jwt_token>`.

    Returns:
        The authenticated user as a `UserOut` (no password field).

    Raises:
        ApiError(401): If the header is missing, the scheme is not "Bearer",
                       the token is invalid/expired, or the user no longer
                       exists in the database.
    """
    if not authorization:
        raise ApiError(401, "Authorization header is missing")

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise ApiError(401, "Authorization header must be 'Bearer <token>'")

    token = parts[1]
    payload = decode_access_token(token)  # raises ApiError(401) on failure

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise ApiError(401, "Token payload is malformed — missing 'sub' claim")

    user_doc = await user_repository.find_by_id(user_id)
    if not user_doc:
        raise ApiError(401, "The user associated with this token no longer exists")

    return UserOut(**user_doc)
