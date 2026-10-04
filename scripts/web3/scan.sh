#!/bin/bash
# Web3 smart contract scan orchestrator
# Replaces the previous TODO placeholder.
#
# Usage:
#   scan.sh --repo <path> --output <dir> [--mode quick|deep]
#   scan.sh --onchain <chain>:<address> --output <dir> [--mode quick|deep]

set -euo pipefail

MODE="quick"
REPO=""
ONCHAIN=""
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo) REPO="$2"; shift 2 ;;
        --onchain) ONCHAIN="$2"; shift 2 ;;
        --output) OUTPUT_DIR="$2"; shift 2 ;;
        --mode) MODE="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [[ -z "$OUTPUT_DIR" ]]; then
    echo "Usage: scan.sh --repo <path> | --onchain <chain>:<addr>  --output <dir> [--mode quick|deep]"
    exit 1
fi
if [[ -z "$REPO" && -z "$ONCHAIN" ]]; then
    echo "Need --repo or --onchain"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════════════════"
echo "[BBT Web3] Scope: EVM-compatible chains only."
echo "[BBT Web3] Solana / Cosmos / Move not supported in v1."
echo "[BBT Web3] Mode: $MODE"
echo "═══════════════════════════════════════════════════════════════════"

# ─── INPUT RESOLUTION ─────────────────────────────────────────────────────────

PROJECT_DIR=""
IS_VERIFIED="true"
PROXY_INFO=""

if [[ -n "$ONCHAIN" ]]; then
    echo "[*] [1/8] Fetching source from chain..."
    python3 "$SCRIPT_DIR/fetch_source.py" --target "$ONCHAIN" --output "$OUTPUT_DIR"

    SUMMARY="$OUTPUT_DIR/fetch_summary.json"
    if [[ -f "$SUMMARY" ]]; then
        IS_VERIFIED=$(jq -r '.is_verified' "$SUMMARY" 2>/dev/null || echo "false")
        PROXY_DETECTED=$(jq -r '.proxy.is_proxy' "$SUMMARY" 2>/dev/null || echo "false")
        if [[ "$PROXY_DETECTED" == "true" ]]; then
            PROXY_INFO=$(jq -r '.proxy.type' "$SUMMARY")
            echo "[!] Proxy detected: $PROXY_INFO"
        fi
    fi

    if [[ "$IS_VERIFIED" == "true" ]]; then
        PROJECT_DIR="$OUTPUT_DIR/foundry-project"
    else
        echo "[!] Contract not verified — only Mythril (bytecode) will run"
        PROJECT_DIR=""
    fi
else
    PROJECT_DIR="$REPO"
    echo "[*] [1/8] Using local repo: $PROJECT_DIR"
fi

# ─── FRAMEWORK DETECTION ──────────────────────────────────────────────────────

