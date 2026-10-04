#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Disclosed benchmark replay — Layer-B generator-recall scorer (FDE Plan 8, Task 2).

WHAT THIS IS (one paragraph): Layer B = a scalable continuous metric. We run the mechanical
generators against the disclosed corpus (the manifest's `disclosed:` block, Task 1) and measure **whether
the EXPECTED generator surfaced in the bug's FILE** — per-generator and per-class recall + FP, the 3 split
groups SEPARATELY (soft-seen / dev / held-out). Ground-truth = `expected_generators[]` of each disclosed record.

⚠ HONESTY BOUNDARY (Layer B != Layer A):
  - The metric is "lead-surfacing recall" at the FILE level (`matches()` from regression_replay,
    file-token matching). NOT file:line, NOT confirmed-exploit, NOT true-find. This is a NECESSARY-NOT-
    SUFFICIENT condition: the generator pointed at the right file != the bug is proven. Every emit record
    carries `layer:"B"` · `metric_kind:"lead-surfacing"` · `match_granularity:"file"` — these fields must
    travel ALONGSIDE any recall number (downstream must not render a bare number without a disclaimer).
  - splits are computed SEPARATELY and NEVER averaged. held-out (n=0 at Task 1) is rendered as
    n_cases=0, recall=null — does not crash, does not flow into other splits.

⚠ TASK 3 — TWO honesty enforcement layers (anti-Goodhart stops being decorative):
  - min-N (MIN_N=5): ANY recall slice (per-generator / per-class / per-split) with n<MIN_N is rendered
    as `insufficient-sample` — the float recall is SUPPRESSED (recall:null + insufficient_sample:true),
    the raw fraction k/n with an explicit n STAYS visible (transparency). Symmetric: 0/1 is NOT "the generator
    is silent", 1/1 is NOT "the generator catches" — both insufficient at n<MIN_N (downstream Task 4/6 must not
    fire on n<MIN_N). A tiny-N slice (21 cases spread over many generators) WITHOUT this = false precision "2/3=67%".
  - held-out = the PRIMARY honest number (fresh-intake outside the 147): stdout prints held-out FIRST with
    the PRIMARY(clean) label, dev = ceiling, soft-seen = sanity-floor(contaminated). split-mix refusal
    (corpus-integrity guard): one case-name in >1 split → CorpusSplitMixError (fail-LOUD — we shout, we do not
    average silently); there is NO function aggregating recall OVER splits (one-directional intake
    is enforced structurally — a case cannot be in both dev and held-out).
  - The corpus is mostly manifest-only (no code on disk): such cases without leads.json coverage AND without a
    runnable scanner → `unscored` (reported SEPARATELY as `unscored_n`, NOT as a miss — otherwise the
    metric lies with an understated recall).

TWO SCORING BRANCHES:
  1. leads.json-fed (PRIMARY, the core): a scout run dumps leads.json; generator G "fired" on
     case C <=> there EXISTS a lead with `generator==G` whose `file_line` matches `C.bug_location`. A lead without
     `generator` contributes only to the overall case-level file-recall/precision, not to the per-generator slice.
  2. live-import (SECONDARY, best-effort): for `local:` cases with a runnable scanner — import the adapter
     and run it against the snapshot → did it flag the bug_location file. The `LIVE_ADAPTERS` registry (empty by
     default — no current scanner gives reproducible cases a simple "scan path → files"
     API; see _register_default_adapters). No adapter → `live-run:N/A`, NOT a miss.

Usage:
  py -3 -X utf8 disclosed_benchmark_replay.py score <leads.json> [<leads2.json> ...] [--live] [--no-write]
  py -3 -X utf8 disclosed_benchmark_replay.py demo      # run without leads (all unscored — record shape)

leads.json format (extends regression_replay: optional `generator` field on a lead + optional `covers`):
  {"target": "<name>",
   "covers": ["<case-name>", ...],                      # optional: which cases this run covers
   "leads": [{"file_line": "src/X.sol:120", "cat": "...", "generator": "<gen-id>",
              "prediction": "...", "falsifier": "...", "confidence": "med"}, ...]}
