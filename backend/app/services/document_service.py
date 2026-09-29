"""
app/services/document_service.py
─────────────────────────────────
Business logic for document upload, listing, and link generation (Module 6).

Orchestration Layer:
  This service coordinates between the storage layer (MinIO via storage_service)
  and the persistence layer (MongoDB via document_repository).  Route handlers
  call these functions after RBAC dependencies have already authorized the
  request — this layer does NOT re-check permissions.

Module Boundary:
  This module's responsibility ENDS once a file is stored in MinIO and a
  Document record exists in MongoDB with status "uploaded".  It does NOT:
    - Enqueue any background/Celery/Redis job
    - Extract text from the uploaded file
    - Chunk, embed, or index the document
    - Interact with ChromaDB or any vector store
  All of the above belong to Module 7+ (Ingestion Pipeline) and will be
  wired in later, potentially by extending upload_document to dispatch an
  async task AFTER the record is created.
"""

from datetime import datetime, timezone

from fastapi import UploadFile

from app.core.exceptions import ApiError
from app.models.document import DocumentOut
from app.models.knowledge_space import KnowledgeSpaceOut
from app.models.user import UserOut
from app.repositories import document_repository
from app.services import storage_service


async def upload_document(
    file: UploadFile,
    space: KnowledgeSpaceOut,
    uploader: UserOut,
) -> DocumentOut:
    """Upload a file to MinIO and create a Document record in MongoDB.

    Workflow:
      1. Read the raw file bytes via ``await file.read()``.
      2. Call ``storage_service.upload_file(...)`` to store the file in MinIO
         and obtain a unique storage_key.
      3. Build a document dict with all metadata and persist it via
         ``document_repository.create_document(...)``.
      4. Return the created document as a ``DocumentOut`` instance.

    Note:
      This function does NOT trigger any ingestion, text extraction, or
      embedding logic.  The document is created with status "uploaded" and
      the ingestion pipeline (Module 7+) will pick it up from there.

    Args:
        file: The FastAPI UploadFile object from the multipart request.
        space: The validated KnowledgeSpaceOut (already authorized by
               require_space_access dependency).
        uploader: The authenticated user profile (from JWT current_user).

    Returns:
        DocumentOut with the newly created document's metadata.
    """
    # 1. Read file bytes asynchronously
    file_bytes = await file.read()

    # 2. Upload to MinIO
    content_type = file.content_type or "application/octet-stream"
    storage_key = await storage_service.upload_file(
        file_bytes=file_bytes,
        original_filename=file.filename or "unnamed",
        knowledge_space_id=space.id,
        content_type=content_type,
    )

    # 3. Build and persist the document record
    doc_dict = {
        "original_name": file.filename or "unnamed",
        "mime_type": content_type,
        "size_bytes": len(file_bytes),
        "storage_key": storage_key,
        "knowledge_space_id": space.id,
        "uploaded_by": uploader.id,
        "status": "uploaded",
        "chunk_count": 0,
        "error_message": "",
        "created_at": datetime.now(timezone.utc),
    }
    created_doc = await document_repository.create_document(doc_dict)

    # 4. Return as DocumentOut
    return DocumentOut(**created_doc)


async def list_documents(space_id: str) -> list[DocumentOut]:
    """List all documents in a Knowledge Space, sorted newest first.

    Args:
        space_id: The ID of the Knowledge Space whose documents to list.

    Returns:
        A list of DocumentOut instances, ordered by creation date descending.
    """
    docs = await document_repository.find_by_space(space_id)
    return [DocumentOut(**doc) for doc in docs]


async def get_document_link(document_id: str, space_id: str) -> str:
    """Generate a presigned download URL for a specific document.

    Security:
      Uses the scoped lookup ``find_by_id_and_space`` which requires BOTH
      the document_id AND the space_id to match.  This prevents IDOR attacks
      where a user with access to Space A tries to fetch a document that
      actually belongs to Space B by guessing the document's ObjectId.

    Args:
        document_id: String ObjectId of the target document.
        space_id: The Knowledge Space the document must belong to.

    Returns:
        A time-limited presigned URL string for direct MinIO download.

    Raises:
        ApiError(404): If the document does not exist or does not belong
                       to the specified space.
    """
    doc = await document_repository.find_by_id_and_space(document_id, space_id)
    if not doc:
        raise ApiError(404, "Document not found")

    return await storage_service.get_presigned_url(doc["storage_key"])
