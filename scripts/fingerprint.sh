#!/bin/bash
# Technology fingerprinting + favicon hash + WAF detection
# Usage: ./fingerprint.sh <domain> <output_dir>

set -euo pipefail

DOMAIN="${1:?Usage: fingerprint.sh <domain> <output_dir>}"
OUTPUT_DIR="${2:?Usage: fingerprint.sh <domain> <output_dir>}"

mkdir -p "$OUTPUT_DIR"
TARGET="https://$DOMAIN"

echo "[*] Fingerprinting: $DOMAIN"

# ─── HTTP HEADERS ─────────────────────────────────────────────────────────────

echo "[*] [1/5] HTTP headers..."
curl -s -I -L "$TARGET" > "$OUTPUT_DIR/headers.txt" 2>/dev/null || echo "  curl failed"

# Security headers analysis — each missing one = a valid low/medium severity finding
echo "[*] [1b/5] Security headers analysis..."
python3 - "$OUTPUT_DIR/headers.txt" "$OUTPUT_DIR/security_headers.json" <<'PYEOF' 2>/dev/null || echo "  analysis skipped"
import json, re, sys
headers_file, output_file = sys.argv[1], sys.argv[2]
try:
    raw = open(headers_file, encoding="utf-8", errors="ignore").read()
except FileNotFoundError:
    sys.exit()
hdrs = {}
for line in raw.splitlines():
    m = re.match(r"^([A-Za-z0-9-]+):\s*(.+)$", line)
    if m:
        hdrs[m.group(1).lower()] = m.group(2).strip()

issues = []
def add(severity, finding, recommendation=""):
    issues.append({"severity": severity, "finding": finding, "recommendation": recommendation})

# HSTS
hsts = hdrs.get("strict-transport-security", "")
if not hsts:
    add("medium", "HSTS missing", "Add Strict-Transport-Security: max-age=31536000; includeSubDomains; preload")
else:
    m = re.search(r"max-age=(\d+)", hsts)
    if m and int(m.group(1)) < 15768000:
        add("low", f"HSTS max-age too short ({m.group(1)})", "Set max-age >= 15768000 (6 months)")
    if "includesubdomains" not in hsts.lower():
        add("low", "HSTS missing includeSubDomains")

# CSP
csp = hdrs.get("content-security-policy", "")
if not csp:
    add("medium", "CSP missing", "Add Content-Security-Policy with strict directives")
else:
    if "unsafe-inline" in csp:
        add("medium", "CSP allows unsafe-inline (XSS amplifier)")
    if "unsafe-eval" in csp:
        add("medium", "CSP allows unsafe-eval")
    if "*" in csp.split("script-src")[1].split(";")[0] if "script-src" in csp else False:
        add("medium", "CSP script-src uses wildcard")

# Other security headers
if "x-frame-options" not in hdrs and (not csp or "frame-ancestors" not in csp):
    add("low", "X-Frame-Options + frame-ancestors missing", "Clickjacking possible")
if "x-content-type-options" not in hdrs:
    add("low", "X-Content-Type-Options missing", "Add: nosniff")
if "referrer-policy" not in hdrs:
    add("info", "Referrer-Policy missing")
if "permissions-policy" not in hdrs:
    add("info", "Permissions-Policy missing")

# Cookie analysis
sc = hdrs.get("set-cookie", "")
if sc:
    if "httponly" not in sc.lower():
        add("medium", "Cookie missing HttpOnly flag", "JS can read session cookie")
    if "secure" not in sc.lower():
        add("medium", "Cookie missing Secure flag", "Cookie sent over HTTP")
    if "samesite" not in sc.lower():
        add("low", "Cookie missing SameSite", "CSRF protection weak")

# Server / version disclosure
if "server" in hdrs and re.search(r"\d+\.\d+", hdrs["server"]):
    add("info", f"Server version disclosed: {hdrs['server']}")
if "x-powered-by" in hdrs:
    add("info", f"X-Powered-By disclosed: {hdrs['x-powered-by']}")

