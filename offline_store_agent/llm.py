# SPDX-License-Identifier: Apache-2.0
"""LLM backends for the store agent: a deterministic mock and a Gemini backend.

The agent is *tool-using*: a backend picks one of the agent's tools for a
question (:meth:`LLMBackend.choose`) and then phrases the tool's structured
result in natural language (:meth:`LLMBackend.summarize`).

:class:`MockLLMBackend` needs no API key and is fully deterministic, so tests
and offline demos run without secrets — satisfying the hackathon rule that any
hosted-secret backend must ship a deterministic fallback. :class:`GeminiBackend`
calls Google's free Generative Language REST API using only the standard library.

Example::

    agent = StoreAgent(store, llm=MockLLMBackend())
    agent.ask("what did I sell while we were offline?")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# Filler/keyword tokens stripped when guessing the item name in a question.
_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "for",
        "do",
        "i",
        "we",
        "is",
        "are",
        "there",
        "have",
        "has",
        "how",
        "many",
        "much",
        "left",
        "in",
        "stock",
        "price",
        "what",
        "whats",
        "what's",
        "my",
        "any",
        "got",
        "remaining",
        "currently",
        "and",
        "to",
        "on",
        "at",
        "now",
    }
)


@dataclass
class ToolSpec:
    """A tool the agent exposes, described for the backend to choose from.

    Example::

        ToolSpec("low_stock", "Items at or below a reorder threshold.")
    """

    name: str
    description: str


@dataclass
class ToolCall:
    """A backend's decision: which tool to run, with optional string args.

    Example::

        ToolCall("stock_of", {"query": "rice"})
    """

    tool: str
    args: dict[str, str] = field(default_factory=dict[str, str])


@runtime_checkable
class LLMBackend(Protocol):
    """Chooses a tool for a question and phrases the tool's result.

    Example::

        backend: LLMBackend = MockLLMBackend()
    """

    def choose(self, question: str, tools: list[ToolSpec]) -> ToolCall:
        """Pick the tool that best answers *question*.

        Example::

            call = backend.choose("what's low on stock?", tools)
        """
        ...

    def summarize(self, question: str, tool: str, data: Any) -> str:
        """Render the structured *data* from *tool* as a natural-language reply.

        Example::

            text = backend.summarize(question, "low_stock", rows)
        """
        ...


def _guess_query(question: str) -> str:
    """Best-effort extraction of an item name from a question."""
    cleaned = question.lower().replace("?", " ").replace("'", "'")
    tokens = [t for t in cleaned.split() if t not in _STOPWORDS]
    return " ".join(tokens).strip()


class MockLLMBackend:
    """Deterministic, key-free backend: keyword routing and templated phrasing.

    Example::

        backend = MockLLMBackend()
        backend.choose("anything running low?", [])
    """

    def choose(self, question: str, tools: list[ToolSpec]) -> ToolCall:
        """Route *question* to a tool by keyword, deterministically.

        Example::

            backend.choose("what did I sell offline?", [])
        """
        q = question.lower()
        if any(
            k in q
            for k in (
                "offline",
                "while the network",
                "while we were down",
                "since last sync",
                "didn't sync",
                "did not sync",
                "pending",
                "unsynced",
                "network was down",
                "sync",
                "reconcile",
            )
        ):
            return ToolCall("offline_changes")
        if any(
            k in q for k in ("low", "running out", "reorder", "restock", "almost out", "run out")
        ):
            return ToolCall("low_stock")
        if any(
            k in q for k in ("sold", "sell", "sales", "revenue", "takings", "earn", "made today")
        ):
            return ToolCall("sales_summary")
        if any(k in q for k in ("stock", "how many", "price", "left", "have", "cost")):
            return ToolCall("stock_of", {"query": _guess_query(q)})
        return ToolCall("list_inventory")

    def summarize(self, question: str, tool: str, data: Any) -> str:
        """Phrase the tool result with a fixed, deterministic template.

        Example::

            backend.summarize("...", "sales_summary", {"count": 1, "total": 3000})
        """
        if tool == "offline_changes":
            rows: list[dict[str, Any]] = data
            if not rows:
                return "Nothing is waiting to sync — every change is reconciled."
            lines = [f"- {r['action']} {r['record']}: {r['fields']}" for r in rows]
            return f"While offline you made {len(rows)} change(s):\n" + "\n".join(lines)
        if tool == "low_stock":
            rows = data
            if not rows:
                return "Nothing is low on stock."
            lines = [f"- {r['name']}: {r['stock']} left" for r in rows]
            return f"{len(rows)} item(s) low on stock:\n" + "\n".join(lines)
        if tool == "sales_summary":
            summary: dict[str, Any] = data
            return f"You recorded {summary['count']} sale(s) totalling {summary['total']}."
        if tool == "stock_of":
            rows = data
            if not rows:
                return "No matching item found."
            lines = [f"- {r['name']}: {r['stock']} in stock at {r['price']}" for r in rows]
            return "\n".join(lines)
        rows = data
        if not rows:
            return "The inventory is empty."
        lines = [f"- {r['name']}: {r['stock']} in stock at {r['price']}" for r in rows]
        return f"You have {len(rows)} item(s):\n" + "\n".join(lines)


class GeminiBackend:
    """Free Gemini backend over the Generative Language REST API (stdlib only).

    Reads the API key from ``GEMINI_API_KEY``. Used only when wired in explicitly;
    the agent defaults to :class:`MockLLMBackend` so no key is needed for tests.

    Example::

        agent = StoreAgent(store, llm=GeminiBackend())
    """

    _ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None) -> None:
        """Create a Gemini backend, falling back to ``GEMINI_API_KEY`` for the key.

        Example::

            backend = GeminiBackend(model="gemini-2.5-flash")
        """
        self._model = model
        # Strip whitespace and any stray BOM (env vars set via some shells gain a
        # leading U+FEFF, which would make the request URL non-ASCII).
        raw_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self._api_key = raw_key.replace("﻿", "").strip()

    def choose(self, question: str, tools: list[ToolSpec]) -> ToolCall:
        """Ask Gemini to name the tool that answers *question*.

        Example::

            backend.choose("what's low?", tools)
        """
        menu = "\n".join(f"- {t.name}: {t.description}" for t in tools)
        prompt = (
            "You route a shopkeeper's question to exactly one tool.\n"
            f"Tools:\n{menu}\n\n"
            f'Question: "{question}"\n'
            'Reply with only JSON: {"tool": "<name>", "args": {"query": "<item or empty>"}}'
        )
        try:
            raw = (
                self._generate(prompt)
                .strip()
                .removeprefix("```json")
                .removeprefix("```")
                .removesuffix("```")
            )
            parsed: dict[str, Any] = json.loads(raw)
            raw_args: dict[str, Any] = parsed.get("args") or {}
            return ToolCall(str(parsed["tool"]), {str(k): str(v) for k, v in raw_args.items()})
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Missing key, network failure, or unparseable reply: fall back to the mock.
            return MockLLMBackend().choose(question, tools)

    def summarize(self, question: str, tool: str, data: Any) -> str:
        """Ask Gemini to phrase the tool result for the shopkeeper.

        Example::

            backend.summarize(question, "low_stock", rows)
        """
        prompt = (
            "You are a concise shop assistant. Answer the question using only the data.\n"
            f'Question: "{question}"\n'
            f"Data (JSON): {json.dumps(data)}\n"
            "Reply in one or two short sentences."
        )
        try:
            return self._generate(prompt).strip()
        except (urllib.error.URLError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            # Missing key, network failure, or unparseable reply: fall back to the mock.
            return MockLLMBackend().summarize(question, tool, data)

    def _generate(self, prompt: str) -> str:
        """Call the Gemini REST API and return the first text candidate."""
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        url = self._ENDPOINT.format(model=self._model) + f"?key={self._api_key}"
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - https endpoint, fixed host
            url, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
            payload: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
        return payload["candidates"][0]["content"]["parts"][0]["text"]
