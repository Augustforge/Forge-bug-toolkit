#!/usr/bin/env python3
"""
onchain_poc_harness.py — Autonomous on-chain PoC verification for dApp findings.

Policy (per [[feedback-onchain-autonomous-policy]] 2026-05-21):

  - Claude MAY autonomously execute on-chain transactions when needed for
    hypothesis verification or exploit PoC.
  - Default mode = LOCAL FORK (anvil/foundry). Real money never moves.
  - TESTNET mode allowed without prompting (faucet money only).
  - MAINNET requires --mainnet flag AND obeys per-tx + session caps.
  - ALL signed actions logged JSONL to sessions/<DOMAIN>/onchain/signed_actions.jsonl
  - ALL non-zero approvals tracked in revocation_pending.jsonl and revoked at session-end.
  - Burner-only enforcement: refuses if loaded private key derives an address
    different from BURNER_ADDRESS in `.env`.
  - If burner balance below threshold → prints REFILL REQUEST, refuses to send.

Subcommands:
  fork-up            Spin up Anvil fork of a chain (defaults to Base mainnet)
  fork-down          Kill running anvil fork (pid file based)
  balance            Read burner balance across configured chains
  call               eth_call (read-only). No signing, safe everywhere.
  send               Sign and send a tx. Respects mode (fork/testnet/mainnet) + caps.
  sign-typed-data    Sign an EIP-712 typed data payload, emit signature (no broadcast)
  replay-signature   Take a captured signature, attempt verification on a different
                     chain/contract to test cross-chain replay hypotheses (fork only)
  permit-submit      Submit a Permit signature to test allowance state (fork preferred)
  revoke-approval    Set token allowance to 0 for a (token, spender)
  session-end        Auto-revoke pending approvals + emit session summary
  audit-log          Tail sessions/<DOMAIN>/onchain/signed_actions.jsonl

Examples:
  # Start a Base mainnet fork on port 8545 (no real money involved)
  py -3 -X utf8 onchain_poc_harness.py fork-up --chain base

  # Check burner balance on Base mainnet (read-only)
  py -3 -X utf8 onchain_poc_harness.py balance --chain base

  # Sign EIP-712 typed data and emit the signature (no broadcast)
  py -3 -X utf8 onchain_poc_harness.py sign-typed-data --json payload.json

  # Send a real tx on Base testnet (Sepolia) — no cap concerns
  py -3 -X utf8 onchain_poc_harness.py send --chain base-sepolia \\
      --to 0xCOFFEE... --data 0xa9059cbb... --value 0

  # Send a small write on Base mainnet (will check caps + log)
  py -3 -X utf8 onchain_poc_harness.py send --mainnet --chain base \\
      --to 0xCOFFEE... --data 0x...

  # End the session — auto-revokes pending approvals + writes summary
  py -3 -X utf8 onchain_poc_harness.py session-end --session sessions/$DOMAIN
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[3]
WALLET_DIR = REPO_ROOT / "wallets" / "burner_evm_001"
ENV_FILE = WALLET_DIR / ".env"
EXAMPLE_ENV = WALLET_DIR / ".env.example"
PID_FILE = REPO_ROOT / ".cache" / "anvil.pid"

BURNER_ADDRESS_CANON = "0x000000000000000000000000000000000000dEaD".lower()


# ──────────────────────────────────────────────────────────────────────────
# Chain registry — keep names aligned with .env RPC_* vars
# ──────────────────────────────────────────────────────────────────────────

_CHAINS: Dict[str, Dict] = {
    # mainnets
    "ethereum":        {"id": 1,       "tier": "l1", "rpc_env": "RPC_ETHEREUM"},
    "base":            {"id": 8453,    "tier": "l2", "rpc_env": "RPC_BASE"},
    "optimism":        {"id": 10,      "tier": "l2", "rpc_env": "RPC_OPTIMISM"},
    "arbitrum":        {"id": 42161,   "tier": "l2", "rpc_env": "RPC_ARBITRUM"},
    "polygon":         {"id": 137,     "tier": "l2", "rpc_env": "RPC_POLYGON"},
    # testnets
    "sepolia":         {"id": 11155111,"tier": "testnet", "rpc_env": "RPC_SEPOLIA"},
    "base-sepolia":    {"id": 84532,   "tier": "testnet", "rpc_env": "RPC_BASE_SEPOLIA"},
    "optimism-sepolia":{"id": 11155420,"tier": "testnet", "rpc_env": "RPC_OPTIMISM_SEPOLIA"},
    # local fork
    "fork":            {"id": None,    "tier": "fork",    "rpc_env": "RPC_FORK"},
}


# ──────────────────────────────────────────────────────────────────────────
# .env loader (no external deps)
# ──────────────────────────────────────────────────────────────────────────

def _load_env() -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not ENV_FILE.exists():
        # Allow operation in read-only modes (e.g. balance over public RPC, fork)
        # but record that no key is available.
        if EXAMPLE_ENV.exists():
            text = EXAMPLE_ENV.read_text(encoding="utf-8")
        else:
            return env
    else:
        text = ENV_FILE.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _bin(env: Dict[str, str], name: str, fallback: str) -> str:
    candidates: List[str] = []
    val = env.get(name)
    if val:
        candidates.append(val)
    candidates.append(fallback)
    # As last resort, hope it's on PATH
    candidates.append(Path(fallback).name)
    for c in candidates:
        if c and (c == Path(c).name or Path(c).exists()):
            return c
    return candidates[0]


def _cast(env: Dict[str, str], *args: str, env_extra: Optional[Dict[str, str]] = None,
          check: bool = True, capture: bool = True, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """Invoke `cast` with absolute path resolution."""
    cast_bin = _bin(env, "CAST_BIN", str(Path.home() / ".foundry" / "bin" / "cast.exe"))
    cmd = [cast_bin, *args]
    proc_env = os.environ.copy()
    proc_env.update(env_extra or {})
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        env=proc_env,
        timeout=timeout,
        check=False,
    )


def _anvil_bin(env: Dict[str, str]) -> str:
    return _bin(env, "ANVIL_BIN", str(Path.home() / ".foundry" / "bin" / "anvil.exe"))


# ──────────────────────────────────────────────────────────────────────────
# Session log helpers
# ──────────────────────────────────────────────────────────────────────────

def _session_dir(session_arg: Optional[str]) -> Path:
    """Return the onchain-log directory for this session, creating it."""
    if session_arg:
        base = Path(session_arg)
    else:
        # Fallback: scratch under repo
        base = REPO_ROOT / "sessions" / "_scratch"
    p = base / "onchain"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _append_jsonl(path: Path, record: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _log_action(session_arg: Optional[str], record: Dict) -> None:
    record.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
    _append_jsonl(_session_dir(session_arg) / "signed_actions.jsonl", record)


def _log_approval(session_arg: Optional[str], record: Dict) -> None:
    record.setdefault("timestamp", datetime.datetime.now(datetime.timezone.utc).isoformat())
    _append_jsonl(_session_dir(session_arg) / "revocation_pending.jsonl", record)


# ──────────────────────────────────────────────────────────────────────────
# Burner enforcement + cap enforcement
# ──────────────────────────────────────────────────────────────────────────

def _resolve_rpc(env: Dict[str, str], chain: str, fork_url: Optional[str] = None) -> str:
    if chain == "fork":
        return fork_url or env.get("RPC_FORK", "http://127.0.0.1:8545")
    info = _CHAINS.get(chain)
    if not info:
        raise ValueError(f"Unknown chain '{chain}'. Known: {sorted(_CHAINS)}")
    rpc = env.get(info["rpc_env"], "")
    if not rpc:
        raise ValueError(f"No RPC configured for {chain}. Set {info['rpc_env']} in {ENV_FILE}")
    return rpc


def _enforce_burner(env: Dict[str, str]) -> str:
    """Return the burner private key after verifying it derives the canonical address."""
    pk = env.get("BURNER_PRIVATE_KEY", "").strip()
    if not pk:
        raise RuntimeError(
            f"BURNER_PRIVATE_KEY is empty in {ENV_FILE}. "
            f"This is read-only mode only. Aborting any signed action."
        )
    # Derive address from key via `cast wallet address`
    res = _cast(env, "wallet", "address", "--private-key", pk if pk.startswith("0x") else f"0x{pk}")
    if res.returncode != 0:
        raise RuntimeError(f"cast wallet address failed: {res.stderr.strip()}")
    derived = res.stdout.strip().lower()
    declared = env.get("BURNER_ADDRESS", "").lower()
    if declared and derived != declared:
        raise RuntimeError(
            f"Private key derives {derived} but BURNER_ADDRESS declares {declared}. "
            f"Refusing to proceed — possible key mix-up."
        )
    if derived != BURNER_ADDRESS_CANON:
        raise RuntimeError(
            f"Private key derives {derived} but canonical burner is {BURNER_ADDRESS_CANON}. "
            f"Refusing to use a non-burner key (per autonomous policy)."
        )
    return pk if pk.startswith("0x") else f"0x{pk}"


def _enforce_caps(env: Dict[str, str], chain: str, value_wei: int, kind: str = "send") -> None:
    info = _CHAINS.get(chain, {})
    tier = info.get("tier")
    if tier == "fork":
        return  # fork mode — no real money
    if tier == "testnet":
        return  # faucet — no real money

    # Mainnet path
    eth_max = Decimal(env.get(
        "MAX_VALUE_ETH_MAINNET" if tier == "l1" else "MAX_VALUE_ETH_L2",
        "0.001" if tier == "l1" else "0.01",
    ))
    cap_wei = int(eth_max * Decimal(10) ** 18)
    if value_wei > cap_wei:
        raise RuntimeError(
            f"Refusing tx on {chain}: value {value_wei} wei exceeds cap {cap_wei} wei "
            f"(MAX_VALUE_ETH_{'MAINNET' if tier=='l1' else 'L2'}={eth_max}). "
            f"To raise, ask the operator explicitly."
        )


# ──────────────────────────────────────────────────────────────────────────
# Subcommands
# ──────────────────────────────────────────────────────────────────────────

def cmd_fork_up(args) -> int:
    env = _load_env()
    src_chain = args.chain or "base"
    rpc = _resolve_rpc(env, src_chain)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        old_pid = PID_FILE.read_text().strip()
        print(f"Anvil pid file already present ({old_pid}). Use fork-down first.")
        return 2
    anvil = _anvil_bin(env)
    cmd = [
        anvil, "--fork-url", rpc,
        "--port", str(args.port),
        "--host", args.host,
    ]
    if args.block_number:
        cmd += ["--fork-block-number", str(args.block_number)]
    log_path = _session_dir(args.session) / "fork.log"
    print(f"Starting anvil fork:")
    print(f"  source chain: {src_chain}")
    print(f"  rpc:          {rpc}")
    print(f"  bind:         {args.host}:{args.port}")
    print(f"  log:          {log_path}")
    log_handle = log_path.open("ab")
    proc = subprocess.Popen(cmd, stdout=log_handle, stderr=subprocess.STDOUT)
    PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    print(f"  pid:          {proc.pid} (recorded in {PID_FILE})")
    print(f"\nUse --rpc http://{args.host}:{args.port} for subsequent calls.")
    return 0


def cmd_fork_down(args) -> int:
    if not PID_FILE.exists():
        print("No recorded anvil pid. Either fork already down or it was started externally.")
        return 1
    pid = int(PID_FILE.read_text().strip())
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        else:
            os.kill(pid, 15)
        print(f"Killed anvil pid {pid}.")
    except Exception as exc:
        print(f"Failed to kill {pid}: {exc}")
    PID_FILE.unlink(missing_ok=True)
    return 0


def cmd_balance(args) -> int:
    env = _load_env()
    chain = args.chain
    rpc = _resolve_rpc(env, chain)
    addr = env.get("BURNER_ADDRESS", "0x000000000000000000000000000000000000dEaD")
    res = _cast(env, "balance", addr, "--rpc-url", rpc)
    if res.returncode != 0:
        print(f"cast balance failed: {res.stderr.strip()}", file=sys.stderr)
        return res.returncode
    bal_wei = res.stdout.strip()
    try:
        bal_eth = Decimal(bal_wei) / Decimal(10) ** 18
    except Exception:
        bal_eth = "?"
    print(f"chain={chain}  burner={addr}  balance={bal_wei} wei  ({bal_eth} ETH)")
    # Speak-up logic — uses explicit REFILL_THRESHOLD_ETH env var (per operator decision 2026-05-21:
    # $6 on L2 is enough; do not over-request refills).
    threshold_eth = Decimal(env.get("REFILL_THRESHOLD_ETH", "0.0005"))
    if isinstance(bal_eth, Decimal) and bal_eth < threshold_eth and _CHAINS[chain]["tier"] not in ("testnet", "fork"):
        print()
        print(f"  REFILL REQUEST: burner balance on {chain} is {bal_eth} ETH, below {threshold_eth} ETH threshold.")
        print(f"  Cannot run signed actions until refilled. Tell the operator.")
    return 0


def cmd_call(args) -> int:
    env = _load_env()
    rpc = _resolve_rpc(env, args.chain, args.fork_url)
    cmd_args = ["call", args.to, "--rpc-url", rpc]
    if args.data:
        cmd_args.append(args.data)
    elif args.sig:
        cmd_args.extend([args.sig, *(args.params or [])])
    res = _cast(env, *cmd_args)
    if res.returncode != 0:
        print(f"cast call failed: {res.stderr.strip()}", file=sys.stderr)
        return res.returncode
    print(res.stdout.strip())
    _log_action(args.session, {
        "op": "call", "chain": args.chain, "to": args.to,
        "data": args.data, "sig": args.sig, "result": res.stdout.strip()[:500],
    })
    return 0


def cmd_send(args) -> int:
    env = _load_env()
    chain = args.chain
    info = _CHAINS.get(chain, {})
    tier = info.get("tier")
    if tier == "l1" or tier == "l2":
        if not args.mainnet:
            print(f"{chain} is a mainnet — pass --mainnet to confirm. Aborting.", file=sys.stderr)
            return 2
    rpc = _resolve_rpc(env, chain, args.fork_url)
    pk = _enforce_burner(env)

    value_wei = 0
    if args.value:
        value_wei = int(Decimal(args.value) * Decimal(10) ** 18)
    _enforce_caps(env, chain, value_wei)

    cmd_args = [
        "send", args.to,
        "--rpc-url", rpc,
        "--private-key", pk,
        "--value", str(value_wei),
    ]
    if args.data:
        # cast send with --data
        cmd_args.extend(["--data", args.data] if args.data.startswith("0x") else [args.data])
    elif args.sig:
        cmd_args.extend([args.sig, *(args.params or [])])
    else:
        # Plain value transfer
        pass

    if args.gas_price_gwei:
        gwei_cap = Decimal(env.get(
            "MAX_GAS_GWEI_L1" if tier == "l1" else "MAX_GAS_GWEI_L2",
            "50" if tier == "l1" else "5",
        ))
        if Decimal(args.gas_price_gwei) > gwei_cap and tier in ("l1", "l2"):
            print(f"Gas price {args.gas_price_gwei} gwei exceeds cap {gwei_cap} gwei for {chain}. Aborting.", file=sys.stderr)
            return 2
        cmd_args.extend(["--gas-price", str(int(Decimal(args.gas_price_gwei) * Decimal(10) ** 9))])

    print(f"sending tx on {chain} (tier={tier}, value_wei={value_wei})")
    res = _cast(env, *cmd_args, timeout=180)
    record = {
        "op": "send", "chain": chain, "tier": tier, "to": args.to,
        "data": args.data, "sig": args.sig, "value_wei": value_wei,
        "stdout": res.stdout.strip()[:1000], "stderr": res.stderr.strip()[:500],
        "returncode": res.returncode,
    }
    _log_action(args.session, record)
    if res.returncode != 0:
        print(f"send failed: {res.stderr.strip()}", file=sys.stderr)
        return res.returncode
    print(res.stdout.strip())
    return 0


def cmd_sign_typed_data(args) -> int:
    env = _load_env()
    pk = _enforce_burner(env)
    payload_text = args.json
    if Path(payload_text).exists():
        payload_text = Path(payload_text).read_text(encoding="utf-8")
    # Validate JSON
    try:
        parsed = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON: {exc}", file=sys.stderr)
        return 2
    # Pass JSON to `cast wallet sign --data` via stdin? cast accepts a file or hex.
    # We'll write to a temp file in session dir.
    tmp = _session_dir(args.session) / f"typed_data_{datetime.datetime.now().strftime('%H%M%S')}.json"
    tmp.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
    res = _cast(env, "wallet", "sign", "--private-key", pk, "--data", "--from-file", str(tmp))
    if res.returncode != 0:
        print(f"sign failed: {res.stderr.strip()}", file=sys.stderr)
        return res.returncode
    sig = res.stdout.strip()
    print(sig)
    _log_action(args.session, {
        "op": "sign_typed_data", "domain": parsed.get("domain"),
        "primary_type": parsed.get("primaryType"), "signature": sig,
        "payload_file": str(tmp),
    })
    return 0


def cmd_replay_signature(args) -> int:
    """Verify a signature against a (possibly different) chain/contract to test
    cross-chain replay. Read-only — never broadcasts.
    """
    env = _load_env()
    if Path(args.typed_data).exists():
        parsed = json.loads(Path(args.typed_data).read_text(encoding="utf-8"))
    else:
        parsed = json.loads(args.typed_data)
    domain = parsed.get("domain", {})
    # Recompute the EIP-712 digest via cast and recover the signer
    tmp = _session_dir(args.session) / f"replay_typed_{datetime.datetime.now().strftime('%H%M%S')}.json"
    tmp.write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")

    # Use `cast hash-typed-data` to get the digest, then `cast wallet verify --address`
    digest_res = _cast(env, "hash-typed-data", "--from-file", str(tmp))
    if digest_res.returncode != 0:
        print(f"hash-typed-data failed: {digest_res.stderr.strip()}", file=sys.stderr)
        return digest_res.returncode
    digest = digest_res.stdout.strip()

    recover_res = _cast(env, "wallet", "recover", "--signature", args.signature, "--message", digest)
    record = {
        "op": "replay_signature",
        "src_chain_in_domain": domain.get("chainId"),
        "dst_chain_target": args.dst_chain,
        "verifying_contract": domain.get("verifyingContract"),
        "digest": digest,
        "recovered_signer": recover_res.stdout.strip() if recover_res.returncode == 0 else None,
        "recovery_stderr": recover_res.stderr.strip()[:300],
    }
    _log_action(args.session, record)

    print(f"digest:           {digest}")
    print(f"recovered signer: {record['recovered_signer']}")
    print(f"signature chainId in domain: {domain.get('chainId')}")
    print(f"target dst-chain:           {args.dst_chain}")
    if domain.get("chainId") and args.dst_chain in _CHAINS:
        if int(domain["chainId"]) != _CHAINS[args.dst_chain]["id"]:
            print()
            print(f"  REPLAY POSSIBLE: signature's domain.chainId ({domain['chainId']}) "
                  f"does not match target chain {args.dst_chain} (id={_CHAINS[args.dst_chain]['id']}).")
            print(f"  This is a cross-chain replay candidate — verify the verifying_contract "
                  f"is deployed on the target chain at the SAME address before drawing conclusions.")
    return 0


def cmd_revoke_approval(args) -> int:
    env = _load_env()
    pk = _enforce_burner(env)
    rpc = _resolve_rpc(env, args.chain, args.fork_url)
    # ERC-20 approve(spender, 0)
    cmd_args = [
        "send", args.token, "approve(address,uint256)",
        args.spender, "0",
        "--rpc-url", rpc, "--private-key", pk,
    ]
    if args.chain in _CHAINS and _CHAINS[args.chain]["tier"] in ("l1", "l2"):
        if not args.mainnet:
            print(f"{args.chain} is mainnet — pass --mainnet to confirm revocation. Aborting.", file=sys.stderr)
            return 2
    res = _cast(env, *cmd_args, timeout=120)
    _log_action(args.session, {
        "op": "revoke_approval", "chain": args.chain,
        "token": args.token, "spender": args.spender,
        "returncode": res.returncode,
        "stdout": res.stdout.strip()[:500], "stderr": res.stderr.strip()[:300],
    })
    if res.returncode != 0:
        print(f"revoke failed: {res.stderr.strip()}", file=sys.stderr)
        return res.returncode
    print(res.stdout.strip())
    return 0


def cmd_session_end(args) -> int:
    """Read revocation_pending.jsonl and auto-revoke any non-zero approval."""
    sess = _session_dir(args.session)
    pending = sess / "revocation_pending.jsonl"
    summary = {
        "ended_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "revocations_attempted": 0,
        "revocations_succeeded": 0,
    }
    if pending.exists():
        env = _load_env()
        for line in pending.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("revoked"):
                continue
            summary["revocations_attempted"] += 1
            # Try to revoke
            pk = _enforce_burner(env)
            rpc = _resolve_rpc(env, rec["chain"])
            cmd_args = ["send", rec["token"], "approve(address,uint256)",
                        rec["spender"], "0", "--rpc-url", rpc, "--private-key", pk]
            res = _cast(env, *cmd_args, timeout=120)
            if res.returncode == 0:
                summary["revocations_succeeded"] += 1
    (sess / "session_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_audit_log(args) -> int:
    sess = _session_dir(args.session)
    log = sess / "signed_actions.jsonl"
    if not log.exists():
        print("(no signed_actions yet)")
        return 0
    for line in log.read_text(encoding="utf-8").splitlines():
        print(line)
    return 0


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--session", help="Hunt session dir, e.g. sessions/oyster.synfutures.com")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_fu = sub.add_parser("fork-up", help="Start an Anvil fork")
    p_fu.add_argument("--chain", default="base", choices=[c for c in _CHAINS if _CHAINS[c]["tier"] != "fork"])
    p_fu.add_argument("--port", type=int, default=8545)
    p_fu.add_argument("--host", default="127.0.0.1")
    p_fu.add_argument("--block-number", type=int)
    p_fu.set_defaults(func=cmd_fork_up)

    p_fd = sub.add_parser("fork-down", help="Kill running anvil fork")
    p_fd.set_defaults(func=cmd_fork_down)

    p_b = sub.add_parser("balance", help="Read burner balance")
    p_b.add_argument("--chain", required=True, choices=list(_CHAINS))
    p_b.set_defaults(func=cmd_balance)

    p_c = sub.add_parser("call", help="Read-only eth_call")
    p_c.add_argument("--chain", required=True, choices=list(_CHAINS))
    p_c.add_argument("--to", required=True)
    p_c.add_argument("--data", help="Hex calldata")
    p_c.add_argument("--sig", help="Function signature, e.g. 'balanceOf(address)'")
    p_c.add_argument("--params", nargs="*")
    p_c.add_argument("--fork-url", help="Override RPC for fork mode")
    p_c.set_defaults(func=cmd_call)

    p_s = sub.add_parser("send", help="Sign+send a tx (respects mode + caps)")
    p_s.add_argument("--chain", required=True, choices=list(_CHAINS))
    p_s.add_argument("--to", required=True)
    p_s.add_argument("--data", help="Hex calldata")
    p_s.add_argument("--sig", help="Function signature")
    p_s.add_argument("--params", nargs="*")
    p_s.add_argument("--value", default="0", help="ETH value (decimal)")
    p_s.add_argument("--gas-price-gwei", type=str)
    p_s.add_argument("--mainnet", action="store_true", help="Explicit acknowledgement that target is a mainnet")
    p_s.add_argument("--fork-url", help="Override RPC for fork mode")
    p_s.set_defaults(func=cmd_send)

    p_st = sub.add_parser("sign-typed-data", help="EIP-712 sign without broadcast")
    p_st.add_argument("--json", required=True, help="Path or inline JSON of EIP-712 typed data")
    p_st.set_defaults(func=cmd_sign_typed_data)

    p_r = sub.add_parser("replay-signature", help="Check cross-chain replay potential of a signature")
    p_r.add_argument("--signature", required=True)
    p_r.add_argument("--typed-data", required=True, help="Path or JSON of the typed data")
    p_r.add_argument("--dst-chain", required=True, choices=list(_CHAINS))
    p_r.set_defaults(func=cmd_replay_signature)

    p_rv = sub.add_parser("revoke-approval", help="Set allowance to 0")
    p_rv.add_argument("--chain", required=True, choices=list(_CHAINS))
    p_rv.add_argument("--token", required=True)
    p_rv.add_argument("--spender", required=True)
    p_rv.add_argument("--mainnet", action="store_true")
    p_rv.add_argument("--fork-url")
    p_rv.set_defaults(func=cmd_revoke_approval)

    p_se = sub.add_parser("session-end", help="Auto-revoke pending approvals + emit summary")
    p_se.set_defaults(func=cmd_session_end)

    p_al = sub.add_parser("audit-log", help="Tail signed_actions.jsonl")
    p_al.set_defaults(func=cmd_audit_log)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except RuntimeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
