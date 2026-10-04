#!/usr/bin/env python3
"""Selftest - model_eval_reader.py on the REAL model_eval: block of the manifest (3 phase0 cases) +
on the fail-open paths (PyYAML / block missing). Lightweight: does not mock YAML, reads the real file.

Prints N/N PASS. Non-zero exit on any failure (for manual runs - this check is NOT
wired into any CI/gate, model_eval/Layer-A remain occasional/manual - R11).

Usage:
  py -3 -X utf8 model_eval_reader_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_eval_reader as mer  # noqa: E402


def _check(label, cond, results):
    results.append((label, bool(cond)))


def run():
    results = []

    # ---- 1. the real manifest loads, the block is non-empty ----
    block, note = mer.load_model_eval()
    _check("model_eval block is readable (note is None)", note is None, results)
    if note is not None:
        print("FATAL: could not read the real model_eval block:", note)
        _print_and_exit(results)
        return 1

    s = mer.summarize(block)

    # ---- 2. three cases, known ids, in known order ----
    expected_ids = [
        "phase0-A-amm-k-invariant",
        "phase0-B-solana-collateral-chain",
        "phase0-C-governance-voting-power",
    ]
    actual_ids = [c.get("id") for c in s["cases"]]
    _check("3 cases in the manifest", s["total"] == 3, results)
    _check("id list matches the expected one (%s)" % expected_ids, actual_ids == expected_ids, results)

    # ---- 3. per-case hit expectations (A hit-baseline, B hit-baseline, C hit-rerun) ----
    expected_hits = {
        "phase0-A-amm-k-invariant": (True, "baseline"),
        "phase0-B-solana-collateral-chain": (True, "baseline"),
        "phase0-C-governance-voting-power": (True, "rerun"),
    }
    for c in s["cases"]:
        cid = c.get("id")
        hit, via = mer.case_hit(c)
        want = expected_hits.get(cid)
        _check(
            "case %s: hit=%s via=%s (expected %s)" % (cid, hit, via, want),
            want is not None and (hit, via) == want,
            results,
        )

    # ---- 4. total score 3/3 hits ----
    _check("total hits == 3/3", (s["hits"], s["total"]) == (3, 3), results)

    # ---- 5. gate line is present and the threshold is recognized as >=2 ----
    _check("gate text is present", bool(s["gate_text"]), results)
    _check("gate threshold recognized as 2", s["threshold"] == 2, results)
    _check("gate verdict == PASS (3>=2)", s["verdict"] == "PASS", results)

    # ---- 6. fail-open: nonexistent manifest path -> note, not a crash ----
    fake_path = os.path.join(os.path.dirname(mer.MANIFEST), "__does_not_exist__.yaml")
    fo_block, fo_note = mer.load_model_eval(fake_path)
    _check("fail-open on a missing file: block=={} and note!=None", fo_block == {} and fo_note is not None, results)

    # ---- 7. fail-open: valid YAML WITHOUT the model_eval key (no block) -> note, not a crash ----
    fd, tmp_path = tempfile.mkstemp(suffix=".yaml", prefix="model_eval_reader_selftest_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("cases:\n  - name: unrelated\n")
        nb_block, nb_note = mer.load_model_eval(tmp_path)
        _check("fail-open without the model_eval key: block=={} and note!=None", nb_block == {} and nb_note is not None, results)
    finally:
        os.remove(tmp_path)

    return _print_and_exit(results)


def _print_and_exit(results):
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print("=== model_eval_reader selftest ===")
    for label, ok in results:
        print("  [%s] %s" % ("PASS" if ok else "FAIL", label))
    print("\n%d/%d PASS" % (passed, total))
    ok_all = passed == total
    if not ok_all:
        print("SELFTEST FAILED")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    run()
