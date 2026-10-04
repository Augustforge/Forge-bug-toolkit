# Cognitive Framework — Phase Mindset Prompts

Each phase of `/deephunt` has a specific mental model. Switching between phases = switching mindset.

This file = reference card. Print and pin if doing deep hunt.

---

## Master Question
**"What hypothesis about the protocol can I test to find what nobody has thought of?"**

If you forget all phase-specific prompts, return to this one.

---

## Phase-by-Phase Mindset

### J-2: Audit Reports Mining
**Mindset**: "What did the auditor miss? What scope was OUT?"

Sub-questions:
- Which attack classes were already known at the time of the audit (in 2022 reentrancy was known, read-only reentrancy was not)?
- What fell OUT of scope — this is the lowest-hanging fruit
- "Acknowledged informational" — often a real bug the team chose not to fix
- Auditor X has known blind spots (Trail of Bits is weaker on oracles, Hacken — on cryptographic primitives)

Output filter: every finding in audits_analysis.md must have a "Why this might still be exploitable" explanation.

---

### J-1: Deep Reconnaissance
**Mindset**: "Where is the economic infrastructure fragile?"

Sub-questions:
- Which dependencies are NEW (deployed < 30 days)? New = unverified.
- Which admin actions happened in the last 30 days — is there a pattern (e.g., emergency pauses signal a known bug)?
- TVL trajectory — growing fast = attack incentive grows
- Who is the auditor — known or unknown (unknown = higher chance bugs remain)
- What does Github say about development — many `fix critical` commits?

Mental flip: "I am NOT reading code, I am understanding **context**."

---

### J0: Hypothesis Generation
**Mindset**: "If this protocol has a bug, where would I put $1000?"

Sub-questions:
- Where does the code look most complex? (Complexity = errors)
- Where are the recent commits? (Fresh code = fewer tests)
- Which functions are "asymmetric" in modifiers?
- Where did the developer write a comment "should never" / "MUST be"?
- Which 2-3 functions do something similar but differ?

**Trick**: after 30 minutes of reading code — close the IDE and write on paper the top-3 places where you would experiment. Those are your top hypotheses.

---

### J1: Invariant Discovery
**Mindset**: "What statement does the developer consider self-evident? What happens if it is false?"

Sub-questions:
- What CAN violate the equality `totalSupply == sum(balances)`?
- What CAN violate `depositedAmount >= stakedAmount`?
- Which inequalities between state vars are assumed?
- If admin can change config — which config-state pairs can break an invariant?

**Format**: invariants must be testable. Not "system is fair" but "user balance never exceeds their deposits + earned rewards".

---

### J2: Invariant Break
**Mindset**: "What is the minimal input state that breaks the invariant?"

Sub-questions:
- Which edge inputs break it? 0, 1, 2^256-1, dust, near-max?
- Which state setups allow achieving the break? (e.g., specific paused/unpaused, specific role configurations)
- Can the tx count be reduced? (The fewer the steps — the larger the class of attackers)

Echidna found a counterexample? → Verify by hand that it is not a false positive (corpus quirks happen).
Didn't find one in 1h? → Hypothesis weak. Drop OR reformulate.

---

### J3: Specialized Analysis
**Mindset**: "How was this protocol class historically broken? Same pattern here?"

Sub-questions:
- What happened to Cream / Curve / Wormhole / KelpDAO / Euler? Does it resemble our target?
- What are the specific patterns of this class (vault → donation, AMM → TWAP, bridge → replay)?
- What came out after Hacken/ToB audits of this class — new patterns they now catch, but the protocol was audited earlier?

Use the class-specific checklist `checklists/specialized/<class>.md`.

---

### J4: Economic Model Analysis
**Mindset**: "If I put $X into an attack, is expected profit ≥ 10X?"

Sub-questions:
- `attack_cost`: gas + capital + risk-of-failure × loss-if-fail
- `expected_profit`: extractable value × probability_of_success
- Threat tier required (T1-T6)?
- Capital sourcable via flash loan? → cost ≈ gas only
- Can attack repeat? (e.g., griefing repeatable, theft one-shot)
- MEV-accessibility: does attacker need ordering control?

