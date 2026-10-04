#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmark_miss_analysis.py — closed-loop miss→blind_spot intake + positive-generalization
patch-acceptance (FDE Plan 8, Task 4, §65).

WHAT THIS IS (one paragraph): Task 2/3 (`disclosed_benchmark_replay.py`) measures per-generator recall
on the disclosed corpus. Here the LOOP IS CLOSED: a miss (an expected generator that was expected &
scored, but NOT firing at bug_location) → **structural artifact** "who should have fired + why it was
silent + what to build out" → `blind_spots.md` (benchmark-miss intake) + recurring-detect (>=3 of the
same class). Plus — a VALIDATOR for detector patch acceptance (positive-generalization, R6): NOT
auto-patch, but a protocol "accept <=> the patch catches NEW held-out cases of the same class".

⚠ HONESTY BOUNDARIES (inherited from the Task 3 scorer):
  - **min-N SYMMETRY (MIN_N=5).** A miss on an `insufficient_sample` slice (n<MIN_N) does NOT produce
    a blind_spot and is NOT counted in recurring. R7 symmetry: a silent generator on an n<5 slice is
    not a signal (exactly like "0/1 is not silent, 1/1 is not catching"). We read the flag FROM the
    scorer output (`by_generator[g].insufficient_sample`), we do NOT recompute min-N ourselves —
    `stamp_insufficient()` (the single source of truth for min-N is the scorer).
  - **fail-open**: a miss-analysis failure does NOT break the scorer/regression — we CONSUME the
    scorer output (records + per-case miss list), we do not mutate the scorer/corpus/manifest.
  - **NOT auto-patch (R6).** We build an acceptance VALIDATOR (`accept_patch`) + a review checklist
    (literal-hardcode is forbidden). A detector patch = a human/agent decision; overfit/regression
    are dangerous → acceptance requires generalization on fresh-intake held-out, not "recall did not
    drop".

Usage:
  py -3 -X utf8 benchmark_miss_analysis.py analyze <misses.json> [--records <records.json>] \
        [--write] [--blind-spots <path>]
  py -3 -X utf8 benchmark_miss_analysis.py demo      # synthetic fixture run (artifact shape)

misses.json format (per-case miss record — a "passed list" OR a per-case dump from a leads run):
  [{"case": "<name>", "expected_generators": ["<g1>", ...], "cat": "<class>", "split": "dev",
    "bug_location": "src/X.sol:120"}, ...]
records.json (optional) — output of the scorer score_corpus() (list[per-split record]); from it we take
  insufficient_sample of each (split, generator) slice. Without --records misses are treated as RELIABLE
  (the flag is already set in misses OR absent → treated as reliable, but this is recorded in the report).
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLIND_SPOTS = os.path.join(ROOT, "sessions", "_methodology", "blind_spots.md")

# ── thresholds ──
# RECURRING_THRESHOLD — OUR OWN threshold (not the scorer's): the same Counter/>=3 pattern as
# failure_analysis.cmd_recurring. A literal with an honest comment — nothing to sync (one threshold family).
RECURRING_THRESHOLD = 3


