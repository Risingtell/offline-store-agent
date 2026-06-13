# SPDX-License-Identifier: Apache-2.0
"""Tests for the field-level LWW-Map CRDT store."""

from __future__ import annotations

import random

from offline_store_agent.crdt import CRDTStore


class TestBasics:
    def test_put_and_get(self) -> None:
        store = CRDTStore(node_id="a")
        assert store.get("item-7") is None
        store.put("item-7", {"price": 1500, "stock": 12})
        assert store.get("item-7") == {"price": 1500, "stock": 12}

    def test_update_merges_fields(self) -> None:
        store = CRDTStore(node_id="a")
        store.put("item-7", {"price": 1500, "stock": 12})
        store.put("item-7", {"stock": 9})
        assert store.get("item-7") == {"price": 1500, "stock": 9}

    def test_delete_hides_record(self) -> None:
        store = CRDTStore(node_id="a")
        store.put("item-7", {"price": 1500})
        store.delete("item-7")
        assert store.get("item-7") is None
        assert "item-7" not in store.all()


class TestFieldLevelMerge:
    def test_concurrent_edits_to_different_fields_both_survive(self) -> None:
        till = CRDTStore(node_id="till")
        phone = CRDTStore(node_id="phone")
        till.put("item-7", {"price": 1500, "stock": 12})
        phone.merge(till)

        # Both go offline and edit different fields of the same item.
        till.put("item-7", {"price": 1400})
        phone.put("item-7", {"stock": 9})

        till.merge(phone)
        phone.merge(till)
        assert till.get("item-7") == {"price": 1400, "stock": 9}
        assert till.export_state() == phone.export_state()

    def test_concurrent_edits_to_same_field_resolve_deterministically(self) -> None:
        a = CRDTStore(node_id="a")
        b = CRDTStore(node_id="b")
        a.put("x", {"v": 1})
        b.put("x", {"v": 2})
        # Same logical clock (both first write); node id "b" > "a" breaks the tie.
        a.merge(b)
        b.merge(a)
        assert a.get("x") == {"v": 2}
        assert a.export_state() == b.export_state()

    def test_delete_then_concurrent_edit_resolves_by_clock(self) -> None:
        a = CRDTStore(node_id="a")
        b = CRDTStore(node_id="b")
        a.put("x", {"v": 1})
        b.merge(a)
        a.delete("x")  # later clock than b's edit below? b edits after seeing v=1
        b.put("x", {"v": 2})
        a.merge(b)
        b.merge(a)
        # Whatever wins, both replicas must agree.
        assert a.export_state() == b.export_state()
        assert a.get("x") == b.get("x")


class TestConvergence:
    def _workload(self, seed: int, n_devices: int, n_items: int, ops: int) -> list[CRDTStore]:
        rng = random.Random(seed)
        devices = [CRDTStore(node_id=f"d{i}") for i in range(n_devices)]
        for device in devices:
            for _ in range(ops):
                item = f"item-{rng.randint(0, n_items - 1)}"
                field = rng.choice(["price", "stock", "name"])
                value = rng.randint(0, 9999)
                device.put(item, {field: value})
        return devices

    def test_converges_regardless_of_merge_order(self) -> None:
        finals: list[bytes] = []
        for order_seed in range(8):
            devices = self._workload(seed=42, n_devices=6, n_items=5, ops=10)
            states = [d.export_state() for d in devices]
            order = list(states)
            random.Random(order_seed).shuffle(order)
            merged = CRDTStore(node_id="merger")
            for blob in order:
                merged.merge_state(blob)
            finals.append(merged.export_state())
        assert all(state == finals[0] for state in finals)
        assert finals[0] != b"{}"

    def test_merge_is_idempotent(self) -> None:
        devices = self._workload(seed=7, n_devices=4, n_items=3, ops=8)
        merged = CRDTStore(node_id="m")
        for device in devices:
            merged.merge(device)
        once = merged.export_state()
        for device in devices:
            merged.merge(device)
        assert merged.export_state() == once

    def test_deterministic_across_runs(self) -> None:
        results: list[bytes] = []
        for _ in range(2):
            devices = self._workload(seed=99, n_devices=5, n_items=4, ops=12)
            merged = CRDTStore(node_id="m")
            for device in devices:
                merged.merge(device)
            results.append(merged.export_state())
        assert results[0] == results[1]
