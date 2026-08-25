"""Same-origin React delivery for the Databricks App process."""

from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_MAX_REQUEST_BYTES = 20 * 1024 * 1024
_RESERVED_TOP_LEVEL_PATHS = frozenset({"api", "docs", "healthz", "openapi.json", "readyz", "redoc"})


class RequestBodyLimitMiddleware:
    """Reject request bodies larger than the former NGINX boundary."""

    def __init__(self, app: ASGIApp, *, maximum_bytes: int = _MAX_REQUEST_BYTES) -> None:
        self._app = app
        self._maximum_bytes = maximum_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope.get("headers", ())
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                declared_bytes = int(content_length)
            except ValueError:
                declared_bytes = self._maximum_bytes + 1
            if declared_bytes < 0 or declared_bytes > self._maximum_bytes:
                await _payload_too_large(send)
                return

        received_bytes = 0
        response_started = False

        async def bounded_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self._maximum_bytes:
                    raise _RequestBodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self._app(scope, bounded_receive, tracked_send)
        except _RequestBodyTooLargeError:
            if response_started:
                raise
            await _payload_too_large(send)


class SecurityHeadersMiddleware:
    """Apply the browser boundary previously owned by NGINX."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = cast(
                    list[tuple[bytes, bytes]],
                    message.setdefault("headers", []),
                )
                present = {name.lower() for name, _ in headers}
                for name, value in (
                    (b"content-security-policy", _content_security_policy()),
                    (b"referrer-policy", b"same-origin"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                ):
                    if name not in present:
                        headers.append((name, value))
            await send(message)

        await self._app(scope, receive, send_with_headers)


class ImmutableStaticFiles(StaticFiles):
    """Serve Vite-hashed assets with durable browser caching."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == status.HTTP_200_OK:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_frontend(app: FastAPI, directory: Path) -> None:
    """Mount built React assets and a final client-side routing fallback."""
    frontend_directory = directory.resolve()
    index_path = frontend_directory / "index.html"
    assets_path = frontend_directory / "assets"
    if not index_path.is_file() or not assets_path.is_dir():
        raise RuntimeError("the built React frontend is unavailable")

    app.mount(
        "/assets",
        ImmutableStaticFiles(directory=assets_path, check_dir=True),
        name="frontend-assets",
    )

    async def spa_fallback(full_path: str) -> FileResponse:
        top_level = full_path.partition("/")[0]
        if top_level in _RESERVED_TOP_LEVEL_PATHS:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return FileResponse(
            index_path,
            media_type="text/html",
            headers={"Cache-Control": "no-cache"},
        )

    app.add_api_route(
        "/{full_path:path}",
        spa_fallback,
        methods=["GET", "HEAD"],
        include_in_schema=False,
    )


class _RequestBodyTooLargeError(Exception):
    pass


async def _payload_too_large(send: Send) -> None:
    body = b'{"detail":"Request body is too large."}'
    await send(
        {
            "type": "http.response.start",
            "status": status.HTTP_413_CONTENT_TOO_LARGE,
            "headers": [
                (b"content-length", str(len(body)).encode("ascii")),
                (b"content-type", b"application/json"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def _content_security_policy() -> bytes:
    return (
        b"default-src 'self'; base-uri 'self'; connect-src 'self'; "
        b"font-src 'self' data:; form-action 'self'; frame-ancestors 'none'; "
        b"img-src 'self' data:; object-src 'none'; script-src 'self'; "
        b"style-src 'self' 'unsafe-inline'"
    )


__all__ = [
    "RequestBodyLimitMiddleware",
    "SecurityHeadersMiddleware",
    "mount_frontend",
]
