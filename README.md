# Offline-first Store Agent

An LLM agent for low-connectivity shops (built for the MIT NANDA hackathon). Shop
records — sales, inventory — are edited **offline-first** on any device and
reconciled **conflict-free** when connectivity returns, using a field-level
Last-Writer-Wins CRDT. The agent then answers plain-language questions over the
reconciled state ("what did I sell while the network was down?").

The reconciliation engine builds on the LWW-Register CRDT contributed to NANDA
Town (problem 02).

## Layout

- `offline_store_agent/crdt.py` — field-level LWW-Map CRDT store (the engine).
- `offline_store_agent/store.py` — offline-first store: local edits, a pending
  journal, and conflict-free sync.

## Develop

```bash
uv sync
uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest -q
```
