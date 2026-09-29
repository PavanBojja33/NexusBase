"""
app/dependencies/rbac.py
─────────────────────────
Role-Based Access Control (RBAC) and Resource Authorization dependencies.

This module enforces the 3-tier authorization hierarchy across the NexusBase
platform:
  1. super_admin : Platform administrator with unrestricted authority (user
                   management, system configuration, global space access).
  2. space_admin : Knowledge Space owner/curator with administrative rights
                   over assigned spaces (document upload, indexing, space settings).
  3. employee    : Standard consumer with query and read access restricted to
                   permitted Knowledge Spaces.

Architecture & Design Decisions:
  - Separation of Concerns:
    Authentication (`get_current_user` in `app/dependencies/auth.py`) answers
    "WHO is making this request?".
    Authorization (`require_role`, `require_space_access` in this module)
    answers "WHAT is this user permitted to do?".
    By decoupling the two, authentication logic remains pure and single-purpose,
    while authorization policies can be combined and layered cleanly at the
    route level via FastAPI's dependency injection system.

  - Dependency Factory Pattern:
    FastAPI dependencies declared as `Depends(...)` normally cannot receive
    arbitrary runtime parameters from the route definition.
    `require_role` is designed as a *dependency factory* (a higher-order
    function that returns a dependency callable). This allows routes to specify
    one or more allowed roles dynamically at route declaration time:
        `Depends(require_role("super_admin"))`
        `Depends(require_role("super_admin", "space_admin"))`
    The generated dependency closes over `allowed_roles`, automatically
    executes `get_current_user` to validate the incoming JWT and load the user,
    and validates the user's role against the permit list.

  - HTTP 403 Forbidden:
    If a user is properly authenticated (valid JWT) but lacks the required role,
    the dependency raises `ApiError(403, "You do not have permission to perform this action")`.
    Per RFC 9110, 401 is reserved for missing or invalid authentication credentials,
    whereas 403 indicates that credentials were authenticated but the server
    refuses to authorize the specific action.
"""

from typing import Callable

from fastapi import Depends

from app.core.exceptions import ApiError
from app.dependencies.auth import get_current_user
from app.models.user import UserOut
from app.repositories import space_repository, user_repository


def require_role(*allowed_roles: str) -> Callable:
    """Dependency factory that creates a role-checking FastAPI dependency.

    Enforces coarse-grained, role-based authorization at the route level.
    The returned dependency delegates authentication to `get_current_user`,
    checks whether the authenticated user's role exists within `allowed_roles`,
    and permits the request or rejects it with HTTP 403.

    Why a Dependency Factory:
        FastAPI dependencies cannot accept custom configuration arguments at the
        route declaration site when passed as plain functions. By returning an
        async dependency function from an outer closure that captures `allowed_roles`,
        we achieve reusable, declarative access control across diverse routes:
            `Depends(require_role("super_admin"))`
            `Depends(require_role("super_admin", "space_admin"))`

    Args:
        *allowed_roles: One or more role names permitted to access the endpoint
                        (e.g., "super_admin", "space_admin", "employee").

    Returns:
        An async FastAPI dependency function that validates the user's role
        and returns the authenticated `UserOut` instance if authorized.

    Raises:
        ApiError(403): If the authenticated user's role is not in `allowed_roles`.
    """

    async def role_checker(
        current_user: UserOut = Depends(get_current_user),
    ) -> UserOut:
        """Inner dependency that verifies the user's role against allowed_roles."""
        if current_user.role not in allowed_roles:
            raise ApiError(403, "You do not have permission to perform this action")
        return current_user

    return role_checker


async def require_space_access(
    space_id: str,
    current_user: UserOut = Depends(get_current_user),
) -> dict:
    """Validate that the authenticated user has access to the specified Knowledge Space.

    Enforces fine-grained, resource-level authorization across all three roles:
      - super_admin : Unrestricted access to all active Knowledge Spaces.
      - space_admin : Allowed only if designated in `space.space_admins`.
      - employee    : Allowed only if `space_id` is in their `knowledge_spaces` list.

    Args:
        space_id: The unique identifier of the target Knowledge Space from the route path.
        current_user: The authenticated user profile injected via `get_current_user`.

    Returns:
        The validated Knowledge Space document dict.

    Raises:
        ApiError(404): If the Knowledge Space does not exist or is inactive.
        ApiError(403): If the user lacks access rights according to their role.
    """
    space = await space_repository.find_by_id(space_id)
    if not space or not space.get("is_active", True):
        raise ApiError(404, "Knowledge Space not found")

    # 1. Platform administrator has global access
    if current_user.role == "super_admin":
        return space

    # 2. Space administrator must be listed in space_admins
    if current_user.role == "space_admin":
        if current_user.id not in space.get("space_admins", []):
            raise ApiError(403, "You do not administer this Knowledge Space")
        return space

    # 3. Employee must have explicit access granted
    user_spaces = getattr(current_user, "knowledge_spaces", None)
    if not user_spaces:
        user_doc = await user_repository.find_by_id(current_user.id)
        user_spaces = user_doc.get("knowledge_spaces", []) if user_doc else []

    if space_id not in user_spaces:
        raise ApiError(403, "You do not have access to this Knowledge Space")

    return space
