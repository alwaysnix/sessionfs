"""Global exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sessionfs.server.schemas.errors import ErrorDetail, ErrorResponse


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the app."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if isinstance(exc.detail, dict):
            body = ErrorResponse(
                error=ErrorDetail(
                    code=exc.detail.get("code", str(exc.status_code)),
                    message=exc.detail.get("message", "Error"),
                    details={
                        k: v
                        for k, v in exc.detail.items()
                        if k not in ("code", "message")
                    },
                )
            )
        else:
            body = ErrorResponse(
                error=ErrorDetail(
                    code=str(exc.status_code),
                    message=str(exc.detail),
                )
            )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        body = ErrorResponse(
            error=ErrorDetail(
                code="422",
                message="Validation error",
                details={"errors": exc.errors()},
            )
        )
        return JSONResponse(status_code=422, content=body.model_dump())
