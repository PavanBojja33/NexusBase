"""
app/queue/tasks.py
──────────────────
Celery task functions for NexusBase.

Current tasks (Module 7 — Queue Skeleton):
  - ping_task: A trivial proof-of-concept task that returns "pong: <message>".
    Exists ONLY to verify that the FastAPI → Redis → Celery worker handoff
    works end-to-end.  It is not part of the production pipeline.

Future tasks (Module 9 — Ingestion Pipeline):
  - process_document_task: The real document ingestion task will be defined
    here once Module 8's RAG functions (text extraction, chunking, embedding)
    exist for it to call.  Module 9 will add that task to this file and wire
    the Module 6 upload route to call process_document_task.delay(...) after
    creating the Document record.

    DO NOT implement process_document_task here yet — it depends on:
      1. Module 8: RAG core functions (extract text, chunk, embed, store in
         ChromaDB) — these don't exist yet.
      2. Module 9: Wiring the upload route to enqueue the task and
         implementing the task body that calls Module 8's functions.
"""

from app.queue.celery_app import celery_app


@celery_app.task(name="nexusbase.ping")
def ping_task(message: str) -> str:
    """Trivial proof-of-concept task for Module 7.

    Proves the async handoff works:
      1. FastAPI route calls ``ping_task.delay("hello")``
      2. Celery serializes the call to JSON and pushes it to Redis broker
      3. The Celery worker (separate process) picks it up and runs this function
      4. The result is stored in the Redis result backend
      5. FastAPI can later query the result via ``AsyncResult(task_id)``

    Args:
        message: Any string to echo back.

    Returns:
        "pong: <message>" — proving the worker received and processed the job.
    """
    return f"pong: {message}"
