#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for disclosed_benchmark_replay.py (Layer-B scorer).

Prove FIRING, not only-pass ([[feedback_hook_must_prove_firing]]): on a SYNTHETIC fixture corpus
(we do NOT touch the real manifest) with a KNOWN ground-truth we check that the scorer counts CORRECTLY and —
critically — DISCRIMINATES: a flipped lead → per-generator recall DROPS (otherwise always-pass), and the
min-N threshold really CUTS (n=4 suppressed <-> n=5 shown — not always-suppress / not always-show).

The fixture is designed to have BOTH slice modes:
  n>=MIN_N: genA n=5 (recall 0.8, discriminating), genFive n=5 (1.0, boundary), CatBig n=5 (1.0);
  n<MIN_N: genFour n=4 (suppressed), genAll 2/2 and genZero 0/2 (symmetry), CatSmall n=4, dev split n=2.

Assert coverage:
  [1] per-generator/per-class/per-split correct + min-N render (n>=5 shown, n<5 suppressed);
      unscored is counted SEPARATELY (genOnlyUnscored excluded from by_generator, NOT a miss);
  [3] STRUCTURAL FIELDS in every emit record (layer/metric_kind/match_granularity/n_cases/split/
      insufficient_sample) + every slice carries n+recall+insufficient_sample alongside;
  [4] DISCRIMINATION: a flipped lead → genA recall drops 0.8 → 0.6 (n=5, a real number);
  [min-N] threshold MIN_N=5: n=4 SUPPRESSED, n=5 SHOWN (threshold discrimination) + SYMMETRY (0/2 and 2/2 at
      n<MIN_N → both insufficient — 0/1 is NOT "silent", 1/1 is NOT "catching");
  [split-mix] corpus-integrity guard: a case in >1 split → CorpusSplitMixError (fail-loud) + no false
      trigger on a clean corpus;
  [held-out] held-out FIRST in stdout, labeled PRIMARY(clean); soft-seen labeled contaminated;
  [collision] BLOB-SCOPE (Important-fix Task 2): a phantom hit via a basename collision does NOT inflate;
  [live] the live-adapter branch is not vaporware + Minor#1 (a co-expected one without an adapter is excluded).

