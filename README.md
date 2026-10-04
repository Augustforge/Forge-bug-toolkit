# Forge Bug Toolkit

An autonomous, white-hat **bug-bounty hunting harness** for LLM agents.

It is not a scanner and not a prompt. It is an operating system for an AI agent that hunts
vulnerabilities the way a senior researcher does: build an independent model of the target,
find where the code diverges from it, and drive one thread down five layers until a bug
either dies with a falsifier or proves out with a PoC. The methodology is the product — the
model underneath is an interchangeable part. It runs on [Claude Code](https://www.claude.com/product/claude-code)
today and is designed to port to any agent runtime that can read files, run a shell, spawn
sub-agents, and drive a browser.

> AI does the typing. The architecture, the calls, and the mistakes are the operator's.

---

## What it does

Point it at a target and it runs a self-driving hunt loop — select one hypothesis, drive it
deep, prove or kill it, repeat — until it has a cold-verified High/Critical, banking Medium
and Low findings along the way. It covers both crypto (EVM, Solana, TON, Move) and web2, and
drives live dApp frontends through a real browser.

Three entry points:

| Command | Surface | What it is |
|---|---|---|
| `/deephunt <target>` | Smart contracts (EVM / Solana / TON) | Hypothesis-driven hunting for High/Critical — deep manual analysis, invariant testing, fork PoC. The main mode. |
| `/dapphunt <domain>` | Live web3 dApp frontends | Divergence-first frontend hunting — cross-clone differential, data-flow divergence, runtime observation. |
| `/hunt <target>` | web2 apps and APIs | Access-model-first hunting with an authorization-diff harness at its core. |

## What makes it different

- **Divergence-first.** It builds a model of the system *before* reading the implementation,
  then hunts the gap between the two — the one place the crowd of duplicate-submitters isn't
  looking.
- **Depth over breadth.** It refuses to call a scope "clean" from a surface sweep. A finding
  only counts when one interaction chain has been pulled down five layers to its seam.
- **Enforcement, not aspiration.** The methodology is wired into runtime hooks — a ledger
  that creates itself before the first action, a loop that won't let the agent quit early, a
  prompt-injection guard over every piece of external content. The discipline runs whether or
  not the agent "remembers" to follow it.
- **Compounding.** Every hunt banks reusable invariants and patterns, so the next target
  starts with a library the crowd doesn't have.
- **Cold verification.** Nothing is reported until a fresh-context agent re-derives it and a
  separate specialist checks scope and payability. It kills roughly a quarter of candidates
  before they waste a submission.

## Ethics and scope

This is a **white-hat** system. It thinks like an attacker in order to *find and prove*
bugs — and then stops.

- **THINK ≠ ACT.** Impact is measured on a fork, never against live state.
- No DoS, no market manipulation, no live-state mutation, no phishing, no RAT/C2, no
  mass-targeting, no destruction of data — ever.
- Funds are returned or never moved; findings are disclosed to the project team.
- Only run it against targets you are authorized to test, within a program's scope.

You are responsible for using it legally and within scope. See [SKILL.md](SKILL.md) for the
full operating doctrine.

## Quickstart

```bash
# 1. Point your agent runtime at this repo (for Claude Code, SKILL.md is the brain —
#    copy or symlink it to CLAUDE.md, and copy .claude/settings.example.json to
#    .claude/settings.json, fixing the hook paths to your checkout).
cp SKILL.md CLAUDE.md
cp .claude/settings.example.json .claude/settings.json

# 2. Configure optional API keys (each missing key just disables that module).
cp .env.example .env    # then edit

# 3. Heavy tools run in Docker; build the image once.
docker build -t bbt docker/

# 4. In your agent, invoke a skill:
#    /deephunt <repo-or-target>
```

Everything an agent needs to operate the system is in **[SKILL.md](SKILL.md)**. The detailed
methodology lives in [`methodology/`](methodology/); the engines in [`scripts/`](scripts/).

## A note on language

The outward-facing surface is English — this README, the operating guide ([SKILL.md](SKILL.md)),
the methodology ([`methodology/`](methodology/)), and the web2 payload/framework references and
report templates. Parts of the internals are still Russian and are being localized progressively,
in the open: the three skill playbooks under [`.claude/commands/`](.claude/commands/) (SKILL.md §4
summarizes each in English), the enforcement hooks and gate engines, the web2 engine's inline
comments, and the replay/self-test fixtures. Much of this is format-strings the runtime matches on,
so translating it in isolation would break the system — it gets its English pass over time. The
tool runs regardless of comment language.

## License

[Apache-2.0](LICENSE). Use it, fork it, build on it. Patent grant included.

---

*Part of [Augustus Forge](https://x.com/augustus_forge) — autonomous decision systems, built
in public. Failures included, wins earned.*