def _import_scorer_min_n():
    """MIN_N — source of truth = the scorer (disclosed_benchmark_replay.MIN_N, Task 3). IMPORT, NOT a
    literal copy (drift-guard: a scorer retune → auto-sync, not a silent desync — the bug class that
    bit Plan 7). Direct import (same-dir), fallback — live-import by path (like rr() in the scorer)."""
    try:
        from disclosed_benchmark_replay import MIN_N as _mn  # same-dir at run/selftest
        return _mn
    except Exception:
        import importlib.util
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "disclosed_benchmark_replay.py")
        spec = importlib.util.spec_from_file_location("disclosed_benchmark_replay", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.MIN_N


MIN_N = _import_scorer_min_n()  # inherited from the scorer (Task 3) — min-N symmetry, not a literal

# ── benchmark-miss intake anchors in blind_spots.md (match the section added in Task 4) ──
INTAKE_HEADING = "## Benchmark-Miss Intake (Plan 8, §65)"
INTAKE_KEY_RE = re.compile(r"<!--\s*miss-key:\s*(.+?)\s*-->")


# ==========================================================================================
# 1. MISS → structural artifact
# ==========================================================================================
def miss_key(m):
    """Stable miss key for intake idempotency: case::primary-generator."""
    return "%s::%s" % (m.get("case", "?"), _primary(m))


def _primary(m):
    gens = [g for g in (m.get("expected_generators") or []) if g and g != "none"]
    return gens[0] if gens else "?"


def _slice_insufficient(records, split, gen):
    """Reads insufficient_sample of the (split, gen) slice FROM the scorer output (min-N — the source
    of truth is the scorer, not a recomputation). A missing slice (gen was not evaluated / n=0) → True
    (no reliable signal, conservatively suppress — min-N symmetry: no data != "silent")."""
    if not records:
        return None  # records not supplied — cannot judge, leave the decision to the caller
    for r in records:
        if r.get("split") != split:
            continue
        bg = r.get("by_generator") or {}
        slc = bg.get(gen)
        if slc is None:
            return True   # generator is not in a reliable slice of this split → suppress
        return bool(slc.get("insufficient_sample", False))
    return True  # the split is not in records at all → suppress


def stamp_insufficient(misses, records, assume_reliable=False):
    """Stamps each miss with `insufficient_sample` FROM the scorer records (min-N symmetry).
    Mutates and returns the list (in-place). Each miss carries `mn_source` — WHERE the reliability
    comes from (surfaced in `_render_report`, honesty is visible).

    ⚠ min-N SYMMETRY on the no-records path (LOW-1 fix): the invariant "do not build a blind_spot/
    recurring on n<5" must NOT hold ONLY when records are supplied. Source priority for EACH miss:
      1. records supplied → flag FROM the scorer (`scorer-records`) — the source of truth for min-N.
      2. NO records, but the miss carries an EXPLICIT `insufficient_sample` preset (an external
         extractor already stamped it, mn_source not yet) → respect it (`preset`).
      3. NO records, `assume_reliable=True` → reliable, BUT a LOUD WARN: min-N NOT verified
         (`assumed-reliable-UNVERIFIED`).
      4. NO records, default → **CONSERVATIVELY SUPPRESS** (`suppressed-no-records`): min-N cannot be
         verified → we do not build a signal on the unverified (safer for honesty than a silent
         reliable). Symmetric to the records-present path, where a missing slice → suppress."""
    if not records and assume_reliable:
        print("WARN: --assume-reliable without records — min-N (n<%d) NOT verified; misses are treated "
              "as reliable WITHOUT slice confirmation (mn_source=assumed-reliable-UNVERIFIED)." % MIN_N,
              file=sys.stderr)
    for m in misses:
        split = m.get("split", "?")
        gen = _primary(m)
        val = _slice_insufficient(records, split, gen)
        if val is not None:                                   # (1) scorer — source of truth
            m["insufficient_sample"] = val
            m["mn_source"] = "scorer-records"
        elif "insufficient_sample" in m and "mn_source" not in m:  # (2) external explicit preset
            m["mn_source"] = "preset"
        elif assume_reliable:                                 # (3) explicit opt-in + WARN above
            m["insufficient_sample"] = False
            m["mn_source"] = "assumed-reliable-UNVERIFIED"
        else:                                                 # (4) conservative default: suppress
            m["insufficient_sample"] = True
            m["mn_source"] = "suppressed-no-records"
    return misses


def _why_silent(m, is_recurring):
    """Structural HYPOTHESIS for why the generator was silent (NOT an auto-fix — a seed for the agent).
    Abduction from the available signals (how many generators were expected, class, file)."""
    g = _primary(m)
    cat = m.get("cat", "?")
    loc = m.get("bug_location", "?")
    n_exp = len([x for x in (m.get("expected_generators") or []) if x and x != "none"])
    parts = [
        "generator %r was expected on class %r, but did not surface at %r." % (g, cat, loc),
        "Structural hypotheses (not a fix): (a) the generator does not cover this SUB-class %r;" % cat,
        "(b) there is no runnable scanner for the file type/surface of this bug_location;",
        "(c) the T1-scout axes/partitions were not enough (the file did not land in the top-5 / not in a scout partition).",
    ]
    if n_exp == 1:
        parts.append("the ONLY expected generator — class coverage rests on it alone "
                     "(single-point coverage, higher priority to build out).")
    if is_recurring:
        parts.append("RECURRING class: the silence is SYSTEMIC (>=%d misses of the class) — not a one-off "
                     "under-dig, but a gap in the generator family." % RECURRING_THRESHOLD)
    return " ".join(parts)


def _what_to_do(m, is_recurring):
    """The 'what to do' field — mandatory (blind_spots.md rule: an entry without it = a diary)."""
    g = _primary(m)
    cat = m.get("cat", "?")
    if is_recurring:
        return ("PRIORITY (recurring): build out the generator family for class %r "
                "(>=%d misses) — not a point patch of %r, but an axis/scanner covering the whole sub-class. "
                "Acceptance of any patch — via accept_patch() (generalization on held-out of the same "
                "class, NOT recall-doesn't-drop)." % (cat, RECURRING_THRESHOLD, g))
    return ("build out generator %r for class %r OR add an axis/scanner covering the surface type "
            "of this bug_location. Patch acceptance — accept_patch() (generalization "
            "on unseen held-out of the same class)." % (g, cat))


def build_artifact(m, is_recurring):
    """Miss → structural artifact (§65 shape). insufficient_sample TRAVELS ALONGSIDE (min-N honesty)."""
    return {
        "case": m.get("case", "?"),
        "expected_primary_generator": _primary(m),
        "all_expected": [g for g in (m.get("expected_generators") or []) if g and g != "none"],
        "cat": m.get("cat", "?"),
        "split": m.get("split", "?"),
        "bug_location": m.get("bug_location", "?"),
        "insufficient_sample": bool(m.get("insufficient_sample", False)),
        "recurring": is_recurring,
        "why_silent": _why_silent(m, is_recurring),
        "what_to_do": _what_to_do(m, is_recurring),
        "miss_key": miss_key(m),
    }


def analyze(misses):
    """Misses → {reliable, suppressed, recurring_classes, recurring_generators, artifacts}.

    ⚠ min-N SYMMETRY: misses on an `insufficient_sample` slice go to `suppressed` — they do NOT produce
    an artifact/blind_spot and are NOT counted in recurring. Only RELIABLE misses participate.
    recurring-detect (reuse failure_analysis Counter/>=3): Counter by class of reliable misses."""
    reliable = [m for m in misses if not m.get("insufficient_sample", False)]
    suppressed = [m for m in misses if m.get("insufficient_sample", False)]

    # recurring — ONLY over reliable (min-N symmetry): Counter/>=3 (the same pattern as
    # failure_analysis.cmd_recurring: by_class + by_root → here by_class(cat) + by_generator).
    by_class = Counter(m.get("cat", "?") for m in reliable)
    by_generator = Counter(_primary(m) for m in reliable)
    recurring_classes = {k: n for k, n in by_class.items() if n >= RECURRING_THRESHOLD}

    artifacts = []
    for m in reliable:
        is_rec = m.get("cat", "?") in recurring_classes
        artifacts.append(build_artifact(m, is_rec))

    return {
        "reliable": reliable,
        "suppressed": suppressed,
        "by_class": dict(by_class),
        "by_generator": dict(by_generator),
        "recurring_classes": recurring_classes,
        "artifacts": artifacts,
    }


# ==========================================================================================
# 2. blind_spots.md benchmark-miss INTAKE (idempotent append)
# ==========================================================================================
def existing_keys(text):
    """Set of miss-keys already present in blind_spots.md (by the HTML-comment marker)."""
    return set(INTAKE_KEY_RE.findall(text or ""))


def _render_entry(a):
    """One intake entry. The `<!-- miss-key: ... -->` marker is the idempotency anchor."""
    rec_tag = "yes (%s, >=%d of the same class)" % (a["cat"], RECURRING_THRESHOLD) if a["recurring"] else "no"
    lines = [
        "### BM — %s miss: %s (expected %s)" % (a["cat"], a["case"], a["expected_primary_generator"]),
        "<!-- miss-key: %s -->" % a["miss_key"],
        "- **case**: %s" % a["case"],
        "- **split**: %s" % a["split"],
        "- **class (cat)**: %s" % a["cat"],
        "- **bug_location**: %s" % a["bug_location"],
        "- **expected primary generator**: %s" % a["expected_primary_generator"],
        "- **all expected**: %s" % (", ".join(a["all_expected"]) or "—"),
        "- **why-silent (structural hypothesis)**: %s" % a["why_silent"],
        "- **what to do**: %s" % a["what_to_do"],
        "- **recurring**: %s" % rec_tag,
        "- **stamped**: %s" % time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "",
    ]
    return "\n".join(lines)


def append_intake(artifacts, path=BLIND_SPOTS):
    """Idempotently appends reliable artifacts to the blind_spots.md benchmark-miss section.

    - One miss (miss_key) twice → one entry (dedup by `<!-- miss-key: -->`).
    - The section is created if absent (works on an untouched file and on a temp fixture).
    - Returns the number of entries ACTUALLY appended (already-present ones are skipped).
    - fail-open: a write error does not crash the caller (print WARN, return 0)."""
    try:
        text = ""
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        have = existing_keys(text)
        new = [a for a in artifacts if a["miss_key"] not in have]
        if not new:
            return 0

        chunks = []
        # create the section once (if there is no heading yet)
        if INTAKE_HEADING not in text:
            header = [
                "",
                "---",
                "",
                INTAKE_HEADING,
                "",
                "> Intake path #4 (benchmark-miss): a disclosed bug where the EXPECTED generator did not surface at",
                "> bug_location → a structural artifact goes here (akin to #3 blind run). Written by",
                "> `benchmark_miss_analysis.py` (append function, idempotent). ⚠ ONLY reliable",
                "> misses — the `insufficient_sample` slice (n<%d) is suppressed (min-N symmetry). Each" % MIN_N,
                "> entry carries \"what to do\"; recurring (>=%d of a class) = a priority blind_spot." % RECURRING_THRESHOLD,
                "",
            ]
            chunks.append("\n".join(header))
        for a in new:
            chunks.append(_render_entry(a))

        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(chunks) + ("\n" if not chunks[-1].endswith("\n") else ""))
        return len(new)
    except Exception as e:  # fail-open: intake is auxiliary, do not crash the loop
        print("WARN: benchmark-miss intake append failed:", e, file=sys.stderr)
        return 0


