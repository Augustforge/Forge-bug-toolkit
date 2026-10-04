# -*- coding: utf-8 -*-
"""Presence-lint: `.claude/commands/hunt.md` FDE Plan 5 Task 11+12 — the web2 profile of `/hunt`.

NOTE: the `/hunt` skill file this lint reads is written in Russian, so many marker strings below
(phase headers, operator phrases, prose markers) are intentionally kept in Russian -- they are
matched literally against that file. Each such constant carries an English gloss.

Task 11: `/hunt` stops being a multiplexer over 5 domains (web2/EVM/Solana/TON/proactive) and
becomes a divergence-first web2 profile:
  (11a) The **Web3 EVM** and **Solana** mode sections were cut out (their work moved to `/deephunt`) + the
        **`/deephunt`-escalation** section (it was needed only while `/hunt` itself hunted web3). RED: the **TON
        mode section is KEPT** (TON has no home skill of its own) and RED: the **Phase 2.5 "Hypothesis
        Generation" slot is KEPT** (the web3 tooling inside was cut out, the phase header/skeleton remained — Task 12
        will fill it with web2/`AC-NN`-driven generation). `chain_detect.py` remains the first step as a ROUTE
        (not a hunt) — an evm/solana verdict → a one-liner pointing to `/deephunt`.
  (11b) A new phase **`### Phase P-AM`** (Access-Trust Model First, a mirror of `Phase P-SM` from
        `/dapphunt`) was inserted BETWEEN Phase 2 (recon) and Phase 2.5 (Hypothesis Generation): namespace
        `AC-`, 6 web2 access axes, 5-status enforcement semantics (`ENFORCED-PARTIAL`/
        `SUBSTITUTED` — highest rank), 3 operators, the `system_model.md` artifact via a toolkit-rooted path.
  (11c) The `MODEL: N/A` prose was rewritten: for a normal web2 app the model is MANDATORY, `N/A` is legitimate
        only for a pure static site without auth/API. The `ACCESS-MODEL:` sentinel is NOT introduced (the
        `AC-` namespace itself switches on the gate's web mode).

Task 12: workflow reorder §20 + proactive web2-only + reference files + `_body` convention:
  (12a) Ph2.5 "Hypothesis Generation" is marked MANDATORY for web2 (not just a web3 slot) and its
        Steps 2-5 are filled with web2/`AC-NN`-driven generation (enforcement-map sweep / endpoint_scoremap
        sweep / business-logic static pass / input-sink sweep). Phases 5-6 (Active recon / Vuln scan)
        were rewritten around the authz-diff harness (`opsec_preflight` → `run_authz_matrix`/`authz_matrix.md`
        → `error_oracle`) as the CORE, nuclei/sqlmap — verification AFTER. Phase 7 (Chain analysis) carries
        a depth drive of ≥5 layers on the strongest `D-NN`. Phase 9 (Report) computes severity via
        `web_severity.py profile="web2"`. The `_body` convention (`Response.fields["_body"]`) is written explicitly
        into the live-capture instruction (Ph5).
  (12b) The proactive mode (the `## Proactive mode` section) became web2-only: Immunefi/Cantina Deep-tier +
        `web3/hotlist/*` TVL scoring + the `candidates.json` glue were removed; H1/Bugcrowd/Intigriti/
        YesWeHack/HackenProof/Standoff365 stayed.
  (12c) A new reference table `## Phase I.7` with all the web2 artifacts of Task 1-10 (authz_diff/
        error_oracle/openapi_to_acnn/business_logic/web_severity/error_recovery/
        differential_observation/opsec_preflight/humanize/payloads/invariant_library §Web2).

Proves FIRING, not a no-op: the Task-11 checks are run against `.pretask11.orig` (see above),
the Task-12 checks — against `.pretask12.orig` (the state AFTER Task 11, BEFORE Task 12) — both backups
must fail at least some of the core checks of their task. A gate that passes on BOTH files
(before and after the edit) proves nothing.

---

FDE Plan 6, Task 11 (carry) — RED: INVERSION of the Plan-5 item (11a-d): "TON mode section KEPT" is cancelled.
The operator, 2026-08-06: "take TON out of web2, into deephunt like solana". TON is a C++ node-core analyzer
(catchain/validator/crypto/tonlib), not FunC/Tact contracts — keeping it in the web2-only `/hunt`
contradicted the Plan 5 framing. Changes:
  - Check **(d)** was flipped: it used to require `TON_HEADER in text` (the TON section MUST be present), now it
    requires the **absence** of any TON marker (`TON_MENTION_MARKERS`) in hunt.md. The `scripts/ton/` engine
    (scan.sh/semgrep_ton.yaml/correlate.py/cpp_logic.md) is NOT touched — only skill dispatch moves.
  - New `lint_deephunt()` checks — a light TON pointer ("TON C++ node core → scripts/ton/") must
    appear in `.claude/commands/deephunt.md` next to EVM/Solana/Move (NOT a full J/S-phase set —
    TON hunts are rare, a full track = a Plan 7 follow-up).
  - New `lint_blind_spots()` checks — web3 discovery (proactive auto-discovery of web3 contract
    programs) is recorded as a documented gap in `sessions/_methodology/blind_spots.md` (R9: we do NOT build a
    proactive mode in deephunt — scope creep; auto-discovery = a Plan 7 target-profiling candidate).
  - FIRING is proven by the new backup `.sdd/backups/hunt.md.task11.orig` (taken BEFORE the rehoming, TON is
    still present there → (d) must FAIL on it, PASS on the current file). Separate from the Plan-5 backups
    `.pretask11.orig`/`.pretask12.orig` — that ladder concerns P-AM/authz-diff, not TON, and must
    stay green unchanged (sanity on it too, below).
"""
import os
import re
import sys

