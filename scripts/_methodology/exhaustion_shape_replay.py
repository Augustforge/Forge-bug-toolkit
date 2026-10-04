# -*- coding: utf-8 -*-
"""OBS-17 replay: `ledger_exhaustion_shape` must NOT false-fire on a template scaffold.

ROOT (2026-07-28): `_KILL_TAG_RE.findall(txt)` on the RAW text counted 8 example kill tags from the
kill taxonomy (rules block + `>` guides + the placeholder `### H-{NN} [KILLED]: {one-line}`) → ANY
freshly created/spurious ledger produced kills=8>=6 → exhaustion_shape falsely True → FALSE-EXHAUSTION
block on a pristine ledger (it actually happened: a spurious smart-contract-audits ledger from OBS-15
was read as the freshest active one → a false give-up block). Fix: `_real_kill_count` (strip scaffold
+ discard `{`-placeholders).

The test proves BOTH directions:
  (1) a pristine/template ledger → real_kill_count low → exhaustion_shape False (false fire killed);
  (2) >=6 REAL canonical kills + an empty Verifier Log → exhaustion_shape True (true-positive intact).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
HOOKS = os.path.join(HERE, "..", "hooks")
sys.path.insert(0, HOOKS)
import hunt_completeness_gate as g  # noqa: E402

results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

def shape(txt):
    """Replica of ledger_exhaustion_shape on text (without a file/sid)."""
    return g._real_kill_count(txt) >= g.EXHAUSTION_KILL_MIN and g._verifier_log_empty(txt)

# ── Fixtures ────────────────────────────────────────────────────────────────
# A real template carries the kill taxonomy: rules block, `>` guides, placeholder [KILLED]: {one-line}.
PRISTINE = """## ⚠ LEDGER RULES
- `[SCOPED-OUT]` (weaker than KILLED, needs a cold re-audit + falsifier `file:line`)

# proto — Hypotheses Registry

## Active Hypotheses
### H-{NN}: {one-line}

## Refuted
### H-{NN} [KILLED]: {one-line}

> **KILL TAXONOMY:**
> - `[KILLED]` — a HARD falsifier: a specific `file:line` guard.
> - `[SCOPED-OUT]` — a kill by JUDGMENT about scope.
> - `[DE-MINIMIS]` — a kill by JUDGMENT about severity.

## Verifier Log
- {timestamp} — H-{NN} — verifier verdict: confirm / kill / downgrade
"""

# Real kills on hypothesis headers (canonical tags), Verifier Log — placeholder only.
SIX_REAL_KILLS = """# proto — Hypotheses Registry
## Active Hypotheses
### H-01 [KILLED]: real one
### H-02 [KILLED]: real two
### H-03 [SCOPED-OUT]: real three
### H-04 [SCOPED-OUT]: real four
### H-05 [DE-MINIMIS]: real five
### H-06 [DE-MINIMIS]: real six
## Verifier Log
- {timestamp} — H-{NN} — verifier verdict: confirm / kill
"""

# Same set, but the Verifier Log is FILLED with a real entry → NOT exhaustion (verification present).
SIX_KILLS_LOGGED = SIX_REAL_KILLS.replace(
    "- {timestamp} — H-{NN} — verifier verdict: confirm / kill",
    "- {timestamp} — H-{NN} — verifier verdict: confirm / kill\n"
    "- 2026-07-28 — H-01 — verdict: kill — cold-verify falsifier file:line",
)

# ── Checks ────────────────────────────────────────────────────────────────
check("1 pristine template → real_kill_count < threshold (scaffold not counted)",
      g._real_kill_count(PRISTINE) < g.EXHAUSTION_KILL_MIN,
      "got %d" % g._real_kill_count(PRISTINE))
check("1 pristine template → exhaustion_shape False (false fire killed)", not shape(PRISTINE))

check("2 six REAL kills → real_kill_count >= threshold",
      g._real_kill_count(SIX_REAL_KILLS) >= g.EXHAUSTION_KILL_MIN,
      "got %d" % g._real_kill_count(SIX_REAL_KILLS))
check("2 six kills + empty Verifier Log → exhaustion_shape True (true-positive intact)",
      shape(SIX_REAL_KILLS))

check("3 six kills, but Verifier Log is FILLED → exhaustion_shape False (verification present)",
      not shape(SIX_KILLS_LOGGED))

# anti-regression: t4_claimed_but_unlogged also relies on _real_kill_count — pristine must not give >=3
check("4 pristine → _real_kill_count < 3 (t4-integrity gate does not trigger on a template)",
      g._real_kill_count(PRISTINE) < 3)

print("=== OBS-17 EXHAUSTION-SHAPE REPLAY (template-blindness fix) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
