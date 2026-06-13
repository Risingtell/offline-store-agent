# SPDX-License-Identifier: Apache-2.0
"""Field-level Last-Writer-Wins map CRDT for offline-first store records.

This is the reconciliation engine of the offline-first store agent. Each device
keeps its own replica and may edit records while completely disconnected; when
connectivity returns the replicas exchange state and :meth:`CRDTStore.merge`
folds them together without conflict.

Conflicts are resolved per *field* (not per record) by ``(lamport_ts, node_id)``
order, so two devices that edit different fields of the same item offline — say
one corrects a price while the other adjusts stock — both keep their change. The
node id breaks timestamp ties so the merged result never depends on sync order.

Example::

    till = CRDTStore(node_id="till")
    phone = CRDTStore(node_id="phone")
    till.put("item-7", {"price": 1500})       # edited at the counter, offline
    phone.put("item-7", {"stock": 9})         # edited on the phone, offline
    till.merge(phone)
    assert till.get("item-7") == {"price": 1500, "stock": 9}  # both survive
"""

from __future__ import annotations

import json

# Store values are kept JSON-native so a record round-trips over the wire.
JsonValue = str | int | float | bool | None
# A field tag: the value plus the (logical clock, node id) that ordered it.
_Tagged = tuple[JsonValue, int, str]

_DELETED = "__deleted__"


class CRDTStore:
    """A replica of a set of records, mergeable across offline devices.

    A record is a flat mapping of field name to JSON value. Deletion is itself
    an LWW field, so a delete on one device and a concurrent edit on another are
    resolved by timestamp rather than by who synced first.

    Example::

        store = CRDTStore(node_id="till-1")
        store.put("sale-1", {"item": "rice", "qty": 2, "total": 3000})
        store.get("sale-1")
    """

    def __init__(self, node_id: str = "node") -> None:
        """Create a replica identified by *node_id* (used for deterministic ties).

        Example::

            store = CRDTStore(node_id="phone")
        """
        self._node_id = node_id
        self._clock = 0
        # record_id -> field -> (value, ts, node)
        self._records: dict[str, dict[str, _Tagged]] = {}

    # -- mutations -----------------------------------------------------------

    def put(self, record_id: str, fields: dict[str, JsonValue]) -> None:
        """Create or update *record_id*, tagging each field with a fresh clock.

        Example::

            store.put("item-7", {"price": 1500, "stock": 12})
        """
        for name, value in fields.items():
            self._set(record_id, name, value, self._tick(), self._node_id)

    def delete(self, record_id: str) -> None:
        """Mark *record_id* deleted (an LWW tombstone, so it merges correctly).

        Example::

            store.delete("item-7")
        """
        self._set(record_id, _DELETED, True, self._tick(), self._node_id)

    # -- reads ---------------------------------------------------------------

    def get(self, record_id: str) -> dict[str, JsonValue] | None:
        """Return the live fields of *record_id*, or ``None`` if absent or deleted.

        Example::

            record = store.get("item-7")
        """
        record = self._records.get(record_id)
        if record is None or self._is_deleted(record):
            return None
        return {name: tag[0] for name, tag in record.items() if name != _DELETED}

    def all(self) -> dict[str, dict[str, JsonValue]]:
        """Return every live record keyed by id (deleted records omitted).

        Example::

            for rid, fields in store.all().items():
                print(rid, fields)
        """
        live: dict[str, dict[str, JsonValue]] = {}
        for record_id in self._records:
            fields = self.get(record_id)
            if fields is not None:
                live[record_id] = fields
        return live

    # -- CvRDT replication ---------------------------------------------------

    def merge(self, other: CRDTStore) -> None:
        """Fold another replica's state into this one (commutative, idempotent).

        Example::

            till.merge(phone)
        """
        for record_id, record in other._records.items():
            for name, (value, ts, node) in record.items():
                self._set(record_id, name, value, ts, node)

    def export_state(self) -> bytes:
        """Serialise the full CRDT state as canonical (sorted) JSON bytes.

        Two replicas that have observed the same edits produce byte-identical
        output, so this is safe both to gossip over the wire and to compare for
        convergence.

        Example::

            blob = store.export_state()
        """
        obj = {
            record_id: {name: [value, ts, node] for name, (value, ts, node) in record.items()}
            for record_id, record in self._records.items()
        }
        return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def merge_state(self, raw: bytes) -> None:
        """Merge a state blob produced by :meth:`export_state` into this replica.

        Example::

            store.merge_state(peer_blob)
        """
        obj = json.loads(raw.decode("utf-8"))
        for record_id, record in obj.items():
            for name, (value, ts, node) in record.items():
                self._set(record_id, name, value, int(ts), str(node))

    # -- internals -----------------------------------------------------------

    def _tick(self) -> int:
        """Advance the Lamport clock for a local event and return the new value."""
        self._clock += 1
        return self._clock

    def _set(self, record_id: str, field: str, value: JsonValue, ts: int, node: str) -> None:
        """Apply one tagged field, keeping the ``(ts, node)``-maximal winner."""
        self._clock = max(self._clock, ts)
        record = self._records.setdefault(record_id, {})
        current = record.get(field)
        if current is None or (ts, node) > (current[1], current[2]):
            record[field] = (value, ts, node)

    @staticmethod
    def _is_deleted(record: dict[str, _Tagged]) -> bool:
        """Return whether the record's tombstone field currently wins."""
        tombstone = record.get(_DELETED)
        return bool(tombstone[0]) if tombstone is not None else False