ROOT = os.getcwd()
while ROOT and not os.path.isdir(os.path.join(ROOT, "sessions")):
    nxt = os.path.dirname(ROOT)
    if nxt == ROOT:
        break
    ROOT = nxt

HUNT_MD = os.path.join(ROOT, ".claude", "commands", "hunt.md")
HUNT_MD_PRETASK11 = os.path.join(ROOT, "methodology", "plans", ".sdd",
                                  "backups", "hunt.md.pretask11.orig")
HUNT_MD_PRETASK12 = os.path.join(ROOT, "methodology", "plans", ".sdd",
                                  "backups", "hunt.md.pretask12.orig")

# -- FDE Plan 6, Task 11 (carry): TON rehoming web2->deephunt + web3-discovery documented-gap ------
DEEPHUNT_MD = os.path.join(ROOT, ".claude", "commands", "deephunt.md")
BLIND_SPOTS_MD = os.path.join(ROOT, "sessions", "_methodology", "blind_spots.md")
HUNT_MD_TASK11_PLAN6 = os.path.join(ROOT, "methodology", "plans", ".sdd",
                                     "backups", "hunt.md.task11.orig")

# web2 profile, 6 access-control axes (namespace AC-, system_model_web_template.md:169-177).
ACCESS_AXES = [
    "object-authz",
    "function-authz",
    "auth-integrity",
    "tenant-isolation",
    "input-sink",
    "business-logic",
]

# The 3 P-AM operators (§3.4, mirrors J-M / P-SM). Russian strings KEPT: matched literally in hunt.md.
OPERATOR_MARKERS = [
    "На всех ли",                       # operator 1 (Russian: "on all of them?")
    "Framework-guard или самодел",      # operator 2 (web2 wording of "canonical mechanism or home-grown")
    "pred:",                            # operator 3: pred against fact
]

# 5-status enforcement semantics — web2 specifics: ENFORCED-PARTIAL / SUBSTITUTED rank above ABSENT.
STATUS_MARKERS = ["ENFORCED-PARTIAL", "SUBSTITUTED", "IMPLICIT", "ABSENT"]

# Old web3 mode headers — they must NOT be in the current file.
# (Header text is in Russian, "mode" in the second word; KEPT: matched literally in hunt.md.)
OLD_WEB3_EVM_HEADER = "## Web3 режим:"
OLD_SOLANA_HEADER = "## Solana режим:"
OLD_ESCALATION_HEADER = "## Escalation в `/deephunt`"  # "Escalation to /deephunt"; KEPT (literal match, Russian preposition)

# Must remain.
PHASE25_HEADER_MARKER = "Фаза 2.5"  # "Phase 2.5" (Russian word for Phase); KEPT (literal match)
HYPOTHESIS_GEN_MARKER = "Hypothesis Generation"

