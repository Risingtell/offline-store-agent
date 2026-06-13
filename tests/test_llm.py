# SPDX-License-Identifier: Apache-2.0
"""Tests for LLM backend fallback behaviour."""

from __future__ import annotations

from offline_store_agent.agent import StoreAgent
from offline_store_agent.llm import GeminiBackend
from offline_store_agent.store import OfflineStore


class TestGeminiFallback:
    def test_choose_falls_back_without_key(self) -> None:
        # No API key -> choose must not raise; it falls back to the mock router.
        backend = GeminiBackend(api_key="")
        call = backend.choose("anything running low?", [])
        assert call.tool == "low_stock"

    def test_summarize_falls_back_without_key(self) -> None:
        backend = GeminiBackend(api_key="")
        text = backend.summarize("how much did I sell?", "sales_summary", {"count": 1, "total": 50})
        assert "1 sale(s) totalling 50" in text

    def test_agent_with_gemini_backend_answers_without_key(self) -> None:
        # The whole agent must stay functional with a keyless Gemini backend.
        store = OfflineStore(node_id="till")
        store.put("item-1", {"name": "Rice 5kg", "price": 1500, "stock": 1})
        reply = StoreAgent(store, llm=GeminiBackend(api_key="")).ask("what's low?")
        assert reply.tool == "low_stock"
        assert reply.data[0]["name"] == "Rice 5kg"
