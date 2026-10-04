#!/usr/bin/env bash
# run_fuzz.sh — wrapper around `trident fuzz run`
#
# Usage:
#   bash run_fuzz.sh <test_dir> [--seed SEED] [--with-exit-code]
#
# Where <test_dir> is e.g. target/trident-tests/fuzz_0/
# OR specify target workspace + test name:
#   bash run_fuzz.sh --workspace <target> --test fuzz_0

set -euo pipefail

TEST_DIR=""
WORKSPACE=""
TEST_NAME=""
SEED=""
WITH_EXIT_CODE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --workspace) WORKSPACE="$2"; shift 2;;
    --test) TEST_NAME="$2"; shift 2;;
    --seed) SEED="$2"; shift 2;;
    --with-exit-code) WITH_EXIT_CODE="--with-exit-code"; shift;;
    *)
      if [[ -z "$TEST_DIR" ]]; then TEST_DIR="$1"; fi
      shift;;
  esac
done

# Determine workspace + test name from test_dir if needed
if [[ -n "$TEST_DIR" ]]; then
  TEST_DIR_ABS="$(cd "$TEST_DIR" && pwd)"
  TEST_NAME=$(basename "$TEST_DIR_ABS")
  TRIDENT_TESTS_DIR=$(dirname "$TEST_DIR_ABS")
  WORKSPACE=$(dirname "$TRIDENT_TESTS_DIR")
fi

if [[ -z "$WORKSPACE" || -z "$TEST_NAME" ]]; then
  echo "Usage: $0 <test_dir> [--seed SEED] [--with-exit-code]"
  echo "   OR: $0 --workspace <anchor_workspace> --test <test_name>"
  exit 1
fi

if [[ ! -f "$WORKSPACE/Anchor.toml" ]]; then
  echo "[!] Workspace lacks Anchor.toml: $WORKSPACE"
  exit 1
fi

TRIDENT_BIN=$(which trident 2>/dev/null || echo "")
if [[ -z "$TRIDENT_BIN" ]]; then
  echo "[!] trident binary not found. Run inside bbt:latest Docker."
  exit 1
fi

echo "[*] Trident fuzz run"
echo "    Workspace: $WORKSPACE"
echo "    Test: $TEST_NAME"
echo "    Seed: ${SEED:-random}"

cd "$WORKSPACE"

CMD="trident fuzz run $TEST_NAME"
if [[ -n "$SEED" ]]; then CMD="$CMD $SEED"; fi
if [[ -n "$WITH_EXIT_CODE" ]]; then CMD="$CMD $WITH_EXIT_CODE"; fi

mkdir -p trident-tests/$TEST_NAME/logs
LOG_FILE="trident-tests/$TEST_NAME/logs/fuzz_$(date -u +%Y%m%dT%H%M%S).log"

echo ""
echo "[*] Running: $CMD"
echo "[*] Log: $LOG_FILE"
echo ""

# Trident has its own internal iteration count (set in Trident.toml fuzz.metrics
# and in FuzzTest::fuzz(N, M) call in test_fuzz.rs).
# Use Ctrl+C or external timeout to stop early.

$CMD 2>&1 | tee "$LOG_FILE"

# Trident outputs crashes to its own location — check both trident-tests cache and fuzz_X dir
CRASH_DIRS=(
    "$WORKSPACE/trident-tests/$TEST_NAME/.crashes"
    "$WORKSPACE/trident-tests/.trident_crashes"
    "$WORKSPACE/trident-tests/$TEST_NAME/hfuzz_workspace"
)

echo ""
echo "[+] Fuzz run complete"
echo "[+] Looking for crashes..."

for CD in "${CRASH_DIRS[@]}"; do
    if [[ -d "$CD" ]]; then
        CRASHES=$(find "$CD" -type f 2>/dev/null | wc -l)
        if [[ "$CRASHES" -gt 0 ]]; then
            echo "    Found $CRASHES file(s) in $CD"
        fi
    fi
done

echo ""
echo "Next steps:"
echo "  Analyze crashes:"
echo "    python3 $(dirname "$0")/analyze_crashes.py $WORKSPACE/trident-tests/$TEST_NAME"
echo ""
echo "  Debug specific seed (reproduce):"
echo "    cd $WORKSPACE && trident fuzz debug $TEST_NAME <SEED>"
echo ""
echo "  Refresh test if dependencies change:"
echo "    cd $WORKSPACE && trident fuzz refresh $TEST_NAME"
