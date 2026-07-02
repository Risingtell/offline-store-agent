# Offline-first Store Agent

An LLM agent for low-connectivity shops (built for the MIT NANDA hackathon). Shop
records — sales, inventory — are edited **offline-first** on any device and
reconciled **conflict-free** when connectivity returns, using a field-level
Last-Writer-Wins CRDT. The agent then answers plain-language questions over the
reconciled state ("what did I sell while the network was down?").

The reconciliation engine is a self-contained field-level LWW-Map CRDT (see
`offline_store_agent/crdt.py`) — the same conflict-free coordination primitive
that NANDA Town is built around, implemented here from scratch for the offline
store domain.

**Live agent:** https://rising-store-agent.vercel.app
**Demo video:** https://youtu.be/unQR-vIBs1A

## Layout

- `offline_store_agent/crdt.py` — field-level LWW-Map CRDT store (the engine).
- `offline_store_agent/store.py` — offline-first store: local edits, a pending
  journal, and conflict-free sync.

## Develop

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q
```
