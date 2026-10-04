#!/usr/bin/env python3
"""
Hack-wave transfer signal — a fresh hack of class X opens a WEEK-window where sibling
protocols of the same family are likely still unpatched (feedback_protocol_family_bug_transfer,
cross-TARGET). Classes arrive in waves: Aztec Payments (17.06) + Hinkal (02.07) were the SAME
ZK proof-binding class 3 weeks apart; Taiko (21.06) re-confirmed the SGX class. React fast,
don't wait — the window is days, not months.

This reads wave_transfer.json, flags waves still inside their hot window (relative to a date you
pass — Date.now() is intentionally NOT used so the tool is deterministic), and prints the
concrete sibling-hunt actions: which family to grep, which patterns, which detector to run.

Usage:
    py -3 -X utf8 wave_transfer.py --today 2026-07-11            # active waves + actions
    py -3 -X utf8 wave_transfer.py --today 2026-07-11 --all      # every wave, hot or cold
    py -3 -X utf8 wave_transfer.py --class 14.12                 # actions for one class
    py -3 -X utf8 wave_transfer.py --add                         # prints the JSON schema to append

To add a wave: append an entry to wave_transfer.json (schema in its `_doc`). One entry per notable
hack; keep it current — this is the operational half of the taxonomy ingest.
"""

import argparse
import datetime as _dt
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "wave_transfer.json")


def _parse(d):
    return _dt.date.fromisoformat(d)


def load_waves():
    with open(LEDGER, encoding="utf-8") as f:
        return json.load(f).get("waves", [])


def print_wave(w, days_left=None):
    hot = "" if days_left is None else ("  🔥 HOT (%d day(s) left)" % days_left if days_left >= 0 else "  (window closed)")
    print("── %s  [%s]  $%s  %s%s" % (
        w["hack"], w["date"], "{:,}".format(w.get("loss_usd", 0)), "Cat " + w["class"], hot))
    print("   class:    %s" % w["class_name"])
    print("   siblings: %s" % w["sibling_family"])
    print("   grep:     %s" % "  ".join(w["grep_patterns"]))
    print("   detector: %s" % w["detector"])
    print("")


def main():
    ap = argparse.ArgumentParser(description="Hack-wave transfer signal (sibling-hunt on fresh hacks).")
    ap.add_argument("--today", help="ISO date to compute the hot-window against (e.g. 2026-07-11)")
    ap.add_argument("--all", action="store_true", help="show every wave, not only hot ones")
    ap.add_argument("--class", dest="klass", help="show actions for one taxonomy class (e.g. 14.12)")
    ap.add_argument("--add", action="store_true", help="print the JSON schema for a new wave entry")
    args = ap.parse_args()

    if args.add:
        print(json.dumps({
            "hack": "<name>", "date": "<ISO>", "loss_usd": 0, "class": "<Cat>",
            "class_name": "<one-line>", "sibling_family": "<who shares this surface>",
            "grep_patterns": ["<pat>"], "detector": "<script.py>", "window_days": 7,
        }, indent=2))
        return 0

    waves = load_waves()

    if args.klass:
        hits = [w for w in waves if w["class"] == args.klass]
        if not hits:
            print("no wave for class %s" % args.klass)
            return 1
        for w in hits:
            print_wave(w)
        return 0

    if not args.today:
        for w in waves:
            print_wave(w)
        print("--- %d wave(s). Pass --today <ISO> to flag hot windows. ---" % len(waves))
        return 0

    today = _parse(args.today)
    shown = 0
    for w in waves:
        end = _parse(w["date"]) + _dt.timedelta(days=w.get("window_days", 7))
        days_left = (end - today).days
        if args.all or days_left >= 0:
            print_wave(w, days_left)
            shown += 1
    hot = sum(1 for w in waves if (_parse(w["date"]) + _dt.timedelta(days=w.get("window_days", 7)) - today).days >= 0)
    print("--- %d wave(s) shown, %d still HOT as of %s. Grep siblings NOW — window is days. ---"
          % (shown, hot, args.today))
    return 0


if __name__ == "__main__":
    sys.exit(main())
