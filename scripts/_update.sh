#!/bin/bash
# Update all toolkit data sources and tool databases.
# Run weekly via cron or manually before serious hunting.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="$ROOT/scripts/_data"
mkdir -p "$DATA_DIR"

echo "═══════════════════════════════════════════════════════════════════"
echo "[BBT] Updating all sources..."
echo "═══════════════════════════════════════════════════════════════════"

# ─── Nuclei templates ─────────────────────────────────────────────────────────
echo "[*] Updating nuclei templates..."
nuclei -update-templates -silent 2>/dev/null \
    || (command -v docker >/dev/null && docker run --rm projectdiscovery/nuclei:latest -update-templates -silent) \
    || echo "  nuclei not found, skip"

# ─── Immunefi programs JSON ───────────────────────────────────────────────────
echo "[*] Refreshing Immunefi programs database..."
curl -sSL "https://raw.githubusercontent.com/infosec-us-team/Immunefi-Bug-Bounty-Programs-Unofficial/main/projects.json" \
    -o "$DATA_DIR/immunefi_projects.json" \
    && echo "  $(jq length "$DATA_DIR/immunefi_projects.json" 2>/dev/null || echo 0) programs cached" \
    || echo "  failed"

# ─── Bounty targets data (HackerOne, Bugcrowd, Intigriti, YesWeHack scope) ────
echo "[*] Refreshing bounty-targets-data..."
for platform in hackerone bugcrowd intigriti yeswehack; do
    curl -sSL "https://raw.githubusercontent.com/arkadiyt/bounty-targets-data/main/data/${platform}_data.json" \
        -o "$DATA_DIR/${platform}_data.json" \
        && echo "  ${platform}: ok" \
        || echo "  ${platform}: failed"
done

# ─── PayloadsAllTheThings ─────────────────────────────────────────────────────
echo "[*] Updating PayloadsAllTheThings..."
if [[ -d "$DATA_DIR/PayloadsAllTheThings" ]]; then
    git -C "$DATA_DIR/PayloadsAllTheThings" pull --quiet || echo "  pull failed"
else
    git clone --depth 1 https://github.com/swisskyrepo/PayloadsAllTheThings.git \
        "$DATA_DIR/PayloadsAllTheThings" 2>/dev/null || echo "  clone failed"
fi

# ─── Decurity Semgrep rules ───────────────────────────────────────────────────
echo "[*] Updating Decurity semgrep rules..."
if [[ -d "$DATA_DIR/semgrep-smart-contracts" ]]; then
    git -C "$DATA_DIR/semgrep-smart-contracts" pull --quiet || true
else
    git clone --depth 1 https://github.com/Decurity/semgrep-smart-contracts.git \
        "$DATA_DIR/semgrep-smart-contracts" 2>/dev/null || true
fi

# ─── SWC Registry ─────────────────────────────────────────────────────────────
echo "[*] Refreshing SWC Registry..."
curl -sSL "https://raw.githubusercontent.com/SmartContractSecurity/SWC-registry/master/export/swc-definition.json" \
    -o "$DATA_DIR/swc.json" 2>/dev/null \
    && echo "  ok" || echo "  failed"

# ─── VRT (Bugcrowd Vulnerability Rating Taxonomy) ─────────────────────────────
echo "[*] Refreshing VRT..."
curl -sSL "https://raw.githubusercontent.com/bugcrowd/vulnerability-rating-taxonomy/master/vulnerability-rating-taxonomy.json" \
    -o "$DATA_DIR/vrt.json" 2>/dev/null \
    && echo "  ok" || echo "  failed"

# ─── Threat intel (RSS-based) ─────────────────────────────────────────────────
echo "[*] Updating threat intelligence..."
if [[ -f "$SCRIPT_DIR/web3/update_threat_intel.py" ]]; then
    python3 "$SCRIPT_DIR/web3/update_threat_intel.py" 2>/dev/null || echo "  threat intel updater failed"
else
    echo "  update_threat_intel.py not yet implemented"
fi

# ─── Foundry tools (forge/cast) ───────────────────────────────────────────────
if command -v foundryup >/dev/null; then
    echo "[*] Updating Foundry..."
    foundryup 2>/dev/null || echo "  failed"
fi

echo "═══════════════════════════════════════════════════════════════════"
echo "[+] Update complete. Data in: $DATA_DIR"
echo "═══════════════════════════════════════════════════════════════════"
