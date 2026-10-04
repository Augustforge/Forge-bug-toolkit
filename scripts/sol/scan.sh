#!/usr/bin/env bash
# scan.sh — Solana orchestrator (fetch + detect + scan + correlate).
#
# Usage:
#   bash scripts/sol/scan.sh --onchain sol:9xQeWv... --output sessions/TARGET
#   bash scripts/sol/scan.sh --local-repo ./my-anchor-repo --output sessions/TARGET
#
# Outputs:
#   $OUTPUT/source_meta.json   (from fetch_program)
#   $OUTPUT/hypothesis/*.json  (from hypothesis scripts)
#   $OUTPUT/specialized/*.json (from specialized hunters)
#   $OUTPUT/detectors/*.json   (from cargo-audit, Sol-azy, Trident, etc.)
#   $OUTPUT/solana_summary.json (correlated)
set -euo pipefail

MODE=""
TARGET=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --onchain) MODE="onchain"; TARGET="$2"; shift 2;;
    --local-repo) MODE="local"; TARGET="$2"; shift 2;;
    --output) OUTPUT="$2"; shift 2;;
    *) echo "[!] Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ -z "$MODE" || -z "$TARGET" || -z "$OUTPUT" ]]; then
  echo "Usage: $0 (--onchain sol:ADDR | --local-repo PATH) --output DIR" >&2
  exit 1
fi

mkdir -p "$OUTPUT"/{hypothesis,specialized,detectors,bytecode}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${PYTHON:-python3}"

echo "[*] Phase 1: chain detection..."
"$PY" "$SCRIPT_DIR/../chain_detect.py" --target "$TARGET" --output "$OUTPUT/chain.json"

echo "[*] Phase 2: source fetch..."
if [[ "$MODE" == "onchain" ]]; then
  ADDR="${TARGET#sol:}"
  ADDR="${ADDR#solana:}"
  "$PY" "$SCRIPT_DIR/fetch_program.py" --address "$ADDR" --output "$OUTPUT"
  SOURCE_PATH="$OUTPUT/source"
else
  SOURCE_PATH="$TARGET"
  echo "[+] Using local repo: $SOURCE_PATH"
fi

if [[ ! -d "$SOURCE_PATH" ]]; then
  echo "[!] No source available at $SOURCE_PATH"
  echo "[!] Will run bytecode-only analysis (Phase S5)"
  # Bytecode pipeline would go here once implemented
  exit 0
fi

echo "[*] Phase 3: hypothesis scan (broader-class scripts)..."
for script in "$SCRIPT_DIR/hypothesis/"*.py; do
  if [[ -f "$script" ]]; then
    name=$(basename "$script" .py)
    "$PY" "$script" --target "$SOURCE_PATH" --output "$OUTPUT/hypothesis/$name" --quiet 2>&1 | head -3 || true
  fi
done

echo "[*] Phase 4: specialized hunters..."
for script in "$SCRIPT_DIR/specialized/"*.py; do
  if [[ -f "$script" ]]; then
    name=$(basename "$script" .py)
    "$PY" "$script" --target "$SOURCE_PATH" --output "$OUTPUT/specialized/$name" --quiet 2>&1 | head -3 || true
  fi
done

echo "[*] Phase 5: Rust ecosystem detectors..."
if [[ -f "$SOURCE_PATH/Cargo.toml" ]] || ls "$SOURCE_PATH"/*/Cargo.toml >/dev/null 2>&1; then
  for script in "$SCRIPT_DIR/detectors/"*.py; do
    if [[ -f "$script" ]]; then
      name=$(basename "$script" .py)
      "$PY" "$script" --target "$SOURCE_PATH" --output "$OUTPUT/detectors/$name" --quiet 2>&1 | head -3 || true
    fi
  done
fi

echo "[*] Phase 6: correlation..."
"$PY" "$SCRIPT_DIR/correlate.py" --scan-dir "$OUTPUT" --output "$OUTPUT/solana_summary.json"

echo ""
echo "[+] Scan complete. Summary: $OUTPUT/solana_summary.json"
echo "[+] Findings:"
"$PY" -c "import json; d=json.load(open('$OUTPUT/solana_summary.json')); print(f'  Total: {d[\"total_findings\"]}'); print(f'  By severity: {d[\"by_severity\"]}'); print(f'  Novel: {d[\"novel_instances\"]} / Known: {d[\"known_classes\"]}')" 2>/dev/null || true
