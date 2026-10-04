#!/usr/bin/env bash
# setup_target.sh — wrapper around `trident init` for Anchor-based Solana program
#
# Usage:
#   bash setup_target.sh <target_anchor_workspace> [--program NAME] [--test NAME]
#
# Prerequisites:
#   - Target is Anchor workspace (has Anchor.toml + programs/)
#   - Anchor program builds successfully (`anchor build`)
#   - Trident v0.12+ installed
#
# Output:
#   <target>/trident-tests/<test_name>/ with auto-generated:
#     - test_fuzz.rs (main fuzz binary)
#     - fuzz_accounts.rs (account storage)
#     - types.rs (instruction types from IDL)
#   + Trident.toml in trident-tests/
#
# Note: Trident ONLY works with Anchor-based programs. For native Solana
# (Pinocchio, raw solana_program), use solana-program-test manually.

set -euo pipefail

TARGET=""
PROGRAM=""
TEST_NAME="fuzz_0"
PROTOCOL_CLASS=""
SKIP_BUILD=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --program) PROGRAM="$2"; shift 2;;
    --test) TEST_NAME="$2"; shift 2;;
    --class) PROTOCOL_CLASS="$2"; shift 2;;
    --skip-build) SKIP_BUILD=true; shift;;
    *)
      if [[ -z "$TARGET" ]]; then TARGET="$1"; fi
      shift;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "Usage: $0 <target_anchor_workspace> [--program NAME] [--test NAME] [--class amm_clmm|staking_lst|...] [--skip-build]"
  exit 1
fi

if [[ ! -f "$TARGET/Anchor.toml" ]]; then
  echo "[!] Not an Anchor workspace (no Anchor.toml): $TARGET"
  echo "[!] Trident requires Anchor framework. For native Solana use solana-program-test."
  exit 1
fi

# Auto-detect program name if not specified
if [[ -z "$PROGRAM" ]]; then
  PROGRAM=$(grep -hE "^[a-z_]+\s*=\s*\"" "$TARGET/Anchor.toml" 2>/dev/null | head -1 | cut -d= -f1 | tr -d ' ')
  if [[ -z "$PROGRAM" ]]; then
    PROGRAM=$(ls "$TARGET/programs/" 2>/dev/null | head -1)
  fi
fi

if [[ -z "$PROGRAM" ]]; then
  echo "[!] Could not auto-detect program name. Specify with --program NAME"
  exit 1
fi

echo "[*] Setup Trident harness"
echo "    Target: $TARGET"
echo "    Program: $PROGRAM"
echo "    Test name: $TEST_NAME"
echo "    Protocol class: ${PROTOCOL_CLASS:-(none — using default)}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$TARGET"

# Step 1: Build Anchor program (generates IDL)
if [[ "$SKIP_BUILD" == "true" ]]; then
  if [[ ! -d "target/idl" ]]; then
    echo "[!] target/idl/ not present and --skip-build. Trident init may fail."
  fi
else
  echo ""
  echo "[*] Building Anchor program (anchor build)..."
  anchor build 2>&1 | tail -10
fi

# Step 2: Run trident init
echo ""
echo "[*] Running: trident init -p $PROGRAM -t $TEST_NAME"
INIT_FLAGS="-p $PROGRAM -t $TEST_NAME"
if [[ "$SKIP_BUILD" == "true" ]]; then INIT_FLAGS="$INIT_FLAGS --skip-build"; fi

trident init $INIT_FLAGS 2>&1 | tee /tmp/trident_init.log
if [[ ${PIPESTATUS[0]} -ne 0 ]]; then
  echo "[!] trident init failed. Check /tmp/trident_init.log"
  exit 1
fi

# Step 3: Copy relevant invariants library to test directory
if [[ -n "$PROTOCOL_CLASS" ]]; then
  INV_LIB="$SCRIPT_DIR/invariants_lib/${PROTOCOL_CLASS}.md"
  CROSS_LIB="$SCRIPT_DIR/invariants_lib/cross_program.md"
  TEST_DIR="trident-tests/$TEST_NAME"

  if [[ -f "$INV_LIB" && -d "$TEST_DIR" ]]; then
    cp "$INV_LIB" "$TEST_DIR/INVARIANTS_${PROTOCOL_CLASS^^}.md"
    cp "$CROSS_LIB" "$TEST_DIR/INVARIANTS_CROSS_PROGRAM.md"
    echo "[+] Invariants library copied to $TEST_DIR/"
  else
    echo "[!] Invariants library for class '$PROTOCOL_CLASS' not found"
  fi
fi

# Step 4: Output instructions
cat <<EOF

==============================================================
[+] Trident harness initialized!

Location: $TARGET/trident-tests/$TEST_NAME/

Files generated (by Trident):
  - test_fuzz.rs       Main fuzz binary (#[flow_executor] impl)
  - fuzz_accounts.rs   Account storage struct
  - types.rs           Instruction types (from Anchor IDL)

Files copied from invariants_lib:
  - INVARIANTS_*.md    Reference invariants for protocol class

==============================================================
NEXT STEPS:

1. Customize test_fuzz.rs:
   - Implement #[init] to setup initial state
   - Add #[flow] methods for each instruction to fuzz
   - Add assertions inside flows = invariants

   Reference: INVARIANTS_<CLASS>.md for what to assert

2. Translate invariants from library to flow code:

   Library text:
     "I1: Vault solvency: vault.balance >= state.escrowed_orca_amount"

   In flow method:
     let vault_balance = self.trident.get_account_lamports(&self.fuzz_accounts.vault);
     let state = self.trident.get_account_with_type::<State>(&state_pda, 8);
     assert!(vault_balance >= state.escrowed_orca_amount,
             "Vault solvency violated!");

3. Run fuzz:
   bash $SCRIPT_DIR/run_fuzz.sh $TARGET/trident-tests/$TEST_NAME

4. Trident docs: https://ackee.xyz/trident/docs/

EOF