result = {
    "headers": hdrs,
    "issues": issues,
    "severity_counts": {sev: sum(1 for i in issues if i["severity"] == sev)
                        for sev in ("medium", "low", "info")},
}
open(output_file, "w", encoding="utf-8").write(json.dumps(result, indent=2))
print(f"  Security header issues: medium={result['severity_counts']['medium']} "
      f"low={result['severity_counts']['low']} info={result['severity_counts']['info']}")
PYEOF

# ─── TECHNOLOGY DETECTION ─────────────────────────────────────────────────────

echo "[*] [2/5] WhatWeb scan..."
whatweb -a 3 --log-json="$OUTPUT_DIR/whatweb.json" "$TARGET" 2>/dev/null \
    > "$OUTPUT_DIR/whatweb.txt" || echo "  whatweb failed"

# ─── WAF DETECTION ────────────────────────────────────────────────────────────

echo "[*] [3/5] WAF detection..."
wafw00f "$TARGET" -o "$OUTPUT_DIR/waf.txt" 2>/dev/null || echo "  wafw00f failed"

# ─── FAVICON HASH ─────────────────────────────────────────────────────────────

echo "[*] [4/5] Favicon hash (mmh3)..."
python3 - <<EOF > "$OUTPUT_DIR/favicon.txt" 2>/dev/null || echo "  favicon hash failed"
import requests, base64, codecs, hashlib
try:
    r = requests.get("$TARGET/favicon.ico", timeout=10, verify=False)
    if r.status_code == 200:
        b64 = codecs.encode(r.content, 'base64')
        # mmh3 hash via shodan style
        try:
            import mmh3
            h = mmh3.hash(b64)
            print(f"mmh3_hash: {h}")
            print(f"shodan_query: http.favicon.hash:{h}")
        except ImportError:
            md5 = hashlib.md5(r.content).hexdigest()
            print(f"md5_hash: {md5}")
            print("Install mmh3 for shodan-compatible hashing")
        print(f"size: {len(r.content)} bytes")
    else:
        print(f"favicon not found ({r.status_code})")
except Exception as e:
    print(f"error: {e}")
EOF

# ─── PORT SCAN (top 1000) ─────────────────────────────────────────────────────

echo "[*] [5/5] Port scan top 1000..."
nmap -sV --top-ports 1000 "$DOMAIN" -oN "$OUTPUT_DIR/nmap_full.txt" 2>/dev/null || echo "  nmap failed"

# ─── EXTRACT TECH VERSIONS ────────────────────────────────────────────────────

if [ -f "$OUTPUT_DIR/whatweb.json" ]; then
    jq -r '.[].plugins | keys[]' "$OUTPUT_DIR/whatweb.json" 2>/dev/null \
        | sort -u > "$OUTPUT_DIR/technologies.txt" || true
fi

# ─── SUMMARY ──────────────────────────────────────────────────────────────────

WAF_DETECTED=$(grep -E "is behind|identified" "$OUTPUT_DIR/waf.txt" 2>/dev/null | head -1 || echo "none")
TECH_COUNT=$(wc -l < "$OUTPUT_DIR/technologies.txt" 2>/dev/null || echo 0)

cat > "$OUTPUT_DIR/fingerprint_summary.json" <<EOF
{
  "domain": "$DOMAIN",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "waf": $(echo "$WAF_DETECTED" | jq -R . 2>/dev/null || echo '"unknown"'),
  "technologies_count": $TECH_COUNT,
  "files": {
    "headers": "$OUTPUT_DIR/headers.txt",
    "whatweb": "$OUTPUT_DIR/whatweb.txt",
    "waf": "$OUTPUT_DIR/waf.txt",
    "favicon": "$OUTPUT_DIR/favicon.txt",
    "ports": "$OUTPUT_DIR/nmap_full.txt",
    "technologies": "$OUTPUT_DIR/technologies.txt"
  }
}
EOF

echo "[+] Fingerprint complete:"
echo "    WAF        : $WAF_DETECTED"
echo "    Tech count : $TECH_COUNT"
