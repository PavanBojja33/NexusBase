"""
app/models/user.py
──────────────────
Pydantic schemas for the User domain.

Three distinct shapes are defined — each with a clear, different purpose:

  UserCreate   →  Input validation for the registration endpoint.
                  Accepts the raw password; no hashing happens here.

  UserInDB     →  Internal representation of a MongoDB document.
                  Contains `hashed_password` and maps MongoDB's `_id` (ObjectId)
                  to a string field called `id`.  This shape NEVER leaves the
                  service/repository layer — it is only used internally.

  UserOut      →  The public, safe representation returned by every route.
                  Contains NO password or hash field.  FastAPI's `response_model`
                  enforces this by serialising responses through this schema,
                  so even if a bug accidentally put a hash into the dict, it
                  would be stripped before hitting the wire.

Role handling:
  - Roles are stored as strings; a `Literal` type enforces the allowed set.
  - Full RBAC enforcement (route guards, permission checks) is Module 3.
    For now, `role` is stored but not checked beyond registration defaults.
"""

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, EmailStr, Field

# The three allowed roles.  New roles must be added here AND in the RBAC
# module (Module 3) before they become meaningful for access control.
UserRole = Literal["super_admin", "space_admin", "employee"]


# ── Input schema ───────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Payload accepted by POST /api/v1/auth/register.

    Pydantic validates `email` format automatically via `EmailStr`.
    The `password` field accepts any non-empty string; strength rules can
    be added here in a later iteration without touching the route or service.
    """

    name: Annotated[str, Field(min_length=1, max_length=120, examples=["Alice Smith"])]
    email: Annotated[EmailStr, Field(examples=["alice@example.com"])]
    password: Annotated[str, Field(min_length=6, examples=["supersecret"])]


# ── Internal (DB) schema ───────────────────────────────────────────────────────

class UserInDB(BaseModel):
    """Internal representation of a user document stored in MongoDB.

    The `id` field is mapped from MongoDB's `_id` field (an ObjectId stored
    as a string after conversion).  This model is ONLY used within the
    repository and service layers — it is never serialised into an HTTP
    response.

    `model_config` enables attribute access (`user.id`) in addition to dict
    access, and allows ORM-style construction from a dict.
    """

    id: str
    name: str
    email: EmailStr
    hashed_password: str
    role: UserRole = "employee"
    department: Optional[str] = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


# ── Public output schema ───────────────────────────────────────────────────────

class UserOut(BaseModel):
    """Public representation of a user, safe to return in any HTTP response.

    Intentional omissions:
      - `hashed_password` — never exposed
      - Any future internal metadata fields

    This is the `response_model` for every auth route and for the
    `get_current_user` dependency.  FastAPI serialises all responses through
    this schema, guaranteeing that the password hash can never leak even if
    an upstream bug populates an unexpected field.
    """

    id: str
    name: str
    email: EmailStr
    role: UserRole
    department: Optional[str] = ""
    created_at: datetime

    model_config = {"from_attributes": True}
