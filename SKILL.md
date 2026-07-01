# Offline-First Store Agent — SkillMD

**Agent ID:** `rising-store-agent`
**Endpoint:** https://rising-store-agent.vercel.app
**AgentFacts:** https://rising-store-agent.vercel.app/agent.json
**Source:** https://github.com/Risingtell/offline-store-agent
**Author:** Oluwasogo Ajala — Rising Technology (Kano, Nigeria)
**License:** Apache-2.0

## What it does

An LLM agent for **low-connectivity shops in emerging markets**. Shop records —
sales and inventory — are edited **offline-first** on any device and reconciled
**conflict-free** when connectivity returns, using a field-level Last-Writer-Wins
CRDT. The agent then answers plain-language questions over the reconciled state.

Two devices can edit the *same item* while both are offline — one correcting a
price, the other adjusting stock — and **both changes survive** the merge, with no
"last sync wins" data loss. The reconciliation engine builds on the LWW-Register
CRDT contributed to NANDA Town (problem 02).

## Skills

| Skill | Description |
|-------|-------------|
| `offline_changes` | Edits made while offline that have not yet synced. |
| `low_stock` | Inventory items at or below the reorder threshold. |
| `sales_summary` | Count and total value of recorded sales. |
| `stock_of` | Stock and price of items matching a name. |
| `list_inventory` | Every inventory item with its stock and price. |

## How to use it

Ask a question in plain English via `POST /ask`:

```bash
curl -s https://rising-store-agent.vercel.app/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "what should I restock first?"}'
```

```json
{ "answer": "Restock Milk first as it has the lowest stock level of 2.",
  "tool": "low_stock", "data": [ ... ] }
```

Other endpoints:

- `GET /health` — liveness check.
- `GET /agent.json` — machine-readable AgentFacts.
- `POST /records` — `{ "id": "...", "fields": { ... } }` add or update a record.
- `POST /sync` — `{ "state": "..." }` merge a device's CRDT state into the hub.
- `GET /state` — export the hub's reconciled CRDT state for a device to pull.

## Reasoning

Backed by Google Gemini (`gemini-2.5-flash`). A deterministic, key-free fallback
keeps the agent fully functional with no secrets, so it never hard-fails on a
missing key or network blip.

## Tags

`offline-first` · `crdt` · `low-connectivity` · `emerging-markets` · `retail` ·
`reconciliation`