# ==========================================================================================
# 3. POSITIVE-GENERALIZATION patch-acceptance (R6 — NOT auto-patch, acceptance VALIDATOR)
# ==========================================================================================
ACCEPT = "ACCEPT"
REJECT_OVERFIT = "REJECT_OVERFIT"
REJECT_REGRESSION = "REJECT_REGRESSION"
REJECT_HARDCODE = "REJECT_HARDCODE"
INSUFFICIENT_HELDOUT = "INSUFFICIENT_HELDOUT"

# review rule: literal-location/name hardcode = overfit by construction → reject.
# We catch equality/membership/suffix against a LITERAL file/path name (a structural pattern is forbidden — NOT).
_HARDCODE_PATTERNS = [
    r"""==\s*['"][^'"]*\.(?:sol|py|js|ts|tsx|jsx|json|rs|go|vy|move|cairo)['"]""",   # x == "Vault.sol"
    r"""['"][^'"]*\.(?:sol|py|js|ts|rs|go|vy)['"]\s*==""",                            # "Vault.sol" == x
    r"""\bif\s+[^\n:]*\b(?:file|name|path|basename|filename|loc)\b[^\n:]*==\s*['"]""",  # if bug_file == "…"
    r"""\.endswith\(\s*['"][^'"]*\.(?:sol|py|js|ts|rs|go|vy)['"]""",                  # .endswith("Vault.sol")
    r"""\bin\s*[\(\{\[]\s*['"][^'"]*\.(?:sol|py|js|ts|rs|go|vy)['"]""",               # name in {"Vault.sol"}
]
_HARDCODE_RE = [re.compile(p) for p in _HARDCODE_PATTERNS]


