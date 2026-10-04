#!/bin/bash
# TON blockchain C++ node analysis
# Focus: node core (catchain, validator, crypto, tonlib, adnl)
# Approach: brute-force and simple — cppcheck + semgrep flag suspicious spots,
#         Claude verifies each finding manually.
#
# Usage:
#   scan.sh --output <dir> [--src <ton-repo-path>] [--module catchain|all]

set -euo pipefail

OUTPUT_DIR=""
TON_SRC="/opt/ton-src"
MODULE="all"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --src)    TON_SRC="$2";    shift 2 ;;
        --module) MODULE="$2";     shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

[[ -z "$OUTPUT_DIR" ]] && { echo "Usage: scan.sh --output <dir>"; exit 1; }

mkdir -p "$OUTPUT_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════════════════"
echo "[BBT TON] C++ node analysis — catchain / validator / crypto / tonlib"
echo "[BBT TON] Target: $TON_SRC"
echo "═══════════════════════════════════════════════════════════════════"

# ─── CLONE if not present ─────────────────────────────────────────────────────

if [[ ! -d "$TON_SRC" || ! -f "$TON_SRC/CMakeLists.txt" ]]; then
    echo "[*] Cloning ton-blockchain/ton (shallow)..."
    git clone --depth 1 https://github.com/ton-blockchain/ton.git "$TON_SRC"
fi

# ─── TARGET MODULES ───────────────────────────────────────────────────────────
# These specific modules are the most valuable for bug bounty:
# - catchain: consensus protocol — history of critical logic bugs
# - validator: validator logic, block processing
# - crypto: cryptographic operations (unchecked returns = $$$)
# - tonlib: node interaction library
# - adnl/dht/overlay: P2P network layer

if [[ "$MODULE" == "all" ]]; then
    MODULES=("catchain" "validator" "crypto" "tonlib" "adnl" "dht" "overlay" "lite-client")
else
    MODULES=("$MODULE")
fi

# Collect the list of files to analyze
TARGET_DIRS=()
for mod in "${MODULES[@]}"; do
    if [[ -d "$TON_SRC/$mod" ]]; then
        TARGET_DIRS+=("$TON_SRC/$mod")
    fi
done

