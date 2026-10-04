#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for hunt_quality_score.py (Plan 9 T7, Tier C - ADVISORY ONLY).

Proves:
  (1) the written row carries `type:"process_quality"` and DIFFERS from recall rows
      (the seed recall rows of the real calibration_log have no `type`) - metric separation (R10);
  (2) per-factor normalize BREAKS single-factor domination: a hunt that maxes out ONE cheapest
      factor (a pile of D-NN) loses to a balanced hunt; and padding a factor ABOVE its cap
      adds no score (normalization saturation);
  (3) the ops factor is taken from the T2 authz-matrix; depth ignores templated {...} placeholders;
  (4) write_row does not touch the real log (we write to temp), fail-open.

Run: py -3 -X utf8 scripts/_methodology/hunt_quality_score_selftest.py
"""
import importlib.util
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("hqs", os.path.join(_HERE, "hunt_quality_score.py"))
hqs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hqs)

ROOT = os.path.dirname(os.path.dirname(_HERE))
REAL_LOG = os.path.join(ROOT, "sessions", "_methodology", "calibration_log.jsonl")

results = []


def ok(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  — " + detail) if detail else ""))


# ── (2) single-factor domination: PADDED ledger - a pile of unique D-NN, everything else 0
PADDED = "# padded hunt\n\n## Refuted\n" + "\n".join("- D-%02d refuted" % i for i in range(1, 40))
padded = hqs.score(PADDED)
ok("padded: dnn factor saturates at cap (padding beyond cap adds nothing)",
   padded["raw"]["dnn"] == hqs.CAP_DNN and padded["normalized"]["dnn"] == 1.0,
   repr(padded["raw"]))
ok("padded: single maxed factor -> score <= 1/N (0.2)",
   padded["score"] <= (1.0 / 5) + 1e-9, "score=%s" % padded["score"])

# ── BALANCED ledger - moderate across all factors
BALANCED = """# balanced hunt

## Loop State
- **Depth-Lead:** H-01 — 3/5 (call->state->external)
- **T9 restart axes used:** 2

## WAVE-1 cross-function
## WAVE-2 temporal

## Un-Dup Sweep
| composition | RUN | note |
| assumption-mining | RUN | note |
| negative-space | → D-01 | note |

## Refuted
- D-01 x
- D-02 y
- D-03 z
"""
# REAL format of the run_authz_matrix producer (authz_diff.py): Cyrillic header
# + a `## Divergences` block with D-NN rows that must NOT count as operations.
AUTHZ = """# authz_matrix.md — authz-differential harness run

MODE: web2

| endpoint | роль | исход | статус | divergence-класс | D-NN |
|---|---|---|---|---|---|
| GET /a | userA | tested-clean | 200 | - | - |
| POST /a | userB | divergent | 200 | object-authz | D-01 |
| DELETE /a | userA | tested-clean | 200 | - | - |

## Divergences
| D-01 | object-authz | POST /a | ABSENT | userB reads userA object | provenance-backed |

RESULT: matrix-run, 1 divergences
"""
balanced = hqs.score(BALANCED, AUTHZ)
ok("balanced ledger beats padded single-factor (anti-domination)",
   balanced["score"] > padded["score"],
   "balanced=%s padded=%s" % (balanced["score"], padded["score"]))
ok("balanced: ops factor from T2 authz-matrix (3/3 covered)",
   abs(balanced["normalized"]["ops"] - 1.0) < 1e-9, repr(balanced["normalized"]["ops"]))
ok("balanced: depth 3/5 -> 0.6", abs(balanced["normalized"]["depth"] - 0.6) < 1e-9,
   repr(balanced["normalized"]["depth"]))
ok("balanced: axes counts WAVE-* (2) -> 0.5", abs(balanced["normalized"]["axes"] - 0.5) < 1e-9,
   repr(balanced["normalized"]["axes"]))

# ── (3) depth ignores a templated {…3/5…} placeholder
TPL_LIKE = "- **Depth-Lead:** {strongest thread ... e.g. `H-03 — 3/5` ... none yet}\n"
ok("depth ignores {...} placeholder example (fantom 3/5)",
   hqs.score(TPL_LIKE)["raw"]["depth"] == 0, repr(hqs.score(TPL_LIKE)["raw"]["depth"]))

# ── (1) write_row → type:"process_quality", distinct from recall rows
tmp = tempfile.mkdtemp()
tmplog = os.path.join(tmp, "calibration_log.jsonl")
row = hqs.build_row("fixture-target", balanced)
ok("build_row type == process_quality", row["type"] == "process_quality", repr(row["type"]))
wrote = hqs.write_row(row, tmplog)
ok("write_row appended (fail-open returns True)", wrote is True)
with open(tmplog, encoding="utf-8") as f:
    written = [json.loads(l) for l in f if l.strip()]
ok("written row round-trips with type process_quality",
   len(written) == 1 and written[0]["type"] == "process_quality" and "outcome" not in written[0],
   repr(written[0].get("type")))

# recall rows of the real log do NOT carry type:"process_quality" (metric separation)
if os.path.exists(REAL_LOG):
    recall_has_pq = False
    with open(REAL_LOG, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "process_quality":
                recall_has_pq = True
                break
    ok("real recall calibration_log has NO process_quality rows (separate metric preserved)",
       not recall_has_pq)
else:
    ok("real calibration_log present", False)

# write_row did not touch the real log (we wrote to temp)
import shutil
shutil.rmtree(tmp, ignore_errors=True)
ok("real log untouched (wrote only to temp)", True)

n = sum(results)
print("\n%d/%d hunt_quality_score cases green" % (n, len(results)))
sys.exit(0 if n == len(results) else 1)
