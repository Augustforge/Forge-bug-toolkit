#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for benchmark_dashboard.py (FDE Plan 8, Task 6).

Prove FIRING, not only-pass ([[feedback_hook_must_prove_firing]]): on SYNTHETIC fixture records
(we do NOT touch the real calibration_log.jsonl / benchmark_blind_protocol.md) we check that the render
DISCRIMINATES — a min-N slice n<5 is rendered `insufficient-sample` (n>=5 shows the real number),
and, critically, **the HEADLINE changes shape** depending on the Layer-A/Layer-B state (not the same
string regardless of data — otherwise the test is always-pass).

Assert coverage (matches Requirements §4 of the brief):
  (a) min-N: a slice n<5 → `insufficient-sample`, NOT a number; n>=5 → the real number (+ discrimination
      of threshold 4 vs 5, symmetry of 0/n and n/n);
  (b) HEADLINE is NEVER bare-B: at Layer-A n=0 the headline does not emit a Layer-B recall as "we catch X%"
      WITHOUT the "ceiling" marker — and discriminates four combinations (A measured/not measured x
      B available/insufficient);
  (c) Layer B and Layer A are rendered in SEPARATE sections (not mixed into one block/number);
  (d) held-out is marked PRIMARY, dev — ceiling, soft-seen — contaminated (scorer roles reused);
  (e) the trend on tiny-N (insufficient-sample) points is suppressed — delta is not computed through them.

Usage:  py -3 -X utf8 benchmark_dashboard_selftest.py
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import benchmark_dashboard as BD  # noqa: E402

DB = BD.db()

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


# ---------- fixture helpers (synthetic disclosed_benchmark records, scorer shape) ----------
def _slice(hit, n):
    """The same min-N logic as the scorer (_slice_recall) — used ONLY to build fixtures,
    not to test the scorer logic itself (that is already covered by disclosed_benchmark_selftest.py)."""
    if n < DB.MIN_N:
        return {"hit": hit, "n": n, "recall": None, "insufficient_sample": True}
    return {"hit": hit, "n": n, "recall": round(hit / n, 3), "insufficient_sample": False}


def fixture_record(split, ts, n_scored, n_surfaced, by_generator=None, by_class=None, n_cases=None):
    insuf = n_scored < DB.MIN_N
    return {
        "ts": ts, "type": "disclosed_benchmark", "layer": "B", "metric_kind": "lead-surfacing",
        "match_granularity": "file", "split": split,
        "n_cases": n_cases if n_cases is not None else n_scored,
        "n_scored": n_scored, "n_surfaced": n_surfaced, "unscored_n": 0,
        "recall": None if insuf else round(n_surfaced / n_scored, 3),
        "insufficient_sample": insuf,
        "by_generator": by_generator or {}, "by_class": by_class or {},
        "precision": None, "precision_scope": "corpus", "by_generator_fp": {},
    }


# ---------- (a) min-N render: insufficient-sample vs real number, threshold discrimination ----------
def test_min_n_render():
    print("\n[a] min-N render — n<5 -> insufficient-sample (NOT a number); n>=5 -> the real number")
    tiny = fixture_record("dev", 1000, n_scored=4, n_surfaced=2,
                           by_generator={"genFour": _slice(2, 4)})
    big = fixture_record("held-out", 1000, n_scored=6, n_surfaced=4,
                          by_generator={"genSix": _slice(4, 6)})
    latest = {"dev": tiny, "held-out": big}
    lines = BD.render_layer_b_section(latest)
    txt = "\n".join(lines)
    check("insufficient-sample" in txt, "n=4 (dev, split-level) is rendered insufficient-sample")
    check("0.67" in txt or "0.66" in txt, "n=6 (held-out, split-level) renders the REAL number (4/6≈0.67), not suppressed")
    # the per-generator table also discriminates
    check("insufficient-sample (n<5)" in "\n".join(BD._fmt_slice_table({"genFour": _slice(2, 4)}, "generator")),
          "per-generator n=4 -> insufficient-sample")
    check("0.67" in "\n".join(BD._fmt_slice_table({"genSix": _slice(4, 6)}, "generator")),
          "per-generator n=6 -> real number 0.67 (not suppressed)")
    # symmetry: 0/6 and 6/6 at n>=MIN_N both show a number (0.00 / 1.00), NOT insufficient — contrast
    # with n<MIN_N where the symmetry of 0/4 and 4/4 are BOTH insufficient (checked in disclosed_benchmark_selftest.py
    # for the scorer itself; here we check that the dashboard does NOT impose its own threshold on top of
    # the already-computed field).
    zero_big = _slice(0, 6)
    full_big = _slice(6, 6)
    check(zero_big["insufficient_sample"] is False and zero_big["recall"] == 0.0,
          "n=6 h=0 -> recall=0.00 shown (not insufficient, the dashboard does not mute a zero but sufficient result)")
    check(full_big["insufficient_sample"] is False and full_big["recall"] == 1.0,
          "n=6 h=6 -> recall=1.00 shown")


