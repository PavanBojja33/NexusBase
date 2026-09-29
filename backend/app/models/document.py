"""
app/models/document.py
──────────────────────
Pydantic schemas for the Document domain (Module 6).

Documents represent files uploaded into a Knowledge Space. Each document
tracks the original filename, MIME type, size, storage key (MinIO object
path), and a processing status that later modules will update as ingestion
progresses.

Schemas:
  DocumentStatus  → Literal enum of allowed processing states.
  DocumentOut     → Public response schema representing a Document record.

Design Decisions:
  - No "DocumentCreate" Input Schema:
    Unlike UserCreate or KnowledgeSpaceCreate, there is no client-facing
    input schema for documents.  The document record is assembled entirely
    server-side from:
      1. The uploaded file's metadata (name, size, MIME type)
      2. The storage_key returned by storage_service after MinIO upload
      3. The space_id from the route path parameter
      4. The uploader's user ID from the JWT-authenticated current_user
    The client sends only a multipart file — no JSON body.

  - Status Lifecycle:
    Documents are created with status "uploaded".  The progression through
    "processing" → "indexed" (or "failed") is Module 7+'s responsibility.
    This module only defines the status values so the schema is complete.

  - chunk_count / error_message:
    These fields exist to track ingestion results once the RAG pipeline
    runs (Module 7+).  They default to 0 and "" respectively — Module 6
    never sets them to anything else.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


# The four allowed processing states.  Transitions are managed by the
# ingestion pipeline (Module 7+), not by this module.
DocumentStatus = Literal["uploaded", "processing", "indexed", "failed"]


class DocumentOut(BaseModel):
    """Public representation of a Document record returned by the API.

    Every field is populated server-side — the client never provides a
    document creation payload.

    Fields:
      id                : MongoDB document _id (string).
      original_name     : Original filename as uploaded by the user.
      mime_type         : MIME content type (e.g., "application/pdf").
      size_bytes        : File size in bytes.
      storage_key       : MinIO object key (e.g., "space-id/uuid-file.pdf").
      knowledge_space_id: The Knowledge Space this document belongs to.
      uploaded_by       : User ID of the uploader (from JWT current_user).
      status            : Processing status — starts as "uploaded".
      chunk_count       : Number of text chunks after ingestion (Module 7+).
      error_message     : Error details if ingestion failed (Module 7+).
      created_at        : Timestamp of upload.
    """

    id: str
    original_name: str
    mime_type: str
    size_bytes: int
    storage_key: str
    knowledge_space_id: str
    uploaded_by: str
    status: DocumentStatus = "uploaded"
    chunk_count: int = 0
    error_message: str = ""
    created_at: datetime

    model_config = {"from_attributes": True}
