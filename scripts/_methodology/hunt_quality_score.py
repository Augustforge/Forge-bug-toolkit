#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hunt_quality_score.py — per-hunt PROCESS-quality (Plan 9 T7, Tier C — ADVISORY ONLY).

Measures hunt PROCESS QUALITY, NOT recall (anti-Goodhart, R10). Five factors:
  depth   — depth of the strongest thread (Depth-Lead `N/5`)          cap 5
  ops     — share of operations with an outcome (T2 operation-completeness)  0..1 (0 if no authz-matrix)
  dnn     — number of unique D-NN (divergence-first)                 cap 6
  axes    — number of axes covered (## WAVE-* + T9 restart axes used)  cap 4
  undup   — number of un-dup generators with status RUN/→ D-NN       cap 6

**per-factor normalize (key requirement of T7):** each factor is normalized to [0,1] by its OWN
cap, the result = MEAN of the normalized values. So one inflated (cheapest) factor gives at most
1/N of the contribution — "padding the cheapest factor cannot dominate": a balanced hunt beats a hunt
where one factor is maxed out. A hunt without a bug is not a black hole (inputs-not-outputs) - the process is measured
separately from the finding.

**ADVISORY ONLY.** Written as a `type:"process_quality"` row in `calibration_log.jsonl` — SEPARATE from
recall rows (those have no `type` / have `outcome`). NEVER feeds SELECT / HUNT-EXIT (R2/R10).

fail-open: bad input -> factor 0, not a crash.

Run: py -3 -X utf8 scripts/_methodology/hunt_quality_score.py --ledger <hypotheses.md> [--target T] \
       [--authz-matrix <authz_matrix.md>] [--log <calibration_log.jsonl>] [--no-write]
"""
import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))  # 
DEFAULT_LOG = os.path.join(ROOT, "sessions", "_methodology", "calibration_log.jsonl")

# normalization caps (retune points)
CAP_DEPTH = 5
CAP_DNN = 6
CAP_AXES = 4
CAP_UNDUP = 6

_DEPTH_RE = re.compile(r"(\d+)\s*/\s*5")
_DNN_RE = re.compile(r"\bD-\d+\b")
_WAVE_RE = re.compile(r"(?im)^#{1,4}\s*WAVE-\S+")
_T9_RE = re.compile(r"(?i)T9 restart axes used:\s*(\d+)")
# operation-completeness (T2) status enum
_OPS_STATUS = ("tested-clean", "divergent", "inconclusive", "excluded", "blocked")


def _depth_factor(text):
    """Maximum N from Depth-Lead `N/5` (ignoring placeholder examples in {...})."""
    best = 0
    for line in text.splitlines():
        s = line.strip()
        if not s.lower().startswith("- **depth-lead"):
            continue
        # strip placeholder examples {...} so the template's `{… 3/5 …}` is not counted as work
        cleaned = re.sub(r"\{[^}]*\}", "", s)
        for m in _DEPTH_RE.finditer(cleaned):
            best = max(best, int(m.group(1)))
    return min(best, CAP_DEPTH)


def _dnn_factor(text):
    return min(len(set(_DNN_RE.findall(text))), CAP_DNN)


def _axes_factor(text):
    waves = len(_WAVE_RE.findall(text))
    t9 = 0
    for m in _T9_RE.finditer(text):
        t9 = max(t9, int(m.group(1)))
    return min(max(waves, t9), CAP_AXES)


def _undup_factor(text):
    """Un-Dup Sweep rows with status RUN or → D-NN (a deliberate generator run)."""
    cnt = 0
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        low = s.lower()
        if ("| run |" in low) or ("→ d-" in low) or ("-> d-" in low):
            cnt += 1
    return min(cnt, CAP_UNDUP)


def _ops_factor(authz_text):
    """Share of (operation,role) rows with an outcome status from the T2 matrix. No matrix → 0.0.
    Count ONLY the operations table; the `## Divergences` block (D-NN rows) is NOT operations.
    The header of the real producer `run_authz_matrix` is Cyrillic
    (columns: endpoint | role | outcome | status | divergence-class | D-NN, with Russian names for role/outcome/status), supported + Latin fallback."""
    if not authz_text:
        return 0.0
    total = 0
    covered = 0
    for line in authz_text.splitlines():
        s = line.strip().lower()
        if s.startswith("## divergences") or s.startswith("## дивергенц"):  # Cyrillic variant kept: matches the producer's heading
            break  # the D-NN block below is not operation rows
        if not s.startswith("|"):
            continue
        # header: Cyrillic (outcome/status + role/endpoint) OR Latin (status + role/operation)
        if ("исход" in s or "статус" in s) and ("роль" in s or "endpoint" in s or "operation" in s):  # Cyrillic header words kept (logic)
            continue
        if "status" in s and ("role" in s or "operation" in s):
            continue
        if set(s) <= set("|-: "):
            continue  # separator
        total += 1
        if any(st in s for st in _OPS_STATUS):
            covered += 1
    if total == 0:
        return 0.0
    return covered / float(total)


def score(ledger_text, authz_text=None):
    """Return dict: raw factors, normalized [0,1], final score (mean of the normalized)."""
    raw = {
        "depth": _depth_factor(ledger_text),
        "ops": _ops_factor(authz_text),
        "dnn": _dnn_factor(ledger_text),
        "axes": _axes_factor(ledger_text),
        "undup": _undup_factor(ledger_text),
    }
    norm = {
        "depth": raw["depth"] / float(CAP_DEPTH),
        "ops": min(max(raw["ops"], 0.0), 1.0),
        "dnn": raw["dnn"] / float(CAP_DNN),
        "axes": raw["axes"] / float(CAP_AXES),
        "undup": raw["undup"] / float(CAP_UNDUP),
    }
    # per-factor normalize → mean: one inflated factor gives at most 1/N of the contribution.
    overall = sum(norm.values()) / float(len(norm))
    return {"raw": raw, "normalized": norm, "score": round(overall, 4)}


def build_row(target, scored, extra=None):
    row = {
        "type": "process_quality",
        "timestamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target": target or "unknown",
        "factors_raw": scored["raw"],
        "factors_normalized": scored["normalized"],
        "process_quality_score": scored["score"],
        "advisory": "ADVISORY ONLY — process quality, NOT recall; NEVER feeds SELECT/HUNT-EXIT (Plan 9 R2/R10).",
    }
    if extra:
        row.update(extra)
    return row


def write_row(row, log_path=None):
    """Append a row to calibration_log.jsonl. fail-open."""
    lp = log_path or DEFAULT_LOG
    try:
        with open(lp, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description="Per-hunt process-quality score (Plan 9 T7, advisory-only).")
    ap.add_argument("--ledger", required=True, help="path to hypotheses.md")
    ap.add_argument("--target", default=None)
    ap.add_argument("--authz-matrix", default=None, help="path to authz_matrix.md (T2 ops)")
    ap.add_argument("--log", default=None, help="calibration_log.jsonl (default: toolkit)")
    ap.add_argument("--no-write", action="store_true", help="compute + print, do not append row")
    args = ap.parse_args(argv)
    try:
        with open(args.ledger, encoding="utf-8") as f:
            ledger_text = f.read()
    except Exception as e:
        print("cannot read ledger: %s" % e, file=sys.stderr)
        return 1
    authz_text = None
    if args.authz_matrix:
        try:
            with open(args.authz_matrix, encoding="utf-8") as f:
                authz_text = f.read()
        except Exception:
            authz_text = None  # fail-open
    scored = score(ledger_text, authz_text)
    row = build_row(args.target, scored)
    print(json.dumps(row, ensure_ascii=False, indent=2))
    if not args.no_write:
        ok = write_row(row, args.log)
        print("written: %s" % ("yes" if ok else "no (fail-open)"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
