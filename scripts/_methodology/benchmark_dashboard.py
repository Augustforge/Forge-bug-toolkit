#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""benchmark_dashboard.py — acceptance-rollup dashboard (FDE Plan 8, Part XII, Task 6).

WHAT THIS IS: a generator → `sessions/_methodology/benchmark_dashboard.md`. Reads (read-only) the
scorer's disclosed_benchmark records (Task 2/3, `disclosed_benchmark_replay.py`) — history from
`calibration_log.jsonl` OR a fresh scorer run when there is no history — and the Layer-A true-find
rounds (Task 5, `benchmark_blind_protocol.md`). Renders recall per-class/per-generator/per-split,
Layer B and Layer A STRICTLY SEPARATELY, a trend over history, and a HEADLINE line under the iron
rule below.

⛔ Does NOT duplicate the scorer logic — only renders what `disclosed_benchmark_replay.py` has ALREADY
computed (reuse-first, live-import of the same pattern as `disclosed_benchmark_selftest.py`). Does NOT
write to `calibration_log.jsonl`, does NOT touch `blind_spots.md`/`benchmark_miss_analysis.py` (Task 4,
disjoint), does NOT modify the manifest/corpus/scorer.

⛔ HONESTY CORE (R2/R7 — enforced below, proven by `benchmark_dashboard_selftest.py`):
  1. min-N: any recall slice with n<MIN_N (=disclosed_benchmark_replay.MIN_N, currently 5) is rendered
     as `insufficient-sample`, NOT a recall number (the value is already computed by the scorer — the
     dashboard reads the `insufficient_sample` field, does not recompute).
  2. Layer B != Layer A — separate sections, NEVER averaged/mixed.
  3. held-out = PRIMARY (clean) is rendered first; dev = ceiling; soft-seen = sanity-floor
     (contaminated) — the same roles/order as the scorer (`RENDER_ORDER`/`SPLIT_ROLE`, reused).
  4. HEADLINE NEVER renders a bare Layer-B recall as "proven: we catch X%". If Layer A is measured
     (n>0) — the headline is dual-stated (A=floor + B=ceiling, explicitly labeled). If Layer A is not
     measured (n=0, the current real state — the Task 5 protocol is ready, rounds have not been run
     yet) — the headline honestly says "true-find not measured" and, if a Layer-B held-out number is
     available at all, labels it "CEILING of lead-surfacing, NOT strength" — never a bare "we catch X%".
  5. The trend on tiny-N (insufficient-sample) points is suppressed — such points do not take part in
     the delta/line.

fail-open (Global Constraints, Plan §1): a generator failure does NOT break the scorer/regression —
main() catches any exception, prints WARN, exit 0 (the dashboard is NOT a hard-gate, NOT a release
blocker, R7).

Usage:
  py -3 -X utf8 benchmark_dashboard.py            # writes sessions/_methodology/benchmark_dashboard.md
  py -3 -X utf8 benchmark_dashboard.py --stdout   # prints to stdout, does not touch the file (dry-run)
