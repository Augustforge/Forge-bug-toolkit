# Mempool Watcher — Safety & OPSEC

## Disposition tiers (read before enabling anything beyond alert_only)

### Tier 1: `alert_only` — ZERO risk
Just emit Telegram/Discord webhook notification. Hunter reviews manually.
- ✅ Default for all patterns
- ✅ No legal exposure
- ✅ No race risk (just observation)

### Tier 2: `tip_protocol` — LOW risk
Auto-DM to a known protocol security contact about a suspected attack.
- ⚠️ Requires pre-approved Discord webhook URL per protocol
- ⚠️ Risk: false positive → spammed protocol team → reputation damage
- ⚠️ Mitigation: 2-stage gate — pattern → manual approve → fire
- ✅ Legal: legitimate white-hat warning, not market manipulation

### Tier 3: `flashbots_protect` — HIGH risk (grey zone)
Submit protective transaction via Flashbots private bundle.
- ❌ **NEVER without explicit operator approval per-event**
- ⚠️ Grey-zone: front-running attacker tx may be considered:
  - White-hat (saving victim) — common interpretation
  - Market manipulation (in some jurisdictions)
  - Theft (if you keep "saved" funds)
- ✅ Acceptable practice IF: tx returns funds to protocol vault, not to your address
- ⚠️ Requires pre-signed wallet with capital — additional opsec surface

## OPSEC checklist (every deploy)

- [ ] Watcher runs through VPN (`scripts/web3/opsec/vpn_recon.py --enable`)
- [ ] Pseudonymous wallet used (not main) — `scripts/web3/opsec/wallet_manager.py --new`
- [ ] Audit log writes to `~/.bbt/audit.log` per match
- [ ] No PII in pattern config files
- [ ] Telegram/Discord webhooks use generated dummy account, not main
- [ ] Flashbots responder requires manual passphrase (no auto-sign)

## Legal posture

This module is designed for **defensive use cases**:
- Alerting protocols to threats
- Documenting suspected attacks
- Coordinated disclosure

**NOT for**:
- Front-running for personal profit
- MEV extraction
- Sybil attacks
- Market manipulation

If you use Tier 3 (flashbots_protect): document **every** execution. Keep receipts. Returns funds explicitly. If in doubt → don't fire.

## Rate limits

- Alerts: max 10 per pattern per hour (prevent spam loops)
- Tips: max 1 per protocol per 30 minutes
- Flashbots: 0 auto-fires. Manual approve only.

## What to do if you received an alert

1. Stop. Read context.
2. Verify on-chain (Etherscan, Tenderly) — pattern triggered correctly?
3. If false positive — disable pattern OR refine YAML
4. If legitimate — manual disposition:
   - Tip protocol via Discord/security@<domain>
   - Document timeline in `sessions/<incident_id>/`
   - Consider rekt.news / Blockaid notification

## Audit log entries

Every match writes JSON line to `~/.bbt/audit.log`:
```json
{
  "timestamp": "2026-05-18T16:00:00Z",
  "pattern": "large_admin_withdrawal",
  "chain": "eth",
  "tx_hash": "0x...",
  "from": "0x...",
  "to": "0x...",
  "value_usd": 250000,
  "disposition": "alert_only",
  "fired": true,
  "reviewer": null
}
```

## Disabling watcher

```bash
# Kill running watcher
pkill -f mempool/watcher.py
# OR via process manager
systemctl stop bbt-mempool-watcher  # if systemd setup
```
