# Hypothesis triage — dApp edition

After running asymmetry / config drift / wildcard / display-vs-reality
detectors AND threat models, you'll have a list of candidate hypotheses.
This prompt tags each one.

## Tag categories

- **REFUTED** — verified false in <5 minutes of reading. Drop. Save why in
  `refuted_hypotheses.md` (one line each) — that's training data.
- **PLAUSIBLE** — consistent with evidence; would require <30 min more work
  to verify. Proceed to Phase 3+.
- **INTERESTING** — novel pattern, worth checking, may need 1-2 hours.
  Proceed but time-box.
- **NEEDS_DEEP** — requires `/deephunt` scope (smart contract review,
  on-chain economic modeling). Note and continue with PLAUSIBLE/INTERESTING.

## For each hypothesis, answer 6 questions

### 1. Concrete prediction

What specific file / line / config field / curl response / browser console
output would confirm this? Be specific.

- BAD: "wildcard somewhere leaks trust"
- GOOD: "`https://auth.privy.io/api/v1/apps/<id>` response JSON contains
  `allowed_domains` array including string `https://*.iftl.info`"

### 2. Falsifier

What specific observation would refute this hypothesis?

- BAD: "if it doesn't work"
- GOOD: "if `curl -I https://sfdev-v3.iftl.info/` returns either
  `X-Frame-Options: DENY` OR `Content-Security-Policy: frame-ancestors 'none'`,
  the clickjacking primitive doesn't exist"

### 3. Severity ceiling

Quantify the worst-case impact. Be specific about what assumptions you're
making about the protocol's value, user base, attack viability.

- BAD: "could be critical"
- GOOD: "High — requires user click; per HackenProof rubric, user-click + 
  significant fund loss = High. Critical reserved for no-user-action /
  private key leak."

### 4. Cost vs payout

Estimate hours to verify + write a PoC + draft a report.

- BAD: "a few hours"
- GOOD: "1h to verify both misconfigs via curl; 1h to build minimal HTML PoC;
  1h to draft 7-field HackenProof report. Total ~3h. HackenProof High
  payout median = $X. ROI positive if probability of acceptance > 30%."

### 5. Refuted-by-read (5-minute check NOW)

Before committing time to verification: spend 5 minutes reading the dApp's
own tests / docs / public audit reports to check if this hypothesis is
already known and patched.

If `git log` mentions a fix, or the audit report flagged it and "Mitigated"
is the resolution — REFUTED. Move on.

If it's a fresh angle not in any audit and not in HackenProof Hacktivity
disclosed reports for this program — proceed.

### 6. Custody pre-mortem + monetization routing (custody targets only)

If the target HOLDS third-party funds (bridge / locker / vault / escrow), ask:
"If the owner/admin key is compromised TOMORROW — what drains, and is there a
timelock / guardian / quorum-integrity barrier?"

- If a privileged actor can move user funds with NO timelock/guardian → that is a
  finding even absent a code bug. But route it correctly:
  - **Designed-trust key theft** (≥quorum keys, Gravity/Ronin style) → NOT findable;
    drop UNLESS the program explicitly pays for centralization (filter from
    `hypothesis_generation.md` anti-patterns).
  - **Unconstrained owner power over others' funds** (DxSale-style mutable lock params,
    emergency-withdraw) → often a valid **centralization / High** finding.
    Monetization routing: Immunefi & Cantina frequently accept this class; HackenProof
    is per-program (read the rubric — `[[feedback_read_scope_before_severity]]`);
    many programs explicitly EXCLUDE "centralization risk" — check scope first.

## Output format

```markdown
## H<id>: <one-line>

| Question | Answer |
|---|---|
| Concrete prediction | <file:line + observable> |
| Falsifier | <specific test that would refute> |
| Severity ceiling | <Low/Med/High/Critical + reason> |
| Cost-vs-payout | <hours + ROI> |
| Refuted-by-read | <5min check result> |
| Custody pre-mortem | <if custody target: what drains on key compromise + monetization route, else N/A> |

**Verdict**: GO / REFUTED / TOO_VAGUE / LOW_ROI / NEEDS_DEEP / DESIGNED_TRUST_OOS
```

## Phase gate

After triage, the surviving GO + NEEDS_DEEP hypotheses go into
`hypothesis_candidates.md` for Phase 3+. If 0 GO survive, abort hunt for
this target — see SKILL "When to ABORT" section.
