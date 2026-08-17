"""
app/core/security.py
─────────────────────
Password hashing and JWT utilities.

All cryptographic operations for the auth module live here.  Services call
these functions; they never touch bcrypt or python-jose directly.  This
makes it trivial to swap the algorithm in one place without touching any
route or service.

Why bcrypt directly (not passlib):
  passlib 1.7.4 (the latest release as of this writing) has a known
  incompatibility with bcrypt >= 4.0 because it inspects `bcrypt.__about__`
  which no longer exists in the newer library.  Since passlib is effectively
  unmaintained, we call the `bcrypt` library directly.  The API is minimal
  and stable: `hashpw`, `checkpw`, and `gensalt`.

JWT design:
  - The token payload carries only `sub` (the user's string id).  Keeping
    the payload minimal limits PII exposure if a token is decoded client-side
    and reduces the surface area for token-stuffing attacks.
  - `exp` is added automatically by python-jose based on JWT_EXPIRES_IN.
  - The algorithm is HS256 (HMAC-SHA256) — symmetric, sufficient for a
    single-service system.  If the architecture later expands to multiple
    services, migrate to RS256 (asymmetric) at that point.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import ApiError

# JWT signing algorithm
_ALGORITHM = "HS256"


# ── Password utilities ─────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.

    The resulting string is safe to store directly in the database.
    bcrypt salts are embedded in the hash string itself (the `$2b$...` prefix),
    so no separate salt column is needed.

    Args:
        plain: The raw password supplied by the user at registration.

    Returns:
        A bcrypt-hashed string (format: `$2b$<cost>$<salt><hash>`).
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(plain.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password.

    Uses a constant-time comparison internally (via bcrypt), preventing
    timing attacks that would otherwise reveal whether a hash prefix matches.

    Args:
        plain:  The raw password supplied during a login attempt.
        hashed: The bcrypt hash retrieved from the database.

    Returns:
        True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT utilities ──────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    """Encode *data* into a signed JWT and return the token string.

    A copy of *data* is made so the caller's dict is not mutated.  An `exp`
    claim is added based on `settings.JWT_EXPIRES_IN` (minutes).

    Args:
        data: Payload to encode — typically `{"sub": user_id}`.

    Returns:
        A compact, URL-safe JWT string.
    """
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRES_IN)
    payload["exp"] = expire
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT, returning its payload as a dict.

    Raises `ApiError(401)` for ANY failure — expired token, bad signature,
    malformed string.  Using a single error type prevents an attacker from
    distinguishing between "token expired" and "token forged".

    Args:
        token: The raw JWT string from the Authorization header.

    Returns:
        The decoded payload dict (e.g., `{"sub": "<user_id>", "exp": ...}`).

    Raises:
        ApiError(401): If the token is invalid, expired, or tampered with.
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])
        return payload
    except JWTError:
        raise ApiError(401, "Token is invalid or has expired")
