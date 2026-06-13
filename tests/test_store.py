# SPDX-License-Identifier: Apache-2.0
"""Tests for the offline-first store wrapper: journal, pending edits, and sync."""

from __future__ import annotations

from offline_store_agent.store import OfflineStore


class TestLocalEdits:
    def test_edits_apply_immediately_offline(self) -> None:
        store = OfflineStore(node_id="till", online=False)
        store.put("sale-1", {"item": "rice", "qty": 2, "total": 3000})
        # Offline-first: the edit is visible without any network.
        assert store.get("sale-1") == {"item": "rice", "qty": 2, "total": 3000}

    def test_journal_tracks_pending(self) -> None:
        store = OfflineStore(node_id="till")
        store.put("sale-1", {"item": "rice"})
        store.delete("sale-1")
        assert [e.action for e in store.pending()] == ["put", "delete"]
        assert all(not e.synced for e in store.pending())


class TestReconciliation:
    def test_two_devices_offline_then_sync(self) -> None:
        till = OfflineStore(node_id="till", online=False)
        phone = OfflineStore(node_id="phone", online=False)

        till.put("sale-1", {"item": "rice", "qty": 2})
        phone.put("item-7", {"price": 1500})

        result = till.sync(phone)

        # Both devices converge on the union of edits.
        assert till.get("sale-1") == {"item": "rice", "qty": 2}
        assert till.get("item-7") == {"price": 1500}
        assert till.export_state() == phone.export_state()
        assert result.reconciled == 1
        assert result.peers == 1

    def test_concurrent_edits_to_same_item_reconcile(self) -> None:
        till = OfflineStore(node_id="till")
        phone = OfflineStore(node_id="phone")
        till.put("item-7", {"price": 1500, "stock": 12})
        till.sync(phone)

        # Both go offline; each edits a different field.
        till.put("item-7", {"price": 1400})
        phone.put("item-7", {"stock": 9})
        till.sync(phone)

        assert till.get("item-7") == {"price": 1400, "stock": 9}
        assert till.export_state() == phone.export_state()

    def test_sync_marks_pending_synced(self) -> None:
        till = OfflineStore(node_id="till", online=False)
        phone = OfflineStore(node_id="phone")
        till.put("sale-1", {"item": "rice"})
        assert len(till.pending()) == 1
        till.sync(phone)
        assert till.pending() == []
        assert till.online is True
