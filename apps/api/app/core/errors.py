"""RFC 7807 problem details for every error the API returns."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemError(Exception):
    status: int = 500
    title: str = "Internal Server Error"

    def __init__(
        self,
        detail: str | None = None,
        *,
        title: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        if title:
            self.title = title
        self.headers = headers
        self.extra = extra


class UnauthorizedError(ProblemError):
    status, title = 401, "Unauthorized"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(ProblemError):
    status, title = 403, "Forbidden"


class NotFoundError(ProblemError):
    status, title = 404, "Not Found"


class ConflictError(ProblemError):
    status, title = 409, "Conflict"


class UnprocessableError(ProblemError):
    status, title = 422, "Unprocessable Entity"


class LockedError(ProblemError):
    status, title = 423, "Locked"


class BadGatewayError(ProblemError):
    status, title = 502, "Bad Gateway"


class ServiceUnavailableError(ProblemError):
    status, title = 503, "Service Unavailable"


class GatewayTimeoutError(ProblemError):
    status, title = 504, "Gateway Timeout"


def problem_response(
    request: Request,
    status: int,
    title: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "instance": request.url.path,
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(jsonable_encoder(body), status_code=status, headers=headers, media_type=PROBLEM_MEDIA_TYPE)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        return problem_response(request, exc.status, exc.title, exc.detail, exc.headers, **exc.extra)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem_response(request, 422, "Unprocessable Entity", "Request validation failed", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(request, exc.status_code, str(exc.detail), headers=dict(exc.headers or {}))

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError) -> JSONResponse:
        sqlstate = getattr(exc.orig, "sqlstate", None)
        if sqlstate == "23505":
            return problem_response(request, 409, "Conflict", "A resource with the same key already exists")
        if sqlstate == "23503":
            return problem_response(request, 422, "Unprocessable Entity", "A referenced resource does not exist")
        log.exception("integrity error", exc_info=exc)
        return problem_response(request, 409, "Conflict", "The request conflicts with stored data")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return problem_response(request, 500, "Internal Server Error")
