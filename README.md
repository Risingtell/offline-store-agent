# Offline-first Store Agent

A **conflict-free offline-sync layer for agents** (built for the MIT NANDA
hackathon). Any agent or device can edit shared state while fully disconnected
and reconcile it **without conflict** when connectivity returns, using a
field-level Last-Writer-Wins CRDT — concurrent edits to *different fields of the
same record* all survive, independent of sync order. It's the conflict-free
coordination primitive NANDA Town is built around (see
`offline_store_agent/crdt.py`), exposed over HTTP as a reusable building block.

Shipped on top is a **low-connectivity shop agent** as the reference application:
shop records — sales, inventory — are edited offline on any device, reconciled on
reconnect, and the agent answers plain-language questions over the reconciled
state ("what did I sell while the network was down?").

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
