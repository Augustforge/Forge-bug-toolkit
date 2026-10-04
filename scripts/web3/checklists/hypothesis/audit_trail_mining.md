# Hypothesis: Audit Trail Mining

**Trigger**: `audit_trail_miner.py` flagged a commit where message claims security fix but diff is empty / docs-only / tiny.

**Real example**: Alchemix V3 commit `16e0882` subject: "Direct WETH-to-wstETH allocation marks down vault shares during depeg". The "fix" was a runbook document, not a code change. The vulnerability remained live.

---

## Checklist

### 1. Pull commit content
```bash
git show <sha> 
git show <sha> --stat  # numstat overview
```

- [ ] Read commit message in full
- [ ] Read PR description if linked (`git log --format='%B' <sha>`)
- [ ] Identify what the message PROMISES (e.g., "fix critical X")

### 2. Compare promise vs diff
- [ ] What does the diff actually change?
- [ ] Files modified — `.sol` source? Tests? Docs only?
- [ ] If only docs/comments/changelogs → **fix was documented, not implemented**

### 3. Find the supposed vulnerable code
- [ ] Based on commit subject, find the function(s) supposedly fixed
- [ ] Check current state of those functions vs what commit says

### 4. Verify "fix" actually addresses the issue
- [ ] If commit says "added guard X" — is guard X present in current code?
- [ ] If commit says "fixed in audit Y" — does Y describe the exact issue addressed?
- [ ] If commit says "added test" — does the test ACTUALLY test the failure mode?

### 5. Look for adjacent / similar functions
- [ ] If commit fixed FunctionA, are there similar FunctionB, FunctionC?
- [ ] Same bug class — was it fixed there too?

### 6. Verify via Foundry test
- [ ] Write test that would have caught the original issue
- [ ] Run against current code
- [ ] Test fails → bug still live → strong hypothesis confirmed

---

## Specific patterns to investigate

### Empty diff with security keyword
```
sha=abc123  subject="fix critical: oracle manipulation"  +0 -0 changes
```
→ Either commit is empty/squashed, or fix is in another commit. Check git log for follow-ups.

### Docs-only diff with audit mention
```
sha=def456  subject="address audit finding XYZ"  files: README.md, AUDIT.md
```
→ Issue acknowledged but not fixed. Very strong signal.

### Tiny diff with major claim
```
sha=ghi789  subject="resolve high-severity vulnerability"  +1 -1 changes
```
→ One-character fix? Check if real or misleading.

### "Documented" pattern
```
sha=jkl012  subject="document direct allocation depeg behavior"
```
→ Behaviour is intentional? Or workaround that should have been code fix?

---

## Past examples

### Alchemix V3 `16e0882`
- Subject: "Direct WETH-to-wstETH allocation marks down vault shares during depeg"
- Diff: documentation file + runbook
- Real fix: not in source code
- Bug live: yes (confirmed via PoC)

### Hypothetical: lending protocol
- Commit: "fix: oracle price floor protection"
- Diff: only adds `// TODO: add price floor` comment
- Real fix: never came
- Bug live: yes

---

## Severity weight

When this hypothesis confirms a bug:
- **+Confidence**: project itself documented the issue → undeniable
- **+Severity argument**: not a misunderstanding from reporter
- Reduce report writing time — protocol team's own words are evidence

---

## Output format

```markdown
## Audit Trail H<N>: Commit `<sha>` claimed fix, diff insufficient

### Commit details
- SHA: `<sha>`
- Author: <name>
- Date: <date>
- Subject: `<subject>`
- Diff: <+X −Y lines, N files: ...>

### Promise vs Reality
- **Promised**: <what subject says>
- **Actually changed**: <list of file changes>
- **Gap**: <what's missing>

### Current code status
- Vulnerability is: live / fixed / partially-fixed
- Evidence: <foundry test result or manual reasoning>

### Verification
- [ ] Foundry test demonstrating bug still live: `verify/H<N>.t.sol`
```