**Severity rule**: profit > 10× cost AND feasibility ≥ 50% → High/Critical.

---

### J5: Mainnet Fork PoC
**Mindset**: "On live mainnet, how many USD does the real exploit yield?"

Sub-questions:
- Fork at a recent block — real balances/oracle prices
- Mock-free — all addresses are real
- At the end of the test print: starting balance, ending balance, extracted USD
- If the number disagrees with J4 — what is wrong?

**Trick**: record a video of the fork PoC running — visual proof significantly strengthens the report.

---

### J6: Variant Scan + Class-of-Bug Expansion
**Mindset**: "Same bug pattern — where else does it live in this code? In forks?"

Sub-questions:
- The same modifier/pattern in other contracts of this protocol?
- What is this protocol a fork of? Are there analogous patches there?
- In adjacent protocols (same auditor / team / fork lineage) — same bug?

**Pattern**: Alchemix WstETH + SFraxETH — same bug class, 2 separate PoCs, 2× report value.

---

### J7: Past Exploit Match
**Mindset**: "This bug is of class X. What is the precedent? What did the auditors miss?"

Sub-questions:
- Match with HIGH_VALUE_PATTERNS.md?
- Match with rekt.news entries from the last year?
- Was this class known at the time of the audit of our target?
- If not — the auditor MAYBE didn't have it in their toolkit (legit miss)
- If YES — the auditor missed it, and that is a strong argument for severity

---

### J8: Class Generalization
**Mindset**: "Which 5 other protocols have the same class of bug?"

Sub-questions:
- Who uses the same auditor / fork / template?
- Who is built on the same primitive (e.g., all ERC-4626 vaults)?
- Whose deploys are fresh but similar?

If a confirmed Critical is found in the target → spawn quick mini-hunts on parallel targets.

---

### J8.5: Multi-Step Exploit Chain Build
**Mindset**: "This is Medium. Which Low can I add to get a Critical?"

Sub-questions:
- Which Low/Info findings exist in this target?
- Can Low #1 be used to enable Low #2?
- Which combination → drain or critical state break?

**Pattern**: rekt.news multi-step exploits — almost all Criticals = a composition of Lows.

---

### J9: Report Polish
**Mindset**: "Severity argument with numbers. Not subjective."

Checklist:
- [ ] `expected_profit_usd`: $X (from J4)
- [ ] `attack_cost_usd`: $Y
- [ ] `capital_required_usd`: $Z
- [ ] `mev_accessibility`: yes/no
- [ ] `lowest_threat_tier`: T1-T6
- [ ] `feasibility_score`: 0-100
- [ ] Fix recommendation with **specific code diff**
- [ ] Disclosure timeline plan
- [ ] Submission platform decision (`post_find/submission_strategist.py`)

**No subjective words**: "significant", "serious", "dangerous" → replace with numbers.

---

## Cognitive Anti-Patterns

These thoughts mean **STOP** — you're tool-driving instead of hypothesizing:

| Thought | Reality | Reframe |
|---------|---------|---------|
| "Let me run slither" | Tool first = no hypothesis | "Let me read 200 lines first" |
| "This is complex, must have bugs" | Too vague | "Where specifically would I attack?" |
| "It uses SafeMath/OZ — safe" | Trust in OZ can be a trap | "What's CUSTOM beyond standard?" |
| "Audit passed, must be ok" | Auditors miss often | "What did they OUT-scope?" |
| "Let me check all OWASP" | Generic | "What's specific to THIS protocol?" |
| "I'll fuzz everything" | No invariant = no signal | "Which invariant first?" |
| "Let me run all detectors" | Volume ≠ value | "Which 3 detectors match my hypothesis?" |

---

## Time-Boxing Rules

If you spend ≥ 50% of phase budget without output → re-evaluate:
- Wrong hypothesis? → return to J0
- Wrong tool? → switch
- Target too complex? → abort

Honest abort > sunk-cost completion.

---

## Use Case: Reset If Lost

If you find yourself confused mid-hunt:

1. Close all tool windows
2. Open `hypothesis_candidates.md` from J0
3. Read top hypothesis
4. Ask: "What ONE thing would prove or disprove this?"
5. Do that ONE thing only
6. Repeat
