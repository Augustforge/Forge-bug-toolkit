<!--
Immunefi submission template — mirrors the ACTUAL submission form (verified Templar Protocol, 2026-06).

FORM FLOW (5 steps):
  1. Assets and Impact   — pick the program asset + one/more in-scope impacts
  2. Severity Level      — must MATCH the impact you picked
  3. Main Report         — Title + Description (Brief/Intro · Vulnerability Details · Impact Details · References)
  4. Proof of Concept    — separate field; runnable PoC. Optional: secret Gist + PNG/JPEG attachments
  5. Wallet Address      — payout address
  6. Review              — verify Asset / Impact / Severity / Title all agree

CRITICAL RULES (learned the hard way):
- IMPACT MUST BE IN THE PROGRAM'S IN-SCOPE LIST and MATCH your severity. An out-of-scope impact = likely auto-reject.
  Read the Scope page's "Impacts in Scope" table first; severity is DERIVED from which impact you pick.
- SEVERITY CEILING = MAGNITUDE, NOT MECHANISM. If realized loss is bounded by a small parameter
  (oracle conf width, rounding, dust, fee tick) the ceiling is Medium no matter how elegant the bug.
  MEASURE the real magnitude input EARLY (on-chain values, historical data) — do not assume a convenient
  number in the PoC. An inflated Critical that triage breaks against real on-chain data = reputation damage.
- ASSET CHOICE: if the bug is systemic across registry-/factory-deployed children, pick the PARENT/registry
  asset and name the affected children in the report. Do not pick a control asset that is NOT affected.
- PoC: runnable code + steps + observed output IN the field is sufficient and required. Attachments are
  PNG/JPEG ONLY (screenshots) — code cannot be attached as a file; use the field or a secret Gist.
  A screenshot of the green test run is a cheap trust boost, not a requirement.
- "Incorrect data supplied by third-party oracles" is a COMMON out-of-scope clause. If your bug is in the
  project's OWN code (its aggregator/adapter), say so explicitly and up front to pre-empt a lazy reject.
- Reconcile DEPLOYED code vs repo HEAD before claiming — build the PoC against the deployed commit.
- KYC + PoC may be required (program-dependent). No HTML/reveals of automation; 1st person or 3rd-passive.
- Severity tiers are program-specific $ (read the Rewards section). Many programs have NO High bucket for a
  given impact class → it is effectively binary Critical-or-Medium; size the claim accordingly.
-->

# ===== STEP 1 — Assets and Impact =====
# Asset:   {{ASSET}}            (parent/registry if systemic; never a non-affected control)
# Impact:  {{IN_SCOPE_IMPACT}}  (copy the EXACT wording from the program's Impacts-in-Scope table)

# ===== STEP 2 — Severity =====
# Severity: {{SEVERITY}}        (must match the impact above; justified by measured magnitude, not mechanism)

# ===== STEP 3 — Main Report =====

## Title (keep it short, one line)
{{TITLE}}

## Description

### Brief/Intro
One concise paragraph: what the bug is and what the consequence is if exploited on mainnet. Lead with the
in-scope impact. {{BRIEF}}

### Vulnerability Details
Detailed, self-contained explanation with code references (file:path + the exact lines/fn). Make it obvious
the bug exists and that you understand it. Cover root cause, the live/deployed config (read on-chain), and
which assets/markets are affected (and any control that is NOT). If it could be mistaken for an OOS clause
(e.g. "incorrect third-party oracle data"), explicitly distinguish it as a bug in the project's own code.
{{VULN_DETAILS}}

### Impact Details
Detailed breakdown of realizable loss — MATCH the selected in-scope impact. State funds actually at risk
(on-chain figures), the attack's effect, and the realistic magnitude with the measured inputs (not a
convenient assumption). Be honest about what bounds the loss; an accurate Medium beats a disputed Critical.
{{IMPACT_DETAILS}}

### References
- {{CODE_REFS}}            (file paths + functions)
- {{DEPLOYED_COMMIT}}      (deployed code_hash / commit reconciled vs HEAD)
- {{ONCHAIN_EVIDENCE}}     (live config / balances read via RPC view calls)

# ===== STEP 4 — Proof of Concept =====
# Runnable. Add to the field directly (and optionally mirror in a secret Gist).

## Proof of Concept

### Environment
{{POC_ENV}}   (repo + DEPLOYED commit, toolchain, harness; deterministic, no external services)

### Code
```{{LANG}}
{{POC_CODE}}
```

### Run
```
{{POC_RUN_CMD}}
```

### Observed output
```
{{POC_OUTPUT}}
```

### What each PoC proves
{{POC_EXPLANATION}}

# ===== STEP 5 — Wallet Address =====
# {{PAYOUT_WALLET}}   (USDC/chain per program Rewards section)

<!--
PRE-SUBMIT CHECKLIST:
- [ ] Impact is in the program's in-scope list AND matches the chosen severity
- [ ] Severity justified by MEASURED magnitude (on-chain / historical), not an assumed PoC number
- [ ] Asset = the affected (parent) asset; control/unaffected assets named as such
- [ ] PoC runnable from the steps without project-internal knowledge; built vs DEPLOYED commit
- [ ] Funds-at-risk quantified with on-chain figures
- [ ] OOS clauses pre-empted (esp. "incorrect third-party oracle data" → it's our own code)
- [ ] WAF linter pass (0 triggers) · Voice linter pass (0 automation reveals)
- [ ] KYC ready if program requires it for payout
- [ ] Review screen: Asset / Impact / Severity / Title all agree
-->
