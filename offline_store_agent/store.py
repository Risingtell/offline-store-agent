# SPDX-License-Identifier: Apache-2.0
"""Offline-first store: local-first edits with conflict-free reconciliation.

An :class:`OfflineStore` always applies edits to its local :class:`CRDTStore`
replica immediately — the shopkeeper never waits for a network round-trip — and
records each edit in a journal. Edits stay marked *pending* until a sync folds
this replica together with one or more peers, at which point the merged state is
conflict-free regardless of who was offline or for how long.

Example::

    till = OfflineStore(node_id="till")
    phone = OfflineStore(node_id="phone")
    till.put("sale-1", {"item": "rice", "qty": 2})   # offline at the counter
    phone.put("item-7", {"price": 1500})             # offline on the phone
    till.sync(phone)                                  # reconnect -> reconcile
    assert till.get("sale-1") == {"item": "rice", "qty": 2}
"""

from __future__ import annotations

from dataclasses import dataclass

from offline_store_agent.crdt import CRDTStore, JsonValue


@dataclass
class JournalEntry:
    """One locally applied edit, marked *synced* once it has been reconciled.

    Example::

        entry = JournalEntry(seq=1, action="put", record_id="sale-1", fields={"qty": 2})
    """

    seq: int
    action: str
    record_id: str
    fields: dict[str, JsonValue] | None
    synced: bool = False


@dataclass
class SyncResult:
    """Summary of a reconciliation: how many local edits cleared and peers seen.

    Example::

        result = till.sync(phone)
        print(result.reconciled, result.peers)
    """

    reconciled: int
    peers: int


class OfflineStore:
    """A device-local, offline-first view of shared store records.

    Example::

        store = OfflineStore(node_id="till-1")
        store.put("item-7", {"price": 1500, "stock": 12})
        store.delete("item-7")
    """

    def __init__(self, node_id: str, *, online: bool = True) -> None:
        """Create a replica for device *node_id*.

        ``online`` is narrative metadata for the agent — it never gates local
        edits, which always succeed offline-first.

        Example::

            store = OfflineStore(node_id="phone", online=False)
        """
        self.node_id = node_id
        self.online = online
        self._crdt = CRDTStore(node_id=node_id)
        self._journal: list[JournalEntry] = []
        self._seq = 0

    # -- local edits ---------------------------------------------------------

    def put(self, record_id: str, fields: dict[str, JsonValue]) -> None:
        """Create or update a record locally and journal it as pending.

        Example::

            store.put("sale-1", {"item": "rice", "qty": 2, "total": 3000})
        """
        self._crdt.put(record_id, fields)
        self._append("put", record_id, dict(fields))

    def delete(self, record_id: str) -> None:
        """Delete a record locally and journal it as pending.

        Example::

            store.delete("sale-1")
        """
        self._crdt.delete(record_id)
        self._append("delete", record_id, None)

    # -- reads ---------------------------------------------------------------

    def get(self, record_id: str) -> dict[str, JsonValue] | None:
        """Return a record's live fields, or ``None`` if absent or deleted.

        Example::

            store.get("item-7")
        """
        return self._crdt.get(record_id)

    def all(self) -> dict[str, dict[str, JsonValue]]:
        """Return every live record keyed by id.

        Example::

            store.all()
        """
        return self._crdt.all()

    @property
    def journal(self) -> list[JournalEntry]:
        """The full edit history on this device, oldest first.

        Example::

            for entry in store.journal:
                print(entry.action, entry.record_id)
        """
        return list(self._journal)

    def pending(self) -> list[JournalEntry]:
        """Edits made on this device that have not yet been reconciled.

        This is what the agent answers "what did I change while offline?" from.

        Example::

            unsynced = store.pending()
        """
        return [e for e in self._journal if not e.synced]

    # -- reconciliation ------------------------------------------------------

    def sync(self, *peers: OfflineStore) -> SyncResult:
        """Reconcile with one or more peers via two-way state exchange.

        Every replica ends up holding the merged, conflict-free state, and this
        device's pending edits are marked synced.

        Example::

            till.sync(phone, warehouse)
        """
        for peer in peers:
            blob = self._crdt.export_state()
            self._crdt.merge_state(peer._crdt.export_state())
            peer._crdt.merge_state(blob)
        reconciled = 0
        for entry in self._journal:
            if not entry.synced:
                entry.synced = True
                reconciled += 1
        self.online = True
        return SyncResult(reconciled=reconciled, peers=len(peers))

    # -- wire format ---------------------------------------------------------

    def export_state(self) -> bytes:
        """Serialise this replica's CRDT state for transport.

        Example::

            blob = store.export_state()
        """
        return self._crdt.export_state()

    def merge_state(self, raw: bytes) -> None:
        """Merge a serialised peer state into this replica.

        Example::

            store.merge_state(blob)
        """
        self._crdt.merge_state(raw)

    # -- internals -----------------------------------------------------------

    def _append(self, action: str, record_id: str, fields: dict[str, JsonValue] | None) -> None:
        """Record a local edit in the journal as pending."""
        self._seq += 1
        self._journal.append(
            JournalEntry(seq=self._seq, action=action, record_id=record_id, fields=fields)
        )
