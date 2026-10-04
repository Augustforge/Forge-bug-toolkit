#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_coverage_invert.py — T14-A: audit report as an INVERTED coverage map (phase 1b).

Today we read audits in order to DEDUPE findings — i.e. after the fact. The inversion (depth_engine_plan
§5-bis): a report is a map of WHERE THE CROWD LOOKED. So:

  map hole     = a place the auditor did not look  -> priority
  covered zone = crowded                           -> rank penalty, but NOT a veto

Key rule (operator correction 2026-07-27, idea B): `hot` != "closed". The crowd looked, but also
DID NOT FOLLOW THROUGH (e.g. bugs have lived in well-discussed places; some code survived years under tier-1
audits). So the script's output is a QUEUE, not a filter: cold goes first, hot is walked
through without fail, but later.

The `crowd-heat` output (hot|cold) per file is the field that is joined into the `I-NN` table in
`system_model.md`.

§52 light reinforcement (Plan 6, Task 8): optional `--commodity-hits <file>` — a list of paths (one per
line, OR a JSON array) already touched by a commodity scanner (nuclei/slither/mythril/etc). These paths
are forced to `hot` in `crowd_heat` REGARDLESS of audit mentions — "a commodity scanner already looked" is also
"the crowd looked". Without the flag behaviour is UNCHANGED (backward compatible, CLI signature preserved).

Usage:
  py -3 -X utf8 audit_coverage_invert.py --src <path to sources> --reports <file-or-folder> \\
                                         [--ext .sol,.rs] [--top 30] [--json] \\
                                         [--commodity-hits <file with a list of paths>]