def review_patch_source(patch_source):
    """Acceptance review checklist (prose rule, machine-checkable part): literal-location/name
    hardcode → structural reject. Returns (ok: bool, reason: str|None).

    ⚠ This is a NECESSARY filter, NOT sufficient: the absence of literal hardcode != "the pattern is
    structural" (a human reviewer still looks). But `if file=="X.sol"→flag` is caught mechanically and
    rejected BEFORE any recall numbers (otherwise an overfit patch would "pass" generalization on the
    case whose name is hardcoded)."""
    if not patch_source:
        return True, None
    for rx in _HARDCODE_RE:
        mo = rx.search(patch_source)
        if mo:
            return False, "literal-location/name hardcode detected: %r (overfit — only a structural " \
                          "pattern is allowed)" % mo.group(0)[:80]
    return True, None


def _recall(results):
    """Fraction fired in {case: bool}. Empty set → None (no data, neither 0 nor 1)."""
    if not results:
        return None
    return round(sum(1 for v in results.values() if v) / len(results), 3)


def accept_patch(heldout_sameclass_before, heldout_sameclass_after,
                 heldout_overall_before=None, heldout_overall_after=None,
                 patch_source=None):
    """VALIDATOR for detector patch acceptance (positive-generalization, R6). Does NOT generate a patch.

    accept <=> the patched generator catches NEW held-out cases OF THE SAME CLASS, NOT used when
    authoring the patch (recall-UP-on-unseen-same-class = SUFFICIENT, catches overfit), AND recall did
    NOT DROP on held-out overall (recall-doesn't-drop = NECESSARY, catches regression), AND the patch
    has no literal hardcode.

    Arguments (all — {case_name: fired_bool}):
      heldout_sameclass_before/after — held-out cases OF THE SAME class that did NOT take part in
        authoring the patch (fresh-intake, R4). Before/after the patch.
      heldout_overall_before/after   — held-out overall (all classes) — regression guard. Optional: if
        not supplied, regression is NOT checked (marked unchecked in the report).
      patch_source                   — patch source/diff for the review rule (optional).

    Order of checks (the first to fire = the verdict): hardcode → min-N held-out → regression → overfit →
    ACCEPT. min-N SYMMETRY: held-out same-class with n<MIN_N → INSUFFICIENT_HELDOUT (generalization
    cannot be confirmed on n<5 — the same threshold that suppresses a blind_spot).

    Returns dict {verdict, reason, newly_caught, heldout_recall_before/after,
    overall_recall_before/after}."""
    hb, ha = heldout_sameclass_before or {}, heldout_sameclass_after or {}

    # 1. review rule (literal-hardcode) — an absolute gate BEFORE any recall numbers
    ok, why = review_patch_source(patch_source)
    if not ok:
        return {"verdict": REJECT_HARDCODE, "reason": why, "newly_caught": [],
                "heldout_recall_before": _recall(hb), "heldout_recall_after": _recall(ha)}

    # 2. min-N symmetry on held-out same-class: n<MIN_N → generalization cannot be judged
    if len(ha) < MIN_N:
        return {"verdict": INSUFFICIENT_HELDOUT,
                "reason": "held-out same-class n=%d < MIN_N=%d — generalization cannot be confirmed "
                          "(min-N symmetry; held-out grows organically, Task 1 is empty)" % (len(ha), MIN_N),
                "newly_caught": [], "heldout_recall_before": _recall(hb),
                "heldout_recall_after": _recall(ha)}

    # 3. NECESSARY: recall-doesn't-drop on held-out overall (catches regression in OTHER classes)
    ob, oa = heldout_overall_before, heldout_overall_after
    reg_before, reg_after = _recall(ob), _recall(oa)
    if reg_before is not None and reg_after is not None and reg_after < reg_before:
        return {"verdict": REJECT_REGRESSION,
                "reason": "held-out overall recall dropped %.3f → %.3f (the patch fixes one class, breaks "
                          "another — the necessary condition recall-doesn't-drop is violated)" % (reg_before, reg_after),
                "newly_caught": [], "heldout_recall_before": _recall(hb),
                "heldout_recall_after": _recall(ha),
                "overall_recall_before": reg_before, "overall_recall_after": reg_after}

    # 4. SUFFICIENT: recall-UP-on-unseen-same-class — the patch catches AT LEAST ONE NEW held-out of the
    #    same class that it did not catch before the patch (catches overfit: dev-recall up, held-out unchanged → reject)
    newly = sorted(c for c, fired in ha.items() if fired and not hb.get(c, False))
    if not newly:
        return {"verdict": REJECT_OVERFIT,
                "reason": "0 NEW held-out same-class cases caught (recall-up not met): the patch may have "
                          "raised dev-recall, but does NOT generalize to unseen of the same class = overfit",
                "newly_caught": [], "heldout_recall_before": _recall(hb),
                "heldout_recall_after": _recall(ha),
                "overall_recall_before": reg_before, "overall_recall_after": reg_after}

    return {"verdict": ACCEPT,
            "reason": "generalizes: caught %d NEW held-out same-class %s; recall-doesn't-drop OK; "
                      "no literal hardcode" % (len(newly), newly),
            "newly_caught": newly, "heldout_recall_before": _recall(hb),
            "heldout_recall_after": _recall(ha),
            "overall_recall_before": reg_before, "overall_recall_after": reg_after}


