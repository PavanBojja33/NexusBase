"""
app/scripts/test_storage.py
───────────────────────────
Standalone verification script for the MinIO storage service (Module 5).

Verifies the object storage layer in total isolation:
  1. Ensures target bucket existence (`ensure_bucket`).
  2. Uploads an in-memory sample document (`upload_file`).
  3. Downloads and compares raw bytes (`get_file_bytes`).
  4. Generates a signed, temporary access URL (`get_presigned_url`).

Usage:
    python -m app.scripts.test_storage
"""

import asyncio

from app.services.storage_service import (
    ensure_bucket,
    get_file_bytes,
    get_presigned_url,
    upload_file,
)

SAMPLE_SPACE_ID = "test-space-123"
SAMPLE_FILENAME = "sample_document.txt"
SAMPLE_TEXT = (
    "===============================================================\n"
    "NexusBase Enterprise RAG Document Intelligence Platform\n"
    "Module 5 Verification: MinIO Storage Integration\n"
    "===============================================================\n"
    "File storage layer functioning properly in asynchronous isolation.\n"
    "Timestamp: 2026-09-29\n"
)


async def run_storage_test() -> None:
    """Execute the storage lifecycle test sequence."""
    print("=" * 65)
    print("NexusBase — MinIO Storage Service Verification (Module 5)")
    print("=" * 65)

    # 1. Bucket initialization
    print("\n[Step 1] Ensuring MinIO bucket exists...")
    await ensure_bucket()
    print("[+] Bucket check completed.")

    # 2. Upload file
    sample_bytes = SAMPLE_TEXT.encode("utf-8")
    print(f"\n[Step 2] Uploading sample file '{SAMPLE_FILENAME}' to space '{SAMPLE_SPACE_ID}'...")
    storage_key = await upload_file(
        file_bytes=sample_bytes,
        original_filename=SAMPLE_FILENAME,
        knowledge_space_id=SAMPLE_SPACE_ID,
        content_type="text/plain",
    )
    print(f"[+] File uploaded successfully!")
    print(f"    Storage Key: {storage_key}")

    # 3. Download and round-trip verification
    print(f"\n[Step 3] Fetching file bytes for key: {storage_key}...")
    downloaded_bytes = await get_file_bytes(storage_key)
    downloaded_text = downloaded_bytes.decode("utf-8")

    assert (
        downloaded_bytes == sample_bytes
    ), "Data integrity error: downloaded bytes do not match uploaded bytes!"

    print("[+] Round-trip verification successful! Downloaded content:")
    print("-" * 55)
    print(downloaded_text.strip())
    print("-" * 55)

    # 4. Generate presigned URL
    print("\n[Step 4] Generating presigned GET URL (valid for 300s)...")
    presigned_url = await get_presigned_url(storage_key, expiry_seconds=300)
    print("[+] Presigned URL generated successfully:")
    print(f"\n    {presigned_url}\n")
    print("=" * 65)
    print("MODULE 5 STORAGE VERIFICATION COMPLETE")
    print("=" * 65)


def main() -> None:
    """Entry point for standalone execution."""
    asyncio.run(run_storage_test())


if __name__ == "__main__":
    main()
