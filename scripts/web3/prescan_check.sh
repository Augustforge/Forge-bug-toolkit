#!/bin/bash
# Web3 target pre-scan validation
# Quickly answers: "is this target worth scanning?"
#
# Usage: prescan_check.sh <chain>:<address>
#   e.g. prescan_check.sh eth:0x1234...
#
# Exit codes:
#   0 = PASS — good target, proceed with scan
#   1 = SKIP — not worth scanning (reason printed)
#   2 = WARN — proceed but with caveats

set -euo pipefail

TARGET="${1:?Usage: prescan_check.sh <chain>:<address>}"
CHAIN="${TARGET%%:*}"
ADDRESS="${TARGET##*:}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "═══════════════════════════════════════════════════════════════════"
echo "[BBT Web3] Pre-scan target validation: $TARGET"
echo "═══════════════════════════════════════════════════════════════════"

PASS=0
WARN=0
FAIL=0

check() {
    local status="$1"
    local label="$2"
    local detail="$3"
    case "$status" in
        PASS) echo "  [+] $label: $detail" ; ((PASS++)) ;;
        WARN) echo "  [~] $label: $detail" ; ((WARN++)) ;;
        FAIL) echo "  [-] $label: $detail" ; ((FAIL++)) ;;
    esac
}

# ─── CHECK 1: Address format ──────────────────────────────────────────────────

if [[ ! "$ADDRESS" =~ ^0x[0-9a-fA-F]{40}$ ]]; then
    echo "[SKIP] Invalid address format: $ADDRESS"
    exit 1
fi
check PASS "Address format" "valid EVM address"

# ─── CHECK 2: Chain support ───────────────────────────────────────────────────

declare -A CHAIN_IDS=([eth]=1 [bsc]=56 [polygon]=137 [arbitrum]=42161
                      [optimism]=10 [base]=8453 [avalanche]=43114 [fantom]=250
                      [pharos]=1672 [linea]=59144 [scroll]=534352 [zksync]=324)

if [[ -z "${CHAIN_IDS[$CHAIN]+x}" ]]; then
    echo "[SKIP] Chain '$CHAIN' not supported. Supported: ${!CHAIN_IDS[*]}"
    exit 1
fi
CHAIN_ID="${CHAIN_IDS[$CHAIN]}"
check PASS "Chain" "$CHAIN (chainid=$CHAIN_ID)"

# ─── CHECK 3: Contract verified on Etherscan V2 ───────────────────────────────

ETHERSCAN_KEY="${ETHERSCAN_API_KEY:-}"
IS_VERIFIED="false"
PROXY_FLAG=""
COMPILER_VERSION=""
CONTRACT_NAME=""

if [[ -n "$ETHERSCAN_KEY" ]]; then
    RESP=$(curl -s --max-time 10 \
        "https://api.etherscan.io/v2/api?chainid=${CHAIN_ID}&module=contract&action=getsourcecode&address=${ADDRESS}&apikey=${ETHERSCAN_KEY}" \
        2>/dev/null || echo "{}")

    SOURCE=$(echo "$RESP" | python3 -c "import sys,json; r=json.load(sys.stdin)['result'][0]; print(r.get('SourceCode',''))" 2>/dev/null || echo "")
    CONTRACT_NAME=$(echo "$RESP" | python3 -c "import sys,json; r=json.load(sys.stdin)['result'][0]; print(r.get('ContractName',''))" 2>/dev/null || echo "")
    COMPILER_VERSION=$(echo "$RESP" | python3 -c "import sys,json; r=json.load(sys.stdin)['result'][0]; print(r.get('CompilerVersion',''))" 2>/dev/null || echo "")
    PROXY_ADDRESS=$(echo "$RESP" | python3 -c "import sys,json; r=json.load(sys.stdin)['result'][0]; print(r.get('Implementation',''))" 2>/dev/null || echo "")

    if [[ -n "$SOURCE" && "$SOURCE" != "{}" ]]; then
        IS_VERIFIED="true"
        check PASS "Source verified" "$CONTRACT_NAME ($COMPILER_VERSION)"
        [[ -n "$PROXY_ADDRESS" && "$PROXY_ADDRESS" != "0x0000000000000000000000000000000000000000" ]] && \
            check WARN "Proxy detected" "impl=$PROXY_ADDRESS — will scan both"
    else
        check FAIL "Source NOT verified" "bytecode-only — only Mythril can run"
    fi
else
    check WARN "Etherscan check" "ETHERSCAN_API_KEY not set — skipping verification check"
fi

# ─── CHECK 4: TVL via DeFiLlama ───────────────────────────────────────────────

TVL=0
TVL_STR="unknown"
PROTOCOL_NAME=""

LLAMA_RESP=$(curl -s --max-time 10 \
    "https://api.llama.fi/protocols" 2>/dev/null || echo "[]")

