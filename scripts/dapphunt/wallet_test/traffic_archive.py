# -*- coding: utf-8 -*-
"""Traffic-archive -- session-scoped HAR/JSONL capture wrapper (Plan 9 Task 9, Tier D).

Problem (Marius: 83% of findings come from FOCUSED re-mining of already-captured traffic, not
from the first pass): a single probe (`authz_diff`/`runtime_harness` `capture_*`) only sees
traffic under its own question and discards the rest. This module is a session-scoped archive
that logs EVERY request/response INDEPENDENTLY of any specific probe, so a later focused pass can
dig through it again (`remine`).

What it does:
    open_archive(target, opsec_config=None, live=False, profile="web2", name="traffic") -> TrafficArchive
    TrafficArchive.record(request, response=None, meta=None) -> bool   -- one capture into the JSONL
    TrafficArchive.remine(predicate=None) -> list[dict]                -- read-back / focused pass
    remine(archive_path, predicate=None) -> list[dict]                 -- same, by path (no handle)
    to_har(records) -> dict                                            -- HAR-compatible log for interop

SECURITY (P5):
    * Any LIVE capture (`live=True`) MUST pass `opsec_preflight.preflight(profile, ...)` fail-CLOSED
      BEFORE the archive becomes writable. Gate not passed -> TrafficArchive(ok=False,
      path=None, mode=MANUAL), `record()` -> False (writes NOTHING -- no live capture to disk).
      `live=False` (default) -- offline: re-mining an already-captured archive / manually imported
      HAR, no network, no gate needed (same live=False/True contract as account_provision.py).
    * The archive is local-session-only: the path resolves ONLY under `sessions/{target}/traffic/`
      (traversal/absolute external `name` is dropped). It contains tokens/cookies/response bodies --
      handle it like PoC evidence: NEVER outbound, no external I/O.

The module itself does NOT do live browser/network I/O: `record()` accepts snapshots of
request/response ALREADY captured by the calling code (the skill's live Playwright driver) -- the
same discipline as runtime_harness.py (`capture_*` only serializes passed-in snapshots). The
calling skill enables live capture ONLY after `open_archive(..., live=True).ok is True`.

Fail-open BY DEFAULT (broken input/write error -> False/[]/None, not a crash) EXCEPT the opsec
branch, which is fail-CLOSED (see opsec_preflight.py).
"""

import os
import json
import time
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLKIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
SESSIONS_DIR = os.path.join(_TOOLKIT_ROOT, "sessions")


# ---------------------------------------------------------------------------
# opsec_preflight -- loaded via importlib (toolkit self-contained, _methodology/wallet_test not on
# sys.path; pattern copied from account_provision.py / runtime_harness.py).
# ---------------------------------------------------------------------------

