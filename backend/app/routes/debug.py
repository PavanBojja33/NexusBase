"""
app/routes/debug.py
───────────────────
Temporary debug endpoints to verify the Celery/Redis wiring in Module 7 —
safe to remove once Module 9's real ingestion task is confirmed working, or
keep for future debugging.

These routes are intentionally lightweight:
  - POST /debug/ping-queue dispatches a trivial task via .delay() and returns
    the Celery task_id immediately (proving the call does NOT block).
  - GET /debug/task-status/{task_id} queries the Redis result backend for the
    task's current state and result.

Both endpoints require a valid JWT (get_current_user) but no specific role —
any authenticated user can use them, since they exist purely for diagnostics.
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.dependencies.auth import get_current_user
from app.models.user import UserOut
from app.queue.tasks import ping_task
from app.queue.celery_app import celery_app

router = APIRouter(prefix="/debug", tags=["Debug (Module 7)"])


# ── Request / Response schemas ─────────────────────────────────────────────────

class PingRequest(BaseModel):
    """JSON body for POST /debug/ping-queue."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        examples=["hello from NexusBase"],
    )


class PingResponse(BaseModel):
    """Response from POST /debug/ping-queue — returns the Celery task ID."""
    task_id: str


class TaskStatusResponse(BaseModel):
    """Response from GET /debug/task-status/{task_id}."""
    task_id: str
    status: str
    result: str | None = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post(
    "/ping-queue",
    response_model=PingResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dispatch a trivial ping task to the Celery worker",
    description=(
        "Sends a message to the Celery worker via Redis and returns the "
        "task ID immediately — the response does NOT wait for the worker "
        "to finish.\n\n"
        "**Authorization:** Any authenticated user (valid JWT).\n\n"
        "Use ``GET /api/v1/debug/task-status/{task_id}`` to poll the result."
    ),
)
async def ping_queue(
    payload: PingRequest,
    _current_user: UserOut = Depends(get_current_user),
) -> PingResponse:
    """Dispatch a ping_task to the Celery worker via .delay().

    .delay() is Celery's shorthand for .apply_async() — it serializes the
    arguments to JSON, pushes the message onto the Redis broker queue, and
    returns an AsyncResult handle instantly.  The actual task execution
    happens in the Celery worker process, NOT in the FastAPI process.

    Args:
        payload: JSON body containing the message string to echo.
        _current_user: Injected user profile (auth gate only).

    Returns:
        202 Accepted with the Celery task_id for status polling.
    """
    # .delay() pushes to Redis and returns immediately — does NOT block
    result = ping_task.delay(payload.message)
    return PingResponse(task_id=result.id)


@router.get(
    "/task-status/{task_id}",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check the status and result of a Celery task",
    description=(
        "Queries the Redis result backend for the current state of a "
        "previously dispatched task.\n\n"
        "**Possible statuses:**\n"
        "- ``PENDING`` — task is waiting in the queue (or task_id is unknown)\n"
        "- ``STARTED`` — worker has begun executing the task\n"
        "- ``SUCCESS`` — task completed; ``result`` contains the return value\n"
        "- ``FAILURE`` — task raised an exception; ``result`` contains the error\n\n"
        "**Authorization:** Any authenticated user (valid JWT)."
    ),
)
async def task_status(
    task_id: str,
    _current_user: UserOut = Depends(get_current_user),
) -> TaskStatusResponse:
    """Query the Celery result backend for a task's current state.

    Uses Celery's AsyncResult, which reads from the Redis result backend
    without contacting the worker process directly.

    Args:
        task_id: The Celery task ID returned by POST /debug/ping-queue.
        _current_user: Injected user profile (auth gate only).

    Returns:
        Task status and result (result is null until the task completes).
    """
    async_result = celery_app.AsyncResult(task_id)

    # Extract the result value if the task has completed
    result_value = None
    if async_result.ready():
        result_value = str(async_result.result)

    return TaskStatusResponse(
        task_id=task_id,
        status=async_result.status,
        result=result_value,
    )