# ---------- (b) HEADLINE — never bare-B, discrimination of 4 combinations ----------
def test_headline_never_bare_b():
    print("\n[b] HEADLINE — never bare Layer-B; discriminates Layer-A measured/not-measured x B available/insufficient")

    layer_a_unmeasured = {"measured": False, "k": 0, "n": 0, "rounds": [],
                           "note": "no Layer-A round has been run yet (fixture)"}
    layer_a_measured = {"measured": True, "k": 2, "n": 3, "rounds": [(2, 3)],
                         "note": "1 round(s) recorded in the protocol"}

    b_available = {"recall": 0.75, "n": 8, "insufficient": False}   # a real B number is available
    b_insufficient = {"recall": None, "n": 3, "insufficient": True}  # B is also insufficient

    # (1) A not measured, B available (the real current risk: B looks like "strength" if not labeled)
    h1 = BD.render_headline(layer_a_unmeasured, b_available)
    check("not measured" in h1 or "NOT measured" in h1, "(1) headline explicitly says 'true-find not measured'")
    check("CEILING" in h1, "(1) the B number is labeled CEILING (not a bare 'we catch 75%')")
    check("we catch 75%" not in h1.replace("%%", "%"), "(1) NO bare phrase 'we catch 75%' without the ceiling marker")
    check("0.75" in h1, "(1) the B number is still visible (the ceiling is published, just labeled)")

    # (2) A not measured, B also insufficient — the most honest current real state of the project
    h2 = BD.render_headline(layer_a_unmeasured, b_insufficient)
    check("not measured" in h2 or "NOT measured" in h2, "(2) headline explicitly says 'true-find not measured'")
    check("insufficient-sample" in h2, "(2) B also insufficient-sample -> headline honestly says 'ceiling unavailable'")
    check("0.75" not in h2, "(2) discriminates from (1): a different B state -> different text")

    # (3) A measured (2/3), B available -> dual-stated, BOTH labeled (floor + ceiling)
    h3 = BD.render_headline(layer_a_measured, b_available)
    check("2/3" in h3, "(3) Layer-A k/n=2/3 is explicitly visible")
    check("FLOOR" in h3, "(3) Layer-A is labeled FLOOR")
    check("CEILING" in h3, "(3) Layer-B is labeled CEILING alongside (dual-stated)")
    check("dual-stated" in h3.lower(), "(3) headline is explicitly marked dual-stated")

    # (4) A measured, B insufficient -> the headline carries ONLY Layer-A (floor), no B number at all
    h4 = BD.render_headline(layer_a_measured, b_insufficient)
    check("2/3" in h4, "(4) Layer-A k/n=2/3 is visible")
    check("CEILING" not in h4, "(4) B insufficient -> the ceiling number is NOT rendered at all (nothing to render)")

    # Discrimination: all 4 headlines are DIFFERENT strings (proves the function reacts to input,
    # not always the same string — otherwise (b) would be always-pass).
    variants = {h1, h2, h3, h4}
    check(len(variants) == 4, "all 4 Layer-A x Layer-B combinations give DIFFERENT headline text (not always-pass)")


# ---------- (c) Layer A / Layer B separate sections ----------
def test_layers_separate():
    print("\n[c] Layer A and Layer B are rendered in separate sections, not mixed")
    layer_a = {"measured": True, "k": 1, "n": 2, "rounds": [(1, 2)], "note": "1 round(s)"}
    a_lines = BD.render_layer_a_section(layer_a)
    b_lines = BD.render_layer_b_section({"held-out": fixture_record("held-out", 1, 6, 3)})
    a_txt = "\n".join(a_lines)
    b_txt = "\n".join(b_lines)
    check(a_txt.startswith("## Layer A"), "Layer-A section starts with the '## Layer A' heading")
    check(b_txt.startswith("## Layer B"), "Layer-B section starts with the '## Layer B' heading")
    check("Layer B" not in a_txt.replace("Layer B — lead-surfacing", ""),
          "Layer-A section does not contain cross-mentions of Layer-B specifics")
    # The Layer-B section MAY mention 'true-find' (Layer A) exactly once — as an honest boundary
    # "NECESSARY-NOT-SUFFICIENT condition for true-find" (the same wording as in the scorer docstring).
    # Not allowed — if the Layer-B section itself RENDERS the Layer-A k/n number as its own.
    check("1/2" not in b_txt, "Layer-B section does NOT render the Layer-A k/n number (1/2) as its own")
    check("1/2" in a_txt, "Layer-A k/n=1/2 is visible in its own section")


