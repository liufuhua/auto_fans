from __future__ import annotations

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")

MAX_LOG_BODY_BYTES = 4096


class RequestResponseLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_body = bytearray()
        response_body = bytearray()
        status_code: int | None = None
        started_at = perf_counter()

        async def receive_wrapper() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body and len(request_body) < MAX_LOG_BODY_BYTES:
                    request_body.extend(body[: MAX_LOG_BODY_BYTES - len(request_body)])
            return message

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body and len(response_body) < MAX_LOG_BODY_BYTES:
                    response_body.extend(body[: MAX_LOG_BODY_BYTES - len(response_body)])
            await send(message)

        try:
            await self.app(scope, receive_wrapper, send_wrapper)
        finally:
            elapsed_ms = (perf_counter() - started_at) * 1000
            logger.info(
                "request method=%s path=%s query=%s status=%s elapsedMs=%.2f "
                "requestBody=%s responseBody=%s",
                scope["method"],
                scope["path"],
                scope.get("query_string", b"").decode("utf-8", errors="replace"),
                status_code,
                elapsed_ms,
                _decode_body(request_body),
                _decode_body(response_body),
            )


def _decode_body(body: bytearray) -> str:
    if not body:
        return ""
    value = bytes(body).decode("utf-8", errors="replace")
    if len(body) >= MAX_LOG_BODY_BYTES:
        return f"{value}...<truncated>"
    return value
