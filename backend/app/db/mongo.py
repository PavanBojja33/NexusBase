"""
app/db/mongo.py
───────────────
Async MongoDB connection management using Motor.

Design decisions:
  - A single `AsyncIOMotorClient` is created once at application startup
    inside the FastAPI lifespan context manager.  Motor clients are
    thread-safe and meant to be shared; creating one per request would be
    an expensive anti-pattern.
  - `get_database()` is the ONLY approved way to obtain the Motor database
    handle in the rest of the codebase.  Repositories import this function;
    they never create their own clients.
  - The lifespan approach (vs. on_event decorators) is the modern FastAPI
    pattern as of v0.93+.  It pairs startup and shutdown logic cleanly in
    one async generator.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

# Module-level client — set during startup, cleared during shutdown.
_client: AsyncIOMotorClient | None = None


def get_database() -> AsyncIOMotorDatabase:
    """Return the Motor database handle for `settings.MONGO_DB_NAME`.

    Repositories call this function to obtain a reference to the database
    and then access named collections.  It does NOT open a new connection —
    Motor manages its own internal connection pool.

    Raises:
        RuntimeError: If called before the application lifespan has started
                      (i.e., before `startup_db_client` ran).
    """
    if _client is None:
        raise RuntimeError(
            "MongoDB client is not initialised. "
            "Ensure the FastAPI lifespan is configured correctly."
        )
    return _client[settings.MONGO_DB_NAME]


@asynccontextmanager
async def lifespan(app) -> AsyncGenerator[None, None]:  # noqa: ANN001
    """FastAPI lifespan context manager that owns the Motor client lifecycle.

    Startup:
        Creates the `AsyncIOMotorClient`, which opens the connection pool
        and verifies connectivity.

    Shutdown:
        Calls `close()` to gracefully drain the pool before the process exits.

    Usage in main.py:
        app = FastAPI(lifespan=lifespan)
    """
    global _client
    _client = AsyncIOMotorClient(settings.MONGO_URI)
    print(f"[NexusBase] Connected to MongoDB at {settings.MONGO_URI}")
    yield
    _client.close()
    _client = None
    print("[NexusBase] MongoDB connection closed.")
