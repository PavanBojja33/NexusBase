"""
app/scripts/create_first_admin.py
──────────────────────────────────
Bootstrap script to create the initial super_admin account.

Bootstrapping Problem:
In Module 3, POST /api/v1/auth/register was secured with RBAC so that only an
existing `super_admin` can register new accounts (public self-registration is
disabled for enterprise security). This introduces a classic "chicken-and-egg"
bootstrap dilemma: if creating any account requires an existing super_admin
token, how does the very first super_admin account get created?

Solution:
This standalone administrative script bypasses the HTTP API entirely. It connects
directly to MongoDB, hashes the super_admin password using bcrypt via the
application's security layer, and calls `user_repository.create_user()` to persist
the seed administrator directly into the database.

Usage:
    Run manually once outside the API from the backend root:
        python -m app.scripts.create_first_admin
"""

import asyncio
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

import app.db.mongo as mongo_module
from app.core.config import settings
from app.core.security import hash_password
from app.repositories import user_repository

# ── Bootstrap Administrator Credentials ─────────────────────────────────────────
# These constants define the initial seed administrator. Modify these values
# before initial provisioning if desired.
ADMIN_NAME: str = "Nexus Admin"
ADMIN_EMAIL: str = "admin@nexusbase.com"
ADMIN_PASSWORD: str = "AdminSecret2026!"
ADMIN_DEPARTMENT: str = "Platform Engineering"


async def create_first_admin() -> None:
    """Connect to MongoDB and insert the initial super_admin user if not present."""
    print("=" * 65)
    print("NexusBase — Initial Super Admin Bootstrapper (Module 3 RBAC)")
    print("=" * 65)
    print(f"Connecting to MongoDB at: {settings.MONGO_URI}...")

    # Initialize the Motor client for the standalone script lifecycle
    client = AsyncIOMotorClient(settings.MONGO_URI)
    mongo_module._client = client

    try:
        # Check if the target admin email already exists in the database
        existing = await user_repository.find_by_email(ADMIN_EMAIL)
        if existing:
            print(f"[!] User with email '{ADMIN_EMAIL}' already exists.")
            print(f"    User ID: {existing['id']}")
            print(f"    Role:    {existing.get('role')}")
            print("No new administrator was created.")
            return

        # Prepare user document with super_admin role and bcrypt-hashed password
        admin_doc = {
            "name": ADMIN_NAME,
            "email": ADMIN_EMAIL,
            "hashed_password": hash_password(ADMIN_PASSWORD),
            "role": "super_admin",
            "department": ADMIN_DEPARTMENT,
            "created_at": datetime.now(timezone.utc),
        }

        user_id = await user_repository.create_user(admin_doc)

        print("\n[+] Initial super_admin created successfully!")
        print(f"    User ID:    {user_id}")
        print(f"    Name:       {ADMIN_NAME}")
        print(f"    Email:      {ADMIN_EMAIL}")
        print(f"    Role:       super_admin")
        print(f"    Department: {ADMIN_DEPARTMENT}")
        print("\nYou can now log in via POST /api/v1/auth/login using these credentials")
        print("to obtain a super_admin Bearer token and register subsequent users.")

    finally:
        # Gracefully close the database connection
        client.close()
        mongo_module._client = None
        print("Database connection closed.")


def main() -> None:
    """Script entry point."""
    asyncio.run(create_first_admin())


if __name__ == "__main__":
    main()
