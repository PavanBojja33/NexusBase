"""
app/models/knowledge_space.py
──────────────────────────────
Pydantic schemas for Knowledge Space management and access grants.

Knowledge Spaces act as logical security perimeters in NexusBase:
every document uploaded, every vector index built, and every retrieval query
executed is scoped to a specific Knowledge Space.

Schemas:
  KnowledgeSpaceCreate  → Input payload for creating a new Knowledge Space.
  KnowledgeSpaceOut     → Public response schema representing a Knowledge Space.
  GrantAccessRequest    → Payload for assigning access rights to an employee or space_admin.
"""

from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, Field
from pydantic.fields import FieldInfo

from app.models.user import UserInDB, UserOut

# Dynamically ensure UserOut and UserInDB declare knowledge_spaces
# so attribute access `user.knowledge_spaces` succeeds cleanly across all modules
for _user_model in (UserOut, UserInDB):
    if "knowledge_spaces" not in _user_model.model_fields:
        _user_model.model_fields["knowledge_spaces"] = FieldInfo(
            annotation=list[str], default_factory=list
        )
        _user_model.model_rebuild(force=True)


class KnowledgeSpaceCreate(BaseModel):
    """Payload for POST /api/v1/spaces (Knowledge Space creation)."""

    name: Annotated[
        str,
        Field(min_length=1, max_length=120, examples=["Engineering Documentation"]),
    ]
    description: Annotated[
        str,
        Field(default="", max_length=500, examples=["Technical specs, RFCs, and API guidelines"]),
    ]
    department: Annotated[
        str,
        Field(default="", max_length=100, examples=["Engineering"]),
    ]


class KnowledgeSpaceOut(BaseModel):
    """Public representation of a Knowledge Space returned by the API."""

    id: str
    name: str
    description: str = ""
    department: str = ""
    created_by: str
    space_admins: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime

    model_config = {"from_attributes": True}


class GrantAccessRequest(BaseModel):
    """Payload for POST /api/v1/spaces/grant-access."""

    user_id: Annotated[str, Field(min_length=1, examples=["6abb75877fb8357ebd8e28a6"])]
    space_id: Annotated[str, Field(min_length=1, examples=["6abb793d082d9a33b805d44d"])]
