"""
app/core/config.py
──────────────────
Application settings loaded from the .env file via pydantic-settings.

A single `settings` singleton is exported from this module and imported
everywhere else that needs configuration (db, security, etc.).  This
keeps configuration changes to one file and makes unit-testing easy —
tests can patch `settings` directly.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reads environment variables (or .env file) and exposes them as
    typed attributes.  Pydantic validates types at startup, so a missing
    or badly-typed variable crashes immediately with a clear error rather
    than silently at runtime.
    """

    # ── MongoDB ────────────────────────────────────────────────────────────
    MONGO_URI: str = "mongodb://localhost:27017"
    MONGO_DB_NAME: str = "nexusbase"

    # ── JWT ────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_EXPIRES_IN: int = 60  # token lifetime in minutes

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Module-level singleton — import this, never instantiate Settings elsewhere.
settings = Settings()
