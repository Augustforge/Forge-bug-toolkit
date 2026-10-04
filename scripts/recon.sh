#!/bin/bash
# Passive + Active recon pipeline
# Usage: ./recon.sh <domain> <output_dir>

set -euo pipefail

DOMAIN="${1:?Usage: recon.sh <domain> <output_dir>}"
OUTPUT_DIR="${2:?Usage: recon.sh <domain> <output_dir>}"

mkdir -p "$OUTPUT_DIR"

echo "[*] Starting recon for: $DOMAIN"
echo "[*] Output: $OUTPUT_DIR"

# ─── PASSIVE RECON ────────────────────────────────────────────────────────────

echo "[*] [1/8] Certificate transparency (crt.sh)..."
curl -s "https://crt.sh/?q=%25.$DOMAIN&output=json" 2>/dev/null \
    | jq -r '.[].name_value' 2>/dev/null \
    | sort -u \
    | grep -v '\*' \
    > "$OUTPUT_DIR/crt_subdomains.txt" || echo "  crt.sh failed or no results"

echo "[*] [2/8] Wayback Machine URLs..."
echo "$DOMAIN" | waybackurls 2>/dev/null \
    | sort -u \
    > "$OUTPUT_DIR/wayback_urls.txt" || echo "  waybackurls failed"

echo "[*] [3/8] DNS zone transfer attempt..."
for ns in $(dig NS "$DOMAIN" +short 2>/dev/null); do
    dig AXFR "$DOMAIN" "@$ns" 2>/dev/null >> "$OUTPUT_DIR/zone_transfer.txt" || true
done

# ─── ACTIVE RECON ─────────────────────────────────────────────────────────────

# SecLists wordlists if available
SUBDOMAIN_WORDLIST="${SECLISTS:-/opt/seclists}/Discovery/DNS/subdomains-top1million-110000.txt"

echo "[*] [4/8] Subdomain enumeration (subfinder + bruteforce)..."
subfinder -d "$DOMAIN" -silent -o "$OUTPUT_DIR/subfinder.txt" 2>/dev/null || echo "  subfinder failed"
if [ -f "$SUBDOMAIN_WORDLIST" ] && command -v dnsx >/dev/null; then
    echo "  + DNS bruteforce with SecLists top-110k..."
    dnsx -silent -d "$DOMAIN" -w "$SUBDOMAIN_WORDLIST" -t 50 \
        -o "$OUTPUT_DIR/dnsx_brute.txt" 2>/dev/null || true
    cat "$OUTPUT_DIR/dnsx_brute.txt" 2>/dev/null >> "$OUTPUT_DIR/subfinder.txt" || true
fi

echo "[*] [5/8] Subdomain enumeration (assetfinder)..."
assetfinder --subs-only "$DOMAIN" 2>/dev/null \
    > "$OUTPUT_DIR/assetfinder.txt" || echo "  assetfinder failed"

# Merge all subdomains
cat "$OUTPUT_DIR/crt_subdomains.txt" \
    "$OUTPUT_DIR/subfinder.txt" \
    "$OUTPUT_DIR/assetfinder.txt" \
    2>/dev/null | sort -u > "$OUTPUT_DIR/all_subdomains.txt"

echo "[*] [6/8] Checking live hosts (httpx)..."
cat "$OUTPUT_DIR/all_subdomains.txt" | httpx -silent -status-code -title -tech-detect \
    -o "$OUTPUT_DIR/live_hosts.txt" 2>/dev/null || echo "  httpx failed"

echo "[*] [7/8] Port scan on main domain (nmap fast)..."
nmap -T4 -F --open "$DOMAIN" -oN "$OUTPUT_DIR/nmap_fast.txt" 2>/dev/null || echo "  nmap failed"

echo "[*] [8/8] Subdomain takeover check (subjack)..."
subjack -w "$OUTPUT_DIR/all_subdomains.txt" -t 50 -timeout 30 \
    -o "$OUTPUT_DIR/takeover.txt" -ssl 2>/dev/null || echo "  subjack failed or nothing found"

# ─── OUTPUT JSON ──────────────────────────────────────────────────────────────

SUBDOMAIN_COUNT=$(wc -l < "$OUTPUT_DIR/all_subdomains.txt" 2>/dev/null || echo 0)
LIVE_COUNT=$(wc -l < "$OUTPUT_DIR/live_hosts.txt" 2>/dev/null || echo 0)
WAYBACK_COUNT=$(wc -l < "$OUTPUT_DIR/wayback_urls.txt" 2>/dev/null || echo 0)
TAKEOVER_COUNT=$(wc -l < "$OUTPUT_DIR/takeover.txt" 2>/dev/null || echo 0)

cat > "$OUTPUT_DIR/recon_summary.json" <<EOF
{
  "domain": "$DOMAIN",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "subdomains_found": $SUBDOMAIN_COUNT,
  "live_hosts": $LIVE_COUNT,
  "wayback_urls": $WAYBACK_COUNT,
  "potential_takeovers": $TAKEOVER_COUNT,
  "files": {
    "all_subdomains": "$OUTPUT_DIR/all_subdomains.txt",
    "live_hosts": "$OUTPUT_DIR/live_hosts.txt",
    "wayback_urls": "$OUTPUT_DIR/wayback_urls.txt",
    "nmap": "$OUTPUT_DIR/nmap_fast.txt",
    "takeover": "$OUTPUT_DIR/takeover.txt"
  }
}
EOF

echo "[+] Recon complete. Summary:"
echo "    Subdomains : $SUBDOMAIN_COUNT"
echo "    Live hosts : $LIVE_COUNT"
echo "    Wayback URLs: $WAYBACK_COUNT"
echo "    Takeover candidates: $TAKEOVER_COUNT"
echo "[+] Summary saved to $OUTPUT_DIR/recon_summary.json"
