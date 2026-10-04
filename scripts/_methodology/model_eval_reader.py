#!/usr/bin/env python3
"""model_eval reader — reads the orphan `model_eval:` block (regression_manifest.yaml) and prints
a summary. `model_eval:` is the THIRD scorer of the manifest (phase0 T10 blind validation of
modeling, see `sessions/_methodology/phase0_blind/PROTOCOL.md`), which `regression_replay.py`
does NOT read (its docstring / the manifest comment at :33: "The run is MANUAL for now —
regression_replay.py does not know about this block"). This script makes the block consumable
without parsing YAML by eye.

Read-only: does NOT mutate the manifest, does NOT run cold agents, does NOT automate the Layer-A
blind hunt (`benchmark_blind_protocol.md`) — that stays a manual occasional run (R11). This reader
only prints what is ALREADY recorded in the `model_eval:` block (baseline/rerun results of past
rounds).

Parser — PyYAML (`yaml.safe_load`), the same path that `regression_replay.py::load_manifest` takes
as primary (the mini-parser there is a fallback for when PyYAML is missing; here that case is
fail-open — we do not reinvent a mini-parser for the nested model_eval structure, that is separate
work).

fail-open: PyYAML is not installed, OR the manifest is unreadable, OR there is no `model_eval:`
block → prints an explanatory note and exits 0 (NOT a crash, NOT a non-zero exit — this is a
read-only convenience tool, not a completeness gate).

Usage:
  py -3 -X utf8 model_eval_reader.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
MANIFEST = os.path.join(SESSIONS, "_methodology", "regression_manifest.yaml")


def load_model_eval(manifest_path=MANIFEST):
    """Returns (block: dict, note: str|None). note!=None => fail-open, block == {}."""
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        return {}, "could not read manifest (%s): %s" % (manifest_path, e)

    try:
        import yaml  # noqa
    except ImportError:
        return {}, 'PyYAML is not installed (py -3 -c "import yaml" will fail) — fail-open, model_eval not read'

    try:
        data = yaml.safe_load(raw)
    except Exception as e:
        return {}, "YAML parse error in manifest: %s" % e

    if not isinstance(data, dict):
        return {}, "manifest is not a top-level dict — unexpected shape"

    block = data.get("model_eval")
    if not block:
        return {}, "model_eval: block is missing from the manifest (nothing to read)"
    if not isinstance(block, dict):
        return {}, "model_eval: block is not a dict (broken YAML) — fail-open"

    return block, None


def case_hit(case):
    """A case counts as a hit if baseline.hit is True, or (baseline.hit False AND rerun.hit True) —
    i.e. a hit on the rerun by a senior model also counts (see PROTOCOL.md section "Model tier
    matters" + manifest case C: baseline missed, rerun on senior — hit).
    Returns (hit: bool, via: 'baseline'|'rerun'|None)."""
    baseline = case.get("baseline") or {}
    if baseline.get("hit"):
        return True, "baseline"
    rerun = case.get("rerun") or {}
    if rerun.get("hit"):
        return True, "rerun"
    return False, None


def parse_gate_threshold(gate_text):
    """Best-effort extraction of the '>=N' threshold from free-text gate. None if it could not be
    parsed — then PASS/FAIL is not printed (we don't guess the shape of future blocks), only the
    raw text."""
    if not gate_text:
        return None
    m = re.search(r">=\s*(\d+)", gate_text)
    return int(m.group(1)) if m else None


def _status_str(entry):
    """pred vs actual — prints both if actual is present and differs from pred (a signal of
    SUBSTITUTED-class misses — see case phase0-C in the manifest, hiding it would be dishonest)."""
    pred = entry.get("status_predicted", "?")
    actual = entry.get("status_actual")
    if actual and actual != pred:
        return "status_pred=%s status_actual=%s" % (pred, actual)
    return "status=%s" % pred


def format_case_line(case):
    cid = case.get("id", "?")
    hit, via = case_hit(case)
    baseline = case.get("baseline") or {}
    rerun = case.get("rerun") or {}
    tag = "[HIT]" if (hit and via == "baseline") else ("[HIT*]" if hit else "[miss]")

    line = "  %-6s %-38s baseline(%s) hit=%s" % (
        tag, cid, baseline.get("tier", "?"), baseline.get("hit"),
    )
    if baseline.get("hit"):
        line += " rank=%s %s" % (baseline.get("rank", "?"), _status_str(baseline))
    if rerun:
        line += "  -> rerun(%s) hit=%s" % (rerun.get("tier", "?"), rerun.get("hit"))
        if rerun.get("hit"):
            line += " rank=%s %s" % (rerun.get("rank", "?"), _status_str(rerun))
    return line


def summarize(block):
    """Counts cases/hits/threshold from the block. Returns a dict — reused by the selftest
    so the counting logic is not duplicated."""
    cases = block.get("cases") or []
    hits = sum(1 for c in cases if case_hit(c)[0])
    gate_text = block.get("gate", "")
    threshold = parse_gate_threshold(gate_text)
    verdict = None
    if threshold is not None:
        verdict = "PASS" if hits >= threshold else "FAIL"
    return {
        "cases": cases,
        "total": len(cases),
        "hits": hits,
        "gate_text": gate_text,
        "threshold": threshold,
        "verdict": verdict,
    }


def print_summary(block):
    print("=== model_eval reader ===")
    for key in ("protocol_ref", "ground_truth_ref", "results_ref"):
        if key in block:
            print("%s: %s" % (key, block[key]))
    if "hit_criteria" in block:
        print("hit_criteria: %s" % block["hit_criteria"])

    s = summarize(block)
    if s["gate_text"]:
        print("gate: %s" % s["gate_text"])

    print("\ncases (%d):" % s["total"])
    for c in s["cases"]:
        print(format_case_line(c))
        note = c.get("note")
        if note:
            print("         note: %s" % note.strip().replace("\n", " "))

    print("\nsummary: hits=%d/%d" % (s["hits"], s["total"]), end="")
    if s["threshold"] is not None:
        print(" (gate threshold >=%d) -> %s" % (s["threshold"], s["verdict"]))
    else:
        print(" (gate threshold not parsed from text — check manually: %r)" % s["gate_text"])
    return s


def main():
    block, note = load_model_eval()
    if note:
        print("model_eval reader: %s" % note)
        sys.exit(0)
    print_summary(block)
    sys.exit(0)


if __name__ == "__main__":
    main()
