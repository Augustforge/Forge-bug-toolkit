#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""yield_rollup.py — PASSIVE aggregator of the `found_by` field (Plan 9 T7, Tier C — BASE ONLY).

Reads the `found_by` column from the `## Banked Findings` section of every ledger
`sessions/*/hypotheses.md` and rolls it up cross-hunt: which phase/technique, which model,
which un-dup-origin actually produced findings. This is READ-ONLY. The script NEVER influences
SELECT/priority/HUNT-EXIT (P2) — analytics consumers (method-priors / model-split /
time-to-confirm) are DELIBERATELY not built (deferred-by-volume, P2/P12).

`found_by` cell format: `<phase/technique> | model | undup-origin | ~cost`
(e.g. `deephunt-J5-depth | opus | composition-seam | ~3h`). Internal `|` are tolerated (the parser
stitches overflow cells back into found_by by the header column count) — escaped `\\|` too.

fail-open: broken ledger / missing file → skip, not crash.

Run: py -3 -X utf8 scripts/_methodology/yield_rollup.py [--sessions <dir>] [--json]
"""
import argparse
import glob
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))  # 
DEFAULT_SESSIONS = os.path.join(ROOT, "sessions")

_PIPE_ESC = "\x00"


def _cells(line):
    """Split a markdown table row into cells; escaped `\\|` is not treated as a separator."""
    s = line.strip()
    if not s.startswith("|"):
        return None
    s = s.replace("\\|", _PIPE_ESC)
    s = s.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace(_PIPE_ESC, "|") for c in s.split("|")]


def _is_sep_row(cells):
    return cells is not None and all(set(c) <= set("-: ") and c for c in cells)


def _split_found_by(val):
    """`phase | model | undup-origin | ~cost` → dict (by position, best-effort)."""
    parts = [p.strip() for p in val.split("|")]
    keys = ["phase", "model", "undup_origin", "cost"]
    out = {k: "" for k in keys}
    for i, p in enumerate(parts):
        if i < len(keys):
            out[keys[i]] = p
    out["raw"] = val.strip()
    return out


def parse_banked(text):
    """Return list[dict] of Banked Findings rows with found_by parsed.

    Empty/placeholder template rows (all cells empty) are skipped.
    """
    lines = text.splitlines()
    rows = []
    i = 0
    n = len(lines)
    while i < n:
        cells = _cells(lines[i])
        low = [c.lower() for c in cells] if cells else []
        # Banked table header: carries both found_by and severity
        if cells and "found_by" in low and any("sever" in c for c in low):
            headers = [c.lower() for c in cells]
            try:
                fb_idx = headers.index("found_by")
            except ValueError:
                i += 1
                continue
            ncols = len(headers)
            i += 1
            # separator row
            if i < n and _is_sep_row(_cells(lines[i])):
                i += 1
            # data rows
            while i < n:
                drow = _cells(lines[i])
                if drow is None:
                    break
                if _is_sep_row(drow):
                    i += 1
                    continue
                # overflow: internal `|` in found_by inflated the cell count → stitch back
                if len(drow) > ncols:
                    extra = len(drow) - ncols
                    fb_val = " | ".join(drow[fb_idx: fb_idx + 1 + extra])
                    merged = drow[:fb_idx] + [fb_val] + drow[fb_idx + 1 + extra:]
                else:
                    merged = drow
                    fb_val = merged[fb_idx] if fb_idx < len(merged) else ""
                if any(c for c in merged):  # not an empty placeholder row
                    rec = {}
                    for h, c in zip(headers, merged):
                        rec[h] = c
                    rec["found_by"] = fb_val
                    rec["found_by_parsed"] = _split_found_by(fb_val) if fb_val else None
                    if fb_val:  # aggregate only rows where found_by is filled
                        rows.append(rec)
                i += 1
            continue
        i += 1
    return rows


def rollup(sessions_dir=None, ledgers=None):
    """Passive found_by rollup across all ledgers. Returns dict (raw + counters)."""
    if ledgers is None:
        sd = sessions_dir or DEFAULT_SESSIONS
        ledgers = glob.glob(os.path.join(sd, "*", "hypotheses.md"))
    by_phase, by_model, by_origin = {}, {}, {}
    records = []
    for lp in ledgers:
        try:
            with open(lp, encoding="utf-8") as f:
                text = f.read()
        except Exception:
            continue  # fail-open
        try:
            banked = parse_banked(text)
        except Exception:
            continue  # fail-open
        for r in banked:
            fb = r.get("found_by_parsed") or {}
            slug = os.path.basename(os.path.dirname(lp))
            rec = {
                "target": slug,
                "severity": r.get("severity", ""),
                "phase": fb.get("phase", ""),
                "model": fb.get("model", ""),
                "undup_origin": fb.get("undup_origin", ""),
                "cost": fb.get("cost", ""),
                "found_by": r.get("found_by", ""),
            }
            records.append(rec)
            for d, k in ((by_phase, rec["phase"]), (by_model, rec["model"]),
                         (by_origin, rec["undup_origin"])):
                if k:
                    d[k] = d.get(k, 0) + 1
    return {
        "total_found": len(records),
        "by_phase": by_phase,
        "by_model": by_model,
        "by_undup_origin": by_origin,
        "records": records,
        "advisory": "PASSIVE aggregate — NEVER influences SELECT/priority/HUNT-EXIT (Plan 9 P2).",
    }


def _fmt(summary):
    out = ["yield_rollup — PASSIVE found_by aggregate (does NOT influence SELECT)"]
    out.append("total confirmed findings with found_by: %d" % summary["total_found"])
    for title, key in (("by phase/technique", "by_phase"), ("by model", "by_model"),
                       ("by undup-origin", "by_undup_origin")):
        out.append("  %s:" % title)
        for k, v in sorted(summary[key].items(), key=lambda kv: -kv[1]):
            out.append("    %-28s %d" % (k, v))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Passive found_by rollup (Plan 9 T7).")
    ap.add_argument("--sessions", default=None, help="sessions/ dir (default: toolkit sessions)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args(argv)
    summary = rollup(sessions_dir=args.sessions)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(_fmt(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