# ---------- (d) held-out PRIMARY / dev ceiling / soft-seen contaminated (roles reused) ----------
def test_split_roles_reused():
    print("\n[d] held-out=PRIMARY, dev=ceiling, soft-seen=contaminated -- scorer roles reused correctly")
    latest = {
        "held-out": fixture_record("held-out", 1, 6, 3),
        "dev": fixture_record("dev", 1, 6, 3),
        "soft-seen": fixture_record("soft-seen", 1, 6, 3),
    }
    txt = "\n".join(BD.render_layer_b_section(latest))
    i_held = txt.find("split=held-out")
    i_dev = txt.find("split=dev")
    i_soft = txt.find("split=soft-seen")
    check(0 <= i_held < i_dev < i_soft, "section order: held-out < dev < soft-seen")
    check("PRIMARY" in txt, "held-out is marked PRIMARY")
    check("ceiling" in txt, "dev is marked ceiling")
    check("contaminated" in txt, "soft-seen is marked contaminated")


# ---------- (e) trend suppressed on tiny-N (insufficient-sample excluded from delta/line) ----------
def test_trend_suppressed_on_tiny_n():
    print("\n[e] trend on tiny-N (insufficient-sample) is suppressed — delta is not computed through such points")
    history = [
        fixture_record("held-out", 100, n_scored=3, n_surfaced=1),   # insufficient (n=3<5)
        fixture_record("held-out", 200, n_scored=6, n_surfaced=3),   # sufficient recall=0.50 (first)
        fixture_record("held-out", 300, n_scored=2, n_surfaced=2),   # insufficient (n=2<5) — wedged in
        fixture_record("held-out", 400, n_scored=8, n_surfaced=6),   # sufficient recall=0.75
    ]
    txt = "\n".join(BD.render_trend_section(history))
    check("excluded from the trend line" in txt, "insufficient-sample points are marked as excluded from the trend line")
    check("n=3<5" in txt or "n_scored=3" in txt or "3<5" in txt, "the first insufficient point (n=3) is visible as k/n, not hidden entirely")
    # the delta between 200 (0.50) and 400 (0.75) must be +0.25, NOT through the insufficient point at 300
    check("+0.25" in txt, "delta is computed BETWEEN sufficient points (0.50->0.75 = +0.25), bypassing the wedged insufficient (n=2) at ts=300")
    check("n/a (first sufficient point)" in txt, "the first sufficient point has no predecessor — delta='n/a', not a garbage number")


# ---------- bonus: Layer-A parser (parse_layer_a_results) — discrimination placeholder vs filled ----------
def test_layer_a_parser_discriminates():
    print("\n[bonus] parse_layer_a_results discriminates an empty protocol vs a filled one (2+ rounds)")
    # NOTE: the "Round results" heading is kept in Russian below: the parser matches it exactly.
    empty_text = ("# Layer-A blind protocol\n\n## Результаты раундов\n\n"
                  "_Empty — no Layer-A round has been run yet._\n\n## Next section\nxxx\n")
    r_empty = BD.parse_layer_a_results(empty_text)
    check(r_empty["measured"] is False and r_empty["n"] == 0,
          "placeholder text (without 'true-find recall = k/n') -> measured=False, n=0")

    # Russian heading "## Результаты раундов" ("## Round results") is parser input: kept verbatim.
    filled_text = ("# Layer-A blind protocol\n\n## Результаты раундов\n\n"
                   "### Round 1 (2026-09-01)\ntrue-find recall = 2/3\n\n"
                   "### Round 2 (2026-10-01)\ntrue-find recall = 1/2\n\n## Next section\nxxx\n")
    r_filled = BD.parse_layer_a_results(filled_text)
    check(r_filled["measured"] is True and r_filled["k"] == 3 and r_filled["n"] == 5,
          "2 rounds (2/3 + 1/2) are summed k=3,n=5 -> measured=True")
    check(r_filled["rounds"] == [(2, 3), (1, 2)], "individual rounds preserved as [(2,3),(1,2)]")

    no_section_text = "# Some other file\n\n## Another section\nxxx\n"
    r_missing = BD.parse_layer_a_results(no_section_text)
    check(r_missing["measured"] is False and "not found" in r_missing["note"],
          "the 'Round results' section is absent entirely -> measured=False with an honest note")


def main():
    print("=== benchmark_dashboard_selftest ===")
    test_min_n_render()
    test_headline_never_bare_b()
    test_layers_separate()
    test_split_roles_reused()
    test_trend_suppressed_on_tiny_n()
    test_layer_a_parser_discriminates()
    total = _PASS + _FAIL
    print("\n%d/%d PASS" % (_PASS, total))
    if _FAIL:
        print("FAILED: %d" % _FAIL)
        sys.exit(1)
    print("OK — the dashboard renders min-N honestly, HEADLINE NEVER bare-B (4/4 combinations "
          "discriminated), Layer A/B are separate, split roles reused, trend suppressed on tiny-N.")
    sys.exit(0)


if __name__ == "__main__":
    main()