# patch-acceptance review checklist — prose for agent/human (docstring + CLI print).
ACCEPTANCE_CHECKLIST = """\
Positive-generalization patch-acceptance checklist (R6 — detector patch acceptance, NOT auto-patch):
  [1] NOT literal-hardcode: `if file=="X.sol"→flag` / `name in {"X.sol"}` / `.endswith("X.sol")` =
      overfit by construction → REJECT (review_patch_source catches it mechanically; a human checks
      "the pattern is structural, not a list of names").
  [2] NECESSARY recall-doesn't-drop: on held-out overall (all classes) the patch's recall is NOT below
      pre-patch — otherwise the patch fixes one class, breaks another → REJECT_REGRESSION.
  [3] SUFFICIENT recall-up-on-unseen-same-class: the patch catches >=1 NEW held-out case OF THE SAME class,
      NOT used when authoring (fresh-intake, R4) → otherwise overfit → REJECT_OVERFIT.
  [4] min-N: held-out same-class n>=5 (MIN_N) — otherwise INSUFFICIENT_HELDOUT (cannot judge).
  Everything rests on fresh-intake held-out; the Task 1 held-out is empty for now → the mechanism is ready,
  it will start organically as held-out grows."""


# ==========================================================================================
# CLI
# ==========================================================================================
def _render_report(res):
    out = ["=== benchmark miss-analysis (Layer B closed-loop, Plan 8 Task 4) ==="]
    out.append("reliable misses: %d | suppressed (insufficient_sample, min-N): %d"
               % (len(res["reliable"]), len(res["suppressed"])))
    # reliability source (mn_source) — surfaces WHERE the min-N judgement comes from (LOW-1: visible that
    # no-records misses are suppressed/assumed, not silently reliable).
    mn = Counter(m.get("mn_source", "?") for m in (res["reliable"] + res["suppressed"]))
    if mn:
        out.append("reliability source (mn_source): %s"
                   % ", ".join("%s=%d" % (k, v) for k, v in sorted(mn.items())))
    if res["recurring_classes"]:
        out.append("⚠️ RECURRING (>=%d of the same class):" % RECURRING_THRESHOLD)
        for cat, n in sorted(res["recurring_classes"].items(), key=lambda kv: -kv[1]):
            out.append("   %s: %d" % (cat, n))
    else:
        out.append("recurring: none (<%d in any class)" % RECURRING_THRESHOLD)
    out.append("")
    out.append("by class: %s" % json.dumps(res["by_class"], ensure_ascii=False))
    out.append("by generator: %s" % json.dumps(res["by_generator"], ensure_ascii=False))
    out.append("")
    for a in res["artifacts"]:
        tag = " [RECURRING]" if a["recurring"] else ""
        out.append("── %s (%s)%s" % (a["case"], a["cat"], tag))
        out.append("   expected: %s | split=%s" % (a["expected_primary_generator"], a["split"]))
        out.append("   why-silent: %s" % a["why_silent"])
        out.append("   what to do: %s" % a["what_to_do"])
    if res["suppressed"]:
        out.append("")
        out.append("suppressed (min-N, NOT in blind_spot): %s"
                   % ", ".join("%s/%s" % (m.get("case"), _primary(m)) for m in res["suppressed"]))
    return "\n".join(out)


