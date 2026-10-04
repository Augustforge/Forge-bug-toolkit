#!/usr/bin/env python3
"""
burner_connect.py — Helper to drive a controlled browser session connecting the
burner wallet to a target dApp.

This script is **interactive scaffolding** — it doesn't auto-drive a browser
(that would require Playwright/Selenium, which we deliberately avoid for OPSEC).
It prints step-by-step instructions and tracks the session in a JSON log.

The burner wallet (per memory):
    0x000000000000000000000000000000000000dEaD
Funded with small amount on Base. Drain back to main after each hunt.

Usage:
    python3 burner_connect.py --target https://oyster.synfutures.com/ \
        --session sessions/$DOMAIN/wallet_test/
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List


BURNER_ADDRESS = "0x000000000000000000000000000000000000dEaD"
BURNER_README = "bug-bounty-toolkit/wallets/burner_evm_001/README.md"


@dataclass
class TestSession:
    target: str
    started_at: str
    burner_address: str
    observations: List[str] = field(default_factory=list)
    signing_requests: List[dict] = field(default_factory=list)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", required=True)
    parser.add_argument("--session", type=Path, required=True, help="Output session dir")
    args = parser.parse_args(argv)

    args.session.mkdir(parents=True, exist_ok=True)
    log = TestSession(
        target=args.target,
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        burner_address=BURNER_ADDRESS,
    )

    instructions = f"""
Burner connect — {args.target}

Burner wallet: {BURNER_ADDRESS}
See: {BURNER_README}

Pre-flight (every test):
  - Open a fresh incognito window (no shared cookies)
  - Verify VPN/Tor on for OPSEC; do not light up your main IP
  - Make sure burner has only a small balance (<$15)
  - Have DevTools → Network + Console open before clicking Connect

Step 1: Navigate to {args.target}
Step 2: Open the wallet (extension popup or hardware bridge)
Step 3: Confirm the wallet is on the burner address {BURNER_ADDRESS}
Step 4: Click "Connect Wallet" on the dApp
Step 5: Observe:
  - What chains does the dApp request? (eth_requestAccounts → chainId)
  - Does it auto-switch chain? (wallet_switchEthereumChain)
  - Does it request additional permissions? (wallet_requestPermissions)
  - What EIP-712 domain does it use for typed data?
  - What does it ask you to sign on connect (SIWE / personal_sign)?

Step 6: Record observations in the session file:
  {args.session / "session.json"}

Step 7: After test:
  - Disconnect wallet from dApp
  - Clear localStorage/cookies via DevTools
  - Drain remaining burner balance back to main wallet if hunt is over

CRITICAL OPSEC:
  - Never connect the burner to a non-bounty dApp in the same browser session
  - Never reuse a wallet that has previously held >$50
  - Never sign anything the dApp asks for if you don't fully understand the payload
"""
    print(instructions)

    # Write skeleton session file
    session_path = args.session / "session.json"
    session_path.write_text(json.dumps(asdict(log), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSession skeleton written: {session_path}")
    print("Edit it after each observation. signing_requests[] should record every wallet popup.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
