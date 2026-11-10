from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_BASE = "https://miap.local/problems"


class AppError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.headers = headers or {}


def problem_body(status: int, code: str, title: str, detail: str | None, path: str) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}/{code}",
        "code": code,
        "title": title,
        "status": status,
        "instance": path,
    }
    if detail:
        body["detail"] = detail
    return body


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            problem_body(exc.status, exc.code, exc.title, exc.detail, request.url.path),
            status_code=exc.status,
            media_type="application/problem+json",
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        body = problem_body(
            422, "validation_error", "Request failed validation", None, request.url.path
        )
        body["errors"] = [
            {"loc": list(err.get("loc", [])), "msg": err.get("msg", ""), "type": err.get("type", "")}
            for err in exc.errors()
        ]
        return JSONResponse(body, status_code=422, media_type="application/problem+json")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        return JSONResponse(
            problem_body(exc.status_code, "http_error", str(exc.detail), detail, request.url.path),
            status_code=exc.status_code,
            media_type="application/problem+json",
        )
