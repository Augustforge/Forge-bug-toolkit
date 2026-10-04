#!/usr/bin/env python3
"""solana_wallet_manager.py — isolated keypair per hunt + reputation tracking.

Every Solana hunt should use a fresh keypair, never reuse one.
Tying a whitehat handle to one wallet = OPSEC leak (chain analytics can see all your activities).

Usage:
    python3 solana_wallet_manager.py create --hunt-id loopscale-2025-05
    python3 solana_wallet_manager.py list
    python3 solana_wallet_manager.py rotate --hunt-id loopscale-2025-05  # marks old as retired
"""
import argparse, json, os, subprocess, sys
from datetime import datetime
from pathlib import Path


HUNTS_DIR = Path.home() / ".bbt" / "sol_wallets"


def _hunts_dir() -> Path:
    HUNTS_DIR.mkdir(parents=True, exist_ok=True)
    return HUNTS_DIR


def cmd_create(args):
    hunt_id = args.hunt_id
    wallet_dir = _hunts_dir() / hunt_id
    if wallet_dir.exists():
        print(f"[!] Wallet for {hunt_id} already exists. Use 'rotate' to retire it.", file=sys.stderr)
        return 1
    wallet_dir.mkdir(parents=True)
    keypair = wallet_dir / "keypair.json"
    try:
        subprocess.run(
            ["solana-keygen", "new", "--no-bip39-passphrase", "--silent", "-o", str(keypair)],
            check=True, capture_output=True, timeout=30,
        )
    except FileNotFoundError:
        print("[!] solana-keygen not installed. Install Solana CLI first.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"[!] solana-keygen failed: {e.stderr.decode()}", file=sys.stderr)
        return 1

    pubkey = subprocess.run(
        ["solana-keygen", "pubkey", str(keypair)],
        check=True, capture_output=True, timeout=10,
    ).stdout.decode().strip()

    metadata = {
        "hunt_id": hunt_id,
        "pubkey": pubkey,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "status": "active",
        "target": args.target or "",
        "platform": args.platform or "",
        "notes": [],
    }
    (wallet_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print(f"[+] Created isolated wallet for hunt '{hunt_id}'")
    print(f"    pubkey: {pubkey}")
    print(f"    keypair: {keypair}")
    print(f"\n[!] OPSEC checklist:")
    print(f"    1. Fund this wallet ONLY from a mixer or fresh CEX off-ramp.")
    print(f"    2. Never link to your main Solana wallet.")
    print(f"    3. Use a different pseudonym for each program's submission portal.")
    return 0


def cmd_list(args):
    hunts = sorted(_hunts_dir().glob("*/metadata.json"))
    if not hunts:
        print("[*] No hunt wallets yet. Create with 'create --hunt-id X'.")
        return 0
    print(f"=== Hunt Wallets ({len(hunts)}) ===\n")
    for m in hunts:
        data = json.loads(m.read_text())
        status_tag = "[ACTIVE]" if data["status"] == "active" else "[retired]"
        print(f"{status_tag} {data['hunt_id']:30} {data['pubkey']:44} created {data['created_at'][:10]}")
        if data.get("target"):
            print(f"           target: {data['target']}")
    return 0


def cmd_rotate(args):
    wallet_dir = _hunts_dir() / args.hunt_id
    if not wallet_dir.exists():
        print(f"[!] No wallet for {args.hunt_id}", file=sys.stderr)
        return 1
    meta_path = wallet_dir / "metadata.json"
    data = json.loads(meta_path.read_text())
    data["status"] = "retired"
    data["retired_at"] = datetime.utcnow().isoformat() + "Z"
    meta_path.write_text(json.dumps(data, indent=2))
    print(f"[+] Marked {args.hunt_id} as retired. Keypair preserved for audit.")
    return 0


def cmd_note(args):
    wallet_dir = _hunts_dir() / args.hunt_id
    if not wallet_dir.exists():
        print(f"[!] No wallet for {args.hunt_id}", file=sys.stderr)
        return 1
    meta_path = wallet_dir / "metadata.json"
    data = json.loads(meta_path.read_text())
    data.setdefault("notes", []).append({
        "ts": datetime.utcnow().isoformat() + "Z",
        "text": args.text,
    })
    meta_path.write_text(json.dumps(data, indent=2))
    print(f"[+] Note added")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Solana isolated wallet manager")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("--hunt-id", required=True)
    p_create.add_argument("--target", help="Target program/protocol name")
    p_create.add_argument("--platform", help="Immunefi/Sec3/direct")
    p_create.set_defaults(func=cmd_create)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)

    p_rotate = sub.add_parser("rotate")
    p_rotate.add_argument("--hunt-id", required=True)
    p_rotate.set_defaults(func=cmd_rotate)

    p_note = sub.add_parser("note")
    p_note.add_argument("--hunt-id", required=True)
    p_note.add_argument("--text", required=True)
    p_note.set_defaults(func=cmd_note)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
