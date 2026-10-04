# Web3 / Smart Contract Vulnerability Disclosure (Immunefi V2.3 Format)

**Title:** {{vulnerability_title}}
**Project:** {{protocol_name}}
**Asset:** {{contract_address_or_repo}}
**Chain:** {{chain_name}} (chainid: {{chainid}})
**Reporter:** {{reporter_name}}
**Date:** {{report_date}}

<!-- WRITING DISCIPLINE (bullet-brevity — pashov report-formatting, [[reference_pashov_skills]] block I):
     The `file:line` ref + code snippet + PoC ARE the evidence. Prose must NOT re-narrate the code.
     - §3 Bug Description: root cause in 1-2 sentences, not a paragraph restating the snippet.
     - §4 Steps: one line each, concrete actor/value/state — no filler.
     - §6 Fix: prefer a `diff` block (- vuln / + fixed) over prose.
     A reviewer should grasp the bug from the code-ref + one sentence; everything else is support.

     🔴 AOE DISCLOSURE-STRIP (§5.5 — infohazard guard): ship ONLY the minimal on-chain bug + PoC-fact.
     Do NOT attach, paste, or summarize `sessions/{target}/actor_payoff.md` or the full multi-actor
     equilibrium recipe, and do NOT include modeled offensive links (Sybil / flood / social-eng). A ready
     multi-actor playbook is an infohazard — the team needs the single bug + fix, not the game-theory recipe. -->

---

## 1. Severity Assessment

**Proposed severity:** {{severity}} (Critical / High / Medium / Low)
**Immunefi V2.3 reference:** [Severity Classification System V2.3](https://immunefi.com/immunefi-vulnerability-severity-classification-system-v2-3/)

**Justification:**
- Funds at risk: ${{funds_at_risk}}
- Realistic max loss: ${{realistic_max_loss}} ({{loss_percent}}% of TVL)
- Attack complexity: {{attack_complexity}} (low / medium / high)
- Required preconditions: {{preconditions}}

**Severity formula applied:**
```
loss_percent = realistic_max_loss / tvl × 100
≥ 20% AND attack_complexity=low → Critical
≥ 5%  OR significant_funds_freezable → High
≥ 1%  OR temporary_loss → Medium
griefing / informational → Low
```

---

## 2. Vulnerability Classification

**Category:** {{vulnerability_category}}
*(reentrancy / access control / oracle manipulation / flash loan / signature replay / integer over-underflow / logic error / front-running / bridge replay / etc.)*

**Affected component:**
- Contract address: `{{contract_address}}`
- File: `{{file_path}}`
- Function: `{{function_name}}`
- Lines: `{{line_numbers}}`
- Proxy detected: {{proxy_type}} (implementation: {{implementation_address}})

```solidity
// Vulnerable code
{{vulnerable_code_snippet}}
```

---

## 3. Bug Description

{{technical_description_paragraph}}

The root cause is {{root_cause}}. This violates the invariant that {{violated_invariant}}, allowing an attacker to {{attacker_action}}.

---

## 4. Attack Scenario (step-by-step)

**Attacker profile:** {{attacker_profile}}
**Required capital:** {{required_capital}}
**Required preconditions:** {{required_preconditions}}

**Steps:**
1. {{step_1}}
2. {{step_2}}
3. {{step_3}}
4. {{step_4_outcome}}

**Concrete impact in $:**
- Direct funds extracted: ${{direct_loss}}
- Funds frozen: ${{frozen_loss}}
- Indirect impact (reputation / cascading): {{indirect_impact}}

---

## 5. Proof of Concept

**Foundry test:** `poc/{{finding_id}}_{{vulnerability_short}}.t.sol`

```bash
forge test --match-test testExploit_{{finding_id}} -vvv
```

```solidity
{{poc_test_code}}
```

**Output (before/after balances):**
```
Attacker before: {{attacker_before}}
Victim   before: {{victim_before}}
[exploit executed]
Attacker after : {{attacker_after}}
Victim   after : {{victim_after}}
NET PROFIT     : {{net_profit}}
```

**On-chain replay (if applicable):**
- Block number: {{block_number}}
- Transaction hash (testnet): {{tx_hash}}

---

## 6. Recommended Fix

**Immediate mitigation:**
{{immediate_mitigation}}

**Code-level fix:**

```solidity
// Before (vulnerable)
{{vulnerable_code}}

// After (fixed)
{{fixed_code}}
```

**Defense-in-depth:**
- {{defense_1}} *(e.g. add ReentrancyGuard, switch to pull-payment pattern)*
- {{defense_2}} *(e.g. use Chainlink price feeds with multiple validators)*
- {{defense_3}} *(e.g. pause function for emergency)*

---

## 7. Bounty Calculation

**Estimated reward (per Immunefi rules):**
```
reward = min(affected_funds × 10%, project_cap)
       = min(${{affected_funds}} × 0.10, ${{project_cap}})
       = ${{calculated_reward}}
```

**KYC requirement:** {{kyc_required}} (yes / no — per program rules)

---

## 8. References

- Immunefi V2.3 spec: https://immunefi.com/immunefi-vulnerability-severity-classification-system-v2-3/
- Project page: {{project_immunefi_url}}
- Similar past incident: {{related_incident_link}}
- {{additional_reference}}

---

## 9. Disclosure Timeline

| Date | Event |
|------|-------|
| {{date_discovered}} | Vulnerability identified by automated tooling ({{tools_flagged}}) |
| {{date_verified}} | Exploitability confirmed via PoC |
| {{date_reported}} | Submitted to {{program_name}} via Immunefi |
| {{date_acknowledged}} | Triaged by project team |
| {{date_fixed}} | Fix deployed |
| {{date_paid}} | Bounty paid |
| {{date_disclosed}} | Public disclosure (post-fix) |

---

*Submitted in good faith under coordinated disclosure principles per Immunefi terms. PoC provided per V2.3 mandatory requirement.*
