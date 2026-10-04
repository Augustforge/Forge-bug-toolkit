# Real-time Mempool Monitoring + Race-to-Disclose

## Why it is needed

30% Critical findings — these are race-conditions with an already-discovered attacker. If you see it first → you can tip the protocol before the drain, or (white-hat) front-run with a protective tx. Plus mempool patterns predict exploits minutes before on-chain.

## Architecture

```
chains/ethereum.py  ──┐
chains/arbitrum.py  ──┤
chains/base.py      ──┼─→  watcher.py (main loop)
chains/bsc.py       ──┤         │
chains/solana.py    ──┘         │
                                ▼
patterns/*.yaml  ──→  pattern matcher
                                │
                                ▼
                       responders.py
                       (alert / tip / flashbots)
                                │
                                ▼
                       ~/.bbt/audit.log
                       Telegram / Discord notify
```

## Components

### `watcher.py`
Main loop. Connects to chain adapters via WebSocket mempool subscription. For each pending tx — runs all loaded patterns. Matched → dispatch to responders.

### `chains/<chain>.py`
Per-chain adapters. Each implements:
- `connect()` — WebSocket / RPC subscription setup
- `iter_pending()` — async generator yielding `{tx_hash, from, to, value, data, ...}`
- `decode_tx(raw)` — chain-specific decoding (EVM vs Solana different)

### `patterns/*.yaml`
Pattern library. Each YAML describes one signature to watch for:
```yaml
id: large_admin_withdrawal
applies_to: [evm]
match:
  to_address_regex: "0x[a-fA-F0-9]{40}"
  function_selector: ["0x2e1a7d4d", "0xa9059cbb"]   # withdraw, transfer
  caller_must_be: known_admin               # check via on-chain ABI
  value_min_usd: 100000
severity: high
disposition: tip_protocol
```

### `responders.py`
Disposition layer. For each pattern match — execute action:
- `alert_only` — Telegram/Discord webhook (always safe)
- `tip_protocol` — auto-DM via known protocol security contacts
- `flashbots_protect` — submit protective tx via Flashbots private bundle (**REQUIRES OPERATOR APPROVAL per-event**)

## OPSEC & Ethics constraints (must read)

See `_safety.md` for the full list. TL;DR:
- ✅ Auto-alerts = always OK (zero risk)
- ✅ Auto-tip-protocol = OK if pre-approved webhook + protocol scope
- ❌ Auto-flashbots-protect = **NEVER without explicit operator approval per-event**

## Usage

```bash
# 1. Setup secrets
cp .env.example .env
# Edit: ETH_WS_URL, TELEGRAM_BOT_TOKEN, DISCORD_WEBHOOK

# 2. Start watcher (ETH only, 1 pattern, dry-run)
bash scripts/web3/mempool/start_watcher.sh \
    --chains eth --patterns large_admin_withdrawal --dry-run

# 3. Multi-chain production
bash scripts/web3/mempool/start_watcher.sh \
    --chains eth,arb,base --patterns all
```

## Phase rollout

1. ✅ Watcher scaffold + ETH only + 1 pattern (`large_admin_withdrawal`)
2. Pattern library expansion (5 patterns) + multi-chain adapters (arb/base/bsc/solana)
3. Responders + Telegram/Discord + audit log
4. Flashbots responder (only if the operator wants grey-zone capability)

## Reuse

- `scripts/web3/realtime/exploit_race_monitor.py` — existing scaffold. Watcher wraps/replaces it.
- `scripts/web3/realtime/deploy_listener.py` — similar pattern, parallel module
- `scripts/web3/threat_models/apply.py` — `unauthorized_outbound.yaml` pattern can cross-reference the TSS threat_model
- `scripts/_audit_log.py` — for legal protection
- `scripts/monitors/notify.py` — existing Telegram/Discord dispatch

## Integration

- Daily digest (`scripts/monitors/daily_digest.py`) adds mempool stats: "over the day matched N patterns, K tipped, 0 false alarms"
- `/hunt` proactive mode — prioritizes targets from the mempool-hit list

## Anti-pattern

**Don't** run watcher 24/7 without a monitoring tier. Mempool subscriptions cost — Alchemy/Blocknative price-per-tx. Set rate limits + USD budget alerts.

**Don't** trust patterns — every match needs human review before tip_protocol fires. Two-stage gate: pattern matches → review queue → manual approve → tip.
