#!/usr/bin/env bash
# spawn_validator.sh — orchestrate solana-test-validator with cloned mainnet state.
#
# Usage:
#   bash spawn_validator.sh --clone-program 9xQeWv... --clone-account ABC123... --output ./fork_state
#   bash spawn_validator.sh --target-config fork_config.json   # JSON spec for batch clone
#
# Output:
#   - validator running on :8899 (RPC) / :8900 (websocket)
#   - $OUTPUT/validator.log
#   - $OUTPUT/keypair.json (funded payer for attacker tx)
#   - $OUTPUT/fork_state.json (manifest)
#
# Cleanup: bash spawn_validator.sh --stop

set -uo pipefail

OUTPUT=""
CLONE_PROGRAMS=()
CLONE_ACCOUNTS=()
CONFIG=""
MAINNET_RPC="${MAINNET_RPC:-https://api.mainnet-beta.solana.com}"
SLOT=""
STOP=false
RESET=true
ATTACKER_FUND_SOL=100

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) OUTPUT="$2"; shift 2;;
    --clone-program) CLONE_PROGRAMS+=("$2"); shift 2;;
    --clone-account) CLONE_ACCOUNTS+=("$2"); shift 2;;
    --target-config) CONFIG="$2"; shift 2;;
    --slot) SLOT="$2"; shift 2;;
    --mainnet-rpc) MAINNET_RPC="$2"; shift 2;;
    --no-reset) RESET=false; shift;;
    --fund-sol) ATTACKER_FUND_SOL="$2"; shift 2;;
    --stop) STOP=true; shift;;
    *) echo "[!] Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ "$STOP" == "true" ]]; then
  echo "[*] Stopping any running solana-test-validator..."
  pkill -f solana-test-validator 2>/dev/null || true
  sleep 1
  echo "[+] Stopped"
  exit 0
fi

if [[ -z "$OUTPUT" ]]; then
  echo "Usage: $0 --output DIR (--clone-program ADDR | --clone-account ADDR | --target-config JSON)+ [--slot N]" >&2
  exit 1
fi

mkdir -p "$OUTPUT"
cd "$OUTPUT" || exit 1

if [[ -n "$CONFIG" ]]; then
  echo "[*] Loading clone config from $CONFIG"
  while IFS= read -r addr; do
    CLONE_PROGRAMS+=("$addr")
  done < <(python3 -c "import json,sys; d=json.load(open('$CONFIG')); print('\n'.join(d.get('programs',[])))")
  while IFS= read -r addr; do
    CLONE_ACCOUNTS+=("$addr")
  done < <(python3 -c "import json,sys; d=json.load(open('$CONFIG')); print('\n'.join(d.get('accounts',[])))")
fi

if [[ ${#CLONE_PROGRAMS[@]} -eq 0 && ${#CLONE_ACCOUNTS[@]} -eq 0 ]]; then
  echo "[!] No programs or accounts to clone. Provide --clone-program OR --clone-account OR --target-config." >&2
  exit 1
fi

if [[ "$RESET" == "true" ]]; then
  rm -rf test-ledger
fi

if [[ ! -f keypair.json ]]; then
  echo "[*] Generating attacker keypair..."
  solana-keygen new --no-bip39-passphrase --silent -o keypair.json
fi
ATTACKER_PUBKEY=$(solana-keygen pubkey keypair.json)
echo "[+] Attacker pubkey: $ATTACKER_PUBKEY"

CLONE_ARGS=()
for addr in "${CLONE_PROGRAMS[@]}"; do
  CLONE_ARGS+=(--clone "$addr")
done
for addr in "${CLONE_ACCOUNTS[@]}"; do
  CLONE_ARGS+=(--clone-account "$addr")
done

if [[ -n "$SLOT" ]]; then
  CLONE_ARGS+=(--warp-slot "$SLOT")
fi

echo "[*] Spawning test validator with $(( ${#CLONE_PROGRAMS[@]} + ${#CLONE_ACCOUNTS[@]} )) cloned entries..."
echo "    Mainnet RPC: $MAINNET_RPC"
echo "    Attacker fund: $ATTACKER_FUND_SOL SOL"

nohup solana-test-validator \
  --url "$MAINNET_RPC" \
  --rpc-port 8899 \
  "${CLONE_ARGS[@]}" \
  --reset \
  > validator.log 2>&1 &

VALIDATOR_PID=$!
echo "$VALIDATOR_PID" > validator.pid
echo "[+] Validator PID: $VALIDATOR_PID"

echo "[*] Waiting for RPC ready..."
for i in {1..30}; do
  if solana --url http://localhost:8899 cluster-version >/dev/null 2>&1; then
    echo "[+] RPC ready (waited ${i}s)"
    break
  fi
  sleep 1
done

if ! solana --url http://localhost:8899 cluster-version >/dev/null 2>&1; then
  echo "[!] RPC failed to start. Check validator.log:" >&2
  tail -20 validator.log >&2
  exit 1
fi

echo "[*] Funding attacker keypair with $ATTACKER_FUND_SOL SOL..."
solana --url http://localhost:8899 airdrop "$ATTACKER_FUND_SOL" "$ATTACKER_PUBKEY" --keypair keypair.json > /dev/null
BALANCE=$(solana --url http://localhost:8899 balance "$ATTACKER_PUBKEY")
echo "[+] Attacker balance: $BALANCE"

cat > fork_state.json <<EOF
{
  "validator_pid": $VALIDATOR_PID,
  "rpc": "http://localhost:8899",
  "websocket": "ws://localhost:8900",
  "attacker_keypair": "$(realpath keypair.json)",
  "attacker_pubkey": "$ATTACKER_PUBKEY",
  "cloned_programs": $(printf '%s\n' "${CLONE_PROGRAMS[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))"),
  "cloned_accounts": $(printf '%s\n' "${CLONE_ACCOUNTS[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))"),
  "mainnet_rpc": "$MAINNET_RPC",
  "slot_warp": "${SLOT:-null}"
}
EOF

echo ""
echo "[+] Fork ready."
echo "    Manifest: $OUTPUT/fork_state.json"
echo "    Logs: $OUTPUT/validator.log"
echo "    To stop: bash spawn_validator.sh --stop"