"""
import importlib.util
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RR = os.path.join(ROOT, "scripts", "_methodology", "regression_replay.py")
SESSIONS = os.path.join(ROOT, "sessions")
CALIB = os.path.join(SESSIONS, "_methodology", "calibration_log.jsonl")

# Canonical splits — ALWAYS emit all three (held-out must render n=0, even when empty).
CANON_SPLITS = ["soft-seen", "dev", "held-out"]

# Order and roles of splits in stdout (Task 3, R4): held-out FIRST as the primary honest number.
RENDER_ORDER = ["held-out", "dev", "soft-seen"]
SPLIT_ROLE = {
    "held-out": "PRIMARY (clean) — fresh-intake outside the 147, the honest primary recall number",
    "dev":      "ceiling — closed-loop tuning (our own hunts; the method has already seen the case)",
    "soft-seen": "sanity-floor (contaminated — the method was tuned on the CLASS, NOT clean anti-Goodhart)",
}

# ── min-N gate (Task 3, R7 — the core against false precision of tiny-N slices) ──
MIN_N = 5  # retune point: a slice with n<MIN_N → `insufficient-sample`, float recall suppressed (symmetric)

# Structural fields, MANDATORY in every emit record (R2 — the honesty core, the selftest ASSERTs).
# +insufficient_sample (Task 3): the split-level min-N flag travels alongside recall (downstream does not render
# a bare number at n<MIN_N).
STRUCT_FIELDS = ("layer", "metric_kind", "match_granularity", "n_cases", "split", "insufficient_sample")


# ⛔ SPLIT-ISOLATION INVARIANT (split-mix refusal, Task 3 R4): in this module there is NOT and MUST NOT be a
# single function aggregating/averaging recall OVER splits. Each split is scored and rendered
# SEPARATELY (see by_split below). held-out is NEVER merged with dev/soft-seen. Any future
# "overall recall" function = an anti-Goodhart violation (the crowd would see one averaged number instead of three
# roles: clean primary / ceiling / contaminated floor). The corpus-integrity guard (_assert_no_split_mix)
# catches the other flank of the same invariant: a case cannot physically live in >1 split.
class CorpusSplitMixError(Exception):
    """Corpus-integrity defect: one case-name appears in >1 split. Fail-LOUD (we do not silently average):
    one-directional intake is violated (a once-dev/soft-seen case NEVER migrates to held-out). This is NOT a
    runtime input, but a defect of OUR corpus artifact — hence raise is justified; the CLI catches and prints,
    without crashing other harnesses (Layer B is isolated from regression_replay Layer A)."""


def _assert_no_split_mix(cases):
    """Guard for split-mix / one-directional-intake: collects name→{splits}; if even one name is in >1
    split → CorpusSplitMixError. A shout, not silent averaging (corpus-integrity, fail-loud)."""
    seen = {}
    for c in cases:
        seen.setdefault(c.get("name"), set()).add(c.get("split", "?"))
    mixed = {nm: sorted(sps) for nm, sps in seen.items() if len(sps) > 1}
    if mixed:
        detail = "; ".join("%r in splits %s" % (nm, sps) for nm, sps in sorted(mixed.items()))
        raise CorpusSplitMixError(
            "split-mix / one-directional-intake violation: %s — a case NEVER migrates between "
            "splits (corpus-integrity defect; fix the manifest's disclosed block)." % detail)


def _slice_recall(hit, n):
    """min-N gate (symmetric): n<MIN_N → (None, True) — float recall suppressed, insufficient_sample.
    Both a high (1/1) and a zero (0/1) hit are equally `insufficient-sample` at n<MIN_N. n>=MIN_N →
    (round(hit/n,3), False). Raw hit/n stay visible to the caller (k/n transparency)."""
    if n < MIN_N:
        return None, True
    return round(hit / n, 3), False


def _slice_rec(hit, n):
    """Slice record {hit, n, recall, insufficient_sample}: k/n is always visible, recall suppressed at n<MIN_N."""
    r, insuf = _slice_recall(hit, n)
    return {"hit": hit, "n": n, "recall": r, "insufficient_sample": insuf}


def _rec_of(records, split):
    for r in records:
        if r.get("split") == split:
            return r
    return None


# ---------- reuse: live-import regression_replay (NOT copied, Task 1 is closed) ----------
def load_rr():
    """Live-import of regression_replay (pattern gate_replay.py:37-41) → load_disclosed/matches/
    file_tokens/lead_file. An import, not a copy (reuse-first, Plan §1)."""
    spec = importlib.util.spec_from_file_location("regression_replay", _RR)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_RRMOD = None


def rr():
    global _RRMOD
    if _RRMOD is None:
        _RRMOD = load_rr()
    return _RRMOD


# ---------- live-adapter registry (SECONDARY branch — extensible, empty by default) ----------
# adapter(snapshot_abs_path) -> set[str] of flagged file paths/basenames.
LIVE_ADAPTERS = {}


def register_live_adapter(gen_id, fn):
    LIVE_ADAPTERS[gen_id] = fn


def _register_default_adapters():
    """Registry of real scanners. EMPTY on purpose: no scanner from the expected_generators of
    reproducible cases (4x local:) gives a simple "scan a source folder → list of files with the bug":
      - display_vs_reality_grep.py → scan_bundle(text) over a JS BUNDLE, returns excerpts (not paths);
      - audit_coverage_invert.py   → analyze(src, report_paths) requires AUDIT FILES (the snapshot has none);
      - error_oracle.py            → needs a LIVE endpoint (SQLi/SSTI blind-diff), not a static path.
    So all current live cases honestly → `live-run:N/A` (not a miss). The branch is implemented structurally
    (an extensible registry) — adding an adapter = register_live_adapter(gen_id, fn), without touching the core."""
    return  # intentionally empty; see docstring


_register_default_adapters()


# ---------- helpers ----------
def _as_list(v):
    if isinstance(v, list):
        return v
    if not v:
        return []
    return [v]


def _norm_tokens(s):
    """Word tokens len>=4 (for target↔case coverage matching). aevo(4)/templar/superform/shapeshift."""
    return {t for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if len(t) >= 4}


def _target_matches_case(target, case):
    """Default coverage: the leads.json target string intersects by a token with case.NAME (project-slug-
    prefixed). NOT with `source`: a descriptive `source` pulls in generic words (core/bridge/contract/finance),
    which gives FALSE coverage → a fake-understated recall (an unrelated case is marked a scored-miss).
    An error with name-only falls on the SAFE side — under-coverage → `unscored` (reported separately,
    NOT a miss), rather than over-coverage → fake-miss. For precise control use an explicit `covers`."""
    return bool(_norm_tokens(target) & _norm_tokens(case.get("name", "")))


def _blob_declared_set(cases, blob):
    """Set of case names declared as covered by THIS blob (explicit `covers` OR target-name-
    match). Per-blob scope is CRITICAL: a lead fires on case C <=> C is in the declared-set OF THAT blob from which the
    lead came. Without this, a lead from a foreign blob phantom-hits a case via a basename collision (`matches()`
    substring: `src/Vault.sol` ↔ `contracts/Vault.sol`) → recall UP (overstate)."""
    if not isinstance(blob, dict):
        return set()
    names = {c.get("name") for c in cases}
    cov = blob.get("covers")
    if cov:
        return {n for n in cov if n in names}
    tgt = blob.get("target", "")
    return {c.get("name") for c in cases if _target_matches_case(tgt, c)}


def _bugfile_flagged(flagged, bug_location):
    """The live adapter returned a set of paths — whether the bug_location file is among them (file-token match)."""
    return any(rr().matches(f, bug_location) for f in flagged)


def _snapshot_path(ref):
    if ref and ref.startswith("local:"):
        return os.path.join(SESSIONS, ref[len("local:"):])
    return None


# ---------- core scoring ----------
def score_corpus(cases, blobs, live=False):
    """Scores the corpus (list[dict] from load_disclosed()) against leads blobs.

    Returns list[record] — EXACTLY ONE record per EACH canonical split (held-out included even
    when empty). Honesty invariant: every recall number travels alongside n_cases+split+layer+metric_kind+
    match_granularity (STRUCT_FIELDS). Writes nothing to disk — write_records() does the writing."""
    # ⛔ corpus-integrity guard FIRST (Task 3, R4): one case-name in >1 split = fail-loud (we shout,
    # we do not average over a broken corpus). The raise is caught by CLI/selftest — see CorpusSplitMixError.
    _assert_no_split_mix(cases)
    blobs = blobs if isinstance(blobs, list) else [blobs]
    blobs = [b for b in blobs if b]

    # Per-blob attribution (Important-fix): each lead CARRIES the declared-set of its blob. A lead may
    # fire/count toward precision ONLY against cases from THAT set — otherwise a phantom hit
    # via a basename collision inflates recall/precision.
    scoped = []          # list[(lead_dict, frozenset(declared_case_names))]
    declared = set()     # union of all declared-sets (determines whether a case is scored at all)
    for b in blobs:
        dset = frozenset(_blob_declared_set(cases, b))
        declared |= set(dset)
        for ld in (b.get("leads", []) if isinstance(b, dict) else []):
            scoped.append((ld if isinstance(ld, dict) else {"file_line": str(ld)}, dset))

    bl_of = {c.get("name"): c.get("bug_location", "") for c in cases}

    # precision / per-generator FP — a lead "hit" if it matches the bug_location of a case FROM ITS OWN declared-set;
    # not hitting any such case = FP. (The scope fixes the same phantom as firing.)
    lead_hit, gen_fp = [], {}
    for ld, dset in scoped:
        lp = rr().lead_file(ld)
        hit = any(rr().matches(lp, bl_of.get(n, "")) for n in dset)
        lead_hit.append(hit)
        if not hit:
            g = ld.get("generator")
            if g:
                gen_fp[g] = gen_fp.get(g, 0) + 1
    precision = round(sum(lead_hit) / len(scoped), 3) if scoped else None

    # per-split aggregates
    by_split = {s: {"cases": [], "scored": 0, "unscored": 0, "surfaced": 0,
                    "gen_hit": {}, "gen_n": {}, "cls_hit": {}, "cls_n": {}}
                for s in CANON_SPLITS}
    for c in cases:
        s = c.get("split", "?")
        by_split.setdefault(s, {"cases": [], "scored": 0, "unscored": 0, "surfaced": 0,
                                "gen_hit": {}, "gen_n": {}, "cls_hit": {}, "cls_n": {}})
        by_split[s]["cases"].append(c.get("name"))

    for c in cases:
        s = c.get("split", "?")
        acc = by_split[s]
        name = c.get("name")
        bl = c.get("bug_location", "")
        cat = c.get("cat", "?")
        gens = [g for g in _as_list(c.get("expected_generators")) if g and g != "none"]

        # ⚠ Firing is scoped to leads whose blob DECLARED this case (name in dset) — not global.
        case_leads = [ld for ld, dset in scoped if name in dset]
        # case-level file-hit: any covering lead (attributed or not) hit the bug_location.
        case_file_hit = any(rr().matches(rr().lead_file(ld), bl) for ld in case_leads)

        # live branch (SECONDARY): local: + a registered adapter.
        live_flag = {}
        live_ran = False
        if live:
            sp = _snapshot_path(c.get("snapshot_ref", ""))
            if sp and os.path.exists(sp):
                for g in gens:
                    fn = LIVE_ADAPTERS.get(g)
                    if fn:
                        try:
                            flagged = fn(sp)
                        except Exception:
                            continue
                        live_ran = True
                        live_flag[g] = _bugfile_flagged(flagged, bl)

        # A case is scored if it is declared covered by leads (lead_covered) OR was run by an adapter.
        # (case_file_hit => lead_covered, since a covering lead lives only when name in dset — not a separate branch.)
        lead_covered = name in declared
        scored = lead_covered or live_ran
        if not scored:
            acc["unscored"] += 1
            continue
        acc["scored"] += 1

        surfaced = case_file_hit or any(live_flag.values())
        if surfaced:
            acc["surfaced"] += 1

        # per-class (case-level file-recall within cat) — only over SCORED cases.
        acc["cls_n"][cat] = acc["cls_n"].get(cat, 0) + 1
        if surfaced:
            acc["cls_hit"][cat] = acc["cls_hit"].get(cat, 0) + 1
        else:
            acc["cls_hit"].setdefault(cat, 0)

        # per-generator. Minor#1-fix: a generator is EVALUABLE on a case <=> the case is lead-covered (the absence of
        # a lead = a meaningful miss) OR an adapter was run for the generator (live_flag). Non-evaluable
        # (the case is scored ONLY via a foreign adapter, and THIS generator has neither a lead nor an adapter) →
        # excluded from gen_n, NOT counted as a miss (otherwise fake-miss / understate).
        for g in gens:
            evaluable = lead_covered or (g in live_flag)
            if not evaluable:
                continue
            fired = any(ld.get("generator") == g and rr().matches(rr().lead_file(ld), bl)
                        for ld in case_leads) or live_flag.get(g, False)
            acc["gen_n"][g] = acc["gen_n"].get(g, 0) + 1
            acc["gen_hit"][g] = acc["gen_hit"].get(g, 0) + (1 if fired else 0)

    # → records (one per split)
    ts = int(time.time())
    records = []
    for s in [x for x in CANON_SPLITS] + [x for x in by_split if x not in CANON_SPLITS]:
        acc = by_split[s]
        n_cases = len(acc["cases"])
        n_scored = acc["scored"]
        # split-level min-N: n_scored is the denominator of case-recall; n_scored<MIN_N → recall suppressed.
        split_recall, split_insuf = _slice_recall(acc["surfaced"], n_scored)
        rec = {
            "ts": ts,
            "type": "disclosed_benchmark",
            "layer": "B",
            "metric_kind": "lead-surfacing",     # NOT true-find (necessary-not-sufficient)
            "match_granularity": "file",         # NOT file:line
            "split": s,
            "n_cases": n_cases,
            "n_scored": n_scored,
            "n_surfaced": acc["surfaced"],       # numerator visible (raw fraction k/n even when suppressed)
            "unscored_n": acc["unscored"],
            "recall": split_recall,              # None at n_scored<MIN_N (Task 3 min-N)
            "insufficient_sample": split_insuf,  # split-level min-N flag (travels alongside recall)
            # per-generator / per-class: the same min-N (_slice_rec suppresses recall at n<MIN_N).
            "by_generator": {g: _slice_rec(acc["gen_hit"][g], acc["gen_n"][g])
                             for g in sorted(acc["gen_n"]) if acc["gen_n"][g] > 0},
            "by_class": {cat: _slice_rec(acc["cls_hit"][cat], acc["cls_n"][cat])
                         for cat in sorted(acc["cls_n"]) if acc["cls_n"][cat] > 0},
            "precision": precision,              # NOT split-scoped — see precision_scope
            "precision_scope": "corpus",         # aggregate over ALL leads of all blobs, NOT per-split
            "by_generator_fp": gen_fp,           # corpus-scope, like precision
        }
        records.append(rec)
    return records


# ---------- render / write ----------
def _fmt_slice(v):
    """k/n is always visible; at insufficient_sample (n<MIN_N) — WITHOUT a float number (symmetric for 0/1 and 1/1)."""
    if v["insufficient_sample"]:
        return "%d/%d (insufficient-sample, n<%d)" % (v["hit"], v["n"], MIN_N)
    return "%d/%d = %.2f" % (v["hit"], v["n"], v["recall"])


def render(records):
    out = []
    out.append("=== disclosed benchmark (Layer B) ===")
    out.append("METRIC: lead-surfacing recall (FILE-level — NOT file:line, NOT confirmed-exploit, "
               "NECESSARY-not-sufficient). splits are SEPARATE, not averaged.")
    out.append("MIN-N: a slice n<%d → 'insufficient-sample' (float recall suppressed, k/n visible; "
               "symmetric for 0/1 and 1/1)." % MIN_N)
    out.append("split ORDER: held-out=PRIMARY(clean) → dev=ceiling → soft-seen=sanity-floor(contaminated).")
    # held-out FIRST (the primary honest number), then dev, soft-seen, then non-standard splits.
    ordered = [_rec_of(records, s) for s in RENDER_ORDER if _rec_of(records, s)]
    ordered += [r for r in records if r["split"] not in RENDER_ORDER]
    for r in ordered:
        role = SPLIT_ROLE.get(r["split"], "?")
        # case-recall with min-N (split-level): at insufficient_sample we print k/n, not a float.
        if r["insufficient_sample"]:
            rc = "%d/%d (insufficient-sample, n<%d)" % (r["n_surfaced"], r["n_scored"], MIN_N)
        else:
            rc = "%d/%d = %.2f" % (r["n_surfaced"], r["n_scored"], r["recall"])
        out.append("")
        out.append("── split=%s  [%s]" % (r["split"], role))
        out.append("   n_cases=%d | scored=%d | unscored_n=%d | case-recall=%s"
                    % (r["n_cases"], r["n_scored"], r["unscored_n"], rc))
        if r["n_cases"] == 0:
            out.append("   (empty — held-out grows organically; n=0 = insufficient-sample, not averaged)")
            continue
        if r["by_generator"]:
            out.append("   per-generator recall:")
            for g, v in r["by_generator"].items():
                out.append("     %-42s %s" % (g, _fmt_slice(v)))
        if r["by_class"]:
            out.append("   per-class (case-level file-recall):")
            for cat, v in r["by_class"].items():
                out.append("     %-42s %s" % (cat[:42], _fmt_slice(v)))
    p = records[0]["precision"] if records else None
    out.append("")
    out.append("precision (corpus-level) = %s (share of leads that hit a known bug)"
               % ("n/a" if p is None else "%.2f" % p))
    return "\n".join(out)


def write_records(records, calib_path=CALIB):
    try:
        with open(calib_path, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print("WARN: could not write calibration_log:", e)
        return False


# ---------- CLI ----------
def _load_blob(path):
    with open(path, "r", encoding="utf-8") as f:
        blob = json.load(f)
    if isinstance(blob, list):
        blob = {"target": "?", "leads": blob}
    return blob


def _score_or_die(cases, blobs, live=False):
    """Wraps score_corpus fail-loud on corpus-integrity: prints a shout and exit(2), does NOT
    throw a traceback (fail-open towards other harnesses — Layer B is isolated)."""
    try:
        return score_corpus(cases, blobs, live=live)
    except CorpusSplitMixError as e:
        print("⛔ CORPUS INTEGRITY ERROR:", e)
        print("   (fail-loud: the scorer does NOT average over a broken corpus — fix the manifest's disclosed block.)")
        sys.exit(2)


def cmd_score(paths, live=False, write=True):
    cases = rr().load_disclosed()
    blobs = [_load_blob(p) for p in paths]
    records = _score_or_die(cases, blobs, live=live)
    print(render(records))
    if write:
        if write_records(records):
            print("\n→ appended %d split-record(s) to %s" % (len(records), os.path.relpath(CALIB, ROOT)))
    else:
        print("\n(--no-write: calibration_log untouched)")


def cmd_demo():
    """Without leads: everything unscored → record shape (n_cases/split/unscored_n) on the real corpus."""
    cases = rr().load_disclosed()
    records = _score_or_die(cases, [], live=False)
    print(render(records))
    print("\n(demo: no leads supplied — all scorable cases are unscored, nothing is written)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "demo":
        cmd_demo()
    elif cmd == "score":
        args = sys.argv[2:]
        live = "--live" in args
        write = "--no-write" not in args
        paths = [a for a in args if not a.startswith("--")]
        if not paths:
            print("A path to leads.json is required (several are allowed).")
            sys.exit(1)
        cmd_score(paths, live=live, write=write)
    else:
        print("Unknown command:", cmd, "\n", __doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