# RED Task 11 (Plan 6 carry) — TON INVERSION: TON_HEADER used to be required PRESENT (Plan 5),
# now hunt.md must be COMPLETELY FREE of TON mentions (rehoming into the /deephunt light pointer).
TON_MENTION_MARKERS = [
    "## TON Node режим", "ton-node", "ton:core", "ton_bugs_bot", "catchain", "tonlib",
    "scripts/ton/",
]  # the first entry is "## TON Node mode" in Russian; KEPT (literal match)

# deephunt.md must carry a light TON pointer next to EVM/Solana/Move (Task 11 carry, item 2).
DEEPHUNT_TON_POINTER_MARKERS = ["scripts/ton/", "catchain", "ton-blockchain/ton", "ton_bugs_bot"]
DEEPHUNT_TON_ARG_MARKER = "ton-node"

# blind_spots.md must carry a documented gap about the homeless web3 discovery (Task 11 carry, item 3).
WEB3_DISCOVERY_GAP_MARKER = "web3-контракт-программ"  # means "web3 contract programs" (Russian genitive); KEPT (literal match)
WEB3_DISCOVERY_HOME_MARKER = "/deephunt"

# web3 tooling that MUST be cut from INSIDE the Phase 2.5 slot (header/skeleton — remains).
WEB3_TOOLING_MARKERS = [
    "asymmetry_scanner.py",
    "comment_miner.py",
    "spec_miner.py",
    "gravity_validator_hunter.py",
    "state_machine_analyzer.py",
    "bridge_detector.py",
    "aa_erc4337_classifier.py",
    "liquidity_locker_privilege_scanner.py",
    "audit_trail_miner.py",
    "scripts/web3/threat_models/apply.py",
    "scripts/web3/prompts/",
]

ROUTE_TO_DEEPHUNT = "/deephunt"
ROUTE_TO_DAPPHUNT = "/dapphunt"
DAPP_SCORE_MARKER = "detection_score >= 50"
CHAIN_DETECT_MARKER = "chain_detect.py"
CHAIN_DETECT_ROUTE_NOT_HUNT = "не хант"  # means "not a hunt" (Russian); KEPT (literal match)

SYSTEM_MODEL_PATH = "bug-bounty-toolkit/sessions/$DOMAIN/system_model.md"
# finalfix: the other two detector-coupled artifacts (active_authz_matrix_skipped reads
# dirname(ledger) = the toolkit-rooted session_dir) — the prose is forbidden from drifting to a bare "sessions/$DOMAIN".
AUTHZ_MATRIX_PATH = "bug-bounty-toolkit/sessions/$DOMAIN/authz_matrix.md"
ENDPOINT_SCOREMAP_PATH = "bug-bounty-toolkit/sessions/$DOMAIN/endpoint_scoremap.md"
BARE_DETECTOR_ARTIFACT_RE = re.compile(
    r"(?<!bug-bounty-toolkit/)sessions/\$DOMAIN/(system_model\.md|endpoint_scoremap\.md|authz_matrix\.md)"
)

FORBIDDEN_SENTINEL = "ACCESS-MODEL:"
# Three independent tokens (not a single phrase — a markdown line wrap can split a long phrase
# in the middle; each token individually lives on one line).
# Russian KEPT (literal match in hunt.md): "model is MANDATORY", "legitimate ONLY", "static site".
MODEL_NA_PROSE_MARKERS = ["модель ОБЯЗАТЕЛЬНА", "законен ТОЛЬКО", "статик-сайта"]

# -- Task 12 markers ------------------------------------------------------------------------------

# The Ph2.5 header carries an explicit "mandatory" marking (§20 12a).
PHASE25_MANDATORY_MARKER = "ОБЯЗАТЕЛЬНА для web2"  # means "MANDATORY for web2" (Russian); KEPT (literal match)

# Reference Files: the new web2 artifacts of Task 1-10 must appear somewhere in the file (12c).
REFERENCE_FILE_MARKERS = [
    "authz_diff",
    "web_severity",
    "authz_matrix.md",
    "error_oracle",
    "openapi_to_acnn",
]

# the authz-diff harness as the CORE of the Active/Vuln phases (Ph5-Ph6) — not a separate option (12a bullet 2).
AUTHZ_HARNESS_CORE_MARKERS = ["run_authz_matrix", "authz_matrix.md", "opsec_preflight"]

# The `_body` convention must be written explicitly into the live-capture instruction (12a bullet 2, cross-task
# from the Task 3 authz_diff.py docstring).
BODY_CONVENTION_MARKER = "_body"