PDF: convert beforehand with `pdftotext -layout report.pdf report.txt` (poppler is in /mingw64/bin).
"""

import argparse
import json
import os
import re
import sys

SRC_EXT_DEFAULT = [".sol", ".rs", ".go", ".move", ".cairo", ".vy"]
REPORT_EXT = [".md", ".txt", ".json"]

# Bug classes — rough markers of "what the auditor was thinking about at all". Not a full taxonomy, but a slice
# sufficient to see UNdiscussed classes (a hole at the class level, not the file level).
# (Cyrillic markers kept: they match Russian-language audit reports — logic.)
CLASS_MARKERS = {
    "reentrancy": ["reentran", "реентр", "nonreentrant", "cei "],
    "access-control": ["access control", "onlyowner", "permission", "unauthorized", "доступ", "роль"],
    "oracle/price": ["oracle", "price feed", "chainlink", "twap", "оракул"],
    "math/precision": ["precision", "rounding", "overflow", "underflow", "округл", "точност", "decimals"],
    "accounting": ["accounting", "balance mismatch", "share", "учёт", "бухгалт", "inflation attack"],
    "liquidation": ["liquidat", "ликвидац", "collateral", "health factor"],
    "upgrade/proxy": ["upgrade", "proxy", "initializ", "прокси", "storage collision"],
    "external-call": ["external call", "low-level call", "delegatecall", "return value", "callback"],
    "dos/griefing": ["denial of service", "dos", "griefing", "gas limit", "unbounded loop"],
    "signature/replay": ["signature", "replay", "nonce", "ecrecover", "permit", "подпис"],
    "economic": ["economic", "incentive", "profitab", "arbitrage", "mev", "sandwich", "экономич"],
    "state-machine": ["state machine", "invariant", "transition", "инвариант", "состояни"],
}


def read_text(path):
    for enc in ("utf-8", "cp1251", "latin-1"):
        try:
            with open(path, "r", encoding=enc, errors="strict") as f:
                return f.read()
        except Exception:
            continue
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def collect_reports(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for fn in files:
                    if os.path.splitext(fn)[1].lower() in REPORT_EXT:
                        out.append(os.path.join(root, fn))
        elif os.path.isfile(p):
            out.append(p)
    return out


def collect_sources(src, exts):
    out = []
    skip = {"node_modules", "lib", "out", "target", "build", ".git", "cache", "artifacts", "test", "tests"}
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d.lower() not in skip and not d.startswith(".")]
        for fn in files:
            if os.path.splitext(fn)[1].lower() in exts:
                full = os.path.join(root, fn)
                try:
                    loc = sum(1 for _ in open(full, "r", encoding="utf-8", errors="replace"))
                except Exception:
                    loc = 0
                out.append({"path": os.path.relpath(full, src).replace("\\", "/"),
                            "base": os.path.splitext(fn)[0], "loc": loc})
    return out


def load_commodity_hits(path):
    """§52: paths already touched by a commodity scanner — one per line, OR a JSON array."""
    if not path:
        return set()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception:
        return set()
    raw = raw.strip()
    if not raw:
        return set()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return {str(p).replace("\\", "/").strip() for p in data if str(p).strip()}
    except Exception:
        pass
    return {ln.strip().replace("\\", "/") for ln in raw.splitlines() if ln.strip()}


def analyze(src, report_paths, exts, top, commodity_hits=None):
    commodity_hits = commodity_hits or set()
    reports = collect_reports(report_paths)
    if not reports:
        return None, "no report file found (.md/.txt/.json)"
    sources = collect_sources(src, exts)
    if not sources:
        return None, "no sources found with extensions %s" % ",".join(exts)

    blob = "\n".join(read_text(p) for p in reports)
    low = blob.lower()

    for s in sources:
        # Matching by the file/contract base name is more robust than by full path:
        # reports almost always write `TrancheVault.sol` or just `TrancheVault`, not a path.
        b = s["base"].lower()
        if len(b) < 4:
            s["mentions"] = 0            # name too short -> noise, don't count
        else:
            s["mentions"] = len(re.findall(r"\b" + re.escape(b) + r"\b", low))
        # §52 commodity-join: scanner touched the path -> hot, even if the audit report was silent.
        s["commodity_hit"] = s["path"] in commodity_hits

    classes = {}
    for cls, markers in CLASS_MARKERS.items():
        classes[cls] = sum(low.count(m) for m in markers)

    def is_hot(s):
        return s["mentions"] > 0 or s["commodity_hit"]

    holes = [s for s in sources if not is_hot(s)]
    holes.sort(key=lambda s: -s["loc"])
    covered = [s for s in sources if is_hot(s)]
    covered.sort(key=lambda s: -s["mentions"])
    # Paths that became hot ONLY because of the commodity scan (the audit did not mention them) — for join transparency.
    commodity_joined = sorted(s["path"] for s in sources if s["commodity_hit"] and s["mentions"] == 0)

    return {
        "reports": reports,
        "sources_total": len(sources),
        "covered": covered[:top],
        "holes": holes[:top],
        "holes_total": len(holes),
        "class_coverage": classes,
        "crowd_heat": {s["path"]: ("hot" if is_hot(s) else "cold") for s in sources},
        "commodity_joined": commodity_joined,
    }, None


def main():
    ap = argparse.ArgumentParser(description="T14-A: audit-map inversion — where the crowd did NOT look")
    ap.add_argument("--src", required=True, help="root of the target's sources")
    ap.add_argument("--reports", required=True, nargs="+", help="report file(s)/folder(s) (.md/.txt)")
    ap.add_argument("--ext", default="", help="comma-separated extensions (default .sol,.rs,.go,.move,.cairo,.vy)")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--commodity-hits", default="",
                     help="§52: file with a list of paths touched by a commodity scanner (one per line, or a JSON array)")
    a = ap.parse_args()

    exts = [e.strip().lower() for e in a.ext.split(",") if e.strip()] or SRC_EXT_DEFAULT
    commodity_hits = load_commodity_hits(a.commodity_hits)
    res, err = analyze(a.src, a.reports, exts, a.top, commodity_hits=commodity_hits)
    if err:
        print("ERROR: %s" % err)
        sys.exit(2)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    print("=== AUDIT COVERAGE INVERT (T14-A)")
    print("reports read: %d · sources: %d · NEVER mentioned: %d"
          % (len(res["reports"]), res["sources_total"], res["holes_total"]))
    print()

    print("--- 🕳 MAP HOLES (crowd-heat: cold) — the crowd did not look here, these go FIRST")
    if not res["holes"]:
        print("    none — the reports cover every file by name (rare; check that the names match)")
    for s in res["holes"]:
        print("    %5d LOC  %s" % (s["loc"], s["path"]))
    print()

    print("--- 🔥 COVERED ZONE (crowd-heat: hot) — MUST be walked, but LATER")
    for s in res["covered"]:
        tag = " [commodity]" if s.get("commodity_hit") and s["mentions"] == 0 else ""
        print("    %3d mentions  %s%s" % (s["mentions"], s["path"], tag))
    print()

    if res["commodity_joined"]:
        print("--- 🔧 commodity-join (§52): hot ONLY via the scanner, the audit was silent — %d"
              % len(res["commodity_joined"]))
        for p in res["commodity_joined"]:
            print("    %s" % p)
        print()

    print("--- Bug classes: what the auditor was THINKING about (0 = class not discussed = class-level hole)")
    for cls, n in sorted(res["class_coverage"].items(), key=lambda kv: kv[1]):
        mark = "🕳" if n == 0 else "  "
        print("    %s %-18s %d" % (mark, cls, n))
    print()
    print("QUEUE RULE (idea B): cold -> first; hot -> mandatory, but after. `hot` does NOT mean")
    print("\"closed\": the crowd looked but did not follow through. A veto by crowd-heat = a voluntary blind spot.")
    print("The crowd-heat field is joined into the I-NN table in system_model.md (--json returns it in full).")


if __name__ == "__main__":
    main()
