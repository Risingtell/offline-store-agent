# SPDX-License-Identifier: Apache-2.0
"""Tests for the agent service routing and the live stdlib HTTP server."""

from __future__ import annotations

import json
import threading
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

from offline_store_agent.server import make_server
from offline_store_agent.service import StoreAgentService


class TestRouting:
    def test_health_reports_ok(self) -> None:
        service = StoreAgentService(seed_demo=True)
        status, payload = service.handle("GET", "/health", {})
        assert status == 200
        assert payload["status"] == "ok"
        assert payload["records"] == 3

    def test_root_is_reachable(self) -> None:
        # The skills page pings the root URL; it must answer 200.
        status, _ = StoreAgentService().handle("GET", "/", {})
        assert status == 200

    def test_ask_requires_question(self) -> None:
        status, payload = StoreAgentService().handle("POST", "/ask", {})
        assert status == 400
        assert "question" in payload["error"]

    def test_ask_answers(self) -> None:
        service = StoreAgentService(seed_demo=True)
        status, payload = service.handle("POST", "/ask", {"question": "what's low?"})
        assert status == 200
        assert payload["tool"] == "low_stock"

    def test_records_validation(self) -> None:
        status, _ = StoreAgentService().handle("POST", "/records", {"id": "x"})
        assert status == 400

    def test_put_then_query_record(self) -> None:
        service = StoreAgentService()
        status, _ = service.handle(
            "POST", "/records", {"id": "item-9", "fields": {"name": "Salt", "stock": 1}}
        )
        assert status == 200
        _, payload = service.handle("POST", "/ask", {"question": "what's running low?"})
        assert payload["data"][0]["name"] == "Salt"

    def test_unknown_route_404(self) -> None:
        status, _ = StoreAgentService().handle("GET", "/nope", {})
        assert status == 404


class TestStateSync:
    def test_state_round_trips_between_hubs(self) -> None:
        # One hub seeds + edits; another merges its exported state.
        hub_a = StoreAgentService(node_id="a", seed_demo=True)
        hub_b = StoreAgentService(node_id="b")
        _, state = hub_a.handle("GET", "/state", {})
        status, payload = hub_b.handle("POST", "/sync", {"state": state["state"]})
        assert status == 200
        assert payload["records"] == 3


@pytest.fixture
def live_base_url() -> Iterator[str]:
    """Run the agent on an ephemeral port in a background thread."""
    httpd = make_server(StoreAgentService(seed_demo=True), host="127.0.0.1", port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _get(url: str) -> tuple[int, dict[str, Any]]:
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 - localhost test
        return resp.status, json.loads(resp.read())


def _post(url: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    req = urllib.request.Request(  # noqa: S310 - localhost test
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.status, json.loads(resp.read())


class TestLiveServer:
    def test_health_endpoint(self, live_base_url: str) -> None:
        status, payload = _get(f"{live_base_url}/health")
        assert status == 200
        assert payload["status"] == "ok"

    def test_ask_endpoint(self, live_base_url: str) -> None:
        status, payload = _post(f"{live_base_url}/ask", {"question": "anything low on stock?"})
        assert status == 200
        assert payload["tool"] == "low_stock"
        assert "low on stock" in payload["answer"]
