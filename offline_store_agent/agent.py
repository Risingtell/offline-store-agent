# SPDX-License-Identifier: Apache-2.0
"""The offline-first store agent: natural-language questions over reconciled state.

:class:`StoreAgent` wraps an :class:`~offline_store_agent.store.OfflineStore` with
a set of deterministic *tools* (inventory lookups, low-stock checks, sales totals,
and the offline-change journal). An :class:`~offline_store_agent.llm.LLMBackend`
chooses which tool a question needs and phrases the result; the data itself is
always computed deterministically from the CRDT-reconciled store.

Example::

    agent = StoreAgent(store)                       # defaults to the mock backend
    reply = agent.ask("what did I sell while offline?")
    print(reply.answer)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from offline_store_agent.llm import LLMBackend, MockLLMBackend, ToolSpec

if TYPE_CHECKING:
    from offline_store_agent.store import OfflineStore

_LOW_STOCK_DEFAULT = 5

_TOOLS = [
    ToolSpec("offline_changes", "Edits made on this device that have not yet synced."),
    ToolSpec("low_stock", "Inventory items at or below the reorder threshold."),
    ToolSpec("sales_summary", "Count and total value of recorded sales."),
    ToolSpec("stock_of", "Stock and price of items matching a name (arg: query)."),
    ToolSpec("list_inventory", "Every inventory item with its stock and price."),
]


@dataclass
class AgentReply:
    """An answer plus the tool and structured data behind it (for transparency).

    Example::

        reply = agent.ask("anything low?")
        reply.tool, reply.data
    """

    answer: str
    tool: str
    data: Any


class StoreAgent:
    """Answers plain-language questions about a reconciled offline-first store.

    Example::

        agent = StoreAgent(store)
        agent.ask("how many bags of rice are left?")
    """

    def __init__(self, store: OfflineStore, llm: LLMBackend | None = None) -> None:
        """Wrap *store* with an agent, defaulting to the key-free mock backend.

        Example::

            agent = StoreAgent(store, llm=GeminiBackend())
        """
        self._store = store
        self._llm = llm or MockLLMBackend()

    def ask(self, question: str) -> AgentReply:
        """Answer *question*: choose a tool, run it, and phrase the result.

        Example::

            agent.ask("what changed while the network was down?")
        """
        call = self._llm.choose(question, _TOOLS)
        data = self._dispatch(call.tool, call.args)
        answer = self._llm.summarize(question, call.tool, data)
        return AgentReply(answer=answer, tool=call.tool, data=data)

    # -- tools ---------------------------------------------------------------

    def _dispatch(self, tool: str, args: dict[str, str]) -> Any:
        """Run the named tool, falling back to the inventory listing."""
        if tool == "offline_changes":
            return self._offline_changes()
        if tool == "low_stock":
            return self._low_stock()
        if tool == "sales_summary":
            return self._sales_summary()
        if tool == "stock_of":
            return self._stock_of(args.get("query", ""))
        return self._list_inventory()

    def _offline_changes(self) -> list[dict[str, Any]]:
        """Pending (unsynced) edits, as plain dicts."""
        return [
            {"action": e.action, "record": e.record_id, "fields": e.fields}
            for e in self._store.pending()
        ]

    def _list_inventory(self) -> list[dict[str, Any]]:
        """Every live inventory item (records carrying a stock or price field)."""
        items: list[dict[str, Any]] = []
        for record_id, fields in sorted(self._store.all().items()):
            if "stock" in fields or "price" in fields:
                items.append(
                    {
                        "id": record_id,
                        "name": fields.get("name", record_id),
                        "stock": fields.get("stock"),
                        "price": fields.get("price"),
                    }
                )
        return items

    def _low_stock(self, threshold: int = _LOW_STOCK_DEFAULT) -> list[dict[str, Any]]:
        """Inventory items whose stock is at or below *threshold*."""
        low: list[dict[str, Any]] = []
        for item in self._list_inventory():
            stock = item["stock"]
            if isinstance(stock, int) and stock <= threshold:
                low.append(item)
        return low

    def _stock_of(self, query: str) -> list[dict[str, Any]]:
        """Inventory items whose name contains *query* (case-insensitive)."""
        tokens = [t for t in query.strip().lower().split() if t]
        if not tokens:
            return self._list_inventory()
        return [
            item
            for item in self._list_inventory()
            if any(tok in str(item["name"]).lower() for tok in tokens)
        ]

    def _sales_summary(self) -> dict[str, Any]:
        """Count and total value of sale records (those with qty and total fields)."""
        count = 0
        total = 0
        for fields in self._store.all().values():
            if "qty" in fields and "total" in fields:
                count += 1
                amount = fields.get("total")
                if isinstance(amount, int):
                    total += amount
        return {"count": count, "total": total}
