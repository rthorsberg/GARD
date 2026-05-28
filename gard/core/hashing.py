"""Canonical-JSON SHA-256 used for audit/evidence row hashes (ADR-0009)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any


def _default(o: Any) -> Any:
    if isinstance(o, uuid.UUID):
        return str(o)
    if isinstance(o, dt.datetime):
        # ISO 8601 with explicit 'Z' for UTC; we ALWAYS store UTC so the
        # serialization is unambiguous.
        if o.tzinfo is None:
            o = o.replace(tzinfo=dt.UTC)
        return o.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")
    if isinstance(o, dt.date):
        return o.isoformat()
    if isinstance(o, bytes):
        return o.hex()
    if isinstance(o, set | frozenset):
        return sorted(o)
    raise TypeError(f"Unhashable type: {type(o).__name__}")


def canonical_json(obj: Any) -> str:
    """Stable, sorted, separator-tight JSON for hashing.

    Keys are sorted alphabetically; no whitespace; floats are rendered
    by ``json.dumps`` (no special handling — we do not store floats in
    audit rows).
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        default=_default,
        ensure_ascii=False,
    )


def row_hash(payload: dict[str, Any], previous_hash: str | None = None) -> str:
    """SHA-256 of canonical JSON of *payload*, optionally chained.

    When ``previous_hash`` is provided, it is mixed in as
    ``payload["__prev"]`` before serialization. This is how the daily
    chain-sealing job links rows.
    """
    if previous_hash is not None:
        payload = {**payload, "__prev": previous_hash}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