FRAMEWORK="raw"
if [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
    if [[ -f "$PROJECT_DIR/foundry.toml" ]]; then
        FRAMEWORK="foundry"
    elif [[ -f "$PROJECT_DIR/hardhat.config.js" || -f "$PROJECT_DIR/hardhat.config.ts" ]]; then
        FRAMEWORK="hardhat"
    elif [[ -f "$PROJECT_DIR/truffle-config.js" ]]; then
        FRAMEWORK="truffle"
    fi
fi
echo "[*] Framework: $FRAMEWORK"

# ─── COMPILER VERSION ─────────────────────────────────────────────────────────

if [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR" ]]; then
    COMPILER=$(grep -rh "pragma solidity" "$PROJECT_DIR/src" 2>/dev/null \
        | grep -oE "[0-9]+\.[0-9]+\.[0-9]+" | sort -u | tail -1 || echo "0.8.20")
    echo "[*] Compiler: $COMPILER"
    solc-select install "$COMPILER" 2>/dev/null || true
    solc-select use "$COMPILER" 2>/dev/null || true
fi

# ─── SLITHER ──────────────────────────────────────────────────────────────────

if [[ -n "$PROJECT_DIR" && "$IS_VERIFIED" == "true" ]]; then
    echo "[*] [2/8] Running Slither (stock + custom detectors)..."
    CUSTOM_DETECTORS_DIR="$SCRIPT_DIR/detectors"

    if [ -d "$CUSTOM_DETECTORS_DIR" ] && [ -f "$CUSTOM_DETECTORS_DIR/setup.py" ]; then
        if ! python3 -c "import bbt_plugin" 2>/dev/null; then
            echo "  Installing custom detectors plugin (one-time)..."
            pip install --break-system-packages -e "$CUSTOM_DETECTORS_DIR" --quiet \
                2>"$OUTPUT_DIR/plugin_install.log" \
                || echo "  ! Plugin install failed — see plugin_install.log"
        fi
    fi

    SLITHER_FLAGS=(--json "$OUTPUT_DIR/slither.json"
        --filter-paths "lib/,node_modules/,test/,mock/,mocks/,script/,scripts/")
    (cd "$PROJECT_DIR" && slither . "${SLITHER_FLAGS[@]}" 2>"$OUTPUT_DIR/slither.log") \
        || echo "  slither finished with findings (non-zero exit is normal)"
fi

# ─── ADERYN ───────────────────────────────────────────────────────────────────

if [[ -n "$PROJECT_DIR" && "$IS_VERIFIED" == "true" ]]; then
    echo "[*] [3/8] Running Aderyn..."
    (cd "$PROJECT_DIR" && aderyn . --output "$OUTPUT_DIR/aderyn.json" 2>"$OUTPUT_DIR/aderyn.log") \
        || echo "  aderyn finished"
fi

# ─── WAKE ─────────────────────────────────────────────────────────────────────

if [[ -n "$PROJECT_DIR" && "$IS_VERIFIED" == "true" ]]; then
    echo "[*] [4/8] Running Wake (Ackee)..."
    (cd "$PROJECT_DIR" && wake detect all --json > "$OUTPUT_DIR/wake.json" 2>"$OUTPUT_DIR/wake.log") \
        || echo "  wake finished"
fi

# ─── SEMGREP (Decurity rules) ─────────────────────────────────────────────────

if [[ -n "$PROJECT_DIR" && "$IS_VERIFIED" == "true" && -d /opt/semgrep-smart-contracts ]]; then
    echo "[*] [5/8] Running Semgrep with Decurity rules..."
    semgrep --config /opt/semgrep-smart-contracts \
        --json --output "$OUTPUT_DIR/semgrep.json" \
        "$PROJECT_DIR" 2>"$OUTPUT_DIR/semgrep.log" || echo "  semgrep finished"
fi

# ─── DEEP MODE: Mythril + Echidna + Halmos ────────────────────────────────────

if [[ "$MODE" == "deep" ]]; then
    # Mythril — only on smaller files (size limit)
    if [[ -n "$PROJECT_DIR" && "$IS_VERIFIED" == "true" ]]; then
        echo "[*] [6/8] Running Mythril (deep mode)..."
        TOTAL_LINES=$(find "$PROJECT_DIR/src" -name "*.sol" -exec cat {} + 2>/dev/null | wc -l)
        if [[ "$TOTAL_LINES" -lt 2000 ]]; then
            for f in $(find "$PROJECT_DIR/src" -name "*.sol" -size -50k); do
                myth analyze "$f" -o jsonv2 \
                    >> "$OUTPUT_DIR/mythril.jsonl" 2>>"$OUTPUT_DIR/mythril.log" || true
            done
        else
            echo "  skipped (codebase too large: $TOTAL_LINES lines)" > "$OUTPUT_DIR/mythril_skipped.txt"
        fi
    fi

    # Echidna — if property tests exist
    if [[ -n "$PROJECT_DIR" ]] && grep -rq "function echidna_" "$PROJECT_DIR" 2>/dev/null; then
        echo "[*] [7/8] Running Echidna..."
        (cd "$PROJECT_DIR" && echidna . --format json > "$OUTPUT_DIR/echidna.json" 2>"$OUTPUT_DIR/echidna.log") \
            || echo "  echidna finished"
    fi

    # Halmos — if foundry tests exist
    if [[ "$FRAMEWORK" == "foundry" ]]; then
        echo "[*] [8/8] Running Halmos..."
        (cd "$PROJECT_DIR" && halmos --json-output "$OUTPUT_DIR/halmos.json" 2>"$OUTPUT_DIR/halmos.log") \
            || echo "  halmos finished"
    fi
fi

# ─── GITLEAKS ─────────────────────────────────────────────────────────────────

if [[ -n "$PROJECT_DIR" && -d "$PROJECT_DIR/.git" ]]; then
    echo "[*] Running gitleaks for private keys..."
    gitleaks detect --source "$PROJECT_DIR" \
        --report-path "$OUTPUT_DIR/gitleaks.json" \
        --report-format json 2>"$OUTPUT_DIR/gitleaks.log" || true
fi

# ─── CORRELATE ────────────────────────────────────────────────────────────────

echo "[*] Correlating findings..."
python3 "$SCRIPT_DIR/correlate.py" --input "$OUTPUT_DIR" --output "$OUTPUT_DIR/web3_summary.json" || true

echo "═══════════════════════════════════════════════════════════════════"
echo "[+] Web3 scan complete"
echo "    Output: $OUTPUT_DIR/web3_summary.json"
echo "═══════════════════════════════════════════════════════════════════"
