# SPDX-License-Identifier: Apache-2.0
"""Vercel serverless entrypoint for the offline-first store agent.

Vercel's Python runtime serves the module-level ``handler`` (a
``BaseHTTPRequestHandler`` subclass), so the same service logic used by the
stdlib server and the NANDA adapter also backs the hosted endpoint.

Routes (via the rewrite in ``vercel.json``): ``GET /`` and ``/health`` for the
reachability check, ``POST /ask`` to query the agent, plus ``/records``,
``/sync`` and ``/state``.
"""

from __future__ import annotations

import os
import sys

# api/ lives one level below the repo root; make the package importable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from offline_store_agent.llm import GeminiBackend  # noqa: E402
from offline_store_agent.server import make_handler  # noqa: E402
from offline_store_agent.service import StoreAgentService  # noqa: E402

# A fresh, demo-seeded hub per cold start; Gemini falls back to the mock with no key.
_service = StoreAgentService(node_id="vercel-hub", llm=GeminiBackend(), seed_demo=True)
handler = make_handler(_service)
