"""
app/repositories/user_repository.py
────────────────────────────────────
All raw Motor queries against the `users` collection.

Repository pattern:
  - This is the ONLY file in the codebase that imports or interacts with the
    MongoDB `users` collection directly.
  - Services call repository functions using domain vocabulary
    (`find_by_email`, `create_user`).  They never build MongoDB query dicts
    themselves.  This means if the storage backend ever changes (e.g., to
    PostgreSQL or a different collection schema), only this file changes.
  - Every function is `async` and every Motor call is `await`ed.  Forgetting
    `await` on a Motor coroutine produces a silent no-op (the query never
    runs), so the pattern is enforced rigorously here.

ObjectId handling:
  - MongoDB stores `_id` as a BSON ObjectId.  Motor returns it as a Python
    `ObjectId` object when querying.  We convert it to a plain string
    immediately in this layer so the rest of the codebase (services, models)
    never needs to import `bson`.
"""

from bson import ObjectId
from bson.errors import InvalidId

from app.db.mongo import get_database


def _collection():
    """Return the Motor collection handle for `users`.

    Called inside each async function (not at module level) so that the
    database handle is always retrieved from the live connection pool, not
    captured at import time before startup is complete.
    """
    return get_database()["users"]


async def find_by_email(email: str) -> dict | None:
    """Find a user document by email address.

    Email lookup is the primary authentication query — called during login
    and duplicate-check during registration.

    Args:
        email: The email address to search for (case-sensitive match).

    Returns:
        The raw MongoDB document dict with `_id` converted to string `id`,
        or None if no user with that email exists.
    """
    doc = await _collection().find_one({"email": email})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def find_by_id(user_id: str) -> dict | None:
    """Find a user document by its string representation of MongoDB ObjectId.

    Used by the `get_current_user` dependency after decoding a JWT to load
    the full user profile from the database.

    Args:
        user_id: The string ObjectId of the user (the `sub` claim from the JWT).

    Returns:
        The raw MongoDB document dict with `_id` converted to string `id`,
        or None if no user with that id exists or the id is malformed.
    """
    try:
        oid = ObjectId(user_id)
    except InvalidId:
        return None

    doc = await _collection().find_one({"_id": oid})
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def create_user(user_doc: dict) -> str:
    """Insert a new user document and return the new user's string id.

    The caller (auth_service) is responsible for:
      - Setting `hashed_password` (never plaintext)
      - Setting `role`, `department`, and `created_at`

    Args:
        user_doc: A dict representing the full user document to insert.
                  Must NOT contain an `_id` key — MongoDB generates it.

    Returns:
        The string representation of the newly inserted document's `_id`.
    """
    result = await _collection().insert_one(user_doc)
    return str(result.inserted_id)
