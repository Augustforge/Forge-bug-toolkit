#!/usr/bin/env python3
"""
dapp_clone_spawn_monitor.py — Detect new subdomains spawning for known programs.

Periodic crt.sh poll for the apex domain of each program in the watchlist.
Diff against last-known subdomain set. When a new subdomain appears:
1. Probe it for X-Frame-Options + CSP frame-ancestors
2. If missing → high-value target (likely new dev/staging clone)
3. Alert

State stored in `sessions/_monitors/clone_spawn_state.json`.

Usage:
    python3 dapp_clone_spawn_monitor.py \
        --watchlist sessions/_proactive/dapp_programs.json \
        --output sessions/_monitors/
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass
class CloneSpawnEvent:
    detected_at: str
    program: str
    apex: str
    new_subdomain: str
    framing_posture: str       # "deny" / "sameorigin" / "wildcard" / "missing" / "error"
    is_finding_candidate: bool


def _fetch(url: str, timeout: float = 8.0) -> tuple[Optional[bytes], Dict[str, str], Optional[int]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-clone-spawn/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(2_000_000), {k.lower(): v for k, v in resp.headers.items()}, resp.status
    except Exception:
        return None, {}, None


def _crtsh_query(apex: str) -> Set[str]:
    url = f"https://crt.sh/?q={apex}&output=json"
    raw, _, status = _fetch(url, timeout=20)
    if not raw or status != 200:
        return set()
    try:
        data = json.loads(raw)
    except Exception:
        return set()
    subs: Set[str] = set()
    for entry in data:
        name_value = entry.get("name_value", "")
        for sub in name_value.split("\n"):
            sub = sub.strip().lower()
            if sub and sub.endswith(apex.lower()):
                # Drop wildcard entries
                if sub.startswith("*."):
                    continue
                subs.add(sub)
    return subs


def _framing_posture(headers: Dict[str, str]) -> str:
    xfo = (headers.get("x-frame-options") or "").upper()
    csp = headers.get("content-security-policy") or ""
    fa = ""
    for d in csp.split(";"):
        if d.strip().lower().startswith("frame-ancestors"):
            fa = d.strip().split(None, 1)[-1].lower() if " " in d.strip() else ""
            break

    if "DENY" in xfo or "'none'" in fa:
        return "deny"
    if "SAMEORIGIN" in xfo or "'self'" in fa:
        return "sameorigin"
    if "*" in fa:
        return "wildcard"
    if fa or xfo:
        return "explicit_list"
    return "missing"


def poll(watchlist: List[dict], state_path: Path, output_dir: Path) -> List[CloneSpawnEvent]:
    state: Dict[str, List[str]] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    events: List[CloneSpawnEvent] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for entry in watchlist:
        program = entry.get("name") or entry.get("program") or "unknown"
        apex = entry.get("apex")
        if not apex:
            continue

        current = _crtsh_query(apex)
        prior = set(state.get(apex, []))
        new_subs = current - prior

        for sub in sorted(new_subs):
            # Probe for framing posture
            posture = "error"
            try:
                _, headers, status = _fetch(f"https://{sub}/", timeout=5)
                if status == 200:
                    posture = _framing_posture(headers)
            except Exception:
                pass
            is_candidate = posture in ("missing", "wildcard", "explicit_list")
            events.append(CloneSpawnEvent(
                detected_at=now_iso, program=program, apex=apex,
                new_subdomain=sub, framing_posture=posture,
                is_finding_candidate=is_candidate,
            ))

        state[apex] = sorted(current)

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    if events:
        log_path = output_dir / f"clone_spawn_events_{now_iso[:10]}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")

    return events


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--watchlist", type=Path, required=True, help="JSON array of {name, apex}")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.watchlist.exists():
        print(f"error: watchlist not found: {args.watchlist}", file=sys.stderr)
        return 2
    try:
        watchlist = json.loads(args.watchlist.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: could not parse: {exc}", file=sys.stderr)
        return 2

    state_path = args.output / "clone_spawn_state.json"
    events = poll(watchlist, state_path, args.output)

    if not args.quiet:
        print(f"Polled {len(watchlist)} apex domains.")
        print(f"New subdomains spawned: {len(events)}")
        for e in events:
            tag = "★" if e.is_finding_candidate else " "
            print(f"  {tag} [{e.detected_at}] {e.program} → {e.new_subdomain}  posture={e.framing_posture}")
    return 0 if not any(e.is_finding_candidate for e in events) else 1


if __name__ == "__main__":
    sys.exit(main())
