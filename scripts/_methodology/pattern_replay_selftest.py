#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Selftest for pattern_replay.py (FDE Plan 7, TIER B §61 · §48.1).

Fixture library + fixture target (temp dir, isolated from the real sessions/) with a known
fingerprint → matched>=1; empty target → 0; missing target/library → fail-open 0.
Plus the update_ledger contract (lifts the `{TODO}` sentinel, idempotent) and parse_library (a comment
is not parsed).

Run: py -3 -X utf8 scripts/_methodology/pattern_replay_selftest.py
"""
# Ensure UTF-8 stdout so the summary (arrows/checks) prints on any console (Windows cp1251, etc.).
import sys as _utf8_sys
try:
    _utf8_sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import importlib.util
import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("pattern_replay", os.path.join(_HERE, "pattern_replay.py"))
pr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pr)

results = []


def ok(name, cond, detail=""):
    results.append(bool(cond))
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name, ("  — " + detail) if detail and not cond else ""))


# fixture library with TWO patterns: one will be found in the target, the other will not.
FIX_LIB = (
    "# fixture library\n\n"
    "### PAT-01 — fixture hit pattern\n"
    "- **pattern:** a known marker that lives in the fixture target.\n"
    "- **fingerprint:** `FINDME_TOKEN_XYZ`\n"
    "- **where to look:** fixture.\n\n"
    "### PAT-02 — fixture miss pattern\n"
    "- **fingerprint:** `THIS_NEVER_APPEARS_9qu9`\n\n"
    "<!--\n"
    "### PAT-99 — commented-out template (must NOT be parsed)\n"
    "- **fingerprint:** `SHOULD_NOT_BE_PARSED`\n"
    "-->\n"
)

print("── parse_library")
pats = pr.parse_library(FIX_LIB)
ok("parse_library: EXACTLY 2 patterns (comment stripped)", len(pats) == 2, "got %d: %r" % (len(pats), pats))
ok("parse_library: PAT-99 from the HTML comment NOT parsed",
   all("SHOULD_NOT_BE_PARSED" not in rx for _n, rx in pats))
ok("parse_library: name = PAT-01 heading", pats and pats[0][0].startswith("PAT-01"))
ok("parse_library: fingerprint PAT-01 == FINDME_TOKEN_XYZ", pats and pats[0][1] == "FINDME_TOKEN_XYZ")

print("── replay: fixture target with a known fingerprint")
tgt = tempfile.mkdtemp(prefix="pr_target_")
empty = tempfile.mkdtemp(prefix="pr_empty_")
try:
    # put the marker deep in the tree, next to it a build dir (must be skipped).
    sub = os.path.join(tgt, "src", "components")
    os.makedirs(sub)
    with open(os.path.join(sub, "Toast.tsx"), "w", encoding="utf-8") as f:
        f.write("import x from 'y';\nconst s = FINDME_TOKEN_XYZ;\nexport default s;\n")
    nm = os.path.join(tgt, "node_modules", "pkg")
    os.makedirs(nm)
    with open(os.path.join(nm, "ignored.js"), "w", encoding="utf-8") as f:
        f.write("FINDME_TOKEN_XYZ = 1  // in node_modules — must not produce a hit\n")

    res = pr.replay(tgt, pats)
    matched = [r for r in res if r["matched"]]
    ok("replay: matched == 1 (PAT-01 found, PAT-02 not)", len(matched) == 1,
       "got %d: %r" % (len(matched), [(r["name"], r["matched"]) for r in res]))
    hit = next((r["hit"] for r in res if r["name"].startswith("PAT-01")), None)
    ok("replay: hit points at src/components/Toast.tsx:2", hit == "src/components/Toast.tsx:2",
       "got %r" % (hit,))
    ok("replay: node_modules skipped (hit is not from there)", hit and "node_modules" not in hit)

    res_empty = pr.replay(empty, pats)
    ok("replay: empty target → 0 matched", sum(1 for r in res_empty if r["matched"]) == 0)

    # fail-open: nonexistent path → 0, no exception.
    res_missing = pr.replay(os.path.join(tgt, "does_not_exist"), pats)
    ok("replay: nonexistent src → 0 matched (fail-open)",
       sum(1 for r in res_missing if r["matched"]) == 0)
    ok("replay: src=None → 0 matched (fail-open)",
       sum(1 for r in pr.replay(None, pats) if r["matched"]) == 0)

    # a broken regex does not crash replay.
    res_bad = pr.replay(tgt, [("PAT-BAD", "(unclosed[")])
    ok("replay: broken regex → matched=False, not a crash", res_bad[0]["matched"] is False)
finally:
    shutil.rmtree(tgt, ignore_errors=True)
    shutil.rmtree(empty, ignore_errors=True)

print("── load_library fail-open")
ok("load_library(nonexistent) == '' (fail-open)",
   pr.load_library(os.path.join(_HERE, "no_such_lib_xyz.md")) == "")
ok("parse_library('') == [] → replay gives 0", len(pr.parse_library("")) == 0)

print("── update_ledger: lifts {TODO}, idempotent, sanitize")
d = tempfile.mkdtemp(prefix="pr_ledger_")
try:
    lp = os.path.join(d, "hypotheses.md")
    with open(lp, "w", encoding="utf-8") as f:
        f.write("## Loop State\n"
                "- **PRIOR-PATTERNS (§48.1 — recon-producer):** {TODO — run pattern_replay}\n"
                "- **Iteration #:** 1\n")
    ok("update_ledger returns True", pr.update_ledger(lp, 2, "PAT-01@a.tsx:2; PAT-03@b.sol:9") is True)
    body = open(lp, encoding="utf-8").read()
    ok("update_ledger: '{TODO}' lifted from the line", "{TODO}" not in body)
    ok("update_ledger: the line carries '2 matched'", "PRIOR-PATTERNS" in body and "2 matched" in body)
    ok("update_ledger: exactly ONE PRIOR-PATTERNS line (not duplicated)",
       body.count("PRIOR-PATTERNS") == 1)
    # idempotency: a re-run replaces the same line.
    pr.update_ledger(lp, 0, "no matches")
    body2 = open(lp, encoding="utf-8").read()
    ok("update_ledger idempotent: still ONE line, value '0 matched'",
       body2.count("PRIOR-PATTERNS") == 1 and "0 matched" in body2)

    # insertion when there is no line at all (pre-Task-5 ledger, but with Loop State).
    lp2 = os.path.join(d, "old_ledger.md")
    with open(lp2, "w", encoding="utf-8") as f:
        f.write("## Loop State\n- **Iteration #:** 1\n")
    pr.update_ledger(lp2, 1, "PAT-01@x:1")
    b3 = open(lp2, encoding="utf-8").read()
    ok("update_ledger: inserts the line into Loop State if it was missing",
       b3.count("PRIOR-PATTERNS") == 1 and "1 matched" in b3)

    # sanitize: detail with {} does not slip through as a sentinel.
    lp3 = os.path.join(d, "san.md")
    with open(lp3, "w", encoding="utf-8") as f:
        f.write("## Loop State\n- **PRIOR-PATTERNS (§48.1 — recon-producer):** {TODO}\n")
    pr.update_ledger(lp3, 1, "weird{brace}detail")
    b4 = open(lp3, encoding="utf-8").read()
    ok("update_ledger: '{'/'}' stripped from detail (does not look like {TODO})", "{" not in b4 and "}" not in b4)

    ok("update_ledger fail-open: nonexistent path → False",
       pr.update_ledger(os.path.join(d, "no", "such", "f.md"), 1) is False)
finally:
    shutil.rmtree(d, ignore_errors=True)

# ── T11: Refuted dead-shape index (2nd pass) ─────────────────────────────────────────────────────
# Refuted-section fixture: 1 hard [KILLED] (indexed), 1 [CONTESTED] (alive → do NOT bury),
# 1 template placeholder {NN} (not parsed), + a Parked block (outside the section boundary).
FIX_REFUTED = (
    "## Active\n### H-01 [DRIVE]: live hypothesis being driven\n\n"
    "## Refuted (kept for composite chaining — T6)\n\n"
    "> - `[KILLED]` — KILL-TAXONOMY prose line, must NOT become an entry.\n\n"
    "### H-07 [KILLED]: oracle conf-strip via none-price fallback causing insolvency\n"
    "- **Killed by (falsifier):** decoder-v1.clar:104 secp256k1 verify binds price atomically.\n"
    "- **Residual:** oracle stack tidy.\n\n"
    "### H-08 [CONTESTED]: reentrancy guard on vault withdraw maybe bypassable\n"
    "- **Guard exists but not provably sufficient:** vault.sol:50\n\n"
    "### H-{NN} [KILLED]: {one-line}\n"
    "- **Killed by (falsifier — MANDATORY):** {evidence / file:line}\n\n"
    "## Parked\n### H-09 [PARKED]: killed-in-parked-should-not-index oracle price fallback insolvency\n"
)

print("── T11 parse_refuted: section, statuses, template/blockquote filtering")
ref = pr.parse_refuted(FIX_REFUTED)
ids = [e["origin"] for e in ref]
ok("parse_refuted: H-07 and H-08 recognized, template H-{NN} and Parked H-09 are not",
   set(ids) == {"H-07", "H-08"}, "got %r" % (ids,))
ok("parse_refuted: KILL-TAXONOMY blockquote prose did NOT become an entry",
   all("KILL-TAXONOMY prose" not in e["title"] for e in ref))
h07 = next(e for e in ref if e["origin"] == "H-07")
ok("parse_refuted: H-07 status KILLED", "KILLED" in h07["status"].upper())
ok("parse_refuted: H-07 falsifier captured", "secp256k1" in h07["falsifier"])
ok("parse_refuted: H-07 shape-tokens >=3", len(h07["tokens"]) >= 3, "got %r" % (h07["tokens"],))

print("── T11 index_refuted: only [KILLED] lands in the bank")
sroot = tempfile.mkdtemp(prefix="pr_sessions_")
bank = os.path.join(tempfile.mkdtemp(prefix="pr_bank_"), "dead_shapes.md")
try:
    # 2 sessions: one with the Refuted fixture, one empty; + _methodology (must be skipped).
    sd = os.path.join(sroot, "granite-x")
    os.makedirs(sd)
    with open(os.path.join(sd, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(FIX_REFUTED)
    meth = os.path.join(sroot, "_methodology")
    os.makedirs(meth)
    with open(os.path.join(meth, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(FIX_REFUTED)  # under `_` → must be skipped by _iter_session_ledgers

    shapes = pr.index_refuted(sroot, bank)
    ok("index_refuted: exactly 1 shape (KILLED H-07; CONTESTED/template/parked/_methodology filtered out)",
       len(shapes) == 1, "got %d: %r" % (len(shapes), [s["origin"] for s in shapes]))
    ok("index_refuted: source points at granite-x/H-07",
       shapes and shapes[0]["source"].endswith("granite-x/hypotheses.md#H-07"))
    ok("index_refuted: bank file written", os.path.isfile(bank))
    bank_txt = open(bank, encoding="utf-8").read()
    ok("index_refuted: bank is greppable (carries DEAD-01 + canonical fingerprint)",
       "DEAD-01" in bank_txt and "**fingerprint:**" in bank_txt)
    # the same parse_library reads the bank (not a parallel indexer)
    ok("index_refuted: bank is read by the SAME parse_library",
       len(pr.parse_library(bank_txt)) == 1)

    print("── T11 match: a dead shape is caught, a fresh one is not, the threshold holds")
    loaded = pr.load_dead_shapes(bank)
    ok("load_dead_shapes: 1 shape with restored tokens",
       len(loaded) == 1 and len(loaded[0]["tokens"]) >= 3)

    # (a) a restatement of the same dead shape → FLAG
    hit = pr.check_hypothesis(
        "oracle price fallback with none conf strip leading to insolvency", bank)
    ok("check_hypothesis: a paraphrase of the dead shape is FLAGGED (grep-able match)", hit is not None,
       "got %r" % (hit,))
    ok("check_hypothesis: >=3 shared tokens", hit and len(hit["shared"]) >= 3,
       "shared=%r" % (hit["shared"] if hit else None))

    # (b) a fresh NON-dead hypothesis → NOT flagged
    fresh = pr.check_hypothesis("integer overflow in reward accrual math rounding drift", bank)
    ok("check_hypothesis: a fresh non-dead shape is NOT flagged", fresh is None, "got %r" % (fresh,))

    # (c) anti-over-flag: 1-2 shared generic words do NOT resurrect a dead shape
    weak = pr.check_hypothesis("oracle price feed staleness monitoring", bank)
    ok("check_hypothesis: 1-2 shared tokens do NOT flag (the threshold holds)", weak is None,
       "got %r" % (weak,))

    # (d) a CONTESTED shape (not indexed) → NOT caught as dead
    contested = pr.check_hypothesis("reentrancy guard on vault withdraw bypass", bank)
    ok("check_hypothesis: CONTESTED shape NOT in the bank → not flagged", contested is None,
       "got %r" % (contested,))

    # fail-open: nonexistent bank → no match, no crash
    ok("check_hypothesis fail-open: no bank → None",
       pr.check_hypothesis("anything at all here", os.path.join(sroot, "no_bank.md")) is None)
    ok("index_refuted fail-open: nonexistent sessions → 0 shapes, no crash",
       pr.index_refuted(os.path.join(sroot, "nope"), bank, write=False) == [])
finally:
    shutil.rmtree(sroot, ignore_errors=True)
    shutil.rmtree(os.path.dirname(bank), ignore_errors=True)

n = sum(results)
print("\n%d/%d pattern_replay selftest cases green" % (n, len(results)))
sys.exit(0 if n == len(results) else 1)
