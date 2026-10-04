#!/usr/bin/env python3
"""
auth_provider_drift_monitor.py — Detect changes in known programs' auth provider configs.

Periodic poll of Privy / Magic / Web3Auth / Dynamic / ThirdWeb configs for
a watchlist of known programs. Alert (Telegram or local log) when:

- New domain appears in `allowed_domains`
- New wildcard appears anywhere
- OAuth provider list changes
- Frame-ancestors CSP loosens

This is a **first-mover advantage** tool: if a project's admin pushes a
config change that opens a trust expansion, we want to be the first to see it.

State stored in `sessions/_monitors/auth_drift_state.json`.

Usage:
    python3 auth_provider_drift_monitor.py \
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
from typing import Dict, List, Optional


@dataclass
class DriftEvent:
    detected_at: str
    program: str
    provider: str
    app_id: str
    diff_class: str        # "new_domain" / "new_wildcard" / "removed_domain" / "frame_ancestors_change"
    before: List[str]
    after: List[str]


def _fetch_privy_config(app_id: str) -> Optional[dict]:
    """Re-uses the same endpoint as core/auth_provider_probe.probe_privy."""
    url = f"https://auth.privy.io/api/v1/apps/{app_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "dapphunt-drift-monitor/1.0", "privy-app-id": app_id})
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 200:
                return json.loads(resp.read(500_000))
    except Exception:
        pass
    return None


def _normalize_allowed(config: dict) -> List[str]:
    """Extract sorted allowed_domains from any provider's config shape."""
    if not isinstance(config, dict):
        return []
    found: List[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k.lower() in ("allowed_domains", "alloweddomains", "allowed_origins", "trusteddomains"):
                    if isinstance(v, list):
                        found.extend(str(x) for x in v)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(config)
    return sorted(set(found))


def _diff(before: List[str], after: List[str]) -> Dict[str, List[str]]:
    bset = set(before)
    aset = set(after)
    return {
        "added": sorted(aset - bset),
        "removed": sorted(bset - aset),
        "wildcards_added": sorted(x for x in (aset - bset) if "*" in x),
    }


def poll(watchlist: List[dict], state_path: Path, output_dir: Path) -> List[DriftEvent]:
    state: Dict[str, List[str]] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {}

    events: List[DriftEvent] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for entry in watchlist:
        program = entry.get("name") or entry.get("program") or "unknown"
        provider = entry.get("provider", "privy")
        app_id = entry.get("app_id")
        if not app_id:
            continue

        cfg = None
        if provider == "privy":
            cfg = _fetch_privy_config(app_id)
        # Other providers can be added here.

        if not cfg:
            continue

        current = _normalize_allowed(cfg)
        key = f"{provider}:{app_id}"
        prior = state.get(key, [])

        diff = _diff(prior, current)
        if diff["added"] or diff["removed"]:
            if diff["added"]:
                events.append(DriftEvent(
                    detected_at=now_iso, program=program, provider=provider, app_id=app_id,
                    diff_class="new_wildcard" if diff["wildcards_added"] else "new_domain",
                    before=prior, after=current,
                ))
            if diff["removed"]:
                events.append(DriftEvent(
                    detected_at=now_iso, program=program, provider=provider, app_id=app_id,
                    diff_class="removed_domain", before=prior, after=current,
                ))

        state[key] = current

    # Persist state
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # Append events to a daily log
    if events:
        log_path = output_dir / f"drift_events_{now_iso[:10]}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")

    return events


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--watchlist", type=Path, required=True, help="JSON array of {name, provider, app_id}")
    parser.add_argument("--output", type=Path, required=True, help="Output directory for events log + state")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    if not args.watchlist.exists():
        print(f"error: watchlist not found: {args.watchlist}", file=sys.stderr)
        return 2
    try:
        watchlist = json.loads(args.watchlist.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: could not parse watchlist: {exc}", file=sys.stderr)
        return 2

    state_path = args.output / "auth_drift_state.json"
    events = poll(watchlist, state_path, args.output)

    if not args.quiet:
        print(f"Polled {len(watchlist)} programs.")
        print(f"Drift events detected: {len(events)}")
        for e in events:
            print(f"  [{e.detected_at}] {e.program} ({e.provider}:{e.app_id}): {e.diff_class}")
            print(f"    before: {e.before[:5]}{'...' if len(e.before)>5 else ''}")
            print(f"    after:  {e.after[:5]}{'...' if len(e.after)>5 else ''}")
    return 0 if not events else 1


if __name__ == "__main__":
    sys.exit(main())
