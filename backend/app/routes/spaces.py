"""
app/routes/spaces.py
────────────────────
HTTP routes for Knowledge Space management and authorization grants.

Design conventions:
  - `POST /spaces` is locked down to `super_admin` only: standard employees or
    space admins cannot provision arbitrary organizational knowledge spaces.
  - `GET /spaces` is open to any authenticated user (`get_current_user`), but
    the returned spaces are strictly filtered at the service layer by the caller's role.
  - `POST /spaces/grant-access` allows a `super_admin` to delegate administration
    or grant employee read access.
"""

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import get_current_user
from app.dependencies.rbac import require_role
from app.models.knowledge_space import (
    GrantAccessRequest,
    KnowledgeSpaceCreate,
    KnowledgeSpaceOut,
)
from app.models.user import UserOut
from app.services import space_service

router = APIRouter(prefix="/spaces", tags=["Knowledge Spaces"])


@router.post(
    "",
    response_model=KnowledgeSpaceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Knowledge Space",
    description=(
        "Provisions a new Knowledge Space container. Restricted to **super_admin**.\n\n"
        "All future document uploads and RAG indices are scoped to a Knowledge Space."
    ),
)
async def create_space(
    payload: KnowledgeSpaceCreate,
    current_admin: UserOut = Depends(require_role("super_admin")),
) -> KnowledgeSpaceOut:
    """Create a new Knowledge Space.

    Args:
        payload: Name, description, and department of the space.
        current_admin: Injected super_admin user profile.

    Returns:
        201 Created with the created KnowledgeSpaceOut representation.
    """
    return await space_service.create_space(payload, current_admin)


@router.get(
    "",
    response_model=list[KnowledgeSpaceOut],
    status_code=status.HTTP_200_OK,
    summary="List visible Knowledge Spaces",
    description=(
        "Returns Knowledge Spaces visible to the authenticated caller based on role:\n\n"
        "- **super_admin**: Sees all active Knowledge Spaces across the enterprise.\n"
        "- **space_admin**: Sees spaces where they are listed as a space administrator.\n"
        "- **employee**: Sees only spaces they have been explicitly granted access to."
    ),
)
async def list_spaces(
    current_user: UserOut = Depends(get_current_user),
) -> list[KnowledgeSpaceOut]:
    """Retrieve all Knowledge Spaces visible to the current authenticated user.

    Args:
        current_user: Injected user profile from JWT Bearer token.

    Returns:
        List of visible KnowledgeSpaceOut objects.
    """
    return await space_service.list_visible_spaces(current_user)


@router.post(
    "/grant-access",
    status_code=status.HTTP_200_OK,
    summary="Grant Knowledge Space access to a user",
    description=(
        "Grants access to a target user for a specific Knowledge Space. "
        "Restricted to **super_admin**.\n\n"
        "- If target user is `space_admin` -> designated in `space.space_admins`.\n"
        "- If target user is `employee` -> space ID appended to `user.knowledge_spaces`."
    ),
)
async def grant_access(
    payload: GrantAccessRequest,
    _: UserOut = Depends(require_role("super_admin")),
) -> dict:
    """Delegate space administration or grant employee space access.

    Args:
        payload: user_id and space_id pair.

    Returns:
        Confirmation message detailing the access grant.
    """
    return await space_service.grant_access(payload)
