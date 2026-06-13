# SPDX-License-Identifier: Apache-2.0
"""Tests for the StoreAgent against the deterministic mock backend."""

from __future__ import annotations

import pytest

from offline_store_agent.agent import StoreAgent
from offline_store_agent.llm import MockLLMBackend, ToolCall
from offline_store_agent.store import OfflineStore


def _stocked_store() -> OfflineStore:
    store = OfflineStore(node_id="till")
    store.put("item-7", {"name": "Rice 5kg", "price": 1500, "stock": 10})
    store.put("item-8", {"name": "Sugar 1kg", "price": 800, "stock": 3})
    store.put("item-9", {"name": "Milk", "price": 600, "stock": 0})
    return store


class TestRouting:
    @pytest.mark.parametrize(
        ("question", "expected_tool"),
        [
            ("what did I sell while we were offline?", "offline_changes"),
            ("anything running low?", "low_stock"),
            ("how much did I sell today?", "sales_summary"),
            ("how many bags of rice are left?", "stock_of"),
            ("anything still waiting to sync?", "offline_changes"),
            ("show me everything", "list_inventory"),
        ],
    )
    def test_keyword_routing(self, question: str, expected_tool: str) -> None:
        call = MockLLMBackend().choose(question, [])
        assert call.tool == expected_tool


class TestTools:
    def test_low_stock_finds_depleted_items(self) -> None:
        agent = StoreAgent(_stocked_store())
        reply = agent.ask("what's running low?")
        assert reply.tool == "low_stock"
        names = {row["name"] for row in reply.data}
        assert names == {"Sugar 1kg", "Milk"}  # 3 and 0 are <= 5; Rice (10) is not

    def test_stock_of_matches_by_name(self) -> None:
        agent = StoreAgent(_stocked_store())
        reply = agent.ask("how many rice do I have?")
        assert reply.tool == "stock_of"
        assert len(reply.data) == 1
        assert reply.data[0]["name"] == "Rice 5kg"
        assert reply.data[0]["stock"] == 10

    def test_stock_of_matches_despite_filler_words(self) -> None:
        # "how many bags of rice do I have?" must still find the rice item.
        agent = StoreAgent(_stocked_store())
        reply = agent.ask("how many bags of rice do I have?")
        assert reply.tool == "stock_of"
        assert [row["name"] for row in reply.data] == ["Rice 5kg"]

    def test_sales_summary_totals_sales(self) -> None:
        store = _stocked_store()
        store.put("sale-1", {"item": "Rice 5kg", "qty": 2, "total": 3000})
        store.put("sale-2", {"item": "Milk", "qty": 1, "total": 600})
        reply = StoreAgent(store).ask("what were today's takings?")
        assert reply.tool == "sales_summary"
        assert reply.data == {"count": 2, "total": 3600}

    def test_offline_changes_lists_pending(self) -> None:
        store = OfflineStore(node_id="till", online=False)
        store.put("sale-1", {"item": "Rice 5kg", "qty": 1, "total": 1500})
        store.put("item-7", {"stock": 4})
        reply = StoreAgent(store).ask("what changed while the network was down?")
        assert reply.tool == "offline_changes"
        assert len(reply.data) == 2
        assert "While offline you made 2 change(s)" in reply.answer

    def test_offline_changes_empty_after_sync(self) -> None:
        till = OfflineStore(node_id="till")
        phone = OfflineStore(node_id="phone")
        till.put("item-7", {"name": "Rice 5kg", "stock": 10})
        till.sync(phone)
        reply = StoreAgent(till).ask("anything still offline?")
        assert reply.data == []
        assert "Nothing is waiting to sync" in reply.answer


class TestReconciledView:
    def test_agent_sees_reconciled_state_after_sync(self) -> None:
        till = OfflineStore(node_id="till")
        phone = OfflineStore(node_id="phone")
        till.put("item-7", {"name": "Rice 5kg", "price": 1500, "stock": 12})
        till.sync(phone)

        # Offline edits on both devices to different fields.
        till.put("item-7", {"stock": 2})
        phone.put("item-7", {"price": 1400})
        till.sync(phone)

        reply = StoreAgent(till).ask("how much rice is left?")
        assert reply.data[0]["stock"] == 2
        assert reply.data[0]["price"] == 1400


class TestDeterminism:
    def test_same_question_same_answer(self) -> None:
        agent = StoreAgent(_stocked_store())
        first = agent.ask("what's low on stock?")
        second = agent.ask("what's low on stock?")
        assert first.answer == second.answer
        assert first.data == second.data


class TestMockSummaries:
    def test_unknown_tool_falls_back_to_inventory_phrasing(self) -> None:
        # An empty inventory listing renders a friendly message, not a crash.
        agent = StoreAgent(OfflineStore(node_id="till"))
        reply = agent.ask("show me everything")
        assert reply.tool == "list_inventory"
        assert reply.answer == "The inventory is empty."

    def test_choose_default_is_list_inventory(self) -> None:
        call: ToolCall = MockLLMBackend().choose("hello there", [])
        assert call.tool == "list_inventory"
