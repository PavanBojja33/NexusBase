"""
app/queue/celery_app.py
───────────────────────
Celery application instance for NexusBase.

This file defines the Celery app and its configuration ONLY.  Actual task
functions live in ``app/queue/tasks.py`` (and future task files), kept
separate so task logic doesn't get tangled with Celery configuration.

Architecture:
  Celery operates as a SEPARATE worker process from the FastAPI application.
  FastAPI dispatches work by calling ``task.delay(...)`` or
  ``task.apply_async(...)``, which serialises the arguments and pushes a
  message onto the Redis broker queue.  The Celery worker process polls
  that queue, deserialises the message, executes the task function, and
  writes the result to the Redis result backend.

  FastAPI  ──(.delay())──►  Redis broker  ──(poll)──►  Celery worker
                                                           │
                                                    executes task
                                                           │
                                                    Redis result backend
                                                           │
  FastAPI  ◄──(AsyncResult)── reads result  ◄──────────────┘

Serialization:
  ``task_serializer`` and ``result_serializer`` are explicitly set to "json"
  rather than relying on Celery's legacy default of "pickle".  Reasons:

    1. Security — pickle can execute arbitrary Python code during
       deserialization, making it a remote-code-execution vector if an
       attacker can inject messages into the broker.  JSON is inert.

    2. Compatibility — all data flowing through our tasks consists of
       MongoDB ObjectId strings, plain dicts, and primitive types, all of
       which serialize to JSON trivially.  We never need to pass live
       Python objects (file handles, DB cursors, etc.) through the queue.

    3. Debuggability — JSON messages are human-readable in Redis, making
       it easy to inspect what's in the queue during development.
"""

from celery import Celery

from app.core.config import settings

# ── Build broker + backend URLs from settings ──────────────────────────────────
# Both the broker (message queue) and the result backend (task result store)
# point at the same local Redis instance, using different database numbers
# (db 0 for broker, db 1 for results) to keep concerns separated within Redis.

_broker_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"
_backend_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1"

# ── Celery application instance ───────────────────────────────────────────────

celery_app = Celery(
    "nexusbase",
    broker=_broker_url,
    backend=_backend_url,
)

celery_app.conf.update(
    # Explicit JSON serialization — see module docstring for rationale.
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Timezone awareness — use UTC for consistency with the rest of NexusBase.
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover task modules so the worker registers all @celery_app.task
# decorated functions without requiring manual imports.
celery_app.autodiscover_tasks(["app.queue"])
