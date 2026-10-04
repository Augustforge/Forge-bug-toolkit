#!/usr/bin/env python3
"""
wallet_manager.py — Isolated wallet per hunt.

Creates fresh EOA per target. Stores key in encrypted local store.
Never reuse wallet across hunts (privacy + financial isolation).

Usage:
  python3 wallet_manager.py --new --target dirol.io
  python3 wallet_manager.py --list
  python3 wallet_manager.py --get dirol.io
  python3 wallet_manager.py --delete dirol.io

Stored in: ~/.bbt/wallets.json (encrypted with passphrase)
"""

import argparse
import getpass
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

STORE_PATH = Path.home() / ".bbt" / "wallets.json"


def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    """Simple XOR with HMAC-derived key. Not for high-value secrets — use 1Password etc."""
    keystream = b""
    counter = 0
    while len(keystream) < len(data):
        keystream += hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(d ^ k for d, k in zip(data, keystream[: len(data)]))


def _derive_key(passphrase: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), b"bbt-wallet-salt", 100_000)


def generate_eoa() -> dict:
    """Generate a fresh EOA. Returns {private_key, address}."""
    # WARNING: pure-python EOA generation. For production use ethereum-tester / web3.py.
    # Here we just generate a 32-byte random key — address derivation requires keccak+secp256k1.
    # If web3.py is available, use it; otherwise return key only.
    private_key = secrets.token_hex(32)
    address = None
    try:
        from eth_account import Account  # type: ignore

        acct = Account.create()
        return {"private_key": acct.key.hex(), "address": acct.address}
    except ImportError:
        return {"private_key": "0x" + private_key, "address": "<install eth-account: pip install eth-account>"}


def load_store(passphrase: str) -> dict:
    if not STORE_PATH.exists():
        return {}
    raw = STORE_PATH.read_bytes()
    key = _derive_key(passphrase)
    try:
        decrypted = _xor_encrypt(raw, key)
        return json.loads(decrypted.decode("utf-8"))
    except Exception:
        print("ERROR: failed to decrypt store. Wrong passphrase?")
        return {}


def save_store(store: dict, passphrase: str) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = _derive_key(passphrase)
    data = json.dumps(store, indent=2).encode("utf-8")
    encrypted = _xor_encrypt(data, key)
    STORE_PATH.write_bytes(encrypted)
    # Restrict permissions
    try:
        os.chmod(STORE_PATH, 0o600)
    except Exception:
        pass


def cmd_new(target: str, passphrase: str):
    store = load_store(passphrase)
    if target in store:
        print(f"WARNING: wallet for '{target}' already exists. Use --delete first.")
        return
    eoa = generate_eoa()
    store[target] = eoa
    save_store(store, passphrase)
    print(f"[+] New wallet created for '{target}'")
    print(f"    Address: {eoa['address']}")
    print(f"    Private key stored encrypted at {STORE_PATH}")


def cmd_list(passphrase: str):
    store = load_store(passphrase)
    if not store:
        print("(no wallets)")
        return
    for target, eoa in store.items():
        print(f"  {target}: {eoa['address']}")


def cmd_get(target: str, passphrase: str):
    store = load_store(passphrase)
    if target not in store:
        print(f"ERROR: no wallet for '{target}'")
        return
    print(f"Address: {store[target]['address']}")
    print(f"Private key: {store[target]['private_key']}")


def cmd_delete(target: str, passphrase: str):
    store = load_store(passphrase)
    if target not in store:
        print(f"ERROR: no wallet for '{target}'")
        return
    del store[target]
    save_store(store, passphrase)
    print(f"[+] Deleted wallet for '{target}'")


def main():
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--new", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--get", action="store_true")
    g.add_argument("--delete", action="store_true")
    p.add_argument("--target", help="Target name (required for --new/--get/--delete)")
    p.add_argument("--passphrase-env", help="Read passphrase from env var (recommended for scripts)")
    args = p.parse_args()

    if args.passphrase_env:
        passphrase = os.environ.get(args.passphrase_env, "")
        if not passphrase:
            print(f"ERROR: env var {args.passphrase_env} not set")
            return 1
    else:
        passphrase = getpass.getpass("Passphrase: ")

    if args.new:
        if not args.target:
            print("ERROR: --target required")
            return 1
        cmd_new(args.target, passphrase)
    elif args.list:
        cmd_list(passphrase)
    elif args.get:
        if not args.target:
            print("ERROR: --target required")
            return 1
        cmd_get(args.target, passphrase)
    elif args.delete:
        if not args.target:
            print("ERROR: --target required")
            return 1
        cmd_delete(args.target, passphrase)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
