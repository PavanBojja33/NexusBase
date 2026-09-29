"""
app/services/storage_service.py
───────────────────────────────
S3-compatible Object Storage service wrapping MinIO.

Architecture & Concurrency Design:
  - Synchronous SDK vs. Async Event Loop:
    The official `minio` Python SDK is fundamentally synchronous and blocking.
    If blocking network calls (such as uploading multi-megabyte document payloads
    or downloading files) run directly on FastAPI's main asyncio event loop, the
    entire server process would stall, preventing all concurrent HTTP requests
    (auth, space queries, health checks) from making progress.
    To preserve asynchronous non-blocking throughput, all MinIO operations are
    wrapped with `asyncio.to_thread(...)`, offloading blocking socket I/O to a
    worker thread pool while keeping the async event loop completely free.

  - Logical Isolation via Object Key Prefixing:
    Every object key is structured as:
        `{knowledge_space_id}/{uuid4()}-{original_filename}`
    This design organizes documents per Knowledge Space inside a unified
    shared bucket (`nexusbase-documents`). It enables easy key scanning, avoids
    filename collisions, and mirrors the access boundaries enforced by RBAC.

Module 6 Integration:
  - `upload_file`: Called by Module 6's `POST /api/v1/spaces/{space_id}/documents`
    endpoint after validating the file and checking space permissions.
  - `get_file_bytes`: Called by the ingestion pipeline (Module 7) to extract text
    and generate chunked embeddings.
  - `get_presigned_url`: Called by document retrieval and citation routes to generate
    temporary, secure viewing links without proxying large files through the API.
"""

import asyncio
from datetime import timedelta
import io
import uuid

from minio import Minio

from app.core.config import settings

# ── Module-level MinIO Client ──────────────────────────────────────────────────
# Initialized once using credentials and connection details from application settings.
minio_client = Minio(
    endpoint=f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=settings.MINIO_USE_SSL,
)


async def ensure_bucket() -> None:
    """Verify that the target storage bucket exists; create it if missing.

    MinIO calls are synchronous, so the check and bucket creation are executed
    in an asynchronous worker thread via `asyncio.to_thread`.

    Module 6 Lifecycle:
        Module 6 can invoke this during startup lifespan or before document
        ingestion to ensure the storage infrastructure is ready.
    """

    def _sync_ensure_bucket() -> None:
        exists = minio_client.bucket_exists(settings.MINIO_BUCKET)
        if not exists:
            minio_client.make_bucket(settings.MINIO_BUCKET)
            print(f"[NexusBase Storage] Created MinIO bucket '{settings.MINIO_BUCKET}'.")
        else:
            print(f"[NexusBase Storage] MinIO bucket '{settings.MINIO_BUCKET}' already exists.")

    await asyncio.to_thread(_sync_ensure_bucket)


async def upload_file(
    file_bytes: bytes,
    original_filename: str,
    knowledge_space_id: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload raw file bytes to MinIO and return a unique storage key.

    Object Key Format:
        `f"{knowledge_space_id}/{uuid4()}-{original_filename}"`
        - Scoped by Knowledge Space to maintain multi-tenant boundaries.
        - UUID ensures idempotency and avoids name collisions when users upload
          differing versions of identically named files (e.g. `report.pdf`).

    Args:
        file_bytes: The raw binary content of the file.
        original_filename: Original name of the uploaded file (e.g. "rfc_doc.pdf").
        knowledge_space_id: The ID of the target Knowledge Space.
        content_type: MIME type of the file (e.g. "application/pdf", "text/plain").

    Returns:
        The generated unique storage key (e.g., "space-123/uuid-file.pdf").
    """
    unique_id = uuid.uuid4()
    storage_key = f"{knowledge_space_id}/{unique_id}-{original_filename}"

    def _sync_upload() -> None:
        data_stream = io.BytesIO(file_bytes)
        minio_client.put_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=storage_key,
            data=data_stream,
            length=len(file_bytes),
            content_type=content_type,
        )

    await asyncio.to_thread(_sync_upload)
    return storage_key


async def get_file_bytes(storage_key: str) -> bytes:
    """Retrieve raw file bytes from MinIO for a given storage key.

    Offloads blocking stream reads to `asyncio.to_thread` and guarantees
    connection release via `try ... finally`.

    Module 7/Worker Usage:
        The ingestion pipeline will fetch document bytes using this method to
        parse text and generate embeddings.

    Args:
        storage_key: The object key returned by `upload_file`.

    Returns:
        The raw bytes of the stored file.
    """

    def _sync_get_bytes() -> bytes:
        response = minio_client.get_object(settings.MINIO_BUCKET, storage_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    return await asyncio.to_thread(_sync_get_bytes)


async def get_presigned_url(storage_key: str, expiry_seconds: int = 300) -> str:
    """Generate a time-limited, presigned GET URL for secure direct document access.

    Allows authenticated clients to preview or download a document directly from
    MinIO without burdening the FastAPI backend with proxying large file streams.

    Args:
        storage_key: The object key returned by `upload_file`.
        expiry_seconds: Lifetime of the signed URL in seconds (defaults to 300s = 5m).

    Returns:
        A signed URL string valid for the requested duration.
    """

    def _sync_presigned_url() -> str:
        return minio_client.presigned_get_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=storage_key,
            expires=timedelta(seconds=expiry_seconds),
        )

    return await asyncio.to_thread(_sync_presigned_url)
