# -*- coding: utf-8 -*-
"""FORK-DIFF gate replay (confession 2026-08-09). Proves active_fork_diff_unrun:
(1) FIRE -- mature model + PARENT-FORK identified + executable diff NOT run -> block;
(2) SILENT -- not a fork / Fork-diff DONE (field) / fork_diff file in session / no field / placeholder /
    immature model / MODEL: N/A;
(3) Part 3 -- diff DONE, but claim >=5 with a NON-executable observed -> block; with a forge log -> silent;
(4) Part 2 -- [ASSUMED-CANONICAL] is counted in _real_kill_count (exhaustion-shape).
proof-of-firing: the test must SHOW firing (case1/case9), not just silence. The real
sessions/ are untouched (unique slug `_forktest_*`, cleanup in finally).

NOTE on kept Russian: a few fixture strings are inputs to the gate's Russian-aware regexes (the Russian
"byte-for-byte" fork-declaration phrasing, the Russian "forge log" exec marker, the template placeholder text) and
one assertion compares against a Russian substring of the gate's message ("executable-<Russian: artifact>");
these are kept verbatim and marked "KEPT RU" at their lines."""
import os, sys, time, shutil, importlib.util

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "bug-bounty-toolkit", "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT: break
    ROOT = nxt
MODPATH = os.path.join(ROOT, "bug-bounty-toolkit", "scripts", "hooks", "hunt_completeness_gate.py")
SESSIONS = os.path.join(ROOT, "bug-bounty-toolkit", "sessions")

spec = importlib.util.spec_from_file_location("hcg", MODPATH)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

results = []
def check(n, c, d=""):
    results.append((n, bool(c), d))

# mature model: 3 bullet I-NN with pred: -> _i_matured_count >= 3
MATURE_MODEL = (
    "# system_model.md\n\n## Invariants\n"
    "- **I-01** [state] check: supply conserved pred: ENFORCED\n"
    "- **I-02** [state] check: exchange-rate monotonic pred: ENFORCED-PARTIAL\n"
    "- **I-03** [state] check: interest accrual pred: ABSENT\n"
)
IMMATURE_MODEL = "# system_model.md\n\n## Invariants\n- **I-01** [state] check: x\n"

LOOP_BASE = ("## Loop State\n- **Iteration #:** 4\n- **Exit:** T4 High/Crit only.\n"
             "- **Depth-Lead:** none yet\n")

def write_sess(slug, ledger, model=MATURE_MODEL, files=()):
    d = os.path.join(SESSIONS, slug)
    if os.path.exists(d): shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(ledger)
    if model is not None:
        with open(os.path.join(d, "system_model.md"), "w", encoding="utf-8") as f:
            f.write(model)
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), slug))
    for fn in files:
        p = os.path.join(d, fn)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("fork diff artifact")
    return d

made = []
def run(slug, ledger, model=MATURE_MODEL, files=()):
    made.append(os.path.join(SESSIONS, slug))
    write_sess(slug, ledger, model, files)
    return mod.active_fork_diff_unrun(slug)