"""
import importlib.util
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SESSIONS = os.path.join(ROOT, "bug-bounty-toolkit", "sessions")
METHOD_DIR = os.path.join(SESSIONS, "_methodology")
CALIB = os.path.join(METHOD_DIR, "calibration_log.jsonl")
BLIND_PROTOCOL = os.path.join(METHOD_DIR, "benchmark_blind_protocol.md")
DASHBOARD_MD = os.path.join(METHOD_DIR, "benchmark_dashboard.md")

_HERE = os.path.dirname(os.path.abspath(__file__))
_DBR_PATH = os.path.join(_HERE, "disclosed_benchmark_replay.py")


# ---------- reuse: live-import disclosed_benchmark_replay (Task 2/3 — read-only, not copied) ----------
def load_dbr():
    """Live-import of the scorer (the same pattern as `disclosed_benchmark_selftest.py`/`gate_replay.py`).
    Gives access to MIN_N/RENDER_ORDER/SPLIT_ROLE/score_corpus/rr() — the dashboard reads, does not duplicate."""
    spec = importlib.util.spec_from_file_location("disclosed_benchmark_replay", _DBR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_DB = None


def db():
    global _DB
    if _DB is None:
        _DB = load_dbr()
    return _DB


# ---------- Layer B: history (calibration_log.jsonl, read-only) + fresh-run fallback ----------
def load_history(calib_path=CALIB):
    """Reads calibration_log.jsonl (read-only, does NOT write), filters type=='disclosed_benchmark'.
    fail-open: a missing file / broken lines → empty history, does not crash (history is currently empty
    on the real corpus — the scorer has never been run with --write yet, the dashboard must show this
    honestly, rather than pretend there is no data at all)."""
    records = []
    try:
        with open(calib_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("type") == "disclosed_benchmark":
                    records.append(e)
    except OSError:
        pass
    return records


def fresh_snapshot():
    """A fresh scorer run WITHOUT leads (equivalent of `disclosed_benchmark_replay.py demo`) — reads the
    REAL disclosed corpus via rr().load_disclosed(), score_corpus(cases, [], live=False).
    write_records() is NOT called — a read-only snapshot, calibration_log is not touched (Task 6
    interface: "either the calibration_log.jsonl history, or a fresh scorer run")."""
    mod = db()
    cases = mod.rr().load_disclosed()
    return mod.score_corpus(cases, [], live=False)


def latest_by_split(history, fallback_records):
    """The latest (by ts) record of EACH split from history; a split that is not in history is filled in
    from fallback_records (fresh run). The scorer's split-isolation invariant is preserved: the function
    does NOT average/mix splits — it just picks one record per split."""
    latest = {}
    for r in history:
        s = r.get("split")
        if s is None:
            continue
        if s not in latest or r.get("ts", 0) >= latest[s].get("ts", 0):
            latest[s] = r
    for r in fallback_records:
        s = r.get("split")
        if s not in latest:
            latest[s] = r
    return latest


def trend_by_split(history):
    """split -> chronological list of records (ts asc) for the trend section."""
    out = {}
    for r in sorted(history, key=lambda e: e.get("ts", 0)):
        out.setdefault(r.get("split"), []).append(r)
    return out


# ---------- Layer A: parsing benchmark_blind_protocol.md section "Round results" (read-only) ----------
# The round format is not defined by a separate script (Layer A is a manual occasional protocol, Task 5) —
# we follow the convention ALREADY documented in the file itself ("the k/n fraction is printed EXPLICITLY
# (e.g. 2/3)", see §Metric: true-find recall) — the regex looks for "true-find recall ... k/n" inside the results section.
_RESULT_FRAC_RE = re.compile(r"true-find\s+recall[^0-9]{0,20}(\d+)\s*/\s*(\d+)", re.IGNORECASE)


def _extract_section(text, heading):
    """Text UNDER the exact '## heading' up to the next '## ' (or EOF). None if the heading is not found.
    Flat line-based parsing, no dependencies (the same level of simplicity as the rest of the toolkit)."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == heading:
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    return "\n".join(lines[start:end])


def parse_layer_a_results(text):
    """Parses the "Round results" section (its heading is kept in Russian — it is matched
    against the protocol document). Empty/placeholder (not a single 'true-find recall = k/n')
    → measured=False, n=0 — THIS is the current honest state (the Task 5 protocol is ready, rounds have not
    been run yet). Returns {'measured','k','n','rounds':[(k,n),...],'note'}."""
    section = _extract_section(text, "## Результаты раундов")  # KEPT: Russian heading ("Round results") matched in the protocol doc
    if section is None:
        return {"measured": False, "k": 0, "n": 0, "rounds": [],
                "note": "section 'Round results' not found in benchmark_blind_protocol.md"}
    matches = _RESULT_FRAC_RE.findall(section)
    if not matches:
        return {"measured": False, "k": 0, "n": 0, "rounds": [],
                "note": "no Layer-A round has been run yet (protocol ready, section empty/placeholder)"}
    rounds = [(int(k), int(n)) for k, n in matches]
    total_k = sum(k for k, _n in rounds)
    total_n = sum(n for _k, n in rounds)
    return {"measured": True, "k": total_k, "n": total_n, "rounds": rounds,
            "note": "%d round(s) recorded in the protocol" % len(rounds)}


def load_layer_a(path=BLIND_PROTOCOL):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        return {"measured": False, "k": 0, "n": 0, "rounds": [],
                "note": "could not read %s: %s" % (path, e)}
    return parse_layer_a_results(text)


# ---------- HEADLINE (⛔ iron rule: never bare Layer B) ----------
def headline_b_candidate(latest):
    """held-out (the PRIMARY split) — the only candidate for the ceiling B number in the headline (dev=ceiling
    and soft-seen=contaminated are NEVER suitable for the headline — the same principle by which the scorer
    prints held-out first). None if there is no record; otherwise {'recall','n','insufficient'}."""
    r = latest.get("held-out")
    if r is None:
        return None
    return {"recall": r.get("recall"), "n": r.get("n_scored", r.get("n_cases", 0)),
            "insufficient": bool(r.get("insufficient_sample", True))}