# web_severity in the bounty/report phase (Ph8-Ph9), profile="web2" (12a bullet 4).
WEB_SEVERITY_REPORT_MARKERS = ["web_severity", 'profile="web2"']

# Proactive web2-only (12b): web3 Deep-tier scoring scripts/artifacts MUST be absent from the
# "## Proactive mode" section (PROACTIVE_SECTION_START below).
PROACTIVE_WEB3_DEEPTIER_MARKERS = [
    "immunefi_scope.py",
    "cantina_scope.py",
    "hotlist/signal_aggregator.py",
    "hotlist/daily_priority.py",
    "candidates.json",
]

# web2 sources MUST remain in the "## Proactive mode" section.
PROACTIVE_WEB2_SOURCE_MARKERS = ["hackerone", "bugcrowd", "yeswehack", "intigriti", "hackenproof",
                                  "standoff365"]

# Section header markers in the Russian hunt.md -- KEPT (literal match):
#   the proactive-mode header = "## Proactive mode"; "### <Phase> N" = "### Phase N" (Russian words).
PROACTIVE_SECTION_START = "## Проактивный режим"
PROACTIVE_SECTION_END = "## Web3 EVM"

PHASE_5_6_START = "### Фаза 5"
PHASE_5_6_END = "### Фаза 7"

PHASE_8_9_START = "### Фаза 8"
PHASE_8_9_END = "### Фаза 10"

PHASE_I7_HEADER = "## Phase I.7"


def _section(text, start_marker, end_marker=None):
    """Cuts out the text between the first occurrence of `start_marker` and the next `end_marker` (exclusive),
    or to the end of the file if `end_marker` is not given/not found after `start_marker`. A literal
    substring search (not regex)."""
    i = text.find(start_marker)
    if i == -1:
        return ""
    if end_marker:
        j = text.find(end_marker, i + len(start_marker))
        if j != -1:
            return text[i:j]
    return text[i:]


def _phase_25_section(text):
    """The text of the Phase 2.5 slot — from the header '### Phase 2.5' to the next '### Phase 3'
    (the word "Phase" is Russian in the real header and in the regexes below; KEPT)."""
    m = re.search(r"###\s*Фаза\s*2\.5\b", text)
    if not m:
        return ""
    start = m.start()
    m2 = re.search(r"###\s*Фаза\s*3\b", text[start:])
    if not m2:
        return text[start:]
    return text[start:start + m2.start()]


