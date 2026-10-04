#!/usr/bin/env bash
# Start mempool watcher. Wraps watcher.py with sensible defaults.
#
# Usage:
#   bash start_watcher.sh --chains eth --patterns large_admin_withdrawal --dry-run
#   bash start_watcher.sh --chains eth,arb,base --patterns all
#   bash start_watcher.sh --chains eth --patterns all --mock

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load .env if exists
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.env"
    set +a
fi

cd "$REPO_ROOT"
exec python3 scripts/web3/mempool/watcher.py "$@"
