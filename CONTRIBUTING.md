# Contributing

Thanks for taking a look. This is an open, built-in-public project — issues, ideas, and pull
requests are welcome.

## Ground rules

- **White-hat only.** Contributions must keep the tool within its scope: finding and proving
  bugs for coordinated disclosure. PRs that add offensive escalation beyond a non-destructive
  PoC (live exploitation, exfiltration, detection-evasion against a third party's defenses,
  DoS, mass-targeting) will be declined. See [SECURITY.md](SECURITY.md).
- **The methodology is the product.** The model is a replaceable part — keep modules
  runtime-agnostic (read files, run a shell, spawn sub-agents, drive a browser) rather than
  tied to one LLM provider.

## Running the self-tests

The engine ships with a self-test suite. Run it from the repo root:

```bash
python run_selftests.py
```

On a fresh clone you should see something like `30 passed, 4 skipped, 0 failed`. The skipped
tests exercise a private benchmark/calibration corpus (per-hunt calibration data) that is not
part of the public release — that's expected, not a failure.

Add a self-test for any new gate or detector: the test must prove the thing **fires**, not
just that it doesn't false-positive.

## A note on language

The outward-facing surface (README, `SKILL.md`, `methodology/`, the web2 payload/framework
references, and the report templates) is English. Some internals — the three skill playbooks
under `.claude/commands/`, the enforcement hooks and gate engines, and some engine comments —
are still Russian and are being localized progressively. Translations are welcome; keep the
runtime format-strings the hooks match on intact (translating them in isolation breaks the
gates).