def lint(text):
    """Runs all presence checks over the file text. Returns a list of (name, bool, detail)."""
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    # -- 11a: cutting out the web3 mode sections + escalation ------------------------------------
    check("(a) NO old Web3-EVM mode section ('%s')" % OLD_WEB3_EVM_HEADER,
          OLD_WEB3_EVM_HEADER not in text)
    check("(b) NO old Solana mode section ('%s')" % OLD_SOLANA_HEADER,
          OLD_SOLANA_HEADER not in text)
    check("(c) NO deephunt-escalation section ('%s')" % OLD_ESCALATION_HEADER,
          OLD_ESCALATION_HEADER not in text)

    # RED Task 11 (Plan 6 carry) — INVERSION of Plan-5: the TON mode section is CUT OUT (rehomed into /deephunt).
    ton_hits = [m for m in TON_MENTION_MARKERS if m in text]
    check("(d) 🔴 NO TON mentions in hunt.md (Plan 6 Task 11 carry — rehomed into /deephunt)",
          len(ton_hits) == 0,
          ("leaked: %s" % ", ".join(ton_hits)) if ton_hits else "")

    # RED The Phase 2.5 "Hypothesis Generation" slot is KEPT (header + marker)
    phase25 = _phase_25_section(text)
    check("(e) 🔴 Phase 2.5 'Hypothesis Generation' slot kept",
          bool(phase25) and HYPOTHESIS_GEN_MARKER in phase25,
          "" if phase25 else "Phase 2.5 not found")

    # web3 tooling from INSIDE the Phase 2.5 slot is cut out (the header remained, the filling — did not)
    leaked_tools = [m for m in WEB3_TOOLING_MARKERS if m in phase25]
    check("(f) web3 tooling cut from INSIDE the Phase 2.5 slot",
          bool(phase25) and len(leaked_tools) == 0,
          ("leaked: %s" % ", ".join(leaked_tools)) if leaked_tools else "")

    # chain_detect.py remains the first step, marked as a ROUTE (not a hunt)
    check("(g) '%s' present as a route ('%s')" % (CHAIN_DETECT_MARKER, CHAIN_DETECT_ROUTE_NOT_HUNT),
          CHAIN_DETECT_MARKER in text and CHAIN_DETECT_ROUTE_NOT_HUNT in text)

    # web2 route one-liners: dapp→/dapphunt (the already existing Phase 3.5) + contract→/deephunt
    check("(h) dApp route →'%s' present (score>=50)" % ROUTE_TO_DAPPHUNT,
          ROUTE_TO_DAPPHUNT in text and DAPP_SCORE_MARKER in text)
    check("(i) contract route →'%s' present" % ROUTE_TO_DEEPHUNT,
          ROUTE_TO_DEEPHUNT in text)

    # -- 11b: Phase P-AM ---------------------------------------------------------------------------
    check("(j) '### Phase P-AM' header present", "### Phase P-AM" in text)

    p_am = _section(text, "### Phase P-AM", "### Фаза 2.5")
    missing_axes = [ax for ax in ACCESS_AXES if ax not in p_am]
    check("(k) all 6 web2 access axes listed in P-AM (%s)" % ", ".join(ACCESS_AXES),
          bool(p_am) and len(missing_axes) == 0,
          ("missing: %s" % ", ".join(missing_axes)) if missing_axes else ("P-AM not found" if not p_am else ""))

    missing_ops = [m for m in OPERATOR_MARKERS if m not in p_am]
    check("(l) 3 operators mentioned in P-AM (%s)" % ", ".join(OPERATOR_MARKERS),
          bool(p_am) and len(missing_ops) == 0,
          ("missing markers: %s" % ", ".join(missing_ops)) if missing_ops else "")

    missing_statuses = [m for m in STATUS_MARKERS if m not in p_am]
    check("(m) 5-status enforcement semantics in P-AM (%s)" % ", ".join(STATUS_MARKERS),
          bool(p_am) and len(missing_statuses) == 0,
          ("missing: %s" % ", ".join(missing_statuses)) if missing_statuses else "")

    # the system_model.md artifact via a toolkit-rooted path
    check("(n) '%s' (toolkit-rooted path) present" % SYSTEM_MODEL_PATH,
          SYSTEM_MODEL_PATH in text)

    # finalfix: authz_matrix.md / endpoint_scoremap.md — the same two detector-coupled artifacts, the same
    # risk (active_authz_matrix_skipped reads dirname(ledger) = toolkit-rooted). The prose is forbidden to carry
    # a bare "sessions/$DOMAIN/<these-three-files>" ANYWHERE in the file (we not only require that a toolkit-rooted mention
    # is present, but also that not a single bare mention of a detector-coupled artifact remains).
    check("(n2) '%s' (toolkit-rooted path) present" % AUTHZ_MATRIX_PATH,
          AUTHZ_MATRIX_PATH in text)
    check("(n3) '%s' (toolkit-rooted path) present" % ENDPOINT_SCOREMAP_PATH,
          ENDPOINT_SCOREMAP_PATH in text)
    bare_hits = sorted(set(BARE_DETECTOR_ARTIFACT_RE.findall(text)))
    check("(n4) NO bare 'sessions/$DOMAIN/<detector-coupled-artifact>' mentions (system_model.md/"
          "endpoint_scoremap.md/authz_matrix.md must be toolkit-rooted EVERYWHERE)",
          len(bare_hits) == 0,
          ("leaked bare mentions: %s" % ", ".join(bare_hits)) if bare_hits else "")

    # -- 11c: MODEL: N/A prose + forbidden sentinel -------------------------------------------------
    missing_prose = [m for m in MODEL_NA_PROSE_MARKERS if m not in text]
    check("(o) rewritten 'MODEL: N/A' prose present (%s)" % ", ".join(MODEL_NA_PROSE_MARKERS),
          len(missing_prose) == 0,
          ("missing: %s" % ", ".join(missing_prose)) if missing_prose else "")
    check("(p) forbidden sentinel '%s' absent" % FORBIDDEN_SENTINEL,
          FORBIDDEN_SENTINEL not in text)

    # -- 12a: Ph2.5 MANDATORY for web2 --------------------------------------------------------------
    check("(q) Ph2.5 marked MANDATORY for web2 ('%s')" % PHASE25_MANDATORY_MARKER,
          bool(phase25) and PHASE25_MANDATORY_MARKER in phase25,
          "" if phase25 else "Phase 2.5 not found")

    # -- 12a: authz-diff harness — the CORE of the Active/Vuln phase (Ph5-Ph6) ----------------------
    phase_5_6 = _section(text, PHASE_5_6_START, PHASE_5_6_END)
    missing_harness = [m for m in AUTHZ_HARNESS_CORE_MARKERS if m not in phase_5_6]
    check("(r) authz-diff harness as the core in Ph5-Ph6 (%s)" % ", ".join(AUTHZ_HARNESS_CORE_MARKERS),
          bool(phase_5_6) and len(missing_harness) == 0,
          ("missing: %s" % ", ".join(missing_harness)) if missing_harness else ("Ph5-Ph6 not found" if not phase_5_6 else ""))

    # -- 12a: the `_body` convention is written into the live-capture instruction ------------------
    check("(s) '%s' convention mentioned in the file" % BODY_CONVENTION_MARKER,
          BODY_CONVENTION_MARKER in text)

    # -- 12a: web_severity in the bounty/report phase (Ph8-Ph9) -------------------------------------
    phase_8_9 = _section(text, PHASE_8_9_START, PHASE_8_9_END)
    missing_sev = [m for m in WEB_SEVERITY_REPORT_MARKERS if m not in phase_8_9]
    check("(t) web_severity in Ph8-Ph9 (%s)" % ", ".join(WEB_SEVERITY_REPORT_MARKERS),
          bool(phase_8_9) and len(missing_sev) == 0,
          ("missing: %s" % ", ".join(missing_sev)) if missing_sev else ("Ph8-Ph9 not found" if not phase_8_9 else ""))

    # -- 12b: proactive web2-only --------------------------------------------------------------------
    proactive = _section(text, PROACTIVE_SECTION_START, PROACTIVE_SECTION_END)
    leaked_deeptier = [m for m in PROACTIVE_WEB3_DEEPTIER_MARKERS if m in proactive]
    check("(u) proactive does NOT contain web3 Deep-tier scoring (%s)" % ", ".join(PROACTIVE_WEB3_DEEPTIER_MARKERS),
          bool(proactive) and len(leaked_deeptier) == 0,
          ("leaked: %s" % ", ".join(leaked_deeptier)) if leaked_deeptier else ("proactive not found" if not proactive else ""))

    missing_web2_sources = [m for m in PROACTIVE_WEB2_SOURCE_MARKERS if m not in proactive.lower()]
    check("(v) proactive contains web2 sources (%s)" % ", ".join(PROACTIVE_WEB2_SOURCE_MARKERS),
          bool(proactive) and len(missing_web2_sources) == 0,
          ("missing: %s" % ", ".join(missing_web2_sources)) if missing_web2_sources else "")

    # -- 12c: Reference Files — the new web2 artifacts -----------------------------------------------
    missing_refs = [m for m in REFERENCE_FILE_MARKERS if m not in text]
    check("(w) Reference Files contains web2 artifacts (%s)" % ", ".join(REFERENCE_FILE_MARKERS),
          len(missing_refs) == 0,
          ("missing: %s" % ", ".join(missing_refs)) if missing_refs else "")
    check("(x) '%s' reference table present" % PHASE_I7_HEADER,
          PHASE_I7_HEADER in text)

    return results


