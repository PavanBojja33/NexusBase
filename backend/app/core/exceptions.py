"""
app/core/exceptions.py
──────────────────────
Centralised error handling for the NexusBase API.

Design principles:
  - All intentional API errors are raised as `ApiError`.  Routes and services
    never return raw HTTPException or call `raise` with ad-hoc status codes.
  - The global `api_error_handler` converts every `ApiError` into the
    uniform envelope `{"error": "<message>"}`, which is the contract the
    frontend and Swagger docs expect.
  - Keeping the shape consistent means the frontend only needs one error-
    parsing branch regardless of which endpoint produced the error.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ApiError(HTTPException):
    """A structured API error that carries an HTTP status code and a
    human-readable message.

    Usage:
        raise ApiError(404, "User not found")
        raise ApiError(409, "Email already registered")
        raise ApiError(401, "Invalid credentials")
    """

    def __init__(self, status_code: int, message: str) -> None:
        # Pass message as `detail` so FastAPI's default handler still works
        # if our custom handler is ever bypassed (e.g. in tests).
        super().__init__(status_code=status_code, detail=message)
        self.message = message


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    """FastAPI exception handler for `ApiError`.

    Registered in main.py via:
        app.add_exception_handler(ApiError, api_error_handler)

    Returns the canonical error envelope:
        HTTP <status_code>
        Content-Type: application/json
        {"error": "<message>"}
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message},
    )