Usage:  py -3 -X utf8 disclosed_benchmark_selftest.py
"""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_MOD_PATH = os.path.join(HERE, "disclosed_benchmark_replay.py")


def load_scorer():
    spec = importlib.util.spec_from_file_location("disclosed_benchmark_replay", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DB = load_scorer()

_PASS = 0
_FAIL = 0


def check(cond, label):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print("  [PASS] %s" % label)
    else:
        _FAIL += 1
        print("  [FAIL] %s" % label)


def rec_of(records, split):
    for r in records:
        if r["split"] == split:
            return r
    return None


# ---------- fixture corpus (synthetic, known ground-truth) ----------
def fixture_cases():
    """soft-seen x9 (5 CatBig + 4 CatSmall), dev x3 (D1/D2 scored, D3 unscored), held-out x0.
    Generator expectations are tuned to the thresholds: genA/genFive n=5 (>=MIN_N), genFour n=4 (<MIN_N),
    genAll/genZero n=2 (symmetry), genD n=2 (dev), genOnlyUnscored only in unscored D3."""
    cases = []
    # soft-seen CatBig x5 — genA, genFive are expected on each (n=5 for both)
    for i in range(1, 6):
        cases.append({"name": "C%d" % i, "split": "soft-seen", "cat": "CatBig",
                      "bug_location": "src/f%d.sol:10" % i, "snapshot_ref": "manifest-only",
                      "expected_generators": ["genA", "genFive"]})
    # soft-seen CatSmall x4 — genFour on all (n=4); genAll on C6/C7, genZero on C8/C9 (n=2 each)
    for i in range(6, 10):
        second = "genAll" if i in (6, 7) else "genZero"
        cases.append({"name": "C%d" % i, "split": "soft-seen", "cat": "CatSmall",
                      "bug_location": "src/f%d.sol:10" % i, "snapshot_ref": "manifest-only",
                      "expected_generators": ["genFour", second]})
    # dev x3 — D1/D2 covered (scored), D3 NOT covered (unscored). genOnlyUnscored lives only in D3.
    cases.append({"name": "D1", "split": "dev", "cat": "CatD", "bug_location": "src/d1.sol:10",
                  "snapshot_ref": "manifest-only", "expected_generators": ["genD"]})
    cases.append({"name": "D2", "split": "dev", "cat": "CatD", "bug_location": "src/d2.sol:10",
                  "snapshot_ref": "manifest-only", "expected_generators": ["genD"]})
    cases.append({"name": "D3", "split": "dev", "cat": "CatD", "bug_location": "src/d3.sol:10",
                  "snapshot_ref": "manifest-only", "expected_generators": ["genD", "genOnlyUnscored"]})
    # held-out x0 — intentionally no records
    return cases


def fixture_blob(flip=False):
    """covers = C1..C9,D1,D2 (D3 → unscored). Leads are attributed to generators.
    Ground-truth (base):
      genA hits C1..C4, miss C5 → 4/5 = 0.80 (n=5 >=MIN_N shown);  flip → 3/5 = 0.60 (discrimination)
      genFive hits C1..C5 → 5/5 = 1.0 (n=5 boundary shown)
      genFour hits C6,C7 → 2/4 (n=4 <MIN_N SUPPRESSED)
      genAll hits C6,C7 → 2/2 ; genZero has no hits → 0/2 (symmetry, both n=2 <MIN_N SUPPRESSED)
      genD hits D1, miss D2 → 1/2 (dev)  ;  genZero@NOWHERE = FP."""
    c1_genA = "src/WRONG.sol:11" if flip else "src/f1.sol:11"
    return {
        "target": "fixture",
        "covers": ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "D1", "D2"],
        "leads": [
            {"generator": "genA", "file_line": c1_genA},          # C1 (or a miss when flipped)
            {"generator": "genA", "file_line": "src/f2.sol:11"},  # C2 hit
            {"generator": "genA", "file_line": "src/f3.sol:11"},  # C3 hit
            {"generator": "genA", "file_line": "src/f4.sol:11"},  # C4 hit (miss C5 — no lead)
            {"generator": "genFive", "file_line": "src/f1.sol:12"},
            {"generator": "genFive", "file_line": "src/f2.sol:12"},
            {"generator": "genFive", "file_line": "src/f3.sol:12"},
            {"generator": "genFive", "file_line": "src/f4.sol:12"},
            {"generator": "genFive", "file_line": "src/f5.sol:12"},  # genFive C1..C5 (5/5)
            {"generator": "genFour", "file_line": "src/f6.sol:11"},
            {"generator": "genFour", "file_line": "src/f7.sol:11"},  # genFour C6,C7 (2/4)
            {"generator": "genAll", "file_line": "src/f6.sol:13"},
            {"generator": "genAll", "file_line": "src/f7.sol:13"},   # genAll C6,C7 (2/2)
            {"generator": "genZero", "file_line": "src/NOWHERE.sol:9"},  # FP; genZero does not fire (0/2)
            {"generator": "genD", "file_line": "src/d1.sol:11"},    # D1 hit (miss D2)
        ],
    }


# ---------- tests ----------
def test_primary():
    print("\n[1] leads.json-fed — per-generator/per-class/per-split/unscored (+min-N render)")
    cases = fixture_cases()
    recs = DB.score_corpus(cases, [fixture_blob(flip=False)], live=False)
    ss = rec_of(recs, "soft-seen")
    dev = rec_of(recs, "dev")
    held = rec_of(recs, "held-out")

    # n>=MIN_N slices — real recall + insufficient_sample=False
    check(ss["by_generator"]["genA"] == {"hit": 4, "n": 5, "recall": 0.8, "insufficient_sample": False},
          "genA soft-seen recall = 4/5 = 0.80 (n=5 >= MIN_N → shown)")
    check(ss["by_generator"]["genFive"] == {"hit": 5, "n": 5, "recall": 1.0, "insufficient_sample": False},
          "genFive soft-seen recall = 5/5 = 1.0 (n=5 boundary → shown)")
    check(ss["by_class"]["CatBig"] == {"hit": 5, "n": 5, "recall": 1.0, "insufficient_sample": False},
          "CatBig case-recall = 5/5 (n=5 → shown)")

    # n<MIN_N slices — recall suppressed, k/n stays visible
    gf = ss["by_generator"]["genFour"]
    check(gf["recall"] is None and gf["insufficient_sample"] is True and gf["hit"] == 2 and gf["n"] == 4,
          "genFour n=4 <MIN_N → insufficient-sample (recall:null, k/n=2/4 visible)")
    cs = ss["by_class"]["CatSmall"]
    check(cs["recall"] is None and cs["insufficient_sample"] is True and cs["hit"] == 2 and cs["n"] == 4,
          "CatSmall n=4 <MIN_N → insufficient-sample (recall:null)")

    # per-split separated; dev n_scored=2 <MIN_N → split-level suppressed; D3 unscored
    check(dev["n_cases"] == 3 and dev["n_scored"] == 2 and dev["unscored_n"] == 1,
          "dev: n_cases=3, scored=2, unscored_n=1 (D3 not covered)")
    check(dev["insufficient_sample"] is True and dev["recall"] is None and dev["n_surfaced"] == 1,
          "dev split-level n_scored=2 <MIN_N → insufficient-sample (recall:null; n_surfaced=1 visible)")

    # unscored SEPARATELY, not a miss — a generator ONLY from unscored D3 is excluded
    check("genOnlyUnscored" not in dev["by_generator"],
          "genOnlyUnscored (only in unscored D3) is excluded from by_generator (NOT counted as a miss)")

    # soft-seen split-level n_scored=9 >=MIN_N → SHOWN (contrast with dev)
    check(ss["insufficient_sample"] is False and ss["recall"] == round(7 / 9, 3)
          and ss["n_surfaced"] == 7 and ss["n_scored"] == 9,
          "soft-seen split-level n_scored=9 >=MIN_N → shown 7/9 = %.3f" % round(7 / 9, 3))

    # held-out n=0 handled (no crash; recall=null + insufficient_sample=True, not averaged)
    check(held is not None and held["n_cases"] == 0 and held["recall"] is None
          and held["insufficient_sample"] is True,
          "held-out n_cases=0 → recall=null + insufficient_sample=True (does not crash, not averaged)")

    # precision corpus-level = 14/15 (genZero@NOWHERE = the only FP)
    check(ss["precision"] == round(14 / 15, 3), "precision (corpus) = 14/15 = %.3f" % round(14 / 15, 3))
    check(ss["by_generator_fp"].get("genZero") == 1, "genZero FP = 1 (the NOWHERE.sol lead hit nothing)")

    # render does not crash + prints the FILE-level marker + the insufficient-sample marker
    txt = DB.render(recs)
    check("split=held-out" in txt and "lead-surfacing" in txt.lower(),
          "render prints held-out + the FILE-level marker 'lead-surfacing'")
    check("insufficient-sample" in txt,
          "render prints 'insufficient-sample' for tiny-N slices (not a bare number)")


def test_struct_fields():
    print("\n[3] STRUCTURAL FIELDS (honesty core) — present in EVERY record + every slice")
    cases = fixture_cases()
    recs = DB.score_corpus(cases, [fixture_blob(flip=False)], live=False)
    for r in recs:
        s = r.get("split")
        check(r.get("layer") == "B", "[%s] layer=='B'" % s)
        check(r.get("metric_kind") == "lead-surfacing", "[%s] metric_kind=='lead-surfacing'" % s)
        check(r.get("match_granularity") == "file", "[%s] match_granularity=='file'" % s)
        check("n_cases" in r, "[%s] n_cases present" % s)
        check("split" in r, "[%s] split present" % s)
        check("insufficient_sample" in r, "[%s] split-level insufficient_sample present" % s)
        # invariant: no per-generator recall exists without adjacent n + insufficient_sample
        for g, v in r.get("by_generator", {}).items():
            check("n" in v and "recall" in v and "insufficient_sample" in v,
                  "[%s] by_generator[%s] carries n+recall+insufficient_sample alongside" % (s, g))


def test_discrimination():
    print("\n[4] DISCRIMINATION — a flipped lead → genA recall drops (not always-pass)")
    cases = fixture_cases()
    base = DB.score_corpus(cases, [fixture_blob(flip=False)], live=False)
    flip = DB.score_corpus(cases, [fixture_blob(flip=True)], live=False)
    r0 = rec_of(base, "soft-seen")["by_generator"]["genA"]
    r1 = rec_of(flip, "soft-seen")["by_generator"]["genA"]
    check(r0["recall"] == 0.8 and r1["recall"] == 0.6 and r1["recall"] < r0["recall"],
          "genA soft-seen recall drops 0.80 → 0.60 when the lead is redirected to WRONG.sol (n=5, a real number)")
    check(r1["n"] == 5 and r1["insufficient_sample"] is False,
          "n=5 is stable (the denominator = expectations, not hits); the slice is SHOWN, not suppressed")


def test_min_n_gate():
    print("\n[min-N] threshold MIN_N=%d — n=4 SUPPRESSED <-> n=5 SHOWN; symmetry of 0/2 and 2/2" % DB.MIN_N)
    check(DB.MIN_N == 5, "MIN_N == 5 (retune point)")
    cases = fixture_cases()
    ss = rec_of(DB.score_corpus(cases, [fixture_blob(flip=False)], live=False), "soft-seen")
    # THRESHOLD discrimination (not always-suppress): n=5 shown <-> n=4 suppressed
    g5 = ss["by_generator"]["genFive"]
    check(g5["recall"] == 1.0 and g5["insufficient_sample"] is False,
          "n=5 SHOWN: genFive recall=1.0 (threshold inclusive, insufficient_sample=False)")
    g4 = ss["by_generator"]["genFour"]
    check(g4["recall"] is None and g4["insufficient_sample"] is True,
          "n=4 SUPPRESSED: genFour recall=null, insufficient_sample=True")
    # SYMMETRY: 2/2 (high) and 0/2 (zero) at n<MIN_N → BOTH insufficient
    g_all = ss["by_generator"]["genAll"]
    g_zero = ss["by_generator"]["genZero"]
    check(g_all == {"hit": 2, "n": 2, "recall": None, "insufficient_sample": True},
          "SYMMETRY top: 2/2 at n<MIN_N → insufficient (NOT recall=1.0 \"the generator catches\")")
    check(g_zero == {"hit": 0, "n": 2, "recall": None, "insufficient_sample": True},
          "SYMMETRY bottom: 0/2 at n<MIN_N → insufficient (NOT recall=0.0 \"the generator is silent\")")


def test_split_mix_guard():
    print("\n[split-mix] corpus-integrity guard — a case in >1 split → fail-loud (crash, not silent averaging)")
    dup = [
        {"name": "DUP", "split": "dev", "cat": "C", "bug_location": "src/x.sol:1",
         "snapshot_ref": "manifest-only", "expected_generators": ["g"]},
        {"name": "DUP", "split": "soft-seen", "cat": "C", "bug_location": "src/x.sol:1",
         "snapshot_ref": "manifest-only", "expected_generators": ["g"]},
    ]
    raised = False
    try:
        DB.score_corpus(dup, [], live=False)
    except DB.CorpusSplitMixError:
        raised = True
    check(raised, "case DUP in dev AND soft-seen → CorpusSplitMixError (fail-loud, not silently averaged)")
    # control: a clean corpus (unique name x split) does NOT trip the guard (no false trigger)
    clean = [{"name": "U", "split": "dev", "cat": "C", "bug_location": "src/x.sol:1",
              "snapshot_ref": "manifest-only", "expected_generators": ["g"]}]
    ok = True
    try:
        DB.score_corpus(clean, [], live=False)
    except DB.CorpusSplitMixError:
        ok = False
    check(ok, "a clean corpus does NOT trip the guard (the guard does not falsely trigger)")


def test_heldout_primary_labels():
    print("\n[held-out] stdout: held-out FIRST (PRIMARY clean); soft-seen contaminated; dev ceiling")
    cases = fixture_cases()
    txt = DB.render(DB.score_corpus(cases, [fixture_blob(flip=False)], live=False))
    i_held = txt.find("split=held-out")
    i_dev = txt.find("split=dev")
    i_soft = txt.find("split=soft-seen")
    check(0 <= i_held < i_dev < i_soft,
          "stdout order: held-out < dev < soft-seen (held-out = the primary honest number)")
    check("PRIMARY" in txt, "held-out is labeled PRIMARY (clean)")
    check("contaminated" in txt, "soft-seen is labeled contaminated (sanity-floor)")
    check("ceiling" in txt, "dev is labeled ceiling")


def test_collision_scope():
    print("\n[collision] BLOB-SCOPE — a phantom hit via a basename collision does NOT inflate (Important-fix)")
    # protoA/protoB share the basename Vault.sol. The blob covers ONLY protoA. The lead genA@src/Vault.sol must NOT
    # fire protoB (contracts/Vault.sol). n=1 <MIN_N → recall suppressed, but n proves the scope.
    cases = [
        {"name": "protoA", "split": "dev", "cat": "CatV", "bug_location": "src/Vault.sol:10",
         "snapshot_ref": "manifest-only", "expected_generators": ["genA"]},
        {"name": "protoB", "split": "dev", "cat": "CatV", "bug_location": "contracts/Vault.sol:20",
         "snapshot_ref": "manifest-only", "expected_generators": ["genA"]},
    ]
    blob = {"target": "protoA", "covers": ["protoA"],
            "leads": [{"generator": "genA", "file_line": "src/Vault.sol:11"}]}
    dev = rec_of(DB.score_corpus(cases, [blob], live=False), "dev")
    # BEFORE the fix (global firing): genA would have hit protoB → n=2. The scope holds n=1 (recall suppressed by min-N).
    check(dev["by_generator"]["genA"] == {"hit": 1, "n": 1, "recall": None, "insufficient_sample": True},
          "genA n=1 (protoB does NOT fire phantomly; not n=2), recall suppressed by min-N")
    check(dev["n_scored"] == 1 and dev["unscored_n"] == 1,
          "protoB unscored (a lead from a foreign blob does NOT score it via a collision)")


def test_live_branch():
    print("\n[live] live-adapter branch (SECONDARY) — not vaporware + Minor#1 (co-expected without an adapter)")
    ref = "local:superform/v2-core-public-cantina"
    sp = DB._snapshot_path(ref)
    if not (sp and os.path.exists(sp)):
        print("  [SKIP] snapshot missing — not checking the live branch on this machine")
        return
    bugfile = "src/core/hooks/loan/morpho/MorphoRepayHook.sol"
    DB.register_live_adapter("genLive", lambda path: {bugfile})
    try:
        case = [{"name": "LIVE1", "split": "dev", "cat": "CatL", "bug_location": bugfile,
                 "snapshot_ref": ref, "expected_generators": ["genLive", "genNoAdapter"]}]
        recs = DB.score_corpus(case, [], live=True)  # NO leads — scored ONLY via live
        dev = rec_of(recs, "dev")
        gl = dev["by_generator"].get("genLive", {})
        check(dev["n_scored"] == 1 and gl.get("hit") == 1 and gl.get("insufficient_sample") is True,
              "live adapter: the case is scored+fired via live (hit=1; n=1 <MIN_N → recall suppressed)")
        check("genNoAdapter" not in dev["by_generator"],
              "Minor#1: a co-expected generator without an adapter is excluded from gen_n (non-evaluable, NOT a fake-miss)")
    finally:
        DB.LIVE_ADAPTERS.pop("genLive", None)


def main():
    print("=== disclosed_benchmark_selftest ===")
    test_primary()
    test_struct_fields()
    test_discrimination()
    test_min_n_gate()
    test_split_mix_guard()
    test_heldout_primary_labels()
    test_collision_scope()
    test_live_branch()
    total = _PASS + _FAIL
    print("\n%d/%d PASS" % (_PASS, total))
    if _FAIL:
        print("FAILED: %d" % _FAIL)
        sys.exit(1)
    print("OK — the scorer counts correctly, DISCRIMINATES (lead↓→recall↓) AND the min-N threshold cuts "
          "(n=4 suppressed <-> n=5 shown, symmetric).")
    sys.exit(0)


if __name__ == "__main__":
    main()
