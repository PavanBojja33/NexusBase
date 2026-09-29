"""
app/repositories/space_repository.py
─────────────────────────────────────
All raw Motor queries against the `knowledge_spaces` collection.

Repository pattern:
  - This is the ONLY file in the codebase that imports or interacts with the
    MongoDB `knowledge_spaces` collection directly.
  - Converts MongoDB `_id` (ObjectId) to string `id` across all responses.
  - Every function is async and every Motor call is awaited.
"""

from bson import ObjectId
from bson.errors import InvalidId

from app.db.mongo import get_database


def _collection():
    """Return the Motor collection handle for `knowledge_spaces`.

    Retrieved from the live connection pool at call time.
    """
    return get_database()["knowledge_spaces"]


async def create_space(space_doc: dict) -> str:
    """Insert a new knowledge space document and return the string id.

    Args:
        space_doc: A dict representing the knowledge space document.
                   Must NOT contain an `_id` key.

    Returns:
        The string representation of the newly inserted document's `_id`.
    """
    result = await _collection().insert_one(space_doc)
    return str(result.inserted_id)


async def find_by_id(space_id: str) -> dict | None:
    """Find a knowledge space document by its string ObjectId.

    Args:
        space_id: String ObjectId of the knowledge space.

    Returns:
        The document dict with `_id` converted to `id`, or None if not found or invalid id.
    """
    try:
        oid = ObjectId(space_id)
    except InvalidId:
        return None

    doc = await _collection().find_one({"_id": oid})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def find_all_active() -> list[dict]:
    """Find all active knowledge space documents.

    Used by super_admin queries to view all system spaces.

    Returns:
        A list of active knowledge space dicts with `_id` converted to `id`.
    """
    cursor = _collection().find({"is_active": True})
    spaces: list[dict] = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        spaces.append(doc)
    return spaces


async def find_by_space_admin(user_id: str) -> list[dict]:
    """Find all active spaces where user_id is listed in space_admins.

    Used to retrieve spaces managed by a designated space_admin.

    Args:
        user_id: The string ID of the space admin user.

    Returns:
        A list of matching active knowledge space dicts.
    """
    cursor = _collection().find({"space_admins": user_id, "is_active": True})
    spaces: list[dict] = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        spaces.append(doc)
    return spaces


async def find_by_ids(space_ids: list[str]) -> list[dict]:
    """Find all active spaces matching a list of string IDs.

    Used to retrieve spaces assigned to an employee.

    Args:
        space_ids: List of space string IDs.

    Returns:
        A list of matching active knowledge space dicts.
    """
    valid_oids = []
    for sid in space_ids:
        try:
            valid_oids.append(ObjectId(sid))
        except InvalidId:
            continue

    if not valid_oids:
        return []

    cursor = _collection().find({"_id": {"$in": valid_oids}, "is_active": True})
    spaces: list[dict] = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        spaces.append(doc)
    return spaces


async def add_space_admin(space_id: str, user_id: str) -> bool:
    """Add a user ID to the space_admins list of a space if not already present.

    Uses MongoDB's `$addToSet` operator to avoid duplicate entries.

    Args:
        space_id: String ObjectId of the knowledge space.
        user_id: String ID of the user to designate as space admin.

    Returns:
        True if the space was found and updated, False if invalid ID or not found.
    """
    try:
        oid = ObjectId(space_id)
    except InvalidId:
        return False

    result = await _collection().update_one(
        {"_id": oid},
        {"$addToSet": {"space_admins": user_id}},
    )
    return result.matched_count > 0
