# SPDX-License-Identifier: Apache-2.0
"""Standard-library HTTP server exposing the store agent.

Wraps :class:`StoreAgentService` in a dependency-free ``http.server`` so the
agent is reachable over HTTP from anywhere — including the skills-page
reachability check — without needing the NANDA adapter installed.

Example::

    from offline_store_agent.server import serve
    serve(port=6000)   # blocks, serving the agent
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast

from offline_store_agent.service import StoreAgentService


def make_handler(service: StoreAgentService) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class bound to *service*.

    Example::

        handler = make_handler(StoreAgentService())
    """

    class _Handler(BaseHTTPRequestHandler):
        def _respond(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _dispatch(self, method: str, body: dict[str, Any]) -> None:
            try:
                status, payload = service.handle(method, self.path, body)
            except Exception as exc:  # never drop the connection on an agent error
                status, payload = 500, {"error": "internal error", "detail": str(exc)}
            self._respond(status, payload)

        def do_GET(self) -> None:  # noqa: N802 - http.server callback name
            self._dispatch("GET", {})

        def do_POST(self) -> None:  # noqa: N802 - http.server callback name
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            parsed: Any
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {}
            body = cast("dict[str, Any]", parsed) if isinstance(parsed, dict) else {}
            self._dispatch("POST", body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
            """Silence default request logging."""

    return _Handler


def make_server(
    service: StoreAgentService | None = None,
    host: str = "0.0.0.0",  # noqa: S104 - a hosted agent binds all interfaces by design
    port: int = 6000,
) -> HTTPServer:
    """Create (but do not start) an :class:`HTTPServer` for the agent.

    Example::

        httpd = make_server(port=0)   # port 0 => an ephemeral port, handy in tests
    """
    service = service or StoreAgentService(seed_demo=True)
    return HTTPServer((host, port), make_handler(service))


def serve(
    service: StoreAgentService | None = None,
    host: str = "0.0.0.0",  # noqa: S104 - a hosted agent binds all interfaces by design
    port: int = 6000,
) -> None:
    """Serve the agent forever (blocking).

    Example::

        serve(port=6000)
    """
    make_server(service, host, port).serve_forever()