def lint_deephunt(text):
    """Task 11 (Plan 6 carry): a presence lint for the TON light pointer in `.claude/commands/deephunt.md`.
    The pointer must live next to EVM/Solana/Move (the argument-routing section) AND carry a reference to the
    unchanged `scripts/ton/` engine — NOT a full J/S-phase set (a light pointer, not a duplicate of the engine)."""
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    check("(deephunt-a) TON trigger in the argument-routing section ('%s')" % DEEPHUNT_TON_ARG_MARKER,
          DEEPHUNT_TON_ARG_MARKER in text)

    missing = [m for m in DEEPHUNT_TON_POINTER_MARKERS if m not in text]
    check("(deephunt-b) TON light pointer references the scripts/ton/ engine (%s)"
          % ", ".join(DEEPHUNT_TON_POINTER_MARKERS),
          len(missing) == 0,
          ("missing: %s" % ", ".join(missing)) if missing else "")

    return results


def lint_blind_spots(text):
    """Task 11 (Plan 6 carry, item 3, R9): a presence lint — web3 discovery (proactive auto-discovery of
    web3 contract programs) is recorded as a documented gap, NOT built as code (anti-scope-creep)."""
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    check("(blindspots-a) web3-discovery-gap line present ('%s')" % WEB3_DISCOVERY_GAP_MARKER,
          WEB3_DISCOVERY_GAP_MARKER in text)
    check("(blindspots-b) home pointer to '%s' present next to the gap" % WEB3_DISCOVERY_HOME_MARKER,
          WEB3_DISCOVERY_HOME_MARKER in text)

    return results


