#!/bin/bash
# Bridge source-amount conservation grep.
# Detects bridge entry functions and flags missing amount-conservation assertions.
# Class: Verus 2026 / Wormhole 2022 / Nomad 2022 — cryptographic verification ≠ semantic verification.
#
# Operational replacement for the cut Python AST detector (false-positive bomb).
# Hit rate: ~60% of class value at 5% of cost. Manual review required for each hit.
#
# Usage: bash source_amount_grep.sh <project-dir> [output-dir]
# Example: bash source_amount_grep.sh ./Verus-Ethereum-Contracts ./out
#
# Related: cross_chain_source_destination_binding.yaml (threat_model)
#          checklists/specialized/bridge.md (manual review checklist)

set -uo pipefail

PROJECT="${1:?project dir required (e.g. ./Verus-Ethereum-Contracts)}"
OUTPUT="${2:-./bridge_source_amount_out}"
mkdir -p "$OUTPUT"

REPORT="$OUTPUT/source_amount_findings.md"

# Entry function name patterns (Sol/Vy + Go/Rust naming conventions).
ENTRY_PATTERNS='submitImports|receiveMessage|claimMessage|relayMessage|completeTransfer|completeTransferWithPayload|process|executeMessage|deliver|finalizeTransfer|SubmitImports|ReceiveMessage|ClaimMessage|RelayMessage|CompleteTransfer|Process|ExecuteMessage|Deliver|FinalizeTransfer|redeem|unlock|mintWithProof'

# Conservation assertion patterns — what we WANT to find inside entry functions.
CONSERVATION_PATTERNS='require\s*\(\s*\w+\s*(<=|>=|==).*verifiedPayload|require.*sum.*locked.*paid|assert.*sum.*burned.*minted|require\s*\(\s*amount\s*<=\s*\w+\.(amount|value|burned|locked)|checkCCEValues|verifyAmountConservation|assertAmountConsistent'

{
    echo "# Bridge Source-Amount Conservation Audit"
    echo ""
    echo "**Target**: \`$PROJECT\`"
    echo "**Generated**: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "**Class**: Verus 2026 / Wormhole 2022 / Nomad 2022 — attested-payload semantic gap"
    echo ""
    echo "## Methodology"
    echo ""
    echo "Looking for bridge entry functions (the ones that consume verified payloads"
    echo "and execute mint/release/transfer) and checking if the function body contains"
    echo "an explicit \`require/assert\` linking the incoming amount to a verified"
    echo "source-chain field. Absence = candidate for Verus 2026 class bug."
    echo ""
    echo "**Manual review required for each hit** — grep gives false positives on"
    echo "non-bridge functions with similar names."
    echo ""
    echo "---"
    echo ""
    echo "## Step 1: Entry functions found"
    echo ""
} > "$REPORT"

ENTRY_HITS=$(grep -rEn "(function|fn|func)\s+($ENTRY_PATTERNS)" \
    --include='*.sol' --include='*.vy' --include='*.go' --include='*.rs' --include='*.move' \
    "$PROJECT" 2>/dev/null)

if [ -z "$ENTRY_HITS" ]; then
    {
        echo "_No bridge entry functions matched._"
        echo ""
        echo "**Possible reasons**: (a) not a bridge, (b) uses non-standard naming"
        echo "(check threat_models/cross_chain_source_destination_binding.yaml for full pattern list),"
        echo "(c) entry function in external library (look in dependencies/lib/node_modules)."
        echo ""
    } >> "$REPORT"
else
    {
        echo "\`\`\`"
        echo "$ENTRY_HITS"
        echo "\`\`\`"
        echo ""
        ENTRY_COUNT=$(echo "$ENTRY_HITS" | wc -l)
        echo "**Total entry function declarations**: $ENTRY_COUNT"
        echo ""
    } >> "$REPORT"
fi

{
    echo "## Step 2: Conservation assertions found anywhere in project"
    echo ""
} >> "$REPORT"

CONSERVATION_HITS=$(grep -rEn "$CONSERVATION_PATTERNS" \
    --include='*.sol' --include='*.vy' --include='*.go' --include='*.rs' --include='*.move' \
    "$PROJECT" 2>/dev/null)

if [ -z "$CONSERVATION_HITS" ]; then
    {
        echo "**🚩 RED FLAG**: zero conservation-style assertions found in entire project."
        echo ""
        echo "If bridge entry functions exist (Step 1) and zero conservation"
        echo "assertions exist, this is a **strong indicator of Verus 2026 class gap**."
        echo "Priority for manual deep-read in J2/J3."
        echo ""
        echo "Next steps:"
        echo "1. Open each entry function file:line from Step 1"
        echo "2. Trace the amount field from payload decode → mint/release call"
        echo "3. Look for any \`require/assert\` involving amount + verified source field"
        echo "4. If none found → escalate per stop_signals.md bridge signal"
        echo ""
    } >> "$REPORT"