try:
    PF = "- **PARENT-FORK:** Compound v2 — Comptroller/CToken fingerprints\n"
    PF_NA = "- **PARENT-FORK:** N/A — not a fork\n"
    PF_PLACE = "- **PARENT-FORK:** {identify the parent}\n"

    # 1) FIRE -- parent identified, no Fork-diff
    r = run("_forktest_fire", LOOP_BASE + PF)
    check("1 FIRE: PARENT-FORK identified + no Fork-diff → block", r and "executable differential" in r, repr(r))

    # 2) SILENT -- PARENT-FORK: N/A — not a fork
    r = run("_forktest_na", LOOP_BASE + PF_NA)
    check("2 SILENT: PARENT-FORK N/A — not a fork", r is None, repr(r))

    # 3) SILENT -- Fork-diff: DONE — <exec artifact> (field)
    r = run("_forktest_donefield", LOOP_BASE + PF + "- **Fork-diff:** DONE — deep/fork_diff.md family_fork_diff\n")
    check("3 SILENT: Fork-diff DONE field with an exec reference", r is None, repr(r))

    # 3b) FIRE -- Fork-diff DONE, but WITHOUT an exec reference (just 'DONE') -> does not count
    r = run("_forktest_donebare", LOOP_BASE + PF + "- **Fork-diff:** DONE\n")
    check("3b FIRE: Fork-diff 'DONE' without an exec artifact does not clear it", r and "differential" in r, repr(r))

    # 4) SILENT -- fork_diff file in the session dir
    r = run("_forktest_donefile", LOOP_BASE + PF, files=("fork_diff.md",))
    check("4 SILENT: fork_diff.md file in session", r is None, repr(r))
    # 4b) SILENT -- fork_diff in deep/
    r = run("_forktest_donefiledeep", LOOP_BASE + PF, files=("deep/fork_diff_compound.json",))
    check("4b SILENT: fork_diff in deep/", r is None, repr(r))

    # 5) SILENT -- no PARENT-FORK field at all (old/non-canonical ledger)
    r = run("_forktest_nofield", LOOP_BASE)
    check("5 SILENT: no PARENT-FORK field", r is None, repr(r))

    # 6) SILENT -- placeholder {...}
    r = run("_forktest_place", LOOP_BASE + PF_PLACE)
    check("6 SILENT: PARENT-FORK placeholder {..}", r is None, repr(r))

    # 7) SILENT -- immature model (<3 matured I-NN)
    r = run("_forktest_immature", LOOP_BASE + PF, model=IMMATURE_MODEL)
    check("7 SILENT: immature model", r is None, repr(r))

    # 8) SILENT -- MODEL: N/A in the ledger
    r = run("_forktest_modelna", "## Loop State\n- **MODEL: N/A — small single contract**\n" + PF)
    check("8 SILENT: MODEL N/A clears it", r is None, repr(r))

    # 9) Part 3 FIRE -- diff DONE, claim >=5, DEPTH-TRACE with a STATIC observed (no exec keyword)
    # KEPT RU: the boundary text "спека->реализация" ("spec->implementation") is fixture input.
    trace_static = (
        "- **Depth-Lead:** H-03 — 5/5 (call->state->external->hook->accounting)\n"
        "- **DEPTH-TRACE (T12):**\n"
        "```\nL5 boundary: спека->реализация\n   predicted: interest matches Compound\n"
        "   observed: matches Comptroller.sol:120 canonical\n   fan-in: index <- accrue :90\n```\n")
    r = run("_forktest_part3fire", LOOP_BASE + PF + "- **Fork-diff:** DONE — deep/fork_diff.md\n" + trace_static)
    # KEPT RU: "executable-артефакт" is a substring of the gate's Russian message ("executable artifact").
    check("9 Part3 FIRE: claim>=5 + static observed (no exec) → block", r and "executable-артефакт" in r, repr(r))

    # 10) Part 3 SILENT -- the same, but observed with a forge log (executable)
    # KEPT RU: "статика->рантайм" ("static->runtime") and "forge-лог" ("forge log") are fixture input
    # (the exec-keyword regex may match the Russian "forge-log" token).
    trace_exec = (
        "- **Depth-Lead:** H-03 — 5/5 (call->state->external->hook->accounting)\n"
        "- **DEPTH-TRACE (T12):**\n"
        "```\nL5 boundary: статика->рантайм\n   predicted: redeem returns 99\n"
        "   observed: revert  <- forge-лог fork_diff.log строка 214\n   fan-in: fees <- redeem :179\n```\n")
    r = run("_forktest_part3silent", LOOP_BASE + PF + "- **Fork-diff:** DONE — deep/fork_diff.md\n" + trace_exec)
    check("10 Part3 SILENT: observed with a forge log (executable)", r is None, repr(r))

    # 11) Part 2 -- [ASSUMED-CANONICAL] is counted as a soft-kill (exhaustion-shape counter)
    kills = "\n".join("- H-%02d [ASSUMED-CANONICAL] matches Compound" % i for i in range(1, 7))
    cnt = mod._real_kill_count(LOOP_BASE + kills)
    check("11 Part2: 6×[ASSUMED-CANONICAL] counted in _real_kill_count (>=6)", cnt >= 6, "cnt=%r" % cnt)

    # 12) template<->detector: the REAL template carries the PARENT-FORK/Fork-diff fields, and the regexes match them.
    # Otherwise, on template drift (field renamed/removed) the gate silently becomes orphaned (the LEDGER-LIVE lesson).
    tpl = os.path.join(SESSIONS, "_methodology", "hypotheses_template.md")
    with open(tpl, "r", encoding="utf-8") as f:
        tpl_txt = f.read()
    check("12 template carries the PARENT-FORK field, regex matches", bool(mod._PARENT_FORK_RE.search(tpl_txt)))
    check("12 template carries the Fork-diff field, regex matches", bool(mod._FORK_DIFF_FIELD_RE.search(tpl_txt)))
    # an untouched template (values in `{...}`) must NOT arm the gate: PARENT-FORK placeholder -> off.
    pf_val = mod._PARENT_FORK_RE.search(tpl_txt).group(1)
    check("12 PARENT-FORK value in the template = placeholder {..} (the gate is silent on an untouched one)",
          "{" in pf_val, repr(pf_val[:40]))

    # 13) _status_of fix (a prior audit): a compact 6-column I-NN table (status in col4, not idx7)
    # -> _i_matured_count counts it as mature. Without the fix = 0 (the whole maturity cluster is blind). proof-of-firing.
    COMPACT = ("# system_model.md\n\n## Invariants\n"
               "| I-01 | S-LS | sAVAX exch rate monotonic non-decreasing | StakedAvax submit | ENFORCED | economic |\n"
               "| I-02 | S-ORA | qisAVAX price from exch rate not spot | DualOracle | ENFORCED-PARTIAL | economic |\n"
               "| I-03 | S-CORE | getAccountLiquidity each market once | Comptroller | ENFORCED | state |\n")
    check("13 _status_of fix: compact 6-col table → matured>=3 (was 0)",
          mod._i_matured_count(COMPACT) >= 3, "matured=%r" % mod._i_matured_count(COMPACT))
    # anti-FP: a long formula containing the word ENFORCED does NOT count as a status (whole-cell membership)
    NOSTAT = ("# system_model.md\n\n## Invariants\n"
              "| I-01 | S-X | this invariant is ENFORCED somewhere in prose but no status cell | comp | economic |\n")
    check("13b anti-FP: a formula with the word ENFORCED but without a status cell → not mature",
          mod._i_matured_count(NOSTAT) == 0, "matured=%r" % mod._i_matured_count(NOSTAT))

    # 14) fork_undeclared FIRE -- the ledger itself declares a parent fork, the PARENT-FORK field is empty
    # KEPT RU: "байт-в-байт" ("byte-for-byte") is the fork-declaration phrasing matched by the gate.
    FORKDECL = LOOP_BASE + "- outcome:clean proof: liquidateBorrowAllowed = байт-в-байт canonical Compound V2\n"
    r = run("_forktest_undecl", FORKDECL)
    check("14 fork_undeclared FIRE: the ledger declares canonical Compound, no field → 'compound'",
          mod.active_fork_undeclared("_forktest_undecl") == "compound", repr(mod.active_fork_undeclared("_forktest_undecl")))

    # 15) SILENT -- the PARENT-FORK field is already filled (the fork-diff gate rules, the nudge is silent)
    r = run("_forktest_undecl_declared", FORKDECL + PF)
    check("15 fork_undeclared SILENT: PARENT-FORK filled", mod.active_fork_undeclared("_forktest_undecl_declared") is None)

    # 16) SILENT -- no fork declaration
    r = run("_forktest_undecl_none", LOOP_BASE + "- outcome:clean proof: custom AMM invariant holds\n")
    check("16 fork_undeclared SILENT: no fork declaration", mod.active_fork_undeclared("_forktest_undecl_none") is None)

    # 17) FP-guard (a prior audit, 2026-08-09): target slug in _FORK_PARENTS ('balancer') + a scope line
    # "Balancer DAO ... Fork-PoC accepted" + a template PARENT-FORK placeholder with the example "Compound v2" ->
    # must NOT false-fire (a protocol is not a fork of itself; the placeholder block is cut out). The folder slug = 'balancer'.
    # KEPT RU: the placeholder text inside {...} below mirrors the real template (Russian "e.g."/"= not filled"/"= not run").
    FP_LEDGER = (LOOP_BASE
        + "**Platform:** Immunefi (Balancer DAO). Fork-PoC accepted (Immunefi).\n"
        + "- **PARENT-FORK:** {FORK-DIFF gate. напр. `Compound v2 — Comptroller`. `{...}` = не заполнено.}\n"
        + "- **Fork-diff:** {family_fork_diff Compound-vs-target. `{...}` = не прогнан.}\n"
        + "- **Code:** CompoundV2Wrapping:49 — balancer adapter\n")
    r = run("_forktest_balancer", FP_LEDGER)  # the slug contains 'balancer' in _FORK_PARENTS (we do not touch a real session)
    check("17 FP-guard: slug~'balancer'+scope+placeholder → SILENT (not a fork of itself)",
          mod.active_fork_undeclared("_forktest_balancer") is None, repr(mod.active_fork_undeclared("_forktest_balancer")))

    # 18) do NOT over-correct: slug~'balancer', but a REAL fork declaration of ANOTHER parent in a kill -> FIRES
    # KEPT RU: "байт-в-байт" ("byte-for-byte") is the fork-declaration phrasing matched by the gate.
    r = run("_forktest_balancer2", LOOP_BASE + "- outcome:clean proof: pool math = байт-в-байт canonical Curve stableswap\n")
    check("18 not over-corrected: balancer forks Curve (a real declaration) → FIRES 'curve'",
          mod.active_fork_undeclared("_forktest_balancer2") == "curve", repr(mod.active_fork_undeclared("_forktest_balancer2")))

    # ── SUD-HIGH-2 + R3 (live Solana-fork hunt 2026-08-12): _FORK_PARENTS was EVM-only -> fork enforcement was DARK on
    # Solana/Cosmos/Move forks. The target = a fork of agave/solana-labs + a firedancer-fork.
    # 19) Solana: the ledger declares a "firedancer-fork BAM" + PARENT-FORK empty -> FIRE 'firedancer' (was SILENT).
    # KEPT RU: "C++ канонический путь" ("canonical path") is fork-declaration phrasing matched by the gate.
    r = run("_forktest_fdbam",
            LOOP_BASE + "- outcome:clean proof: firebam = firedancer-fork BAM scheduler, C++ канонический путь\n")
    check("19 R3-Solana FIRE: firedancer-fork declaration → 'firedancer'",
          mod.active_fork_undeclared("_forktest_fdbam") == "firedancer",
          repr(mod.active_fork_undeclared("_forktest_fdbam")))
    # 20) Solana: "a solana fork canonical Agave" -> FIRE (agave parent).
    # KEPT RU: "байт-в-байт" ("byte-for-byte") is the fork-declaration phrasing matched by the gate.
    r = run("_forktest_avval",
            LOOP_BASE + "- outcome:clean proof: bundle-путь байт-в-байт canonical Agave validator\n")
    check("20 R3-Solana FIRE: agave-fork declaration → 'agave'",
          mod.active_fork_undeclared("_forktest_avval") == "agave",
          repr(mod.active_fork_undeclared("_forktest_avval")))
    # 21) Cosmos: "based on cosmos-sdk" -> FIRE.
    r = run("_forktest_cosmos",
            LOOP_BASE + "- outcome:clean proof: staking module based on cosmos-sdk canonical x/staking\n")
    check("21 R3-Cosmos FIRE: cosmos-sdk-fork declaration → 'cosmos-sdk'",
          mod.active_fork_undeclared("_forktest_cosmos") == "cosmos-sdk",
          repr(mod.active_fork_undeclared("_forktest_cosmos")))
    # 22) FP-guard: a bare 'solana program' WITHOUT fork framing -> SILENT (chain name != fork declaration).
    # KEPT RU: the tail "свой Anchor invariant, не форк" ("own Anchor invariant, not a fork") is fixture input.
    r = run("_forktest_sol_plain",
            LOOP_BASE + "- outcome:clean proof: custom solana program, свой Anchor invariant, не форк\n")
    check("22 R3 FP-guard: 'solana program' without fork framing → SILENT",
          mod.active_fork_undeclared("_forktest_sol_plain") is None,
          repr(mod.active_fork_undeclared("_forktest_sol_plain")))
    # 23) SILENT: a Solana fork is declared, but PARENT-FORK is filled -> the nudge is silent (off-switch preserved).
    r = run("_forktest_fdbam_decl",
            LOOP_BASE + "- outcome:clean proof: firedancer-fork BAM\n- **PARENT-FORK:** Agave v2.0 — validator fingerprints\n")
    check("23 R3 SILENT: firedancer fork + PARENT-FORK filled → the nudge is silent",
          mod.active_fork_undeclared("_forktest_fdbam_decl") is None,
          repr(mod.active_fork_undeclared("_forktest_fdbam_decl")))
    # 24) Solana fork + PARENT-FORK filled, no Fork-diff -> the fork-diff gate holds (Solana invariant-test
    # escape: trident/simnet in _EXEC_ARTIFACT_RE -- no deadlock, the H-exec task will extend this).
    r = run("_forktest_agave_diffunrun",
            LOOP_BASE + "- **PARENT-FORK:** Agave v2.0 — validator fingerprints\n")
    check("24 R3 fork-diff holds a Solana fork without a diff (the trident/N/A escape exists)",
          r and "executable differential" in r, repr(r))
    # 25) SILENT: a Solana fork-diff DONE via a trident invariant test -> cleared (escape for non-EVM).
    r = run("_forktest_agave_trident",
            LOOP_BASE + "- **PARENT-FORK:** Agave v2.0 — validator fingerprints\n"
            + "- **Fork-diff:** DONE — deep/trident_invariant.log trident fuzz on solana-test-validator\n")
    check("25 R3 SILENT: Solana Fork-diff DONE via a trident log (non-EVM escape)", r is None, repr(r))
    # 26) H-exec/R8: a Cosmos/Move fork-diff via a simnet/invariant test -> cleared (family_fork_diff is EVM-only,
    # we do not block exit on something that does not exist -- an escape for every ecosystem).
    r = run("_forktest_cosmos_simnet",
            LOOP_BASE + "- **PARENT-FORK:** cosmos-sdk v0.47 — x/staking fingerprints\n"
            + "- **Fork-diff:** DONE — deep/simnet_invariant.log simnet differential vs cosmos-sdk\n")
    check("26 H-exec/R8 SILENT: Cosmos Fork-diff DONE via a simnet log (non-EVM escape)", r is None, repr(r))

finally:
    for d in made:
        shutil.rmtree(d, ignore_errors=True)

print("=== FORK-DIFF GATE REPLAY (confession 2026-08-09) ===")
ok = sum(1 for _, p, _ in results if p)
for n, p, d in results:
    print(("  [PASS] " if p else "  [FAIL] ") + n + (("  -- " + d) if d and not p else ""))
print("\n%d/%d green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