def _read(path):
    return open(path, encoding="utf-8").read() if os.path.exists(path) else ""


def main():
    current_text = _read(HUNT_MD)
    if not current_text:
        print("[FAIL] %s not found or empty" % HUNT_MD)
        sys.exit(1)

    print("=== HUNT SKILL LINT (FDE Plan 5 Task 11+12) ===\n")

    print("-- CURRENT hunt.md (all checks must PASS) --")
    current_results = lint(current_text)
    current_ok = sum(1 for _, p, _ in current_results if p)
    for n, p, d in current_results:
        print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
    print("  %d/%d\n" % (current_ok, len(current_results)))

    pretask11_exists = os.path.exists(HUNT_MD_PRETASK11)
    firing_proved = False
    if pretask11_exists:
        pretask11_text = _read(HUNT_MD_PRETASK11)
        print("-- .sdd/backups/hunt.md.pretask11.orig (pre-Task-11, must fail at least some) --")
        pretask11_results = lint(pretask11_text)
        pretask11_ok = sum(1 for _, p, _ in pretask11_results if p)
        for n, p, d in pretask11_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
        print("  %d/%d\n" % (pretask11_ok, len(pretask11_results)))
        # FIRING is proven if the .orig fails AT LEAST ONE of the core checks 11a/11b:
        # (a)-(c) the old headers ARE present on the .orig → FAIL; (j)-(n) P-AM is absent on the .orig → FAIL.
        core_names = {"(a)", "(b)", "(c)", "(j)", "(k)", "(l)", "(m)", "(n)", "(o)"}
        core_checks = [r for r in pretask11_results if r[0].split()[0] in core_names]
        firing_proved = any(not p for _, p, _ in core_checks)
        print(("  [PASS] " if firing_proved else "  [FAIL] ")
              + "Task-11 FIRING proven: .pretask11.orig fails at least one core check\n")
    else:
        print("  [FAIL] backup %s not found — Task-11 FIRING not proven\n" % HUNT_MD_PRETASK11)

    pretask12_exists = os.path.exists(HUNT_MD_PRETASK12)
    firing_proved_12 = False
    if pretask12_exists:
        pretask12_text = _read(HUNT_MD_PRETASK12)
        print("-- .sdd/backups/hunt.md.pretask12.orig (pre-Task-12, must fail at least some) --")
        pretask12_results = lint(pretask12_text)
        pretask12_ok = sum(1 for _, p, _ in pretask12_results if p)
        for n, p, d in pretask12_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
        print("  %d/%d\n" % (pretask12_ok, len(pretask12_results)))
        # FIRING is proven if the .orig (Task-11-complete, Task-12-empty) fails AT LEAST ONE
        # of the core checks 12a/12b/12c: (q) Ph2.5 not marked mandatory / (r) the authz-diff harness
        # is not yet the core of Ph5-Ph6 / (s) the `_body` convention is not written in / (t) web_severity is not in Ph8-Ph9 /
        # (u) proactive still carries web3 Deep-tier / (w) Reference Files does not yet contain the web2 artifacts /
        # (x) the Phase I.7 table does not exist yet.
        core_names_12 = {"(q)", "(r)", "(s)", "(t)", "(u)", "(w)", "(x)"}
        core_checks_12 = [r for r in pretask12_results if r[0].split()[0] in core_names_12]
        firing_proved_12 = any(not p for _, p, _ in core_checks_12)
        print(("  [PASS] " if firing_proved_12 else "  [FAIL] ")
              + "Task-12 FIRING proven: .pretask12.orig fails at least one core check\n")
        # Sanity: the Task-11 core checks MUST stay green on pretask12.orig (Task 11 had already been
        # applied to this file before Task 12) — if they fail here, it is a Task-11 regression, not Task-12.
        core_names_11 = {"(a)", "(b)", "(c)", "(j)", "(k)", "(l)", "(m)", "(n)", "(o)"}
        core_checks_11_on_12 = [r for r in pretask12_results if r[0].split()[0] in core_names_11]
        task11_intact_on_pretask12 = all(p for _, p, _ in core_checks_11_on_12)
        print(("  [PASS] " if task11_intact_on_pretask12 else "  [FAIL] ")
              + "Task-11 core checks intact on .pretask12.orig (not a Task-11 regression)\n")
    else:
        print("  [FAIL] backup %s not found — Task-12 FIRING not proven\n" % HUNT_MD_PRETASK12)
        task11_intact_on_pretask12 = False

    all_current_pass = current_ok == len(current_results)
    overall_ok = (all_current_pass and pretask11_exists and firing_proved
                  and pretask12_exists and firing_proved_12 and task11_intact_on_pretask12)

    # === Task 11 (FDE Plan 6, carry): TON rehoming web2->deephunt + web3-discovery documented-gap ===
    print("=== TASK 11 (FDE Plan 6 carry): TON rehoming + web3-discovery gap ===\n")

    deephunt_text = _read(DEEPHUNT_MD)
    print("-- CURRENT deephunt.md (the TON light pointer must PASS) --")
    if not deephunt_text:
        print("  [FAIL] %s not found or empty\n" % DEEPHUNT_MD)
        deephunt_ok_all = False
    else:
        deephunt_results = lint_deephunt(deephunt_text)
        deephunt_ok = sum(1 for _, p, _ in deephunt_results if p)
        for n, p, d in deephunt_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
        print("  %d/%d\n" % (deephunt_ok, len(deephunt_results)))
        deephunt_ok_all = deephunt_ok == len(deephunt_results)

    blind_spots_text = _read(BLIND_SPOTS_MD)
    print("-- CURRENT blind_spots.md (the web3-discovery gap must PASS) --")
    if not blind_spots_text:
        print("  [FAIL] %s not found or empty\n" % BLIND_SPOTS_MD)
        blind_spots_ok_all = False
    else:
        blind_spots_results = lint_blind_spots(blind_spots_text)
        blind_spots_ok = sum(1 for _, p, _ in blind_spots_results if p)
        for n, p, d in blind_spots_results:
            print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
        print("  %d/%d\n" % (blind_spots_ok, len(blind_spots_results)))
        blind_spots_ok_all = blind_spots_ok == len(blind_spots_results)

    # FIRING proof: hunt.md.task11.orig (taken BEFORE the rehoming — TON is still present) must FAIL
    # check (d); the current hunt.md (after the cut-out) must PASS it. A gate that is green on both
    # states proves nothing (see the docstring).
    task11_plan6_backup_exists = os.path.exists(HUNT_MD_TASK11_PLAN6)
    firing_proved_task11_plan6 = False
    if task11_plan6_backup_exists:
        task11_plan6_backup_text = _read(HUNT_MD_TASK11_PLAN6)
        print("-- .sdd/backups/hunt.md.task11.orig (pre-rehoming, TON still present) --")
        task11_plan6_backup_results = lint(task11_plan6_backup_text)
        for n, p, d in task11_plan6_backup_results:
            if n.startswith("(d)"):
                print(("  [PASS] " if p else "  [FAIL] ") + n + ((" -- " + d) if d else ""))
                firing_proved_task11_plan6 = not p  # the backup MUST fail (d) — TON is there
        print(("  [PASS] " if firing_proved_task11_plan6 else "  [FAIL] ")
              + "Task-11 (Plan 6) FIRING proven: .task11.orig fails (d) TON-absence\n")
    else:
        print("  [FAIL] backup %s not found — Task-11 (Plan 6) FIRING not proven\n" % HUNT_MD_TASK11_PLAN6)

    current_check_d_pass = next((p for n, p, _ in current_results if n.startswith("(d)")), False)
    print(("  [PASS] " if current_check_d_pass else "  [FAIL] ")
          + "Current hunt.md passes (d) TON-absence (TON really cut out)\n")

    task11_plan6_ok = (task11_plan6_backup_exists and firing_proved_task11_plan6
                        and current_check_d_pass and deephunt_ok_all and blind_spots_ok_all)

    print("=== TASK 11 SUMMARY (Plan 6 carry): %s ===\n" % ("PASS" if task11_plan6_ok else "FAIL"))

    overall_ok = overall_ok and task11_plan6_ok

    print("=== SUMMARY: %s ===" % ("PASS" if overall_ok else "FAIL"))
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
