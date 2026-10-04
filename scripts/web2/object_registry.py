# -*- coding: utf-8 -*-
"""object_registry — standalone Object Provenance Ledger (Plan 9, Task T4, Tier A).

Marius (verbatim): «the difference between changing a random ID and PROVING broken access control».

Per-target JSON registry recording, for EACH resource CREATED during a run, one create-event:
`{object_id, created_by, creating_request, owner, timestamp}`. `authz_diff.py` consults it (opt-in
`registry=` param / auto-load in `run_authz_matrix`), so a later cross-owner access to a registered
`object_id` is reported as a PROVEN create->access chain — the recorded create event PLUS the
observed foreign read — rather than a single-response marker-diff ("changed a random ID and got
different data»).

Standalone (P6): NO traffic-archive dependency. The writer is called explicitly at the moment a
create is observed (by the harness/agent). Task T10 (Wave 4) UPGRADES this ledger by auto-filling the
create->access chain from the traffic-archive (T9) — re-mining, 0 extra probes — but that fusion is
NOT this task; this file must stand on its own.

File: `{session_dir}/object_registry.json`, append-only records list (full history preserved; a
re-create of the same id appends, `lookup` returns the most-recent match):
    {"schema": "object_registry/v1",
     "records": [{"object_id","created_by","creating_request","owner","timestamp"}, ...]}

fail-open (non-security script): any read/parse error -> empty registry; a write error -> `None`
return (caller decides), never crash the hunt.
"""

import os
import json
import time

SCHEMA = "object_registry/v1"
REGISTRY_FILENAME = "object_registry.json"


def _registry_path(session_dir):
    return os.path.join(str(session_dir), REGISTRY_FILENAME)


def _now_iso():
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    except Exception:
        return None


def load_registry(session_dir):
    """Load `{session_dir}/object_registry.json` -> `{"schema", "records":[...]}`. Missing file or
    broken/foreign shape -> empty `{"schema": SCHEMA, "records": []}` (fail-open — no registry is a
    valid state, never raises)."""
    path = _registry_path(session_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data
    except Exception:
        pass
    return {"schema": SCHEMA, "records": []}


def register_object(session_dir, object_id, created_by, creating_request=None, owner=None,
                    timestamp=None):
    """Append a create-event record to `{session_dir}/object_registry.json` (append-only). `owner`
    defaults to `created_by` (the creator owns the object by default); `timestamp` defaults to
    wall-clock ISO-8601 UTC (pass an explicit value for deterministic tests). Returns the written
    record dict, or `None` on any write failure (fail-open — caller decides; never raises)."""
    try:
        session_dir = str(session_dir)
        os.makedirs(session_dir, exist_ok=True)
        reg = load_registry(session_dir)
        record = {
            "object_id": str(object_id),
            "created_by": created_by,
            "creating_request": creating_request,
            "owner": owner if owner is not None else created_by,
            "timestamp": timestamp if timestamp is not None else _now_iso(),
        }
        reg["records"].append(record)
        reg["schema"] = SCHEMA
        with open(_registry_path(session_dir), "w", encoding="utf-8") as f:
            json.dump(reg, f, ensure_ascii=False, indent=2)
        return record
    except Exception:
        return None


def _records_of(registry):
    if isinstance(registry, dict):
        recs = registry.get("records")
        return recs if isinstance(recs, list) else []
    if isinstance(registry, list):
        return registry
    return []


def lookup(registry, object_id):
    """Most-recent create-event record for `object_id` (append-only -> last match wins), or `None`.
    `registry` may be the dict from `load_registry` or a bare records list (fail-open on either)."""
    oid = str(object_id)
    found = None
    for rec in _records_of(registry):
        if isinstance(rec, dict) and str(rec.get("object_id")) == oid:
            found = rec
    return found


def lookup_by_endpoint(registry, endpoint):
    """Most-recent record whose `object_id` appears as a concrete path segment of `endpoint`, or
    `None`. `/objects/A` -> record for "A"; `/orders/123` -> record for "123"; templated segments
    (`{orderId}`) are ignored (a concrete probe carries the real id, not the template). Purely
    lexical, fail-open — this is how the authz consumer maps a probed endpoint back to a registered
    create-event without the caller having to restate the id."""
    try:
        segs = set(
            s for s in str(endpoint).split("/")
            if s and not (s.startswith("{") and s.endswith("}"))
        )
    except Exception:
        return None
    found = None
    for rec in _records_of(registry):
        if isinstance(rec, dict) and str(rec.get("object_id")) in segs:
            found = rec
    return found
