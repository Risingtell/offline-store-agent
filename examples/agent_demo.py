# SPDX-License-Identifier: Apache-2.0
"""Demo: ask the store agent questions over CRDT-reconciled, offline-first state.

Run::

    uv run python examples/agent_demo.py
"""

from __future__ import annotations

from offline_store_agent import OfflineStore, StoreAgent


def main() -> None:
    """Stock a shop, edit offline on two devices, reconcile, then ask the agent."""
    till = OfflineStore(node_id="till")
    phone = OfflineStore(node_id="phone")

    # Morning: inventory synced across both devices.
    till.put("item-1", {"name": "Rice 5kg", "price": 1500, "stock": 12})
    till.put("item-2", {"name": "Sugar 1kg", "price": 800, "stock": 4})
    till.put("item-3", {"name": "Milk", "price": 600, "stock": 2})
    till.sync(phone)

    # --- NETWORK DOWN ---
    till.put("sale-1", {"item": "Rice 5kg", "qty": 2, "total": 3000})  # counter sale
    till.put("item-1", {"stock": 10})  # rice stock falls
    phone.put("item-1", {"price": 1400})  # owner cuts rice price on the phone

    agent = StoreAgent(till)  # mock backend — no API key needed
    print("=== While still OFFLINE (asking the till) ===")
    for q in ["What did I sell while the network was down?", "What's running low?"]:
        print(f"\nQ: {q}\n{agent.ask(q).answer}")

    # --- NETWORK BACK: reconcile both devices ---
    till.sync(phone)

    print("\n\n=== After RECONNECT (state reconciled) ===")
    for q in [
        "How many bags of rice do I have?",
        "How much did I sell today?",
        "Anything still waiting to sync?",
    ]:
        print(f"\nQ: {q}\n{agent.ask(q).answer}")


if __name__ == "__main__":
    main()
