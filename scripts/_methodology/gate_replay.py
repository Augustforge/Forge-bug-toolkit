#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate replay — regression harness for the completeness-gate DETECTORS (missing instrument).

Problem (diagnosis 2026-07-06): we have regression_replay.py for ONE axis — scout recall.
But the fastest-growing/riskiest layer — the abort/give-up detectors of the Stop hook (ABORT list + FORK_RE +
DECISION_Q_RE + BREADTH_RE, we add to them nearly every session) — was measured by nothing except ad-hoc unit tests
"the regex fires on a constructed input". This harness closes the gap: a corpus of REAL
final assistant messages (give-ups from past hunts + legitimate statuses) → run through the LIVE
detectors (imported from hunt_completeness_gate.py, not a copy) → two metrics:

  - recall  on label=abort  : share of give-ups the gate CATCHES (should be high — a miss =
                              the instance gave up and left the loop).
  - FP-rate on label=benign : share of legitimate statuses wrongly blocked (should be LOW —
                              FP = a legitimate hunt is looped / ritual busywork instead of thinking).

Block predicate = an EXACT copy of main() step-1: any(ABORT) or FORK_RE or DECISION_Q_RE or BREADTH_RE.
Prints MISSES (uncaught give-ups) and FALSE-POSITIVES (needlessly caught benign) by name + WHICH
detector/substring fired — this is an actionable output (what to fix), not a bare number. Writes a summary to
calibration_log.jsonl (type gate_regression) — so future detector edits are measured: recall does not
drop / FP does not rise (measure-don't-feel for a layer that was previously unmeasured).

Usage:  py -3 -X utf8 gate_replay.py [path/to/gate_corpus.jsonl]
"""
import importlib.util
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOOK = os.path.join(ROOT, "scripts", "hooks", "hunt_completeness_gate.py")
CORPUS = os.path.join(ROOT, "sessions", "_methodology", "gate_corpus.jsonl")
CALIB = os.path.join(ROOT, "sessions", "_methodology", "calibration_log.jsonl")


def load_gate():
    spec = importlib.util.spec_from_file_location("gate", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def which_detectors(gate, text, ctx=None):
    """Which detectors fired + for ABORT — exactly WHICH substring (actionable for FP triage).
    ctx='exhaustion' simulates ledger_exhaustion_shape=True → adds a check of the contextual
    soft-exhaustion detector. Without ctx the soft vocabulary is NOT checked (as in the hook:
    in a healthy ledger the same words are legitimate)."""
    al = text.lower()
    hits = []
    abort_subs = [a for a in gate.ABORT if a in al]
    if abort_subs:
        hits.append("ABORT{%s}" % ",".join(abort_subs[:4]))
    if gate.FORK_RE.search(al):
        hits.append("FORK")
    if gate.DECISION_Q_RE.search(al):
        hits.append("DECISION")
    if gate.BREADTH_RE.search(al):
        hits.append("BREADTH")
    # _paraphrase_giveup — a cluster give-up detector (>=2 categories hardened/exhaustion/bad-EV/park/
    # decision/pivot). It was in the main() predicate, but NOT in the harness (a gap — not measured). 2026-08-18.
    if gate._paraphrase_giveup(text):
        hits.append("PARAPHRASE")
    if ctx == "exhaustion":
        soft = gate.soft_exhaustion_signal(text)
        if soft:
            hits.append("SOFT-EXH{%s}" % ",".join(soft[:3]))
    return hits


def load_corpus(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CORPUS
    gate = load_gate()
    rows = load_corpus(path)

    aborts = [r for r in rows if r.get("label") == "abort"]
    benigns = [r for r in rows if r.get("label") == "benign"]

    misses, fps, ok_abort, ok_benign = [], [], [], []
    for r in aborts:
        hits = which_detectors(gate, r["text"], r.get("ctx"))
        (ok_abort if hits else misses).append((r, hits))
    for r in benigns:
        hits = which_detectors(gate, r["text"], r.get("ctx"))
        (fps if hits else ok_benign).append((r, hits))

    n_ab, n_be = len(aborts), len(benigns)
    recall = len(ok_abort) / n_ab if n_ab else 0.0
    fp_rate = len(fps) / n_be if n_be else 0.0

    print("=== gate replay (completeness-gate detectors) ===")
    print("corpus: %d abort / %d benign" % (n_ab, n_be))
    print("recall  (abort caught)   = %d/%d = %.2f" % (len(ok_abort), n_ab, recall))
    print("FP-rate (benign flagged) = %d/%d = %.2f" % (len(fps), n_be, fp_rate))

    if misses:
        print("\n--- MISSES (give-up NOT caught → fix: add a structural detector) ---")
        for r, _ in misses:
            print("  ! %-28s %s" % (r["id"], r["text"][:90]))
    else:
        print("\nMISSES: none — all give-ups caught.")

    if fps:
        print("\n--- FALSE-POSITIVES (benign needlessly blocked → fix: narrow the detector/substring) ---")
        for r, hits in fps:
            print("  x %-28s via %s" % (r["id"], " ".join(hits)))
            print("      %s" % r.get("note", ""))
    else:
        print("\nFALSE-POSITIVES: none — no benign blocked.")

    rec = {
        "ts": int(time.time()),
        "type": "gate_regression",
        "corpus": os.path.relpath(path, ROOT),
        "abort_n": n_ab,
        "benign_n": n_be,
        "recall": round(recall, 3),
        "fp_rate": round(fp_rate, 3),
        "misses": [r["id"] for r, _ in misses],
        "false_positives": [r["id"] for r, _ in fps],
    }
    try:
        with open(CALIB, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print("\n-> appended to", os.path.relpath(CALIB, ROOT))
    except Exception as e:
        print("WARN: could not write calibration_log:", e)

    # Not failing on FP/miss (this is diagnostics, not a CI gate) — exit 0 always.
    sys.exit(0)


if __name__ == "__main__":
    main()
