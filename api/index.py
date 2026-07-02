# SPDX-License-Identifier: Apache-2.0
"""Vercel serverless entrypoint for the offline-first store agent.

Vercel's Python runtime serves the module-level ``handler`` class. It delegates
to the shared :class:`StoreAgentService`, so the same logic used by the stdlib
server and the NANDA adapter also backs the hosted endpoint.

Routes (the ``vercel.json`` rewrite sends every path here): ``GET /`` and
``/health`` for the reachability check, ``POST /ask`` to query the agent, plus
``/records``, ``/sync`` and ``/state``.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

# api/ lives one level below the repo root; make the package importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from offline_store_agent.llm import GeminiBackend  # noqa: E402
from offline_store_agent.service import StoreAgentService  # noqa: E402

# A fresh, demo-seeded hub per cold start; Gemini falls back to the mock with no key.
_service = StoreAgentService(node_id="vercel-hub", llm=GeminiBackend(), seed_demo=True)


class handler(BaseHTTPRequestHandler):  # noqa: N801 - Vercel requires this exact name
    """Vercel serverless handler delegating to the shared StoreAgentService."""

    def _route(self) -> str:
        """Normalise the request path (strip query and any /api/index prefix)."""
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/index"):
            path = path[len("/api/index") :] or "/"
        return path

    def _respond(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _dispatch(self, method: str, body: dict[str, Any]) -> None:
        try:
            status, payload = _service.handle(method, self._route(), body)
        except Exception as exc:  # never drop the connection on an agent error
            status, payload = 500, {"error": "internal error", "detail": str(exc)}
        self._respond(status, payload)

    def _query_body(self) -> dict[str, Any]:
        """Lift a ``?namespace=`` query param into the request body for GETs."""
        namespace = parse_qs(urlparse(self.path).query).get("namespace", [None])[0]
        return {"namespace": namespace} if namespace else {}

    def do_GET(self) -> None:  # noqa: N802 - http.server callback name
        self._dispatch("GET", self._query_body())

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
