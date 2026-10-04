#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmark_miss_analysis_selftest.py — proof of FIRING + discrimination (FDE Plan 8, Task 4).

Run: py -3 -X utf8 benchmark_miss_analysis_selftest.py
Covers (brief §4): (a) miss→structural artifact with fields; (b) >=3 of one class→RECURRING,
2→NOT recurring; (c) a miss on an insufficient_sample slice does NOT produce a blind_spot (min-N symmetry);
(d) positive-generalization discrimination: accept / overfit-reject / regression-reject / hardcode-
reject / insufficient-heldout; (e) intake idempotency (one miss twice → one entry).
Non-zero exit on any fail."""
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
import benchmark_miss_analysis as B  # noqa: E402

FAILS = []
N = 0


def check(cond, label):
    global N
    N += 1
    if cond:
        print("  PASS  %s" % label)
    else:
        print("  FAIL  %s" % label)
        FAILS.append(label)


# ── fixtures ────────────────────────────────────────────────────────────────────────────
def make_misses():
    """3x Cat 1 Math (quantity_edge, reliable) → RECURRING; 2x Cat 8 Vault (vault_gen, reliable) →
    NOT recurring; 1x Cat 4 Access (comment_miner) — lands on an insufficient slice → suppressed."""
    return [
        {"case": "m-math-01", "expected_generators": ["quantity_edge", "negative_space"],
         "cat": "Cat 1 Math", "split": "dev", "bug_location": "src/Vault.sol:120"},
        {"case": "m-math-02", "expected_generators": ["quantity_edge"],
         "cat": "Cat 1 Math", "split": "dev", "bug_location": "src/Pool.sol:88"},
        {"case": "m-math-03", "expected_generators": ["quantity_edge"],
         "cat": "Cat 1 Math", "split": "dev", "bug_location": "src/Router.sol:200"},
        {"case": "m-vault-01", "expected_generators": ["vault_gen"],
         "cat": "Cat 8 Vault", "split": "dev", "bug_location": "src/Share.sol:44"},
        {"case": "m-vault-02", "expected_generators": ["vault_gen"],
         "cat": "Cat 8 Vault", "split": "dev", "bug_location": "src/Liq.sol:77"},
        {"case": "m-tiny-01", "expected_generators": ["comment_miner"],
         "cat": "Cat 4 Access", "split": "dev", "bug_location": "src/Admin.sol:12"},
    ]


def make_records():
    """Fake scorer score_corpus() output: quantity_edge/vault_gen are reliable (n>=5), comment_miner on
    an n<5 slice → insufficient_sample=True (min-N suppression)."""
    return [
        {"split": "dev", "by_generator": {
            "quantity_edge": {"hit": 0, "n": 8, "recall": 0.0, "insufficient_sample": False},
            "vault_gen": {"hit": 0, "n": 6, "recall": 0.0, "insufficient_sample": False},
            "comment_miner": {"hit": 0, "n": 2, "recall": None, "insufficient_sample": True},
        }},
        {"split": "held-out", "by_generator": {}},
        {"split": "soft-seen", "by_generator": {}},
    ]


# ── (a) structural artifact with fields ───────────────────────────────────────────────────
def test_artifact_fields():
    print("\n[a] miss → structural artifact with fields")
    misses = make_misses()
    B.stamp_insufficient(misses, make_records())
    res = B.analyze(misses)
    a = next(x for x in res["artifacts"] if x["case"] == "m-math-01")
    required = ["case", "expected_primary_generator", "all_expected", "cat", "split",
               "bug_location", "insufficient_sample", "recurring", "why_silent",
               "what_to_do", "miss_key"]
    check(all(k in a for k in required), "all required fields present: %s" % required)
    check(a["expected_primary_generator"] == "quantity_edge", "primary generator = first expected")
    check(a["all_expected"] == ["quantity_edge", "negative_space"], "all_expected preserved")
    check(bool(a["why_silent"]) and bool(a["what_to_do"]), "why-silent + what-to-do are non-empty")
    check("quantity_edge" in a["what_to_do"], "what-to-do names the generator to build out")


# ── (b) recurring >=3, NOT on 2 ─────────────────────────────────────────────────────────────
def test_recurring():
    print("\n[b] >=3 of one class → RECURRING; 2 → NOT recurring")
    misses = make_misses()
    B.stamp_insufficient(misses, make_records())
    res = B.analyze(misses)
    check("Cat 1 Math" in res["recurring_classes"], "Cat 1 Math (3 misses) = RECURRING")
    check(res["recurring_classes"].get("Cat 1 Math") == 3, "recurring counter = 3")
    check("Cat 8 Vault" not in res["recurring_classes"], "Cat 8 Vault (2 misses) NOT recurring")
    math_art = next(x for x in res["artifacts"] if x["cat"] == "Cat 1 Math")
    vault_art = next(x for x in res["artifacts"] if x["cat"] == "Cat 8 Vault")
    check(math_art["recurring"] is True, "Math artifact marked recurring=True")
    check(vault_art["recurring"] is False, "Vault artifact recurring=False")
    check("RECURRING" in math_art["why_silent"], "recurring why-silent carries the escalation")


# ── (c) min-N symmetry: an insufficient slice does NOT produce a blind_spot ────────────────────────
def test_min_n_symmetry():
    print("\n[c] a miss on an insufficient_sample slice does NOT produce a blind_spot")
    misses = make_misses()
    B.stamp_insufficient(misses, make_records())
    tiny = next(m for m in misses if m["case"] == "m-tiny-01")
    check(tiny["insufficient_sample"] is True, "comment_miner miss marked insufficient (from records)")
    check(tiny.get("mn_source") == "scorer-records", "flag taken FROM the scorer output, not recomputed")
    res = B.analyze(misses)
    check(any(m["case"] == "m-tiny-01" for m in res["suppressed"]), "tiny miss → suppressed")
    check(all(a["case"] != "m-tiny-01" for a in res["artifacts"]),
          "tiny miss did NOT produce an artifact")
    check("Cat 4 Access" not in res["by_class"], "insufficient class NOT counted in the recurring Counter")
    # symmetry: reliable quantity_edge (0/8) — also 0 hit, but n>=5 → the signal is ALIVE (not suppressed)
    check(any(a["expected_primary_generator"] == "quantity_edge" for a in res["artifacts"]),
          "reliable 0/8 miss (n>=5) NOT suppressed — symmetry (n<5 suppressed, n>=5 alive)")


# ── (d) positive-generalization discrimination ─────────────────────────────────────────────
def test_positive_generalization():
    print("\n[d] positive-generalization: accept / overfit / regression / hardcode / insufficient")
    # ACCEPT: n>=5 held-out same-class, catches NEW (h1,h4), overall does not drop, structural patch
    hb = {"h1": False, "h2": False, "h3": True, "h4": False, "h5": False}
    ha_accept = {"h1": True, "h2": False, "h3": True, "h4": True, "h5": False}  # newly: h1,h4
    overall_b = {"o1": True, "o2": False, "o3": True}
    overall_a = {"o1": True, "o2": False, "o3": True}  # 0.667 → 0.667, does not drop
    struct_patch = "if node.assigns_advice and not node.copies_constraint:\n    flag(node)"
    r = B.accept_patch(hb, ha_accept, overall_b, overall_a, patch_source=struct_patch)
    check(r["verdict"] == B.ACCEPT, "ACCEPT: catches new held-out same-class, recall does not drop, structural patch")
    check(r["newly_caught"] == ["h1", "h4"], "ACCEPT lists the newly caught cases")

    # OVERFIT: n>=5, but NOT ONE NEW (h3 was already True) → recall-up not met
    ha_overfit = {"h1": False, "h2": False, "h3": True, "h4": False, "h5": False}
    r = B.accept_patch(hb, ha_overfit, overall_b, overall_a, patch_source=struct_patch)
    check(r["verdict"] == B.REJECT_OVERFIT,
          "REJECT_OVERFIT: 0 new held-out (dev-recall may have grown, held-out unchanged)")

    # REGRESSION: catches new (sufficient would pass), BUT overall recall dropped → necessary violated
    overall_a_drop = {"o1": True, "o2": False, "o3": False}  # 0.667 → 0.333
    r = B.accept_patch(hb, ha_accept, overall_b, overall_a_drop, patch_source=struct_patch)
    check(r["verdict"] == B.REJECT_REGRESSION,
          "REJECT_REGRESSION: held-out overall recall dropped (fixes one class, breaks another)")

    # HARDCODE: the same good numbers, BUT literal-location hardcode → the review rule rejects
    hc_patch = 'if bug_file == "Vault.sol":\n    flag()'
    r = B.accept_patch(hb, ha_accept, overall_b, overall_a, patch_source=hc_patch)
    check(r["verdict"] == B.REJECT_HARDCODE, "REJECT_HARDCODE: literal-location hardcode rejected BEFORE recall")

    # HARDCODE variants (endswith / membership) are also caught
    ok1, _ = B.review_patch_source('name.endswith("Router.sol")')
    ok2, _ = B.review_patch_source('if f in {"Pool.sol", "Vault.sol"}: flag()')
    ok3, _ = B.review_patch_source(struct_patch)
    check(ok1 is False and ok2 is False, "review catches .endswith and membership literal")
    check(ok3 is True, "review PASSES a structural patch (no literal names)")

    # INSUFFICIENT_HELDOUT: held-out same-class n<5 → cannot judge generalization (min-N symmetry)
    ha_tiny = {"h1": True, "h2": False}  # n=2 < MIN_N
    r = B.accept_patch(hb, ha_tiny, overall_b, overall_a, patch_source=struct_patch)
    check(r["verdict"] == B.INSUFFICIENT_HELDOUT,
          "INSUFFICIENT_HELDOUT: held-out same-class n<5 → not accept (min-N symmetry)")


# ── (e) intake idempotency ───────────────────────────────────────────────────────────────
def test_idempotency():
    print("\n[e] intake idempotency (one miss twice → one entry)")
    misses = make_misses()
    B.stamp_insufficient(misses, make_records())
    res = B.analyze(misses)
    fd, tmp = tempfile.mkstemp(suffix="_blind_spots.md", text=True)
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("# temp blind_spots\n\n## Active blind spots\n\n(seed)\n")
        n1 = B.append_intake(res["artifacts"], path=tmp)
        n2 = B.append_intake(res["artifacts"], path=tmp)  # repeat — 0 new
        with open(tmp, "r", encoding="utf-8") as f:
            text = f.read()
        keys = B.existing_keys(text)
        expected = len(res["artifacts"])  # only reliable (5), tiny suppressed is not written
        check(n1 == expected, "first append wrote all reliable artifacts (%d)" % expected)
        check(n2 == 0, "repeat append wrote 0 (idempotent)")
        check(len(keys) == expected, "exactly %d miss-key entries in the file (no duplicates)" % expected)
        check(text.count(B.INTAKE_HEADING) == 1, "section heading created exactly once")
        check("m-tiny-01" not in text, "suppressed miss did NOT land in blind_spots (min-N)")
        check("what to do" in text, "entry carries \"what to do\" (the file's rule)")
    finally:
        os.remove(tmp)


# ── (f) LOW-1: no-records path — conservative suppression (min-N symmetry) ───────────────
def test_no_records_symmetry():
    print("\n[f] LOW-1: no-records path — conservatively suppressed unless --assume-reliable")
    # default: records=None, assume_reliable=False → ALL misses suppressed (min-N unverifiable)
    misses = make_misses()  # 6 misses, WITHOUT a preset insufficient_sample
    B.stamp_insufficient(misses, None)
    check(all(m["insufficient_sample"] for m in misses), "no-records default: ALL misses suppressed")
    check(all(m["mn_source"] == "suppressed-no-records" for m in misses),
          "mn_source=suppressed-no-records (visible where the reliability comes from)")
    res = B.analyze(misses)
    check(res["artifacts"] == [], "0 artifacts — NO blind_spot on unverified min-N")
    check(res["recurring_classes"] == {}, "0 recurring — we do not build a signal without checking n<5")

    # opt-in --assume-reliable → reliable, BUT mn_source shouts UNVERIFIED
    misses2 = make_misses()
    B.stamp_insufficient(misses2, None, assume_reliable=True)
    check(all(not m["insufficient_sample"] for m in misses2), "assume_reliable: misses reliable")
    check(all(m["mn_source"] == "assumed-reliable-UNVERIFIED" for m in misses2),
          "mn_source=assumed-reliable-UNVERIFIED (min-N not confirmed)")
    res2 = B.analyze(misses2)
    check(len(res2["artifacts"]) == 6, "assume_reliable → 6 artifacts (symmetry opened by explicit opt-in)")

    # an external EXPLICIT preset is respected even without records (not overwritten by suppression)
    misses3 = [{"case": "ext-01", "expected_generators": ["g"], "cat": "Cat X", "split": "dev",
                "bug_location": "a.sol:1", "insufficient_sample": False}]
    B.stamp_insufficient(misses3, None)
    check(misses3[0]["mn_source"] == "preset" and misses3[0]["insufficient_sample"] is False,
          "external explicit preset respected (mn_source=preset)")


# ── (g) LOW-2: MIN_N imported from the scorer (drift-guard) ─────────────────────────────────
def test_min_n_import_sync():
    print("\n[g] LOW-2: MIN_N inherited from disclosed_benchmark_replay (drift-guard)")
    import importlib.util
    p = os.path.join(os.path.dirname(os.path.abspath(B.__file__)), "disclosed_benchmark_replay.py")
    spec = importlib.util.spec_from_file_location("disclosed_benchmark_replay_probe", p)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    check(B.MIN_N == scorer.MIN_N,
          "benchmark_miss_analysis.MIN_N (%d) == disclosed_benchmark_replay.MIN_N (%d)"
          % (B.MIN_N, scorer.MIN_N))
    check(B.RECURRING_THRESHOLD == 3, "RECURRING_THRESHOLD=3 literal (ours, failure_analysis pattern)")


def main():
    print("=== benchmark_miss_analysis selftest (FDE Plan 8, Task 4) ===")
    test_artifact_fields()
    test_recurring()
    test_min_n_symmetry()
    test_no_records_symmetry()
    test_min_n_import_sync()
    test_positive_generalization()
    test_idempotency()
    print("\n=== %d/%d PASS ===" % (N - len(FAILS), N))
    if FAILS:
        print("FAILURES:")
        for f in FAILS:
            print("  - %s" % f)
        sys.exit(1)
    print("all green")


if __name__ == "__main__":
    main()
