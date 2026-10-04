# Prompt: Hypothesis Triage

After asymmetry_scanner / comment_miner / audit_trail_miner / spec_miner / threat_models/apply.py have all emitted hypotheses — this is a **raw feed**. Without a filter — a wall of noise, and time goes to claims refuted by a quick read.

This prompt is a required step before J1/J2. Skipping it = losing hours on dead ends.

---

## Input

Files to read:
- `sessions/$TARGET/[deep/]hypothesis_candidates.md` — main aggregation
- `sessions/$TARGET/[deep/]threat_model_hypotheses.md` — threat_model instantiations
- `sessions/$TARGET/[deep/]spec_delta.md` (if present — spec_miner output)
- All output JSON from hypothesis scripts

## Task

For **each** hypothesis in the input — assign exactly one tag:

| Tag | When |
|---|---|
| `REFUTED` | Can be refuted within ≤5 minutes of reading the relevant code. State the **file:line where the defense is present**. |
| `PLAUSIBLE` | Not refuted instantly, but requires non-trivial reasoning or a PoC to confirm. Default state. |
| `INTERESTING` | High payout × probability. Worth a sprint. |
| `NEEDS_DEEP` | Requires Foundry test / fork PoC / symbolic execution — cannot be settled by reading. → escalate to J2/J5. |

## Output format

For each hypothesis:

```markdown
### H<N>: <one-line>
- **Tag**: REFUTED | PLAUSIBLE | INTERESTING | NEEDS_DEEP
- **Reasoning**:
  - If REFUTED: give the file:line where the defense is, quote the guard
  - If PLAUSIBLE: what is needed to confirm (effort estimate)
  - If INTERESTING: payout estimate + why high-confidence
  - If NEEDS_DEEP: which tool/method (forge invariant / halmos / mainnet fork PoC)
- **Severity if confirmed**: Low / Med / High / Critical
- **Effort to verify**: trivial / 30min / 2h / 1d
```

After all hypotheses — summary table:

```markdown
| Status | Count |
|---|---|
| REFUTED | N |
| PLAUSIBLE | N |
| INTERESTING | N |
| NEEDS_DEEP | N |
```

And **next steps**:
- INTERESTING + NEEDS_DEEP go to J1 (invariant discovery) / J2 (invariant break)
- PLAUSIBLE — second-pass review if time permits
- REFUTED — drop, but keep in `sessions/$TARGET/refuted_hypotheses.md` (for learning loop)

---

## Anti-patterns

**Don't** tag everything PLAUSIBLE "just in case". This defeats the purpose. Be decisive.

**Don't** REFUTE without citing the exact file:line of the defense. "Looks defended" — not enough.

**Don't** mark INTERESTING without a severity argument with numbers. "Cool finding" — no, "$X drainable in Y scenario" — yes.

**Bias correction**: tools often emit fake-confident output. If an auto-generator says "asymmetry between A and B = bug" — verify it is not intended (overload, different access pattern, etc.). Often the asymmetry is a design choice, not a bug.

---

## Hypothesis context to triage:

(paste hypothesis_candidates.md + threat_model_hypotheses.md + spec_delta.md content below)
