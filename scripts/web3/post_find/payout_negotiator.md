# Payout Negotiator — Templates

Use when triager assigns lower severity than you believe is warranted.

---

## Principle

Don't argue. Demonstrate. Numbers > adjectives.

If triager says "Low — minor info leak", and you computed J4 analysis showing $50k extractable + T3-accessible — show the numbers. They'll re-grade.

---

## Template 1: Severity Disagreement (Polite Push)

```
Hi [Triager],

Thanks for the assessment. I'd like to provide additional context that may affect severity classification.

Per Immunefi/HackerOne severity scale:
- I argued: [Original severity]
- Triage marked: [Their severity]

My reasoning (with numbers):
- Extractable value: $X (computed via fork PoC, see report)
- Attack cost: $Y (gas + capital + risk-adjusted)
- ROI: Z×
- Threat tier required: T[N] — [explanation of who can execute]
- Affected funds: $W (TVL × % at risk)

Class-of-impact:
- This pattern was rated [Critical/High] by [other reputable program] in past finding [link if public]
- Or: this falls under Immunefi's bug taxonomy section [X.Y] which is [severity]

I'd like to respectfully request reconsideration. If new info needed for re-assessment, happy to provide.

Thanks for your time.
```

---

## Template 2: Disputing "Already Known"

```
Hi [Triager],

You marked this as "duplicate of prior report." Could you share:
1. Date of prior report
2. Whether the report covered the SAME root cause vs same symptom
3. Whether the prior fix actually addresses what I demonstrated

My finding is specifically [X] — root cause is [Y]. If the prior report only covered [Z symptom], and my PoC shows the root cause still extractable, this is a separate finding.

Happy to provide additional differentiation evidence.
```

---

## Template 3: Disputing "Out of Scope"

```
Hi [Triager],

The finding was marked out of scope. Reviewing the program rules at [link]:
- Section: "[exact quote of scope rule]"
- My finding location: [contract/file]
- My understanding: [why I think it's in scope]

Could you clarify which scope rule specifically excludes this? Want to ensure I understand boundaries for future submissions.
```

---

## Template 4: Acknowledging Triager Was Right

```
Thanks for the detailed explanation. Now I understand why [reason]. I'll incorporate this into my methodology for future findings.

Closing this report.
```

(Always close gracefully. Reputation matters across programs.)

---

## Template 5: Escalation to Mediation

For Immunefi, if disagreement persists:
- Use built-in mediation request after 14 days of disagreement
- HackerOne: contact "mediation@hackerone.com" with clear timeline
- Sherlock: senior reviewer escalation

Don't escalate prematurely. Try direct dialogue 2-3 times first.

---

## Tactical Tips

1. **Lead with numbers, not severity**: don't argue "it's High" — show "$X extractable, T[N] feasible"
2. **Reference past precedent**: if a similar bug was paid as Critical elsewhere, mention it
3. **Demonstrate, don't argue**: link to fork PoC
4. **Stay professional**: even if triager is wrong, future programs see your tone
5. **Time-box**: if disagreement doesn't resolve in 14 days, escalate to mediation
6. **Document**: keep all communications. May help across reports.

---

## What NOT to Do

- Publish on Twitter "Immunefi underpaid me!" — kills future programs
- Argue with adjectives ("This is OBVIOUSLY Critical!")
- Resubmit same finding with new severity (counts as spam)
- Threaten to disclose publicly — violates RFD/standards
- Be ungracious if triager was correct

---

## When to Accept Triager's Severity

- They're an expert; their domain knowledge is often correct
- If your J4 analysis was rough, accept lower
- If "duplicate" was legit, accept and move on
- "Acknowledged informational" with no payout — common, accept

Good hunters lose 20-30% of submissions. That's healthy calibration.
