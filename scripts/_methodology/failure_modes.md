# Failure Modes Log

Auto-grown by `failure_analysis.py`. Every rejected/disputed/duplicate report — entry below.

After every rejection — record reason + root_cause_class + lesson. If a pattern repeats 3+ times — `failure_analysis.py recurring` outputs a recommendation (patch threat_model / checklist / process).

## Classification taxonomy

| Code | Meaning | Lesson |
|---|---|---|
| `already-known` | The bug is already known / in an audit / in Solodit | Solodit search BEFORE submission; check past disclosure |
| `intended-behavior` | This is a feature by the protocol's design | Read project tests + docs BEFORE the hypothesis |
| `out-of-scope` | Code/asset/chain is not in the bounty scope | Check the Immunefi scope BEFORE a deep dive |
| `insufficient-PoC` | Severity claim is not proven, no working exploit | Mandatory PoC in J5 — do not submit without it |
| `not-exploitable` | Theoretical, but no actual attack path | Adversarial mindset is weaker; a spec-vs-code gap is not impact |
| `duplicate` | Already reported by another hunter | Solodit + race monitor active; submit faster |
| `severity-downgrade` | Accepted but severity is lower than claimed | Auto-fit severity calibration per platform |
| `premature-refute` | A real finding WOULD BE KILLED by a practicality/hardened/bad-EV kill without netting against the attacker profile (self-inflicted near-miss) | `profile-cleared:` net the kill against `attacker_capability_baseline.md`; corpus `false_refute_eval:` (AOE §2.1); blind_spots BS-04 |
| `unknown` | Cannot be classified | Pure manual review needed |

---

## Gradient critique format (for MISSED bugs — not just rejected reports)

When WE missed a bug that existed (post-disclosure, lost dup race, or a re-audit found it
where we didn't), `failure_analysis.py` logging isn't enough — a miss needs a *structured
critique that points at the exact file/section to patch*, so the lesson actually changes the
system. Format (adapted from ugwst-sec `audit-feedback/gradient-templates`):

```
### MISS: <bug class> on <target> (<date>)
- Signal Missed:   the concrete code signal we walked past (paste the line / `file:line`)
- Root Cause:      why we didn't flag it — wrong frame? not in our taxonomy? skipped file?
- Pattern Gap:     which taxonomy Cat / detector SHOULD have caught it but didn't (or "none exists")
- Process Gap:     which T-step / checklist let it through (T1 prioritization? T4? gap-map?)
- Edit Targets:    EXACTLY what to change, as a list:
    - methodology/hypothesis_taxonomy.md: add Cat X.Y "<name>" with signal "<regex/desc>"
    - scripts/web3/hypothesis/<scanner>.py: add signal "<key>"
    - <skill>.md phase <N>: add step "<…>"
- Validate:        the query/test that proves the patch now catches it (re-run on the vuln code)
```

Difference from the rejected-report log below: that log is for *false positives we submitted*
(reason → root_cause_class). This is for *false negatives we missed* (signal → edit-target).
Both feed `failure_analysis.py recurring` — 3+ repeats of one Pattern Gap = mandatory patch.

---

## Entries

### MISS: premature-refute (self-inflicted near-miss) — AOE corpus (2026-08-05)
- Signal Missed:   surface/hypothesis killed as "hardened / bad-EV / not-profitable" BEFORE reading the score-4/5 files or BEFORE netting against the attacker-capability profile
- Root Cause:      wrong frame — "practicality was not measured" silently became "impractical"; refute is cheap in prose, confirm requires a PoC → asymmetric premature kill
- Pattern Gap:     the class did not exist; the `false_refute_eval:` corpus was created (`regression_manifest.yaml`) + `blind_spots.md` BS-04
- Process Gap:     T2 STATE-A/GATE lets a practicality-kill through without `profile-cleared`; Mandate 0.2 second-pass — the existing safety net
- Edit Targets:
    - sessions/_methodology/blind_spots.md: BS-04 (added)
    - sessions/_methodology/regression_manifest.yaml: false_refute_eval: corpus (added; 2 confirmed — superform-abort-reversal, shapeshift-abort-reversal)
    - methodology/mythos_techniques.md: Mandate 0.10 (objective=protocol_loss, measure-don't-estimate) + Mandate 0.11 (white-hat guardrails)
    - (Task 2) profile-cleared gate: net a practicality-kill against attacker_capability_baseline.md
- Validate:        superform-abort-reversal & shapeshift-abort-reversal — both reversed → real Med/High; a `profile-cleared` requirement would have flagged the premature kill

<!-- failure_analysis.py appends here -->
