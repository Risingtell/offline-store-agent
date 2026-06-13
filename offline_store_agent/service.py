# SPDX-License-Identifier: Apache-2.0
"""Transport-agnostic request handling for the store agent service.

:class:`StoreAgentService` owns the reconciliation hub's :class:`OfflineStore`
replica and a :class:`StoreAgent`, and turns a ``(method, path, body)`` request
into a ``(status, payload)`` pair. Keeping this independent of any HTTP framework
makes it trivial to unit-test and lets the same logic sit behind the stdlib HTTP
server or the NANDA adapter.

Example::

    service = StoreAgentService(seed_demo=True)
    status, payload = service.handle("POST", "/ask", {"question": "what's low?"})
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from offline_store_agent.agent import StoreAgent
from offline_store_agent.store import OfflineStore

if TYPE_CHECKING:
    from offline_store_agent.crdt import JsonValue
    from offline_store_agent.llm import LLMBackend


class StoreAgentService:
    """A hosted reconciliation hub: merges device state and answers questions.

    Devices POST their CRDT state to ``/sync`` and pull the merged state from
    ``/state``; anyone can ask the agent a question at ``/ask``.

    Example::

        service = StoreAgentService(node_id="hub")
        service.handle("GET", "/health", {})
    """

    def __init__(
        self,
        node_id: str = "hub",
        llm: LLMBackend | None = None,
        *,
        seed_demo: bool = False,
    ) -> None:
        """Create the hub, optionally seeding a small demo inventory.

        Example::

            service = StoreAgentService(seed_demo=True)
        """
        self.store = OfflineStore(node_id=node_id)
        self.agent = StoreAgent(self.store, llm)
        if seed_demo:
            self._seed_demo()

    def handle(self, method: str, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Route one request to a ``(status_code, json_payload)`` pair.

        Example::

            status, payload = service.handle("POST", "/ask", {"question": "hi"})
        """
        route = path.rstrip("/") or "/"
        if method == "GET" and route in ("/", "/health"):
            return 200, {
                "status": "ok",
                "service": "offline-store-agent",
                "records": len(self.store.all()),
            }
        if method == "GET" and route == "/state":
            return 200, {"state": self.store.export_state().decode("utf-8")}
        if method == "POST" and route == "/ask":
            question = body.get("question")
            if not isinstance(question, str) or not question.strip():
                return 400, {"error": "missing 'question'"}
            reply = self.agent.ask(question)
            return 200, {"answer": reply.answer, "tool": reply.tool, "data": reply.data}
        if method == "POST" and route == "/records":
            record_id = body.get("id")
            fields = body.get("fields")
            if not isinstance(record_id, str) or not isinstance(fields, dict):
                return 400, {"error": "need 'id' (string) and 'fields' (object)"}
            self.store.put(record_id, cast("dict[str, JsonValue]", fields))
            return 200, {"ok": True, "id": record_id}
        if method == "POST" and route == "/sync":
            state = body.get("state")
            if not isinstance(state, str):
                return 400, {"error": "need 'state' (string from /state)"}
            self.store.merge_state(state.encode("utf-8"))
            return 200, {"ok": True, "records": len(self.store.all())}
        return 404, {"error": "not found", "path": route}

    def _seed_demo(self) -> None:
        """Seed a tiny shop inventory so a fresh hub has something to answer about."""
        self.store.put("item-1", {"name": "Rice 5kg", "price": 1500, "stock": 12})
        self.store.put("item-2", {"name": "Sugar 1kg", "price": 800, "stock": 4})
        self.store.put("item-3", {"name": "Milk", "price": 600, "stock": 2})
