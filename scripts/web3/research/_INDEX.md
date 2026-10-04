# Research Catalog — Emerging Primitives

Goal: a 9.99 hunter catches bugs in known classes. **A 10/10 catches bugs in newly emerged primitives** before they become mainstream — there are no audited patterns there, only spec + first implementations. A window of advantage while the rest of the industry hasn't caught up yet.

## Study status per primitive

| Primitive | Status | Priority | First active target |
|---|---|---|---|
| [Post-quantum crypto](post_quantum.md) | not-started | high | Solana PQ pilot (experimental) |
| [ZK virtual machines](zk_vms.md) | not-started | very-high | Risc0 / SP1 / Linea / Scroll |
| [DAG consensus](dag_consensus.md) | not-started | medium | Sui (Mysticeti), Aptos (BlockSTM) |
| [DA layers](da_layers.md) | not-started | high | Celestia, EigenDA, Avail |
| [Restaking AVS](restaking_avs.md) | studying | very-high | EigenLayer AVS catalog, Symbiotic |
| [Intent-based solvers](intent_solvers.md) | studying | high | UniswapX, CoWSwap, Across, 1inch Fusion |
| [MPC threshold (beyond GG18/20)](mpc_threshold.md) | familiar | high | FROST, GG24, threshold BLS |

**Status legend**:
- `not-started` — primitive identified, no study done
- `studying` — actively reading specs/papers, not able to hunt yet
- `familiar` — understand mechanics, can recognize surface in code
- `can-hunt` — confident enough to write threat_models, generate hypotheses

**Priority legend** (combination of: bounty TVL × novelty × adoption velocity):
- `very-high` — actively shipping protocols with large TVL, no industry tooling yet
- `high` — production but limited tooling
- `medium` — production, some tooling exists, lower bounty $$$

## Why each primitive matters for a hunter

- **ZK VMs** — soundness errors can drain $100M+ from any rollup. Almost no static analysis tooling exists.
- **Restaking AVS** — EigenLayer reaches $15B+ TVL by 2026. AVS bugs are a NEW class, the audit ecosystem is still maturing.
- **Post-quantum** — protocols starting PQ migrations (Solana pilot, Algorand). Migration bugs are juicy.
- **Intent solvers** — solver-side MEV is a grey area, batch auction surface largely unexplored.
- **DA layers** — Celestia/EigenDA underpin many L2s. Data unavailability attacks could brick chains.
- **DAG consensus** — Sui/Aptos $1B+ each. DAG ordering bugs are a different class from blockchain ordering.
- **MPC threshold (post-Thorchain)** — FROST/GG24 are newer variants of GG18/20. The hunter's lens from Thorchain transfers.

## Workflow

1. **Schedule** (`_schedule.md`) — time-box 4h/week on one primitive from the top-3 priority
2. **Read** — start with linked papers/specs/posts in the per-primitive .md
3. **Hands-on** — clone a real implementation, walk through key flows
4. **Active targets** (`_active_targets.md`) — track which protocols ship this primitive (auto-updated weekly via `_check_active_targets.py`)
5. **Migrate to threat_intel.md** when the pattern crystallizes
6. **Author threat_model YAML** in `scripts/web3/threat_models/` when can-hunt level reached

## Sub-directories — Tier A depth tooling (Thorchain 2026 lesson)

After the Thorchain lessons — depth tooling was added for cryptographic primitives:

| Subdir | Purpose | Entry point |
|---|---|---|
| [`_crypto_corpus/`](_crypto_corpus/) | Local cache of TSS/MPC implementations for cross-diff hunting | `_crypto_corpus/fetch.py` → `diff_critical_rounds.py` |
| [`_audit_corpus/`](_audit_corpus/) | Grep-able archive of public audit reports + `_known_findings.jsonl` | `_audit_corpus/fetch.py --list` |
| [`_primers/`](_primers/) | Compact knowledge transfer (cryptographer-level concepts for the hunter) | `_primers/tss_math_for_hunters.md` |
| [`_papers/`](_papers/) | Verichains-grade paper template + worked examples for Critical findings | `_papers/_INDEX.md`, `paper_template.md` |

**When to use**:
- Found a candidate TSS/crypto-primitive bug → read primer, run crypto_corpus diff, write paper template
- Auditing a TSS bridge → grep `_audit_corpus/` first for known findings, then `diff_critical_rounds.py`
- Writing a Critical bounty submission → use `_papers/paper_template.md` instead of a short report

## Integration with the rest of the toolkit

- `scripts/proactive.py --filter primitive=zk_vm` — boost priority for proactive search
- `scripts/monitors/github_monitor.py` — watch list of repos from per-primitive docs
- `scripts/_update.sh` weekly includes `_check_active_targets.py` for refresh
- In `/hunt` proactive mode — if target uses a primitive with status=can-hunt → auto-include research doc in context

## Anti-pattern

**Don't** make this a "wikipedia of crypto". Each per-primitive file must answer:
- What's the attack surface?
- What bugs have already happened?
- Where are current implementations?
- What can the hunter check next time he sees this primitive?

Theory without actionability = dead doc.