def render_headline(layer_a, b_cand):
    """⛔ IRON RULE (R2/R7): HEADLINE = Layer A (floor) OR dual-stated (B-ceiling + A-floor
    together), NEVER bare Layer B. Any appearance of a B number in the headline carries an explicit marker
    'CEILING'/'NOT strength'. Layer A n=0 → 'true-find NOT measured' is said explicitly, before any B."""
    b_txt = None
    if b_cand and not b_cand["insufficient"] and b_cand["recall"] is not None:
        b_txt = ("Layer B held-out (CEILING of lead-surfacing, NOT strength): %.2f (n=%d)"
                 % (b_cand["recall"], b_cand["n"]))

    if layer_a["measured"] and layer_a["n"] > 0:
        a_txt = "Layer A (FLOOR, true-find recall): %d/%d" % (layer_a["k"], layer_a["n"])
        if b_txt:
            return ("HEADLINE (dual-stated): %s | %s — the truth lies between the floor and the ceiling, "
                     "NOT a single number 'we catch X%%'." % (a_txt, b_txt))
        return ("HEADLINE: %s (Layer B held-out is still insufficient-sample — the ceiling number "
                 "is not rendered)." % a_txt)

    a_txt = "Layer A: n=0 — true-find recall NOT measured (%s)." % layer_a["note"]
    if b_txt:
        return ("HEADLINE: %s %s — this is the CEILING of lead-surfacing (necessary-not-sufficient), "
                 "NOT proof of 'we catch X%%' (true-find not confirmed)." % (a_txt, b_txt))
    return ("HEADLINE: %s Layer B held-out is also insufficient-sample (n<%d) — even the ceiling "
            "number is not available yet." % (a_txt, db().MIN_N))


# ---------- render: Layer B section (per-split / per-generator / per-class) ----------
def _fmt_case_recall(r):
    if r is None:
        return "n/a (record missing)"
    if r.get("insufficient_sample"):
        return "%d/%d (insufficient-sample, n<%d)" % (
            r.get("n_surfaced", 0), r.get("n_scored", 0), db().MIN_N)
    return "%d/%d = %.2f" % (r.get("n_surfaced", 0), r.get("n_scored", 0), r.get("recall"))


def _fmt_slice_table(d, title):
    """per-generator/per-class table — reads the fields already computed by the scorer (hit/n/recall/
    insufficient_sample), does NOT recompute min-N itself (reuse-first)."""
    if not d:
        return ["_(%s: no evaluable data on this split)_" % title]
    out = ["| %s | k/n | recall |" % title, "|---|---|---|"]
    for k in sorted(d):
        v = d[k]
        cell = ("insufficient-sample (n<%d)" % db().MIN_N) if v["insufficient_sample"] else ("%.2f" % v["recall"])
        out.append("| `%s` | %d/%d | %s |" % (k, v["hit"], v["n"], cell))
    return out


def render_layer_b_section(latest):
    mod = db()
    out = ["## Layer B — lead-surfacing recall (FILE-level, scorer: `disclosed_benchmark_replay.py`)", "",
           "METRIC: did the EXPECTED generator/scan fire ON THE FILE of a known disclosed bug. "
           "A NECESSARY-NOT-SUFFICIENT condition for true-find (Layer A) — the right file != bug proven.", ""]
    for s in mod.RENDER_ORDER:  # held-out → dev → soft-seen (the same role/order as the scorer)
        r = latest.get(s)
        role = mod.SPLIT_ROLE.get(s, "?")
        out.append("### split=%s — %s" % (s, role))
        out.append("")
        if r is None:
            out.append("_(no records)_")
            out.append("")
            continue
        out.append("- n_cases=%d, scored=%d, unscored=%d, case-recall=%s"
                    % (r.get("n_cases", 0), r.get("n_scored", 0), r.get("unscored_n", 0),
                       _fmt_case_recall(r)))
        out.append("")
        out.append("**per-generator:**")
        out.extend(_fmt_slice_table(r.get("by_generator", {}) or {}, "generator"))
        out.append("")
        out.append("**per-class:**")
        out.extend(_fmt_slice_table(r.get("by_class", {}) or {}, "class"))
        out.append("")
    return out


