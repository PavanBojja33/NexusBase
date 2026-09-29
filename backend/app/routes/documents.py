"""
app/routes/documents.py
───────────────────────
HTTP routes for Document upload, listing, and download link generation (Module 6).

This module is the FIRST place in the entire NexusBase project where
``require_space_access`` is actually attached to a route.  All three
endpoints require the caller to have authorized access to the target
Knowledge Space.

Design Conventions:
  - POST .../upload uses BOTH ``require_role`` AND ``require_space_access``:
    Role alone is insufficient — a space_admin who administers Space A must
    NOT be able to upload into Space B.  Both dependencies must independently
    pass for the request to proceed.

  - GET .../ (list) and GET .../link use only ``require_space_access``:
    Any role that has access to the space (including employees) can view
    the list of documents and generate download links.

  - File Size Guard:
    A 50 MB limit is enforced as a basic safeguard before reading file bytes
    into memory.  This is a sensible default, not a production-tuned limit.

  - The ``space`` return value from ``require_space_access`` is used to pass
    the validated KnowledgeSpaceOut to the service layer without a redundant
    database lookup.
"""

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.exceptions import ApiError
from app.dependencies.rbac import require_role, require_space_access
from app.models.document import DocumentOut
from app.models.knowledge_space import KnowledgeSpaceOut
from app.models.user import UserOut
from app.services import document_service

router = APIRouter(prefix="/documents", tags=["Documents"])

# Maximum upload size: 50 MB (in bytes)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.post(
    "/{space_id}/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document into a Knowledge Space",
    description=(
        "Accepts a multipart file upload and stores it in MinIO, creating a "
        "Document metadata record in MongoDB with status ``uploaded``.\n\n"
        "**Authorization (defense-in-depth):**\n"
        "- ``require_role('super_admin', 'space_admin')``: Only admin roles "
        "are allowed to upload documents.\n"
        "- ``require_space_access``: The caller must also have authorized "
        "access to THIS specific Knowledge Space.  A space_admin who "
        "administers a different space will be rejected with 403.\n\n"
        "**File size limit:** 50 MB maximum.\n\n"
        "This endpoint does NOT trigger any background processing, text "
        "extraction, or embedding — that is Module 7+."
    ),
)
async def upload_document(
    space_id: str,
    file: UploadFile = File(..., description="The document file to upload"),
    _role_check: UserOut = Depends(require_role("super_admin", "space_admin")),
    space: dict = Depends(require_space_access),
) -> DocumentOut:
    """Upload a document file into a Knowledge Space.

    Both ``require_role`` and ``require_space_access`` must pass:
      - require_role ensures only super_admin or space_admin roles can upload.
      - require_space_access ensures the caller actually has access to THIS
        specific space (not just any space they happen to administer).

    The ``space`` dict returned by require_space_access is converted to
    KnowledgeSpaceOut so the service layer receives a typed object.

    Args:
        space_id: Path parameter — the target Knowledge Space ID.
        file: The uploaded file from multipart/form-data.
        _role_check: Injected by require_role (used for authorization only).
        space: The validated Knowledge Space dict from require_space_access.

    Returns:
        201 Created with the DocumentOut metadata of the newly uploaded document.

    Raises:
        ApiError(403): If the user's role is not super_admin/space_admin, or
                       if they lack access to this specific space.
        ApiError(413): If the uploaded file exceeds 50 MB.
    """
    # File size guard — read the bytes and check length
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "File too large — maximum upload size is 50 MB")

    # Reset the file position so the service can re-read if needed
    # (We pass file_bytes directly via the UploadFile's spooled buffer)
    await file.seek(0)

    # Convert the space dict to KnowledgeSpaceOut for the service layer
    space_out = KnowledgeSpaceOut(**space)

    # The current_user is available from _role_check (require_role returns the user)
    return await document_service.upload_document(
        file=file,
        space=space_out,
        uploader=_role_check,
    )


@router.get(
    "/{space_id}",
    response_model=list[DocumentOut],
    status_code=status.HTTP_200_OK,
    summary="List documents in a Knowledge Space",
    description=(
        "Returns all documents belonging to a Knowledge Space, sorted newest "
        "first.\n\n"
        "**Authorization:** ``require_space_access`` — any role (including "
        "employees) that has been granted access to the space can list its "
        "documents.  Employees need this to see what has been indexed and to "
        "eventually query against these documents."
    ),
)
async def list_documents(
    space_id: str,
    _space: dict = Depends(require_space_access),
) -> list[DocumentOut]:
    """List all documents in a Knowledge Space.

    Only ``require_space_access`` is needed — any user with access to the
    space can view the document list, regardless of role.

    Args:
        space_id: Path parameter — the target Knowledge Space ID.
        _space: Injected by require_space_access (authorization gate).

    Returns:
        A list of DocumentOut instances sorted by created_at descending.
    """
    return await document_service.list_documents(space_id)


@router.get(
    "/{space_id}/{document_id}/link",
    status_code=status.HTTP_200_OK,
    summary="Get a presigned download link for a document",
    description=(
        "Generates a time-limited presigned URL (5 minutes) for direct "
        "download of a document from MinIO.\n\n"
        "**Authorization:** ``require_space_access`` — any role with access "
        "to the space can generate download links.\n\n"
        "**Security:** The document is looked up using BOTH document_id AND "
        "space_id to prevent IDOR attacks — a document ID from Space B "
        "cannot be fetched through a Space A route."
    ),
)
async def get_document_link(
    space_id: str,
    document_id: str,
    _space: dict = Depends(require_space_access),
) -> dict:
    """Generate a presigned download URL for a document.

    Uses the scoped lookup (document_id + space_id) to ensure the document
    genuinely belongs to the space the caller has been authorized to access.

    Args:
        space_id: Path parameter — the Knowledge Space ID.
        document_id: Path parameter — the Document ID.
        _space: Injected by require_space_access (authorization gate).

    Returns:
        ``{"url": "<presigned_url>"}`` — a temporary download link valid
        for 5 minutes.

    Raises:
        ApiError(404): If the document does not exist or does not belong
                       to the specified space.
    """
    url = await document_service.get_document_link(document_id, space_id)
    return {"url": url}
