#!/bin/bash
# Regression test — runs the Web3 pipeline on Damn Vulnerable DeFi
# and verifies we still catch known vulnerabilities after any tool update.
#
# Usage: bash test_regression.sh [dvd_path]
#
# If dvd_path not provided, clones DVD v4 latest into /tmp/dvd

set -euo pipefail

DVD_PATH="${1:-/tmp/dvd}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT="/tmp/dvd_regression_$(date +%s)"

# ─── Clone DVD if not present ─────────────────────────────────────────────────

if [[ ! -d "$DVD_PATH" ]]; then
    echo "[*] Cloning Damn Vulnerable DeFi v4..."
    git clone --depth 1 https://github.com/theredguild/damn-vulnerable-defi "$DVD_PATH"
fi

# ─── Run scan in quick mode ───────────────────────────────────────────────────

echo "[*] Running pipeline in quick mode..."
mkdir -p "$OUTPUT"
bash "$SCRIPT_DIR/scan.sh" --repo "$DVD_PATH" --output "$OUTPUT" --mode quick

# ─── Verify expected findings ─────────────────────────────────────────────────

SUMMARY="$OUTPUT/web3_summary.json"
if [[ ! -f "$SUMMARY" ]]; then
    echo "[FAIL] No summary produced at $SUMMARY"
    exit 1
fi

TOTAL=$(jq -r '.findings_total' "$SUMMARY" 2>/dev/null || echo 0)
CRITICAL=$(jq -r '.findings_by_severity.critical // 0' "$SUMMARY" 2>/dev/null || echo 0)
HIGH=$(jq -r '.findings_by_severity.high // 0' "$SUMMARY" 2>/dev/null || echo 0)
TOOLS_RUN=$(jq -r '.tools_run | join(",")' "$SUMMARY" 2>/dev/null || echo "")

echo "═══════════════════════════════════════════════════════════════════"
echo "[Regression Results]"
echo "  Tools run    : $TOOLS_RUN"
echo "  Total        : $TOTAL"
echo "  Critical     : $CRITICAL"
echo "  High         : $HIGH"
echo "═══════════════════════════════════════════════════════════════════"

# ─── Expected categories — DVD v4 has ALL of these patterns ───────────────────

EXPECTED_CATEGORIES=(
    "reentrancy"
    "access"
    "uninitialized"
    "delegatecall"
    "arbitrary"
)

FOUND=0
for cat in "${EXPECTED_CATEGORIES[@]}"; do
    if jq -e --arg c "$cat" '.findings[] | select(.vulnerability | test($c; "i"))' \
            "$SUMMARY" >/dev/null 2>&1; then
        echo "  [✓] Category found: $cat"
        FOUND=$((FOUND + 1))
    else
        echo "  [✗] Category MISSING: $cat"
    fi
done

# ─── Pass/fail criteria ──────────────────────────────────────────────────────

MIN_TOTAL=10
MIN_HIGH_OR_CRIT=3
MIN_CATEGORIES=3

EXIT=0
if [[ "$TOTAL" -lt "$MIN_TOTAL" ]]; then
    echo "[FAIL] Expected ≥$MIN_TOTAL findings, got $TOTAL"
    EXIT=1
fi

HIGH_OR_CRIT=$((CRITICAL + HIGH))
if [[ "$HIGH_OR_CRIT" -lt "$MIN_HIGH_OR_CRIT" ]]; then
    echo "[FAIL] Expected ≥$MIN_HIGH_OR_CRIT high/critical, got $HIGH_OR_CRIT"
    EXIT=1
fi

if [[ "$FOUND" -lt "$MIN_CATEGORIES" ]]; then
    echo "[FAIL] Expected ≥$MIN_CATEGORIES vulnerability categories, got $FOUND"
    EXIT=1
fi

if [[ "$EXIT" -eq 0 ]]; then
    echo "[+] PASS — pipeline catches expected DVD vulnerabilities"
else
    echo "[!] FAIL — investigate which tools regressed"
fi

echo "[i] Full output preserved at: $OUTPUT"
exit $EXIT