def render_layer_a_section(layer_a):
    out = ["## Layer A — true-find recall (protocol: `benchmark_blind_protocol.md`, occasional/manual)", "",
           "METRIC: did a cold agent find the bug END-TO-END in a blind hunt (NOT lead-surfacing). Expensive, "
           "occasional — NOT CI, NOT per-commit, NOT automated.", ""]
    if not layer_a["measured"]:
        out.append("**n=0 — true-find recall NOT measured.** %s" % layer_a["note"])
        out.append("")
        out.append("(The protocol is ready — see `benchmark_blind_protocol.md` §Seed. Occasional rounds: "
                    ">=2-3 new seed cases since the last round, OR after a significant edit of the "
                    "T10/scout prompt, OR on explicit request from the operator.)")
    else:
        out.append("**true-find recall = %d/%d** (%s)" % (layer_a["k"], layer_a["n"], layer_a["note"]))
        out.append("")
        out.append("Rounds: " + ", ".join("%d/%d" % (k, n) for k, n in layer_a["rounds"]))
    out.append("")
    return out


def render_trend_section(history):
    out = ["## Trend (history from `calibration_log.jsonl`)", ""]
    if not history:
        out.append("_No history — 0 `disclosed_benchmark` records in `calibration_log.jsonl` so far "
                    "(the scorer has never been run with writing / `demo` intentionally writes nothing). "
                    "The Layer B snapshot above = a fresh run, NOT history — the trend will appear organically "
                    "as `score --write` runs accumulate._")
        out.append("")
        return out
    grouped = trend_by_split(history)
    for s in db().RENDER_ORDER:
        recs = grouped.get(s, [])
        if not recs:
            continue
        out.append("### %s" % s)
        out.append("")
        out.append("| ts | case-recall | Δ vs prev. sufficient |")
        out.append("|---|---|---|")
        last_sufficient = None
        for r in recs:
            ts_h = time.strftime("%Y-%m-%d %H:%M", time.localtime(r.get("ts", 0)))
            if r.get("insufficient_sample"):
                line_recall = "insufficient-sample (n=%d<%d, excluded from the trend line)" % (
                    r.get("n_scored", 0), db().MIN_N)
                delta = "—"
            else:
                rc = r.get("recall")
                line_recall = "%.2f (n=%d)" % (rc, r.get("n_scored", 0))
                delta = "n/a (first sufficient point)" if last_sufficient is None else "%+.2f" % (rc - last_sufficient)
                last_sufficient = rc
            out.append("| %s | %s | %s |" % (ts_h, line_recall, delta))
        out.append("")
    return out


# ---------- assemble ----------
def build_dashboard():
    history = load_history()
    fresh_err = None
    try:
        fresh = fresh_snapshot()
    except Exception as e:
        fresh = []
        fresh_err = str(e)
    latest = latest_by_split(history, fresh)
    layer_a = load_layer_a()
    b_cand = headline_b_candidate(latest)
    headline = render_headline(layer_a, b_cand)

    lines = []
    lines.append("# Benchmark Dashboard — Layer A (true-find) + Layer B (lead-surfacing)")
    lines.append("")
    lines.append("_Auto-generated by `scripts/_methodology/benchmark_dashboard.py` — do NOT edit "
                 "by hand, edits will be wiped on the next run. NOT a hard-gate (R7) — track+trend, not a "
                 "release blocker._")
    lines.append("")
    lines.append("Generated: %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    if fresh_err:
        lines.append("")
        lines.append("_(WARN: the fresh scorer run failed: %s — rendering history only, "
                     "fail-open.)_" % fresh_err)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## HEADLINE")
    lines.append("")
    lines.append(headline)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.extend(render_layer_a_section(layer_a))
    lines.append("---")
    lines.append("")
    lines.extend(render_layer_b_section(latest))
    lines.append("---")
    lines.append("")
    lines.extend(render_trend_section(history))
    lines.append("---")
    lines.append("")
    lines.append("## Honesty (R2/R7 — do not remove when editing)")
    lines.append("")
    lines.append("- Layer B != Layer A: NEVER averaged/mixed (separate sections above).")
    lines.append("- held-out = PRIMARY (clean); dev = ceiling; soft-seen = sanity-floor (contaminated).")
    lines.append("- min-N=%d: a slice with n<%d → `insufficient-sample`, NOT a recall number (symmetric for "
                 "0/n and n/n)." % (db().MIN_N, db().MIN_N))
    lines.append("- HEADLINE never renders a bare Layer-B recall as \"proven: we catch X%\".")
    lines.append("")
    return "\n".join(lines)


def write_dashboard(path=DASHBOARD_MD):
    text = build_dashboard()
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main():
    try:
        if "--stdout" in sys.argv[1:]:
            print(build_dashboard())
            return
        p = write_dashboard()
        print("→ wrote %s" % os.path.relpath(p, ROOT))
    except Exception as e:
        # fail-open (Global Constraints, Plan §1): the generator must not break the scorer/regression.
        print("WARN: benchmark_dashboard generator crashed: %s (fail-open, nothing broken)" % e)
        sys.exit(0)


if __name__ == "__main__":
    main()
