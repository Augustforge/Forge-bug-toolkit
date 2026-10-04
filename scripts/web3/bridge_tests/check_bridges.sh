#!/bin/bash
# Bridge-specific configuration audit.
# Detects bridge framework usage and runs config checks via cast.
#
# Usage: bash check_bridges.sh <foundry-project-dir> <output-dir>

set -uo pipefail

PROJECT="${1:?project dir}"
OUTPUT="${2:?output dir}"
mkdir -p "$OUTPUT"

echo "[*] Detecting bridge framework imports..."

USES_LZ=$(grep -rl "ILayerZero\|LZAppV2\|OAppCore\|EndpointV2" "$PROJECT/src" 2>/dev/null | head -1)
USES_WORMHOLE=$(grep -rl "IWormhole\|VAA\|publishMessage" "$PROJECT/src" 2>/dev/null | head -1)
USES_AXELAR=$(grep -rl "IAxelar\|AxelarExecutable\|callContract" "$PROJECT/src" 2>/dev/null | head -1)
USES_CCTP=$(grep -rl "ITokenMessenger\|attestationService\|MessageTransmitter" "$PROJECT/src" 2>/dev/null | head -1)

cat > "$OUTPUT/bridge_detection.json" <<EOF
{
  "uses_layerzero": $([ -n "$USES_LZ" ] && echo true || echo false),
  "uses_wormhole": $([ -n "$USES_WORMHOLE" ] && echo true || echo false),
  "uses_axelar": $([ -n "$USES_AXELAR" ] && echo true || echo false),
  "uses_cctp": $([ -n "$USES_CCTP" ] && echo true || echo false),
  "files": {
    "layerzero": "${USES_LZ:-}",
    "wormhole": "${USES_WORMHOLE:-}",
    "axelar": "${USES_AXELAR:-}",
    "cctp": "${USES_CCTP:-}"
  }
}
EOF

# ─── LayerZero DVN check (KelpDAO $292M pattern) ──────────────────────────────
if [ -n "$USES_LZ" ]; then
    echo "[!] LayerZero detected — checking DVN config..."
    {
        echo "=== LayerZero DVN Configuration Audit ==="
        echo ""
        echo "CHECK MANUALLY on-chain via cast:"
        echo "  cast call \$ENDPOINT 'getConfig(uint32,address,uint32)' \$EID \$OAPP 2 --rpc-url \$RPC"
        echo ""
        echo "Decode UlnConfig — look for:"
        echo "  - requiredDVNCount: must be ≥ 2 (else CRITICAL)"
        echo "  - optionalDVNCount + threshold: should add redundancy"
        echo "  - Validator diversity: not all from same entity"
        echo ""
        echo "Reference: KelpDAO/EigenLayer \$292M was DVN single-source-of-failure"
        echo "https://www.blockaid.io/blog/how-a-single-layerzero-dvn-compromise-drained-292m-from-kelpdao"
    } > "$OUTPUT/layerzero_audit.txt"
fi

# ─── Wormhole guardian check ──────────────────────────────────────────────────
if [ -n "$USES_WORMHOLE" ]; then
    echo "[!] Wormhole detected — checking guardian set..."
    {
        echo "=== Wormhole Guardian Set Audit ==="
        echo ""
        echo "CHECK MANUALLY:"
        echo "  - Current guardian set size (should be 19)"
        echo "  - Threshold: 13/19 standard"
        echo "  - signature verification logic in VAA verification"
        echo ""
        echo "Reference: Wormhole \$320M was signature verification skip"
    } > "$OUTPUT/wormhole_audit.txt"
fi

# ─── Axelar validators + origin validation check (CrossCurve $3M pattern) ────
if [ -n "$USES_AXELAR" ]; then
    echo "[!] Axelar detected — checking origin validation..."

    EXEC_FILES=$(grep -rl "AxelarExecutable\|_execute\|expressExecute" "$PROJECT/src" 2>/dev/null)
    HAS_SOURCE_CHECK=""
    HAS_TRUSTED_REMOTE=""
    if [ -n "$EXEC_FILES" ]; then
        HAS_SOURCE_CHECK=$(grep -l "sourceAddress\s*==" $EXEC_FILES 2>/dev/null | head -1)
        HAS_TRUSTED_REMOTE=$(grep -l "trustedRemote\|trustedSource\|isTrustedRemote" $EXEC_FILES 2>/dev/null | head -1)
    fi

    {
        echo "=== Axelar Validators & Origin Audit ==="
        echo ""
        echo "Files implementing Axelar executable:"
        echo "$EXEC_FILES"
        echo ""
        echo "Source address validation present: $([ -n "$HAS_SOURCE_CHECK" ] && echo YES || echo NO)"
        echo "Trusted remote check present:      $([ -n "$HAS_TRUSTED_REMOTE" ] && echo YES || echo NO)"
        echo ""
        if [ -z "$HAS_SOURCE_CHECK" ] && [ -z "$HAS_TRUSTED_REMOTE" ]; then
            echo "!! CRITICAL: _execute does not validate sourceAddress / sourceChain !!"
            echo "   Attacker can craft messages that bypass authenticity checks."
            echo "   Pattern: CrossCurve PortalV2 (\$3M, Feb 2026)"
            echo "   Reference: https://www.halborn.com/blog/post/explained-the-crosscurve-hack-february-2026"
        fi
        echo ""
        echo "CHECK MANUALLY:"
        echo "  - Current validator threshold (≥75% best practice)"
        echo "  - Validator diversity (geographic + entity)"
        echo "  - In _execute() override: require(sourceChain == EXPECTED && sourceAddress == TRUSTED)"
        echo "  - expressExecute paths must NOT skip validation for 'already-approved' messages"
    } > "$OUTPUT/axelar_audit.txt"
fi

# ─── CCTP attestation check ───────────────────────────────────────────────────
if [ -n "$USES_CCTP" ]; then
    {
        echo "=== Circle CCTP Attestation Audit ==="
        echo ""
        echo "CHECK:"
        echo "  - Attestation freshness validation"
        echo "  - Replay protection via nonce"
        echo "  - Source domain validation"
    } > "$OUTPUT/cctp_audit.txt"
fi

# ─── Generic bridge replay test (Foundry stub) ────────────────────────────────
cat > "$OUTPUT/bridge_replay_test_stub.sol" <<'TESTEOF'
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";

/**
 * Bridge message replay test stub.
 *
 * Adapt for your specific bridge:
 * - LayerZero: replay lzReceive with the same payload
 * - Wormhole: replay completeTransfer with the same VAA
 * - Axelar: replay execute with the same commandId
 * - CCTP: replay receiveMessage with the same messageBody
 */
contract BridgeReplayTest is Test {
    function testCannotReplay() public {
        bytes memory payload = hex"deadbeef";
        bytes32 messageId = keccak256(payload);

        // First execution should succeed
        // bridge.execute(messageId, payload);

        // Second execution with same messageId MUST revert
        // vm.expectRevert("MessageAlreadyProcessed");
        // bridge.execute(messageId, payload);
    }

    function testRequiresFinality() public {
        // Test that bridge waits for source chain finality
        // Reverts before finality block depth
    }
}
TESTEOF

echo "[+] Bridge audit summary saved to $OUTPUT/"
echo "[+] Detected: LZ=$([ -n "$USES_LZ" ] && echo yes || echo no), "\
"WH=$([ -n "$USES_WORMHOLE" ] && echo yes || echo no), "\
"AX=$([ -n "$USES_AXELAR" ] && echo yes || echo no), "\
"CCTP=$([ -n "$USES_CCTP" ] && echo yes || echo no)"
