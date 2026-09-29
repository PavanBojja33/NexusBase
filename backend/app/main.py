"""
app/main.py
────────────
NexusBase FastAPI application entry point.

Responsibilities of this file:
  - Create the FastAPI application instance with metadata used in Swagger UI.
  - Attach the MongoDB lifespan context manager so the connection pool is
    opened on startup and cleanly closed on shutdown.
  - Register global exception handlers so `ApiError` is always converted to
    the canonical `{"error": "..."}` JSON envelope.
  - Configure CORS — origins are intentionally permissive during development.
    Tighten `allow_origins` to specific frontend URLs before production.
  - Mount all route routers under versioned prefixes (`/api/v1`).

Module registration order (dependency → dependent):
  Module 0: config (settings singleton)
  Module 1: db (Motor client), exceptions (ApiError handler)
  Module 2: auth routes  ← current module
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.exceptions import ApiError, api_error_handler
from app.db.mongo import lifespan
from app.routes import auth as auth_router, spaces as spaces_router, documents as documents_router

# ── Application instance ───────────────────────────────────────────────────────

app = FastAPI(
    title="NexusBase API",
    description=(
        "Enterprise RAG Document Intelligence Platform — REST API.\n\n"
        "Authenticate via **POST /api/v1/auth/login** to obtain a Bearer token, "
        "then click the 🔒 Authorize button in Swagger UI and paste the token."
    ),
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Development: allow all origins.
# Production: replace "*" with the deployed frontend URL(s).

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ─────────────────────────────────────────────────────────

app.add_exception_handler(ApiError, api_error_handler)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(spaces_router.router, prefix="/api/v1")
app.include_router(documents_router.router, prefix="/api/v1")

# ── Health check ───────────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Health"],
    summary="API health probe",
    description="Returns `{status: ok}` if the API process is running. "
                "Does not verify database connectivity.",
)
async def health() -> dict:
    """Lightweight liveness probe — no database interaction."""
    return {"status": "ok"}