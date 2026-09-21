"""Exception handlers: every error leaves the API in one consistent JSON shape.

    {"error": {"code": "...", "message": "...", "details": [...]}}

Server-side failures (5xx) are logged with context; their internal details are
never sent to the client.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.collectors.snapshot import CollectionError
from app.models import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int, code: str, message: str, details: list[ErrorDetail] | None = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def _code_for_status(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        return f"http_{status_code}"


async def collection_error_handler(request: Request, exc: CollectionError) -> JSONResponse:
    logger.error(
        "metric_collection_failed",
        exc_info=exc,
        extra={"collector": exc.collector, "method": request.method, "path": request.url.path},
    )
    return _error_response(
        503, "collection_failed", f"Failed to collect {exc.collector} metrics. Try again shortly."
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        ErrorDetail(field=".".join(str(part) for part in err["loc"]), message=err["msg"])
        for err in exc.errors()
    ]
    return _error_response(422, "validation_error", "Request validation failed.", details)


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    response = _error_response(exc.status_code, _code_for_status(exc.status_code), str(exc.detail))
    if exc.headers:  # e.g. "Allow" on 405
        response.headers.update(exc.headers)
    return response


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "api_error",
        exc_info=exc,
        extra={"method": request.method, "path": request.url.path},
    )
    return _error_response(500, "internal_error", "Internal server error.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CollectionError, collection_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_error_handler)
