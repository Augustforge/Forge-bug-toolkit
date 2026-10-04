#!/usr/bin/env python3
"""Selftest for the manifest's `disclosed:` block (FDE Plan 8 Task 1).

Proves FIRING on the REAL regression_manifest.yaml ([[feedback_hook_must_prove_firing]]):
  (a) the parser reads ALL `disclosed:` records (count > 0, the expected N);
  (b) EVERY record carries the mandatory fields (name, bug_location, expected_generators=non-empty
      list, primary, disclosure_class ∈ {CATCH,PARTIAL,GAP}, split ∈ {soft-seen,dev,held-out});
  (c) primary ∈ expected_generators;
  (d) the split distribution is sane (soft-seen+dev ≈ 20, held-out small);
  (e) the MINI-parser path is checked DIRECTLY on a fixture string with an inline list — even if
      PyYAML is present on the system (otherwise the fallback is blind to drift).

Run: py -3 -X utf8 disclosed_corpus_selftest.py
Prints N/N PASS; non-zero exit on any fail.
"""
import sys
import os
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
RR_PATH = os.path.join(HERE, "regression_replay.py")

_spec = importlib.util.spec_from_file_location("regression_replay", RR_PATH)
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)

VALID_DCLASS = {"CATCH", "PARTIAL", "GAP"}
VALID_SPLIT = {"soft-seen", "dev", "held-out"}
REQUIRED = ("name", "bug_location", "expected_generators", "primary",
            "disclosure_class", "split")

# Expected N — a sanity lower bound, NOT a brittle exact comparison (plan: ~20, >=18 ok).
MIN_RECORDS = 18


def expected_dclass(expected_generators):
    """OBJECTIVE mechanical rule v1 (fix-round 1) — computes disclosure_class from the generator list.
    Keeps the label consistent: the selftest ASSERTs it matches what is set in the manifest, so
    a desync/manual skew is physically impossible under future edits.
      CATCH   <=> >=1 concrete executable generator (a .py name / .workflow.js / an active_* gate);
                `divergence_fanout` == divergence_fanout.workflow.js → concrete.
      GAP     <=> expected_generators == ['none'].
      PARTIAL <=> otherwise (only model-first:<axis> and/or un-dup methods).
    """
    eg = expected_generators or []
    if [str(x).strip().lower() for x in eg] == ["none"]:
        return "GAP"
    for g in eg:
        g = str(g).strip()
        if g.endswith(".py") or g.endswith(".workflow.js") or g == "divergence_fanout" \
                or g.startswith("active_"):
            return "CATCH"
    return "PARTIAL"


class Checks:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.log = []

    def ok(self, cond, label):
        if cond:
            self.passed += 1
            self.log.append("  [PASS] " + label)
        else:
            self.failed += 1
            self.log.append("  [FAIL] " + label)
        return cond


def run():
    c = Checks()

    # ── (a) PyYAML/primary path: load_disclosed() reads the real manifest ──
    disc = rr.load_disclosed()
    c.ok(isinstance(disc, list) and len(disc) > 0,
         "load_disclosed() returned a non-empty list")
    c.ok(len(disc) >= MIN_RECORDS,
         "records >= %d (actually %d)" % (MIN_RECORDS, len(disc)))

    # ── (b)+(c) mandatory fields on EVERY record + primary ∈ expected_generators ──
    for i, d in enumerate(disc):
        nm = d.get("name", "<#%d>" % i)
        for field in REQUIRED:
            c.ok(field in d and d[field] not in (None, "", []),
                 "%s: field '%s' is present and non-empty" % (nm, field))
        eg = d.get("expected_generators")
        c.ok(isinstance(eg, list) and len(eg) > 0,
             "%s: expected_generators = non-empty list" % nm)
        c.ok(d.get("disclosure_class") in VALID_DCLASS,
             "%s: disclosure_class ∈ %s" % (nm, sorted(VALID_DCLASS)))
        c.ok(d.get("split") in VALID_SPLIT,
             "%s: split ∈ %s" % (nm, sorted(VALID_SPLIT)))
        if isinstance(eg, list):
            c.ok(d.get("primary") in eg,
                 "%s: primary ∈ expected_generators" % nm)
            # honesty-by-mechanism: the label MUST match the one computed by the objective rule v1
            want = expected_dclass(eg)
            c.ok(d.get("disclosure_class") == want,
                 "%s: disclosure_class '%s' == computed by rule v1 '%s'"
                 % (nm, d.get("disclosure_class"), want))

    # ── (d) the split distribution is sane ──
    from collections import Counter
    dist = Counter(d.get("split") for d in disc)
    soft, dev, held = dist.get("soft-seen", 0), dist.get("dev", 0), dist.get("held-out", 0)
    c.ok(soft + dev >= MIN_RECORDS,
         "soft-seen+dev >= %d (soft=%d dev=%d)" % (MIN_RECORDS, soft, dev))
    c.ok(held <= 5,
         "held-out is small (<=5, actually %d)" % held)

    # ── (e) MINI-parser path DIRECTLY on a fixture (inline list) — mandatory ──
    fixture = (
        "cases:\n"
        "  - name: dummy-case\n"
        "    bug_location: src/Foo.sol:10\n"
        "disclosed:\n"
        "  - name: fixture-inline-list\n"
        "    bug_location: src/Bar.sol:42\n"
        "    expected_generators: [alpha.py, model-first:some-axis, negative-space]\n"
        "    primary: model-first:some-axis\n"
        "    disclosure_class: CATCH\n"
        "    split: soft-seen\n"
        "  - name: fixture-empty-list\n"
        "    expected_generators: []\n"
        "trailing_block:\n"
        "  - name: must-not-leak-into-disclosed\n"
    )
    mdisc = rr._mini_parse(fixture, "disclosed")
    c.ok(len(mdisc) == 2,
         "mini _mini_parse(disclosed) returned 2 records (did not pull in trailing_block): %d" % len(mdisc))
    if mdisc:
        eg0 = mdisc[0].get("expected_generators")
        c.ok(isinstance(eg0, list) and eg0 == ["alpha.py", "model-first:some-axis", "negative-space"],
             "mini: the inline list [a, b, c] is parsed into a python list: %r" % (eg0,))
        c.ok(mdisc[0].get("primary") == "model-first:some-axis",
             "mini: scalar fields are parsed alongside the list")
    if len(mdisc) > 1:
        c.ok(mdisc[1].get("expected_generators") == [],
             "mini: an empty inline list [] → []")
    # cases: must NOT pull in disclosed/trailing (top-level block boundary)
    mcases = rr._mini_parse(fixture, "cases")
    c.ok(len(mcases) == 1 and mcases[0].get("name") == "dummy-case",
         "mini: cases: stopped at the block boundary (did not pull in disclosed)")

    # ── output ──
    total = c.passed + c.failed
    print("\n".join(c.log))
    print("\n%d/%d PASS" % (c.passed, total))
    if c.failed:
        print("FAILED: %d checks did not pass" % c.failed)
        return 1
    dc = Counter(d.get("disclosure_class") for d in disc)
    print("disclosed-corpus selftest: OK (records=%d, soft=%d dev=%d held=%d | CATCH=%d PARTIAL=%d GAP=%d)"
          % (len(disc), soft, dev, held,
             dc.get("CATCH", 0), dc.get("PARTIAL", 0), dc.get("GAP", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(run())
