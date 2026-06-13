# SPDX-License-Identifier: Apache-2.0
"""Hosting entrypoint for the offline-first store agent.

On a server with the NANDA adapter installed this registers the agent into the
NANDA network (A2A endpoint + AgentFacts). Without the adapter — e.g. local
development — it falls back to the dependency-free stdlib HTTP server, so the
exact same agent logic is reachable either way.

Run locally::

    uv run python nanda_app.py            # stdlib server on :6000

Run on the host (adapter installed)::

    DOMAIN_NAME=agent.example.org GEMINI_API_KEY=... python3 nanda_app.py
"""

from __future__ import annotations

import importlib
import os
from typing import TYPE_CHECKING

from offline_store_agent.llm import GeminiBackend
from offline_store_agent.service import StoreAgentService

if TYPE_CHECKING:
    from collections.abc import Callable


def build_service() -> StoreAgentService:
    """Create the hosted service backed by free Gemini, seeded with demo stock.

    Example::

        service = build_service()
    """
    return StoreAgentService(node_id="hub", llm=GeminiBackend(), seed_demo=True)


def agent_logic(service: StoreAgentService) -> Callable[[str], str]:
    """Adapt the agent to the NANDA ``message_text -> reply_text`` contract.

    Example::

        improve = agent_logic(build_service())
        improve("what's running low?")
    """

    def improvement(message_text: str) -> str:
        return service.agent.ask(message_text).answer

    return improvement


def main() -> None:
    """Run via the NANDA adapter if installed, else the stdlib HTTP server."""
    service = build_service()
    try:
        nanda_module = importlib.import_module("nanda_adapter")
    except ImportError:
        from offline_store_agent.server import serve

        port = int(os.environ.get("PORT", "6000"))
        print(f"nanda_adapter not installed — serving stdlib HTTP agent on :{port}")
        serve(service, port=port)
        return

    domain = os.environ.get("DOMAIN_NAME", "")
    # The adapter's start_server_api takes an Anthropic key for its own features;
    # our agent logic reasons with Gemini, so an empty key is fine here.
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    nanda = nanda_module.NANDA(agent_logic(service))
    nanda.start_server_api(anthropic_key, domain)


if __name__ == "__main__":
    main()
