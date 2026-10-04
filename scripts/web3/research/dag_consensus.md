# DAG Consensus

**Status**: not-started
**Priority**: medium
**Why hunter cares**: Sui/Aptos $1B+ TVL each. **DAG ordering bugs** different class from blockchain ordering — many novel attack vectors. Limited tooling.

## Core concept

Traditional blockchain: linear sequence of blocks. DAG-based: transactions form directed acyclic graph; multiple parallel branches converge. Faster throughput, harder reasoning.

Key DAG variants:
- **Mysticeti** (Sui) — directly authenticated by Bullshark variant
- **Narwhal + Bullshark** (older Sui) — separated mempool + consensus
- **BlockSTM** (Aptos) — parallel execution + DAG-ish state graph
- **Hashgraph** (Hedera) — gossip-about-gossip + virtual voting

## Top bug classes

### 1. Fork choice bugs
DAG can have legitimately conflicting blocks. Fork choice rule selects canonical chain. Bugs:
- Fork choice doesn't terminate (DoS on consensus)
- Two honest nodes disagree on canonical fork (split chain)
- Adversary can manipulate fork choice with minimal stake

### 2. Double-spend windows
DAG finality often longer than blockchain finality. Double-spend window:
- Tx A spent in branch X, tx B spent in branch Y (same inputs)
- Both branches accepted by separate honest nodes
- Eventually one wins — opposite branch reorganized
- Application-level finality assumption vs actual finality mismatch

### 3. Parallel execution races (Aptos BlockSTM)
- Optimistic concurrency — transactions re-executed on conflict
- Read/write set tracking bugs
- Order-dependent execution → re-execution gives different result?
- Gas accounting drift across re-executions

### 4. Validator set updates
- New validator joins mid-round — fork choice changes
- Validator removal during pending blocks
- Stake re-weighting attacks

### 5. Equivocation handling
- Validator signs conflicting blocks (intentional equivocation)
- Slashing must be triggered, by whom?
- Equivocation evidence formation

### 6. Light client soundness
- Light client must understand DAG (not just header chain)
- Validator set synchronization
- Fork choice replication

## Implementations to read

### Sui (Mysticeti / Bullshark)
- Repo: https://github.com/MystenLabs/sui
- Key modules: `narwhal/`, `consensus/`, `core/`
- Architecture: https://docs.sui.io/concepts/sui-architecture/consensus

### Aptos (BlockSTM)
- Repo: https://github.com/aptos-labs/aptos-core
- Key module: `aptos-vm/src/block_executor/`
- Whitepaper: BlockSTM paper

### Mysticeti (Sui's newer consensus)
- Repo (specific): https://github.com/asonnino/mysticeti
- Whitepaper: "Mysticeti: Reaching the Limits of Latency with Uncertified DAGs"

## Notable past bugs

- **Sui early disclosures** — historical Move/consensus interface bugs
- **Aptos** — gas accounting bugs in parallel execution
- **Hedera** — multiple disclosed Hashgraph fixes

## Hunting workflow once we reach `can-hunt`

1. Identify DAG protocol (Sui/Aptos/proprietary)
2. Check fork choice:
   - Termination conditions?
   - Adversarial fork choice manipulation?
3. Check parallel execution:
   - Read/write set bounds correctly?
   - Re-execution semantics correct?
4. Validator set:
   - Mid-round join/leave handling?
   - Equivocation slashing working?
5. Light client:
   - Header verification understands DAG?
   - Validator set checked across rounds?

## Active programs

- **Sui Immunefi** — $500k cap
- **Aptos** — Immunefi
- **Move ecosystem** — various

## To-author once can-hunt status is reached

- `scripts/web3/checklists/specialized/dag_consensus.md`
- `scripts/web3/threat_models/dag_fork_choice_attack.yaml`
- `scripts/web3/threat_models/parallel_execution_race.yaml`

## Reading list

1. **Bullshark paper** — Spiegelman et al.
2. **Mysticeti paper** — Sonnino et al.
3. **BlockSTM paper** — Aptos Labs
4. **"From DAGs to Blockchains"** — survey paper
5. **Sui Move documentation** (Move VM context)

## Realistic timeline

DAG protocols mature enough to hunt but requires deep consensus knowledge. **6-12 month investment** for real productivity. Lower priority than ZK VMs / Restaking AVS where the audit ecosystem is more immature.