MATCH=$(echo "$LLAMA_RESP" | python3 -c "
import sys, json
addr_lower = '${ADDRESS}'.lower()
protocols = json.load(sys.stdin)
for p in protocols:
    addrs = str(p.get('address','') or '').lower()
    if addr_lower in addrs:
        print(p.get('name',''), p.get('tvl', 0))
        break
" 2>/dev/null || echo "")

if [[ -n "$MATCH" ]]; then
    PROTOCOL_NAME=$(echo "$MATCH" | awk '{print $1}')
    TVL=$(echo "$MATCH" | awk '{print $2}' | cut -d'.' -f1)
    TVL_STR="\$$TVL"

    if [[ "$TVL" -ge 1000000 ]]; then
        check PASS "TVL" "$TVL_STR — high-value target"
    elif [[ "$TVL" -ge 100000 ]]; then
        check WARN "TVL" "$TVL_STR — medium value"
    else
        check WARN "TVL" "$TVL_STR — low value (bounty may be small)"
    fi
else
    check WARN "TVL" "not found on DeFiLlama (new protocol or not indexed)"
fi

# ─── CHECK 5: Immunefi scope ──────────────────────────────────────────────────

IN_SCOPE="false"
IMMUNEFI_PROGRAM=""
MAX_BOUNTY=""

PROJECTS_JSON="$HOME/.bbt/cache/immunefi_projects.json"
if [[ ! -f "$PROJECTS_JSON" || $(find "$PROJECTS_JSON" -mmin +60 2>/dev/null | wc -l) -gt 0 ]]; then
    mkdir -p "$HOME/.bbt/cache"
    curl -s --max-time 15 \
        "https://raw.githubusercontent.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial/main/projects.json" \
        -o "$PROJECTS_JSON" 2>/dev/null || true
fi

if [[ -f "$PROJECTS_JSON" ]]; then
    SCOPE_CHECK=$(python3 -c "
import json, sys
addr_lower = '${ADDRESS}'.lower()
try:
    data = json.load(open('$PROJECTS_JSON'))
    for program in data:
        assets = program.get('assets', []) or []
        for a in assets:
            if addr_lower in str(a.get('address','')).lower():
                print(program.get('project',''), program.get('maxBounty', ''))
                sys.exit(0)
except Exception:
    pass
" 2>/dev/null || echo "")

    if [[ -n "$SCOPE_CHECK" ]]; then
        IMMUNEFI_PROGRAM=$(echo "$SCOPE_CHECK" | awk '{print $1}')
        MAX_BOUNTY=$(echo "$SCOPE_CHECK" | awk '{print $2}')
        check PASS "Immunefi scope" "YES — program=$IMMUNEFI_PROGRAM maxBounty=$MAX_BOUNTY"
        IN_SCOPE="true"
    else
        check WARN "Immunefi scope" "not found — coordinated disclosure only"
    fi
else
    check WARN "Immunefi scope" "projects.json unavailable (network error?)"
fi

# ─── CHECK 6: Code age (recent = potentially unaudited) ───────────────────────

if [[ -n "$ETHERSCAN_KEY" && "$IS_VERIFIED" == "true" ]]; then
    CREATION_RESP=$(curl -s --max-time 10 \
        "https://api.etherscan.io/v2/api?chainid=${CHAIN_ID}&module=contract&action=getcontractcreation&contractaddresses=${ADDRESS}&apikey=${ETHERSCAN_KEY}" \
        2>/dev/null || echo "{}")

    CREATION_TS=$(echo "$CREATION_RESP" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(data['result'][0].get('timestamp', 0))
except:
    print(0)
" 2>/dev/null || echo "0")

    if [[ "$CREATION_TS" -gt 0 ]]; then
        NOW=$(date +%s)
        AGE_DAYS=$(( (NOW - CREATION_TS) / 86400 ))
        if [[ "$AGE_DAYS" -le 30 ]]; then
            check PASS "Code age" "${AGE_DAYS}d old — fresh, likely unaudited"
        elif [[ "$AGE_DAYS" -le 90 ]]; then
            check WARN "Code age" "${AGE_DAYS}d old — relatively new"
        else
            check WARN "Code age" "${AGE_DAYS}d old — established, more competition"
        fi
    fi
fi

# ─── VERDICT ──────────────────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "[BBT] Results: PASS=$PASS  WARN=$WARN  FAIL=$FAIL"

if [[ "$IS_VERIFIED" == "false" && "$FAIL" -gt 0 ]]; then
    echo "[SKIP] Contract not verified — limited scan only (bytecode/Mythril)"
    echo "       Consider: fetch from Sourcify, or find GitHub repo"
    exit 2
fi

if [[ "$PASS" -ge 2 ]]; then
    echo "[PROCEED] Target looks good — run scan.sh"
    [[ "$IN_SCOPE" == "true" ]] && echo "          Immunefi program: $IMMUNEFI_PROGRAM (max: $MAX_BOUNTY)"
    exit 0
else
    echo "[CAUTION] Weak target — low TVL or missing scope. Proceed if you have time."
    exit 2
fi
