# Offline-First Store Agent — SkillMD

**Agent ID:** `rising-store-agent`
**Endpoint:** https://rising-store-agent.vercel.app
**AgentFacts:** https://rising-store-agent.vercel.app/agent.json
**Source:** https://github.com/Risingtell/offline-store-agent
**Demo:** https://youtu.be/unQR-vIBs1A
**Author:** Oluwasogo Ajala — Rising Technology (Kano, Nigeria)
**License:** Apache-2.0

## What it does

A **conflict-free offline-sync layer for agents**. Any agent or device can edit
shared state while fully disconnected and reconcile it **without conflict** when
connectivity returns, using a field-level Last-Writer-Wins CRDT. Concurrent edits
to *different fields of the same record* all survive — one device correcting a
price, another adjusting stock, both kept — with no "last sync wins" data loss,
independent of sync order. This is the conflict-free coordination primitive NANDA
Town is built around, exposed over HTTP (`POST /records`, `POST /sync`,
`GET /state`) as a reusable building block.

Shipped on top is a **low-connectivity shop agent** as the reference application:
it records sales and inventory offline, reconciles on reconnect, and answers
plain-language questions over the reconciled state (`POST /ask`) — built for shops
in emerging markets where the network is unreliable.

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

### Namespaces (multi-tenant)

Every request may carry an optional **`namespace`** — a url-safe token (≤ 64
chars) that reconciles against its own **isolated** CRDT space. Omit it and you
share the zero-config `demo` space; pass one and you get a private space no other
caller can see. This lets any agent use the hub as its own conflict-free store.

```bash
# POST: put namespace in the JSON body
curl -s https://rising-store-agent.vercel.app/records \
  -H 'Content-Type: application/json' \
  -d '{"namespace": "my-agent", "id": "beans", "fields": {"stock": 7}}'

# GET: pass it as a query param
curl -s "https://rising-store-agent.vercel.app/state?namespace=my-agent"
```

## Reasoning

Backed by Google Gemini (`gemini-2.5-flash`). A deterministic, key-free fallback
keeps the agent fully functional with no secrets, so it never hard-fails on a
missing key or network blip.

## Tags

`offline-first` · `crdt` · `low-connectivity` · `emerging-markets` · `retail` ·
`reconciliation`
