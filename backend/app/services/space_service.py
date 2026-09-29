"""
app/services/space_service.py
──────────────────────────────
Business logic for Knowledge Space lifecycle and access control.

Knowledge Space Security Architecture:
  - Role-based visibility filtering:
    Knowledge Spaces implement "hidden, not just denied" security. Rather than
    listing all spaces and rejecting unauthorized access upon entry, endpoints
    filter the space collection based on the caller's role:
      - super_admin : Sees all active Knowledge Spaces in the organization.
      - space_admin : Sees only spaces where their user ID is in `space_admins`.
      - employee    : Sees only spaces whose IDs are in their `knowledge_spaces` list.
    This guarantees that unprivileged users cannot infer the existence of confidential
    or restricted spaces (e.g., M&A, HR investigations, Executive Leadership).

  - Access Delegation:
    When granting access:
      - Assigning access to a `space_admin` adds them to `space.space_admins`,
        empowering them to curate documents and administer that specific space.
      - Assigning access to an `employee` appends `space_id` to `user.knowledge_spaces`,
        granting read and query permissions to that space.
"""

from datetime import datetime, timezone

from app.core.exceptions import ApiError
from app.models.knowledge_space import (
    GrantAccessRequest,
    KnowledgeSpaceCreate,
    KnowledgeSpaceOut,
)
from app.models.user import UserOut
from app.repositories import space_repository, user_repository


async def create_space(
    payload: KnowledgeSpaceCreate, creator: UserOut
) -> KnowledgeSpaceOut:
    """Create a new Knowledge Space.

    Args:
        payload: Validated space creation payload (name, description, department).
        creator: The authenticated user profile creating the space.

    Returns:
        The newly created KnowledgeSpaceOut representation.
    """
    space_doc = {
        "name": payload.name,
        "description": payload.description,
        "department": payload.department,
        "created_by": creator.id,
        "space_admins": [creator.id] if creator.role == "space_admin" else [],
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
    }

    space_id = await space_repository.create_space(space_doc)
    space_doc["id"] = space_id
    return KnowledgeSpaceOut(**space_doc)


async def list_visible_spaces(current_user: UserOut) -> list[KnowledgeSpaceOut]:
    """Retrieve all Knowledge Spaces visible to the authenticated user.

    Applies role-based filtering:
      - super_admin : Returns all active spaces across the platform.
      - space_admin : Returns only spaces where current_user.id is in space_admins.
      - employee    : Returns only spaces where space_id is in user.knowledge_spaces.

    Args:
        current_user: The authenticated user profile.

    Returns:
        A list of visible KnowledgeSpaceOut instances.
    """
    if current_user.role == "super_admin":
        spaces = await space_repository.find_all_active()
    elif current_user.role == "space_admin":
        spaces = await space_repository.find_by_space_admin(current_user.id)
    else:
        # Retrieve user's assigned knowledge space IDs
        user_spaces = getattr(current_user, "knowledge_spaces", None)
        if not user_spaces:
            user_doc = await user_repository.find_by_id(current_user.id)
            user_spaces = user_doc.get("knowledge_spaces", []) if user_doc else []

        spaces = await space_repository.find_by_ids(user_spaces)

    return [KnowledgeSpaceOut(**doc) for doc in spaces]


async def grant_access(payload: GrantAccessRequest) -> dict:
    """Grant Knowledge Space access to an employee or designate a space_admin.

    Args:
        payload: GrantAccessRequest containing target user_id and space_id.

    Returns:
        Confirmation dictionary detailing the access grant.

    Raises:
        ApiError(404): If the target user or knowledge space does not exist.
    """
    # 1. Validate target user existence
    target_user = await user_repository.find_by_id(payload.user_id)
    if not target_user:
        raise ApiError(404, "User not found")

    # 2. Validate target knowledge space existence and active status
    target_space = await space_repository.find_by_id(payload.space_id)
    if not target_space or not target_space.get("is_active", True):
        raise ApiError(404, "Knowledge Space not found")

    # 3. Route assignment based on target user's role
    if target_user.get("role") == "space_admin":
        await space_repository.add_space_admin(payload.space_id, payload.user_id)
        granted_as = "space_admin"
    else:
        await user_repository.add_knowledge_space_to_user(
            payload.user_id, payload.space_id
        )
        granted_as = "employee"

    return {
        "message": (
            f"Successfully granted access to {target_user['name']} "
            f"for Knowledge Space '{target_space['name']}'"
        ),
        "user_id": payload.user_id,
        "space_id": payload.space_id,
        "granted_as": granted_as,
    }