def _load_opsec():
    path = os.path.join(_HERE, "opsec_preflight.py")
    spec = importlib.util.spec_from_file_location("opsec_preflight", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------
# archive path resolution -- local-session-only (same traversal-guard as
# account_provision._resolve_session_path, but under sessions/{slug}/traffic/)
# ---------------------------------------------------------------------------

def _resolve_archive_path(name, target_slug):
    """`name` (e.g. "traffic") -> absolute `sessions/{slug}/traffic/<name>.jsonl` or None.

    Only relative `name` without traversal is allowed; resolved under sessions/{slug}/traffic/,
    and we verify the result did NOT escape that folder. Absolute/external `name` is dropped --
    the archive is kept strictly local-session-only (it contains tokens/cookies)."""
    if not name or not isinstance(name, str):
        name = "traffic"
    if not target_slug:
        return None
    if os.path.isabs(name):
        return None
    base = os.path.abspath(os.path.join(SESSIONS_DIR, str(target_slug), "traffic"))
    fname = name if name.endswith(".jsonl") else (name + ".jsonl")
    candidate = os.path.abspath(os.path.join(base, fname))
    # Traversal-guard: candidate MUST sit DIRECTLY inside base (no sub-paths escaping outward).
    if not candidate.startswith(base + os.sep):
        return None
    return candidate


# ---------------------------------------------------------------------------
# TrafficArchive
# ---------------------------------------------------------------------------

class TrafficArchive(object):
    """Session-scoped traffic archive. {ok, mode, errors, path, target_slug}.

    ok      -- the archive is writable (offline ok, OR live passed opsec).
    mode    -- 'MANUAL' (offline / opsec block) | 'AUTO' (live passed opsec fail-closed).
    path    -- absolute JSONL path under sessions/{slug}/traffic/ OR None (cannot write).
    """

    def __init__(self, ok, mode, path, target_slug, errors=None):
        self.ok = ok
        self.mode = mode
        self.path = path
        self.target_slug = target_slug
        self.errors = errors or []

    def __repr__(self):
        return "TrafficArchive(ok=%r, mode=%r, path=%r, errors=%r)" % (
            self.ok, self.mode, self.path, self.errors)

    def record(self, request, response=None, meta=None):
        """Logs one request/response into the JSONL (one line). Writes INDEPENDENTLY of any
        probe -- this archive logs EVERYTHING, a focused pass can dig through it later via
        `remine`.

        Returns True if the record landed on disk; False -- if the archive is not writable
        (`ok is False`: opsec block / unresolved path -> writes NOTHING, fail-CLOSED for a
        blocked live capture) OR on a write error (fail-open, not a crash)."""
        if not self.ok or not self.path:
            return False
        entry = {
            "ts": time.time(),
            "request": request if isinstance(request, dict) else {"raw": request},
            "response": response if isinstance(response, dict) else (
                {} if response is None else {"raw": response}),
        }
        if meta is not None:
            entry["meta"] = meta
        try:
            out_dir = os.path.dirname(self.path)
            os.makedirs(out_dir, exist_ok=True)
            # default=str: a non-JSON-serializable value (e.g. a stray object in meta) does not crash the capture.
            line = json.dumps(entry, ensure_ascii=False, default=str)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return True
        except Exception:
            return False

    def remine(self, predicate=None):
        """Read-back / focused re-mining pass over THIS archive (see the module-level `remine`)."""
        return remine(self.path, predicate=predicate)


# ---------------------------------------------------------------------------
# open_archive -- entry point
# ---------------------------------------------------------------------------

def open_archive(target, opsec_config=None, live=False, profile="web2", name="traffic"):
    """Opens a session-scoped traffic archive; for a live capture runs opsec_preflight fail-CLOSED.

    target       -- opsec target dict `{"slug":..., "in_scope":...}`; `slug` sets the archive
                    folder `sessions/{slug}/traffic/`. Without a slug -> ok=False (we do not make
                    up a slug).
    opsec_config -- flat config for opsec_preflight (see opsec_preflight._common_checks + web2/web3);
                    needed ONLY when live=True.
    live         -- False (default): offline (re-mining / importing a captured HAR), no network,
                    opsec not needed, mode='MANUAL'. True: MUST pass opsec before a writable
                    archive is issued -> mode='AUTO'.
    profile      -- 'web2' (/hunt) | 'web3' (/dapphunt) -- which opsec profile to run when live=True.
    name         -- archive name (traversal-guarded, resolved under sessions/{slug}/traffic/<name>.jsonl).
    """
    errors = []
    target_slug = target.get("slug") if isinstance(target, dict) else None

    path = _resolve_archive_path(name, target_slug)
    if path is None:
        if not target_slug:
            errors.append("target.slug is missing -- nowhere to write the archive")
        else:
            errors.append("name outside sessions/%s/traffic/ -- dropped (local-session-only)" % (target_slug,))
        return TrafficArchive(False, "MANUAL", None, target_slug, errors)

    if not live:
        # Offline: pure read/write of already-captured traffic, no live capture -> opsec not run.
        return TrafficArchive(True, "MANUAL", path, target_slug, errors)

    # ---- LIVE: fail-CLOSED opsec gate BEFORE the archive becomes writable ----
    opsec = _load_opsec()
    cfg = opsec_config if isinstance(opsec_config, dict) else {}
    tgt = target if isinstance(target, dict) else {"slug": target_slug}

    result = opsec.preflight(profile, tgt, cfg)
    if not result.ok:
        return TrafficArchive(
            False, "MANUAL", None, target_slug,
            errors + ["opsec_preflight blocked the live capture: %s" % ("; ".join(result.failed_checks),)],
        )

    return TrafficArchive(True, "AUTO", path, target_slug, errors)


# ---------------------------------------------------------------------------
# remine -- read-back / focused pass (module-level, by path; no handle)
# ---------------------------------------------------------------------------

def remine(archive_path, predicate=None):
    """Reads a JSONL archive by path -> list[dict]. `predicate(record)->bool` filters (focused
    pass: e.g. `lambda r: r["response"]["status"] == 403`). A broken/missing file, a broken line
    -> skipped (fail-open: no file -> [], one broken line does not crash the whole re-mining)."""
    out = []
    if not archive_path or not os.path.isfile(archive_path):
        return out
    try:
        with open(archive_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue  # broken line -- skip, keep reading the rest of the archive
                if predicate is not None:
                    try:
                        if not predicate(rec):
                            continue
                    except Exception:
                        continue  # a broken predicate on this record -- skip the record, not a crash
                out.append(rec)
    except Exception:
        return out
    return out


# ---------------------------------------------------------------------------
# to_har -- HAR-compatible export (interop with DevTools/Burp/har-viewers)
# ---------------------------------------------------------------------------

def _har_headers(headers):
    """{name: value} -> HAR `[{"name":..., "value":...}]`."""
    if not isinstance(headers, dict):
        return []
    return [{"name": str(k), "value": str(v)} for k, v in headers.items()]


def to_har(records):
    """`records` (output of `remine`) -> a minimal HAR-compatible log (`{"log": {"version","creator",
    "entries":[...]}}`). Each record -> a HAR entry (request/response/headers). Fail-open: a broken
    record is skipped, does not crash the export."""
    entries = []
    for rec in (records if isinstance(records, list) else []):
        try:
            req = rec.get("request") if isinstance(rec, dict) else None
            resp = rec.get("response") if isinstance(rec, dict) else None
            req = req if isinstance(req, dict) else {}
            resp = resp if isinstance(resp, dict) else {}
            entries.append({
                "startedDateTime": rec.get("ts"),
                "request": {
                    "method": req.get("method", ""),
                    "url": req.get("url", ""),
                    "headers": _har_headers(req.get("headers")),
                    "postData": {"text": req.get("body")} if req.get("body") is not None else {},
                },
                "response": {
                    "status": resp.get("status", 0),
                    "headers": _har_headers(resp.get("headers")),
                    "content": {"text": resp.get("body")} if resp.get("body") is not None else {},
                },
            })
        except Exception:
            continue
    return {"log": {"version": "1.2", "creator": {"name": "traffic_archive", "version": "1.0"},
                    "entries": entries}}


# ---------------------------------------------------------------------------
# CLI (operator convenience: re-mine a captured archive offline)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: traffic_archive.py <archive.jsonl>   -- re-mine a captured archive")
        sys.exit(2)
    recs = remine(sys.argv[1])
    print("%d records" % len(recs))
    for r in recs[:20]:
        req = r.get("request", {})
        resp = r.get("response", {})
        print("  %s %s -> %s" % (req.get("method", "?"), req.get("url", "?"), resp.get("status", "?")))
