#!/usr/bin/env bash
# smoke_test.sh — verify Trident infrastructure end-to-end (no real fuzz run)

set +e

echo "=== Trident infrastructure smoke test ==="
echo ""

echo "[1/6] Trident binary..."
which trident && trident --version

echo ""
echo "[2/6] Solana CLI + Anchor..."
solana --version
anchor --version

echo ""
echo "[3/6] Fuzzing scripts present..."
SCRIPT_DIR="/work/scripts/sol/fuzzing"
for f in setup_target.sh run_fuzz.sh analyze_crashes.py README.md; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        echo "  OK: $f"
    else
        echo "  MISSING: $f"
    fi
done

echo ""
echo "[4/6] Invariants library..."
ls "$SCRIPT_DIR/invariants_lib/" | grep .md | sed 's/^/  /'

echo ""
echo "[5/6] Translation guide present..."
if [ -f "$SCRIPT_DIR/invariants_to_flow_guide.md" ]; then
    echo "  OK: invariants_to_flow_guide.md ($(wc -l < $SCRIPT_DIR/invariants_to_flow_guide.md) lines)"
else
    echo "  MISSING: invariants_to_flow_guide.md"
fi

echo ""
echo "[6/6] Help output (setup_target.sh + run_fuzz.sh)..."
bash "$SCRIPT_DIR/setup_target.sh" 2>&1 | head -3
echo "---"
bash "$SCRIPT_DIR/run_fuzz.sh" 2>&1 | head -3

echo ""
echo "=== All checks complete ==="
