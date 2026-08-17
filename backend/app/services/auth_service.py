"""
app/services/auth_service.py
─────────────────────────────
Business logic for user registration and authentication.

Service layer responsibilities:
  - Enforce business rules (no duplicate emails, password verification).
  - Coordinate between the repository (data access) and security (crypto).
  - Return domain objects (`UserOut`) — never raw dicts or DB documents.
  - Routes call services; services call repositories and security utilities.
    Routes themselves contain no business logic.

Security note — identical error messages:
  `authenticate_user` raises `ApiError(401, "Invalid credentials")` for
  BOTH "user not found" and "wrong password".  This is intentional and
  important:

  If the two cases returned different messages (e.g., "User not found" vs.
  "Wrong password"), an attacker could enumerate valid email addresses by
  probing the login endpoint — a user-enumeration attack.  A common
  technique is to try every address in a leaked list and record which ones
  get "wrong password" (confirming the account exists) vs. "not found".

  By using a single, generic message, the API reveals zero information
  about whether a given email is registered.  This is documented in
  OWASP's Authentication Cheat Sheet and is cited in the security section
  of the project report.
"""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import UserCreate, UserOut
from app.repositories import user_repository


async def register_user(payload: UserCreate) -> UserOut:
    """Create a new user account.

    Steps:
      1. Check that the email is not already registered (409 if it is).
      2. Hash the plaintext password with bcrypt.
      3. Build the full user document (with defaults for role, department, etc.).
      4. Persist the document and return a `UserOut` safe for HTTP responses.

    Args:
        payload: Validated registration data from the request body.

    Returns:
        A `UserOut` representing the newly created user.

    Raises:
        ApiError(409): If a user with the same email already exists.
    """
    existing = await user_repository.find_by_email(payload.email)
    if existing:
        raise ApiError(409, "A user with this email address is already registered")

    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "hashed_password": hash_password(payload.password),
        "role": "employee",          # Default role — RBAC enforcement is Module 3
        "department": "",
        "created_at": datetime.now(timezone.utc),
    }

    new_id = await user_repository.create_user(user_doc)
    user_doc["id"] = new_id

    return UserOut(**user_doc)


async def authenticate_user(email: str, password: str) -> tuple[UserOut, str]:
    """Verify credentials and return a user profile with a fresh access token.

    SECURITY: Both "user not found" and "wrong password" raise the same
    `ApiError(401, "Invalid credentials")`.  See module docstring for the
    reasoning.  Do NOT split these branches into separate error messages.

    Args:
        email:    The email address from the login request.
        password: The plaintext password from the login request.

    Returns:
        A tuple of (UserOut, access_token_string).

    Raises:
        ApiError(401): If the user does not exist OR the password is wrong.
                       The message is intentionally identical for both cases.
    """
    _INVALID = ApiError(401, "Invalid credentials")

    user_doc = await user_repository.find_by_email(email)
    if not user_doc:
        raise _INVALID

    if not verify_password(password, user_doc["hashed_password"]):
        raise _INVALID

    user_out = UserOut(**user_doc)
    token = create_access_token({"sub": user_out.id})
    return user_out, token