else
    {
        echo "\`\`\`"
        echo "$CONSERVATION_HITS"
        echo "\`\`\`"
        echo ""
        CONSERVATION_COUNT=$(echo "$CONSERVATION_HITS" | wc -l)
        echo "**Total conservation-style assertions**: $CONSERVATION_COUNT"
        echo ""
        echo "Manually verify that **each entry function** from Step 1 has at least one"
        echo "conservation assertion in its body or in functions it transitively calls."
        echo "Asymmetry between entry functions (one has, another doesn't) is a strong"
        echo "Alchemix-class signal."
        echo ""
    } >> "$REPORT"
fi

{
    echo "## Step 3: Sentinel-value trust check (Nomad 2022 class)"
    echo ""
} >> "$REPORT"

SENTINEL_HITS=$(grep -rEn 'require\s*\(\s*(merkleRoot|messageHash|stateRoot|verifiedHash)\s*[!=]=\s*(0x00|bytes32\(0\)|0)' \
    --include='*.sol' --include='*.vy' \
    "$PROJECT" 2>/dev/null)

if [ -z "$SENTINEL_HITS" ]; then
    {
        echo "_No sentinel-zero comparisons found (good — Nomad class unlikely here)._"
        echo ""
    } >> "$REPORT"
else
    {
        echo "**🚩 NOMAD 2022 CLASS CANDIDATE**:"
        echo ""
        echo "\`\`\`"
        echo "$SENTINEL_HITS"
        echo "\`\`\`"
        echo ""
        echo "Sentinel zero values used in trust comparison. Verify:"
        echo "1. Can \`0x00\` ever be set as 'trusted' state (e.g., upgrade initializer)?"
        echo "2. Is there fallback path that accepts default zero hash as confirmed?"
        echo "3. Cross-reference Nomad post-mortem in research/_audit_corpus/notes/"
        echo ""
    } >> "$REPORT"
fi

{
    echo "## Step 4: Attestation account validation (Wormhole 2022 class — Solana/Anchor only)"
    echo ""
} >> "$REPORT"

ACCOUNT_HITS=$(grep -rEn "signature_set|signatureSet|guardian_set|guardianSet" \
    --include='*.rs' \
    "$PROJECT" 2>/dev/null)

if [ -z "$ACCOUNT_HITS" ]; then
    {
        echo "_No signatureSet/guardianSet account pattern found (not a Solana bridge or different naming)._"
        echo ""
    } >> "$REPORT"
else
    {
        echo "Solana attestation account pattern detected:"
        echo ""
        echo "\`\`\`"
        echo "$ACCOUNT_HITS"
        echo "\`\`\`"
        echo ""
        echo "**Manual verify**: account creation path validates authorship through"
        echo "legitimate guardian-signing flow (not just 'account exists')."
        echo "Reference: wormhole-2022-signature-bypass in _known_findings.jsonl"
        echo ""
    } >> "$REPORT"
fi

{
    echo "---"
    echo ""
    echo "## Cross-references"
    echo ""
    echo "- Threat model: \`scripts/web3/threat_models/cross_chain_source_destination_binding.yaml\`"
    echo "- Checklist: \`scripts/web3/checklists/specialized/bridge.md\`"
    echo "- Sibling lens (broader): \`scripts/web3/threat_models/attested_amount_trust_gap.yaml\`"
    echo "- Stop signal: bridge-no-conservation = strong escalate (\`sessions/_methodology/stop_signals.md\`)"
    echo "- Case studies: \`research/_audit_corpus/_known_findings.jsonl\` IDs:"
    echo "  - verus-2026-source-amount-forge"
    echo "  - wormhole-2022-signature-bypass"
    echo "  - nomad-2022-merkle-root-init"
    echo "- Reading note: \`research/_audit_corpus/notes/verus_2026_source_amount.md\`"
    echo ""
} >> "$REPORT"

echo "[+] Source-amount audit complete: $REPORT"
echo ""
echo "Next:"
echo "  1. Review the report manually"
echo "  2. If RED FLAGs present → escalate per stop_signals.md"
echo "  3. Feed any GO hypotheses into hypothesis_quality.md 5Q pre-flight"
echo "  4. Append outcome to calibration_log.jsonl with class=[bridge-cross-chain]"