def cmd_analyze(args):
    with open(args.misses, "r", encoding="utf-8") as f:
        misses = json.load(f)
    records = None
    if args.records:
        with open(args.records, "r", encoding="utf-8") as f:
            records = json.load(f)
    stamp_insufficient(misses, records, assume_reliable=args.assume_reliable)
    res = analyze(misses)
    print(_render_report(res))
    if args.write:
        n = append_intake(res["artifacts"], path=args.blind_spots or BLIND_SPOTS)
        print("\n→ benchmark-miss intake: %d new record(s) → %s"
              % (n, os.path.relpath(args.blind_spots or BLIND_SPOTS, ROOT)))
    else:
        print("\n(--write not set: blind_spots.md untouched)")


def cmd_demo(args):
    """Synthetic fixture — the artifact shape without a real corpus (held-out is empty, Task 1)."""
    misses = [
        {"case": "demo-math-01", "expected_generators": ["quantity_edge"], "cat": "Cat 1 Math",
         "split": "dev", "bug_location": "src/Vault.sol:120", "insufficient_sample": False},
        {"case": "demo-math-02", "expected_generators": ["quantity_edge"], "cat": "Cat 1 Math",
         "split": "dev", "bug_location": "src/Pool.sol:88", "insufficient_sample": False},
        {"case": "demo-math-03", "expected_generators": ["quantity_edge"], "cat": "Cat 1 Math",
         "split": "dev", "bug_location": "src/Router.sol:200", "insufficient_sample": False},
        {"case": "demo-tiny-01", "expected_generators": ["comment_miner"], "cat": "Cat 4 Access",
         "split": "held-out", "bug_location": "src/Admin.sol:12", "insufficient_sample": True},
    ]
    stamp_insufficient(misses, None)  # presets are respected (mn_source=preset), no-records path
    res = analyze(misses)
    print(_render_report(res))
    print("\n" + ACCEPTANCE_CHECKLIST)
    print("\n(demo: blind_spots.md NOT touched; held-out is empty in Task 1 — positive-generalization "
          "starts organically)")


def main():
    ap = argparse.ArgumentParser(description="benchmark miss-analysis (FDE Plan 8, Task 4)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("analyze", help="miss list → structural artifacts + recurring + intake")
    p.add_argument("misses", help="misses.json (per-case miss records)")
    p.add_argument("--records", help="records.json (scorer output — min-N insufficient_sample)")
    p.add_argument("--assume-reliable", action="store_true",
                   help="WITHOUT records: treat misses as reliable (min-N NOT verified, loud WARN). "
                        "Default without this flag — conservatively suppress (LOW-1 symmetry).")
    p.add_argument("--write", action="store_true", help="append to blind_spots.md (idempotent)")
    p.add_argument("--blind-spots", help="path to blind_spots.md (default: sessions/_methodology)")
    p.set_defaults(func=cmd_analyze)

    d = sub.add_parser("demo", help="synthetic fixture run (artifact shape)")
    d.set_defaults(func=cmd_demo)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
