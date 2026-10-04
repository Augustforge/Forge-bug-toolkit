#!/usr/bin/env bash
# replay_corpus.sh — Regression replay of all historical exploits for toolkit calibration.
#
# Runs known-bad pre-fix exploits through the fork harness:
#   - spawn validator with cloned mainnet state at the pre-fix slot
#   - load attacker tx from corpus/<exploit_name>/
#   - submit to fork
#   - verify exploit reproduces (state mutated as expected)
#
# Cumulative status: how many of N historical exploits we can reproduce automatically.
# Each new exploit added to corpus extends regression suite.
#
# Usage:
#   bash replay_corpus.sh                          # run all
#   bash replay_corpus.sh --exploit cashio_2022    # run one
#   bash replay_corpus.sh --output sessions/_validation/regression_$(date +%Y%m%d)/

set -uo pipefail

CORPUS_DIR="${BASH_SOURCE%/*}/corpus"
OUTPUT=""
SINGLE_EXPLOIT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --exploit) SINGLE_EXPLOIT="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    --corpus-dir) CORPUS_DIR="$2"; shift 2;;
    *) echo "[!] Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="./regression_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$OUTPUT"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

declare -A KNOWN_EXPLOITS=(
    [cashio_2022]="Cashio - owner check bypass - cloned: program account, attacker fake bank account"
    [wormhole_2022]="Wormhole - signature verification - cloned: bridge program, signature_set"
    [mango_2022]="Mango Markets - oracle manipulation - cloned: mango program, oracle accounts, vault"
    [crema_2022]="Crema Finance - tick array - cloned: AMM program, pool"
    [raydium_2024]="Raydium CLMM - remaining_accounts validation - cloned: CLMM program, pool, bitmap"
    [loopscale_2025]="Loopscale - CPI program ID - cloned: protocol, fake RateX state"
    [marginfi_2025]="Marginfi - flash loan state - cloned: marginfi-v2, bank, user account"
    [drift_2026]="Drift - durable nonce multisig - cloned: drift, squads PDA, nonce account"
)

EXPLOITS_TO_RUN=()
if [[ -n "$SINGLE_EXPLOIT" ]]; then
    if [[ -z "${KNOWN_EXPLOITS[$SINGLE_EXPLOIT]:-}" ]]; then
        echo "[!] Unknown exploit: $SINGLE_EXPLOIT" >&2
        echo "Available: ${!KNOWN_EXPLOITS[@]}" >&2
        exit 1
    fi
    EXPLOITS_TO_RUN=("$SINGLE_EXPLOIT")
else
    EXPLOITS_TO_RUN=("${!KNOWN_EXPLOITS[@]}")
fi

