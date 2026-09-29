"""
app/repositories/document_repository.py
────────────────────────────────────────
All raw Motor queries against the ``documents`` collection.

Repository Pattern:
  This is the ONLY file in the codebase that directly accesses the MongoDB
  ``documents`` collection.  All other layers (services, routes) interact
  with documents exclusively through this module's async functions.

Design Decisions:

  - Scoped Lookup (find_by_id_and_space):
    A document is ALWAYS fetched with both its own ID and the knowledge
    space ID.  This prevents Insecure Direct Object Reference (IDOR)
    attacks: even if an attacker guesses a valid document_id, they cannot
    retrieve it unless they also pass the correct space_id — which is
    itself guarded by require_space_access at the route level.  Without
    this dual-key lookup, a user with access to Space A could potentially
    fetch documents from Space B by supplying a Space-B document ID to a
    Space-A route.

  - update_status:
    Built now because the shape belongs to the document repository, even
    though nothing in Module 6 calls it.  Module 7's ingestion worker will
    use this to transition documents through "processing" → "indexed" or
    "failed", optionally recording chunk_count and error_message.

  - _id → id Conversion:
    Consistent with the project's convention (see space_repository.py),
    every returned document dict has MongoDB's ObjectId ``_id`` converted
    to a string ``id`` field.
"""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

from app.db.mongo import get_database


def _collection():
    """Return the Motor collection handle for ``documents``.

    Retrieved from the live connection pool at call time.
    """
    return get_database()["documents"]


async def create_document(doc_dict: dict) -> dict:
    """Insert a new document record and return the created document with string id.

    Args:
        doc_dict: A dict representing the document record.
                  Must NOT contain an ``_id`` key.  Should include at minimum:
                  original_name, mime_type, size_bytes, storage_key,
                  knowledge_space_id, uploaded_by, status, created_at.

    Returns:
        The inserted document dict with ``_id`` converted to ``id``.
    """
    result = await _collection().insert_one(doc_dict)
    doc_dict["id"] = str(result.inserted_id)
    doc_dict.pop("_id", None)
    return doc_dict


async def find_by_space(knowledge_space_id: str) -> list[dict]:
    """Find all documents belonging to a Knowledge Space, sorted newest first.

    Args:
        knowledge_space_id: The ID of the target Knowledge Space.

    Returns:
        A list of document dicts with ``_id`` converted to ``id``,
        ordered by ``created_at`` descending.
    """
    cursor = _collection().find(
        {"knowledge_space_id": knowledge_space_id}
    ).sort("created_at", -1)

    documents: list[dict] = []
    async for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        documents.append(doc)
    return documents


async def find_by_id_and_space(document_id: str, knowledge_space_id: str) -> dict | None:
    """Find a single document scoped to a specific Knowledge Space.

    Security-Critical Design:
      This function intentionally requires BOTH the document_id AND the
      knowledge_space_id.  A lookup by document_id alone would allow a
      user with access to Space A to retrieve a document from Space B
      simply by knowing (or guessing) the document's ObjectId.  The
      compound query ensures that the document must genuinely belong to the
      space the caller has been authorized to access via require_space_access.

    Args:
        document_id: String ObjectId of the document.
        knowledge_space_id: The ID of the Knowledge Space the document must
                            belong to.

    Returns:
        The document dict with ``_id`` converted to ``id``, or None if
        not found, invalid ID, or space mismatch.
    """
    try:
        oid = ObjectId(document_id)
    except InvalidId:
        return None

    doc = await _collection().find_one({
        "_id": oid,
        "knowledge_space_id": knowledge_space_id,
    })
    if doc:
        doc["id"] = str(doc.pop("_id"))
    return doc


async def update_status(
    document_id: str,
    status: str,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> bool:
    """Update a document's processing status and optional ingestion metadata.

    Module 7+ Usage:
      The ingestion worker will call this to transition a document through
      its lifecycle:
        "uploaded" → "processing" → "indexed"  (success path)
        "uploaded" → "processing" → "failed"   (error path)
      Optionally recording the number of text chunks produced and/or the
      error message if ingestion failed.

    Args:
        document_id: String ObjectId of the document.
        status: New status value ("processing", "indexed", or "failed").
        chunk_count: Number of chunks produced by the ingestion pipeline
                     (set on successful indexing).
        error_message: Error details (set on ingestion failure).

    Returns:
        True if the document was found and updated, False otherwise.
    """
    try:
        oid = ObjectId(document_id)
    except InvalidId:
        return False

    update_fields: dict = {
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }
    if chunk_count is not None:
        update_fields["chunk_count"] = chunk_count
    if error_message is not None:
        update_fields["error_message"] = error_message

    result = await _collection().update_one(
        {"_id": oid},
        {"$set": update_fields},
    )
    return result.matched_count > 0
