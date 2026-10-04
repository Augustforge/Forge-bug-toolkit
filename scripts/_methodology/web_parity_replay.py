# -*- coding: utf-8 -*-
"""§38.5 parity: a web ledger with a web model (TB-/AC-) ARMS the model detectors (not disarmed as N/A);
an explicit N/A disarms them. HUNT-EXIT releases the loop. Proves: web got the deephunt discipline."""
import os, sys, shutil, time, importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT: break
    ROOT = nxt
HOOKS = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks")
SESSIONS = os.path.join(ROOT, "bug-bounty-toolkit", "sessions")

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
gate = _load("hunt_completeness_gate", os.path.join(HOOKS, "hunt_completeness_gate.py"))

SID = "WEBPARITY-TESTSID-Z9"    # unique sid → _owned_markers isolates from real .hunt_active
SESS = os.path.join(SESSIONS, "webparitytest")
results = []
def check(n, c, d=""):
    results.append((n, bool(c), d))

# NOTE: Russian table headers below (Formula / Axis / Source / Status; Invariant / Where / Status / Rank / Resolution)
# are parser input and are kept verbatim.
MODEL_MD = (
    "## Invariants\n"
    "| ID | Ф | `check:` | Ось | Ист | `component:` | `pred:` | Статус | ep | tests | crowd | lib |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| TB-I01 | origin===exact | as valid origin | origin-trust | CSP | msgRouter | ENFORCED | ABSENT | b:1 | 0 | cold | pm |\n"
    "## Divergences\n"
    "| ID | Инв | Где | Статус | vw | pc | t0 | conv | heat | Ранг | Резолюция |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
    "| D-01 | TB-I01 | bundle:1 | ABSENT | all | 3 | yes | 2 | cold | 12 |  |\n"
)

def _write(model_line):
    os.makedirs(SESS, exist_ok=True)
    open(os.path.join(SESS, "system_model.md"), "w", encoding="utf-8").write(MODEL_MD)
    open(os.path.join(SESS, "hypotheses.md"), "w", encoding="utf-8").write(
        "## Loop State\n- Iteration #: 3\n" + model_line + "\n")
    with open(os.path.join(SESS, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID))

try:
    # MODE A — web model (MODEL line is NOT N/A): active_divergence_unresolved ARMED (D-01 open). The MODEL line below is parser input, kept verbatim in Russian.
    _write("- **MODEL (WEB):** TB всего: 1 / ABSENT: 1 / открытых D-NN: 1 / текущий: D-01")
    a = gate.active_divergence_unresolved(SID)
    check("§38.5-A web model → active_divergence_unresolved ARMED (D-01 open, not None)",
          a is not None, "got None — web disarmed as N/A (parity regression)")

    # MODE B — same ledger, but MODEL: N/A → same detector DISARMED (None), per contract.
    _write("- **MODEL:** N/A — static")
    b = gate.active_divergence_unresolved(SID)
    check("§38.5-B MODEL:N/A → active_divergence_unresolved DISARMED (None) — contract semantics",
          b is None, "got block — N/A must disarm")

    check("§38.5 PARITY: web model arms, N/A disarms (A!=None and B==None)",
          a is not None and b is None)

    check("§38.5-EXIT HUNT-EXIT High → _EXIT_RE matches (releases the loop)",
          bool(gate._EXIT_RE.search("HUNT-EXIT: T4-CONFIRMED HIGH")))
    check("§38.5-EXIT Medium token → _EXIT_RE does NOT match (Medium is banked, does not terminate)",
          not gate._EXIT_RE.search("HUNT-EXIT: T4-CONFIRMED MEDIUM"))
finally:
    shutil.rmtree(SESS, ignore_errors=True)

print("=== WEB PARITY REPLAY (§38.5) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  — " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