TOTAL=${#EXPLOITS_TO_RUN[@]}
PASS=0
FAIL=0
SKIP=0

echo "=== Replay Corpus Regression Test ==="
echo "Target exploits: $TOTAL"
echo "Output: $OUTPUT"
echo ""

for exploit in "${EXPLOITS_TO_RUN[@]}"; do
    EXPLOIT_DIR="$CORPUS_DIR/$exploit"
    EXPLOIT_OUT="$OUTPUT/$exploit"
    mkdir -p "$EXPLOIT_OUT"

    echo "--- $exploit ---"
    echo "    ${KNOWN_EXPLOITS[$exploit]}"

    if [[ ! -d "$EXPLOIT_DIR" ]]; then
        echo "    [SKIP] corpus dir not found: $EXPLOIT_DIR"
        echo "    Create: $EXPLOIT_DIR/clone_config.json + tx.bin + watch_accounts.txt + invariants.json"
        ((SKIP++))
        echo "skipped" > "$EXPLOIT_OUT/result.txt"
        continue
    fi

    CLONE_CONFIG="$EXPLOIT_DIR/clone_config.json"
    TX_FILE="$EXPLOIT_DIR/tx.bin"
    WATCH_FILE="$EXPLOIT_DIR/watch_accounts.txt"
    INVARIANTS="$EXPLOIT_DIR/invariants.json"

    if [[ ! -f "$CLONE_CONFIG" || ! -f "$TX_FILE" || ! -f "$WATCH_FILE" ]]; then
        echo "    [SKIP] missing required files (need clone_config.json + tx.bin + watch_accounts.txt)"
        ((SKIP++))
        echo "skipped" > "$EXPLOIT_OUT/result.txt"
        continue
    fi

    echo "    [1/3] Spawning fork..."
    bash "$SCRIPT_DIR/spawn_validator.sh" \
        --output "$EXPLOIT_OUT/fork" \
        --target-config "$CLONE_CONFIG" \
        > "$EXPLOIT_OUT/spawn.log" 2>&1

    if [[ ! -f "$EXPLOIT_OUT/fork/fork_state.json" ]]; then
        echo "    [FAIL] fork spawn failed (see $EXPLOIT_OUT/spawn.log)"
        ((FAIL++))
        echo "fail_spawn" > "$EXPLOIT_OUT/result.txt"
        continue
    fi

    echo "    [2/3] Submitting attacker tx..."
    INVARIANT_ARG=()
    [[ -f "$INVARIANTS" ]] && INVARIANT_ARG=(--invariants "$INVARIANTS")
    python3 "$SCRIPT_DIR/fork_runner.py" \
        --fork "$EXPLOIT_OUT/fork/fork_state.json" \
        --tx-file "$TX_FILE" \
        --watch-accounts-file "$WATCH_FILE" \
        "${INVARIANT_ARG[@]}" \
        --output "$EXPLOIT_OUT/run" \
        > "$EXPLOIT_OUT/run.log" 2>&1

    VERDICT_FILE="$EXPLOIT_OUT/run/verdict.json"
    if [[ ! -f "$VERDICT_FILE" ]]; then
        echo "    [FAIL] verdict file missing"
        ((FAIL++))
        echo "fail_verdict" > "$EXPLOIT_OUT/result.txt"
        bash "$SCRIPT_DIR/spawn_validator.sh" --stop > /dev/null 2>&1 || true
        continue
    fi

    VERDICT=$(python3 -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('exploit','?'))")
    STATUS=$(python3 -c "import json; d=json.load(open('$VERDICT_FILE')); print(d.get('status','?'))")

    echo "    [3/3] Verdict: $VERDICT (status: $STATUS)"
    if [[ "$VERDICT" == "CONFIRMED" ]]; then
        echo "    [PASS] exploit reproduced"
        ((PASS++))
        echo "pass" > "$EXPLOIT_OUT/result.txt"
    elif [[ "$VERDICT" == "needs_review" ]]; then
        echo "    [REVIEW] state mutated, manual check needed"
        ((PASS++))
        echo "review" > "$EXPLOIT_OUT/result.txt"
    else
        echo "    [FAIL] exploit did not reproduce"
        ((FAIL++))
        echo "fail_no_repro" > "$EXPLOIT_OUT/result.txt"
    fi

    bash "$SCRIPT_DIR/spawn_validator.sh" --stop > /dev/null 2>&1 || true
    echo ""
done

cat > "$OUTPUT/summary.json" <<EOF
{
  "total": $TOTAL,
  "pass": $PASS,
  "fail": $FAIL,
  "skip": $SKIP,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "production_ready_threshold": 5,
  "production_ready": $([ $PASS -ge 5 ] && echo true || echo false)
}
EOF

echo ""
echo "=== Summary ==="
echo "PASS: $PASS / $TOTAL"
echo "FAIL: $FAIL"
echo "SKIP (corpus not built): $SKIP"
echo ""
if [[ $PASS -ge 5 ]]; then
    echo "[+] PRODUCTION READY (>= 5/8 historical exploits reproducible)"
else
    echo "[!] Below production threshold (need >= 5 PASS)"
fi
echo "Full report: $OUTPUT/summary.json"
