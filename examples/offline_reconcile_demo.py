# SPDX-License-Identifier: Apache-2.0
"""Demo: two shop devices edit offline, then reconcile conflict-free on reconnect.

Run::

    uv run python examples/offline_reconcile_demo.py
"""

from __future__ import annotations

from offline_store_agent import OfflineStore


def main() -> None:
    """Walk through an offline edit / reconnect / converge cycle."""
    # Two devices in a Kano shop. The network is down, so both are offline.
    till = OfflineStore(node_id="till", online=False)
    phone = OfflineStore(node_id="phone", online=False)

    # A shared starting point synced earlier in the day.
    till.put("item-7", {"name": "Rice 5kg", "price": 1500, "stock": 12})
    till.sync(phone)

    # --- NETWORK DOWN: each device edits independently ---
    till.put("sale-101", {"item": "Rice 5kg", "qty": 2, "total": 3000})  # sale at counter
    till.put("item-7", {"stock": 10})  # stock falls to 10
    phone.put("item-7", {"price": 1400})  # owner cuts price on the phone

    till_item = till.get("item-7")
    phone_item = phone.get("item-7")
    assert till_item is not None and phone_item is not None
    print("Before reconnect:")
    print(f"  till  sees price={till_item['price']} stock={till_item['stock']}")
    print(f"  phone sees price={phone_item['price']} stock={phone_item['stock']}")
    print(f"  till pending (unsynced) edits: {len(till.pending())}")

    # --- NETWORK BACK: reconcile ---
    result = till.sync(phone)
    print(f"\nAfter reconnect (reconciled {result.reconciled} pending edits):")
    print(f"  item-7 -> {till.get('item-7')}")
    print(f"  sale   -> {till.get('sale-101')}")
    print(f"  both devices converged: {till.export_state() == phone.export_state()}")


if __name__ == "__main__":
    main()