if [[ ${#TARGET_DIRS[@]} -eq 0 ]]; then
    echo "[!] No target modules found in $TON_SRC"
    exit 1
fi

echo "[*] Analyzing modules: ${MODULES[*]}"
echo "[*] Found dirs: ${#TARGET_DIRS[@]}"

# ─── CPPCHECK ─────────────────────────────────────────────────────────────────

echo ""
echo "[*] [1/3] Running cppcheck..."
cppcheck \
    --enable=all \
    --inconclusive \
    --xml \
    --xml-version=2 \
    --suppress=missingIncludeSystem \
    --suppress=unmatchedSuppression \
    --std=c++17 \
    "${TARGET_DIRS[@]}" \
    2>"$OUTPUT_DIR/cppcheck.xml" || true

# Also plain text for quick viewing
cppcheck \
    --enable=warning,performance,portability,style \
    --inconclusive \
    --std=c++17 \
    "${TARGET_DIRS[@]}" \
    2>"$OUTPUT_DIR/cppcheck.txt" || true

CPPCHECK_COUNT=$(grep -c "error\|warning" "$OUTPUT_DIR/cppcheck.txt" 2>/dev/null || echo 0)
echo "  cppcheck: $CPPCHECK_COUNT findings"

# ─── SEMGREP C++ ──────────────────────────────────────────────────────────────

echo ""
echo "[*] [2/3] Running Semgrep (C++ rules + TON custom patterns)..."

# Standard C/C++ semgrep rules
semgrep \
    --config "p/c" \
    --json \
    --output "$OUTPUT_DIR/semgrep_cpp.json" \
    "${TARGET_DIRS[@]}" \
    2>"$OUTPUT_DIR/semgrep.log" || true

# TON-specific patterns
CUSTOM_RULES="$SCRIPT_DIR/semgrep_ton.yaml"
if [[ -f "$CUSTOM_RULES" ]]; then
    semgrep \
        --config "$CUSTOM_RULES" \
        --json \
        --output "$OUTPUT_DIR/semgrep_ton.json" \
        "${TARGET_DIRS[@]}" \
        2>>"$OUTPUT_DIR/semgrep.log" || true
fi

SEMGREP_COUNT=$(python3 -c "
import json
try:
    d = json.load(open('$OUTPUT_DIR/semgrep_cpp.json'))
    print(len(d.get('results', [])))
except: print(0)
" 2>/dev/null || echo 0)
echo "  semgrep: $SEMGREP_COUNT findings"

# ─── GREP CUSTOM PATTERNS ─────────────────────────────────────────────────────
# Quick patterns specific to TON — from analysis of real CVEs and
# typical mistakes in C++ blockchain nodes

echo ""
echo "[*] [3/3] Scanning for TON-specific patterns..."
{
    echo "=== TON C++ Pattern Scan ==="
    echo "Target: ${TARGET_DIRS[*]}"
    echo ""

    # Unchecked return values (crypto operations are especially dangerous)
    echo "--- [HIGH] Unchecked return values ---"
    grep -rn --include="*.cpp" --include="*.h" \
        -E "(verify|check|validate|decrypt|encrypt|sign)\s*\(" \
        "${TARGET_DIRS[@]}" 2>/dev/null | \
    grep -v "if\s*(\|assert\|CHECK\|LOG_IF\|VLOG_IF\|return\|=\s*(" | \
    head -30 || true

    echo ""
    # Integer conversions without checks (often leads to overflow)
    echo "--- [MEDIUM] Potentially unsafe int casts ---"
    grep -rn --include="*.cpp" --include="*.h" \
        -E "\(int\)|\(unsigned\)|\(td::int32\)|\(td::uint32\)" \
        "${TARGET_DIRS[@]}" 2>/dev/null | head -30 || true

    echo ""
    # Missing size validation before deserialization (TL-B parser)
    echo "--- [HIGH] Unvalidated size before read ---"
    grep -rn --include="*.cpp" --include="*.h" \
        -E "fetch_bytes|fetch_string|fetch_long|as_slice" \
        "${TARGET_DIRS[@]}" 2>/dev/null | \
    grep -v "is_ok\|check()\|CHECK\|if.*size\|status" | \
    head -30 || true

    echo ""
    # Use of assert instead of proper error handling in production code
    echo "--- [MEDIUM] assert() in production paths (use CHECK instead) ---"
    grep -rn --include="*.cpp" \
        -E "^\s*assert\s*\(" \
        "${TARGET_DIRS[@]}" 2>/dev/null | head -20 || true

    echo ""
    # Potential race conditions in catchain
    echo "--- [HIGH] Mutex/lock patterns in catchain/validator ---"
    grep -rn --include="*.cpp" \
        -E "std::mutex|td::Mutex|lock_guard" \
        "$TON_SRC/catchain" "$TON_SRC/validator" 2>/dev/null | head -20 || true

    echo ""
    # Signature comparisons without constant-time (timing attack)
    echo "--- [MEDIUM] Non-constant-time comparisons ---"
    grep -rn --include="*.cpp" --include="*.h" \
        -E "memcmp.*sig|== sig|sig ==" \
        "${TARGET_DIRS[@]}" 2>/dev/null | head -20 || true

} > "$OUTPUT_DIR/ton_patterns.txt"

PATTERN_HITS=$(grep -c "^\s*[^-=]" "$OUTPUT_DIR/ton_patterns.txt" 2>/dev/null || echo 0)
echo "  patterns: $PATTERN_HITS raw hits (needs Claude verification)"

# ─── CORRELATE ────────────────────────────────────────────────────────────────

echo ""
echo "[*] Correlating findings..."
python3 "$SCRIPT_DIR/correlate.py" \
    --input "$OUTPUT_DIR" \
    --output "$OUTPUT_DIR/ton_summary.json" || true

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "[+] TON scan complete"
echo "    cppcheck findings : $CPPCHECK_COUNT"
echo "    semgrep findings  : $SEMGREP_COUNT"
echo "    pattern hits      : $PATTERN_HITS"
echo "    Output: $OUTPUT_DIR/ton_summary.json"
echo ""
echo "[!] Next step: Claude AI pass"
echo "    Read ton_summary.json + checklists/cpp_logic.md"
echo "    Verify each HIGH finding manually (brute-force and simple)"
echo "═══════════════════════════════════════════════════════════════════"
