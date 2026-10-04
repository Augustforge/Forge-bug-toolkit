# -*- coding: utf-8 -*-
"""Replay for active_impacts_intake_paraphrased (example protocol, 2026-08-18).

Defect: `IMPACTS-TODO` is cleared by ANY filling - it does not distinguish a VERBATIM rubric from a research SUMMARY.
The hunter filled in a summary + ITSELF marked it "research-paraphrased / verify VERBATIM / research gap" (in Russian),
cleared the sentinel, ran the hunt → anchored on permanent-freeze, missed the verbatim clause
"temporary-freezing = High", re-applied the OOS carve-out to an explicit in-scope exception = frame-error from
a partial intake. feedback_program_spec_intake_enforced action-item "extend missing_impacts".

feedback_hook_must_prove_firing: we prove FIRING (self-declared marker → fire) AND protections
(clean intake / marker only in a {} template / blockquote / HUNT-EXIT / MANUAL). feedback_detector_state_
not_phrase: the key is the self-declared-incompleteness marker in FILLED content, not a generic word form."""
import importlib.util, os, sys, time, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS = os.path.join(ROOT, "sessions")
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "hooks", "hunt_completeness_gate.py")
spec = importlib.util.spec_from_file_location("gate", HOOK)
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)

SLUG = "_iitest"
SID = "ii-sid-1"
results = []
def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))

HEAD = "# _iitest — Registry\n## Loop State\n- HUNT-MODE: AUTONOMOUS\n## Active\n- **I-01** a\n- **I-02** b\n- **I-03** c\n"  # NOTE: Russian text in the fixtures below is input data for the Russian-keyword gate; kept as is (logic)
FILLED_PARAPHRASE = ("**Impacts in Scope:** Critical = theft/permanent-freeze; High = theft unclaimed-yield.\n"
                     "  Medium/Low buckets НЕ извлечены (research-дыра) — доверифай Playwright ДО сабмита.\n"
                     "**Out-of-Scope:** ⚠ формулировки research-перефразированы, ДОСЛОВНО сверить Playwright.\n")
FILLED_CLEAN = ("**Impacts in Scope:** Critical = direct theft / permanent freeze / insolvency (verbatim).\n"
                "  High = temporary-freezing (24h doubling) / theft unclaimed-yield (verbatim из программы).\n"
                "**Out-of-Scope:** governance, centralization, oracle-no-manip (verbatim снято Playwright).\n")
TEMPLATE_NOISE = ("**Impacts in Scope:** {IMPACTS-TODO — сними дословно; при research-дыре доверифай Playwright,\n"
                  "  формулировки не перефразируй, дословно сверить}\n")
BLOCKQUOTE_NOISE = ("> подсказка: если research-перефразировано — дословно сверить через Playwright.\n"
                    "**Impacts in Scope:** Critical = theft (verbatim).\n")


def write_ledger(body):
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    with open(os.path.join(d, "hypotheses.md"), "w", encoding="utf-8") as f:
        f.write(body)
    with open(os.path.join(d, ".hunt_active"), "w", encoding="utf-8") as f:
        f.write("%d\n%s" % (int(time.time()), SID))


def fires():
    return g.active_impacts_intake_paraphrased(SID) is not None


try:
    # 1) FIRE: filled intake with a self-declared marker (Russian "paraphrased / verify verbatim / research gap").
    write_ledger(HEAD + FILLED_PARAPHRASE)
    check("1 FIRE: filled intake + self-declared paraphrase marker → fire (the example-hunt class)", fires())

    # 2) SILENT: verbatim intake without a marker.
    write_ledger(HEAD + FILLED_CLEAN)
    check("2 SILENT: verbatim intake without a marker → no fire", not fires())

    # 3) SILENT: marker only in a {} template (IMPACTS-TODO placeholder) → brace-skip.
    write_ledger(HEAD + TEMPLATE_NOISE)
    check("3 SILENT: marker in a {} template → no fire (brace-skip)", not fires())

    # 4) SILENT: marker only in a blockquote hint → skip.
    write_ledger(HEAD + BLOCKQUOTE_NOISE)
    check("4 SILENT: marker in a blockquote → no fire", not fires())

    # 5) OFF: HUNT-EXIT.
    write_ledger(HEAD + FILLED_PARAPHRASE + "\nHUNT-EXIT: T4-CONFIRMED High\n")
    check("5 OFF: HUNT-EXIT → no fire", not fires())

    # 6) OFF: MANUAL.
    write_ledger(HEAD + "- **HUNT-MODE: MANUAL**\n" + FILLED_PARAPHRASE)
    check("6 OFF: MANUAL → no fire", not fires())

    # 7) REAL ledgers (read-only replay of the scan logic, no marker writes into live hunts).
    def scan(lt):
        depth = 0
        for line in lt.splitlines():
            o, c = line.count("{"), line.count("}")
            inside = depth > 0 or o > 0
            depth = max(0, depth + o - c)
            s = line.lstrip()
            if inside or s.startswith(">"):
                continue
            if g._INTAKE_PARAPHRASE_RE.search(line):
                return True
        return False
    # NOTE: we do NOT read live ledgers (active hunts, state mutates: the hunter itself closed the
    # intake-paraphrase → test flake). Synthetic VERBATIM wording of the example hunt (stable).
    VEDA_SHAPE = ("**Impacts in Scope:** Critical = theft/permanent-freeze.\n"
                  "  Medium/Low buckets НЕ извлечены (research-дыра) — доверифай Playwright ДО сабмита.\n"
                  "**Out-of-Scope:** ⚠ формулировки research-перефразированы, ДОСЛОВНО сверить Playwright.\n")
    ZX_SHAPE = "**Impacts in Scope:** Critical = theft (verbatim из программы, Playwright-снято).\n"
    check("7 REAL-SHAPE: verbatim wording of the example hunt → fire, clean 0x-form → silent (synthetic, not live)",
          scan(VEDA_SHAPE) and not scan(ZX_SHAPE), "veda-shape=%s 0x-shape=%s" % (scan(VEDA_SHAPE), scan(ZX_SHAPE)))

finally:
    d = os.path.join(SESSIONS, SLUG)
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)

print("=== IMPACTS-INTAKE-PARAPHRASED REPLAY (research summary ≠ verbatim rubric) ===\n")
ok = 0
for name, passed, detail in results:
    print(("  [PASS] " if passed else "  [FAIL] ") + name + (("  — " + detail) if detail and not passed else ""))
    ok += 1 if passed else 0
print("\n%d/%d checks green" % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
