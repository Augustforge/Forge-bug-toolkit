#!/usr/bin/env python3
"""
role_centralization_scanner.py — On-chain centralization risk scanner for ERC-20 tokens.

Mission: Detect the Echo Protocol Monad pattern (19.05.2026) BEFORE it gets exploited.
That hack chained: single EOA admin + no timelock + no supply cap + unconstrained mint +
cross-protocol collateral acceptance = $76.7M nominal / $816K realized loss.

What this scanner does:
1. Pulls all role holders (DEFAULT_ADMIN_ROLE, MINTER_ROLE, PAUSER_ROLE, UPGRADER_ROLE)
   via OpenZeppelin AccessControlEnumerable interface.
2. For each holder: classifies as EOA / Gnosis Safe / TimelockController / Unknown contract.
3. Reads supply cap, current totalSupply, owner() (legacy pattern), paused().
4. Outputs JSON + human-readable summary with centralization risk score.

Pure-stdlib JSON-RPC client (no web3.py / no external deps) — portable across hunting envs.

Usage:
    python3 role_centralization_scanner.py \\
        --rpc https://rpc.monad.xyz \\
        --token 0xTokenContractAddress \\
        --out sessions/$DOMAIN/onchain/token_role_holders.json

    # Multiple roles beyond defaults
    python3 role_centralization_scanner.py --rpc ... --token ... \\
        --extra-role "BRIDGE_OPERATOR" --extra-role "FREEZER"

    # Aggregate across multiple tokens (e.g., wrapped + governance + LP)
    python3 role_centralization_scanner.py --rpc ... \\
        --token 0xToken1 --token 0xToken2 --token 0xToken3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ──────────────── keccak256 (pure-Python fallback for role hashing) ────────────────
# We need keccak256 for role names. We avoid pycryptodome; sha3.keccak_256 is in
# stdlib only on some builds. Try multiple fallbacks.

def _keccak256(data: bytes) -> bytes:
    """Compute keccak-256 with best-available implementation."""
    try:
        # eth_hash style
        from Crypto.Hash import keccak  # type: ignore
        h = keccak.new(digest_bits=256)
        h.update(data)
        return h.digest()
    except ImportError:
        pass
    try:
        # Some Python builds expose sha3_keccak via hashlib
        return hashlib.new("keccak_256", data).digest()
    except (ValueError, AttributeError):
        pass
    # Pure-Python keccak fallback (slow but correct, no deps)
    return _pure_keccak256(data)


# Pure-Python Keccak-256 reference implementation (NIST SHA-3 with 0x01 padding).
# Adapted for portability when neither pycryptodome nor sha3 is available.
def _pure_keccak256(message: bytes) -> bytes:
    RC = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A,
        0x8000000080008000, 0x000000000000808B, 0x0000000080000001,
        0x8000000080008081, 0x8000000000008009, 0x000000000000008A,
        0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089,
        0x8000000000008003, 0x8000000000008002, 0x8000000000000080,
        0x000000000000800A, 0x800000008000000A, 0x8000000080008081,
        0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
    ]
    R = [
        [0, 36, 3, 41, 18],
        [1, 44, 10, 45, 2],
        [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56],
        [27, 20, 39, 8, 14],
    ]

    def rotl(n: int, b: int) -> int:
        return ((n << b) | (n >> (64 - b))) & 0xFFFFFFFFFFFFFFFF

    def keccak_f(state: list) -> list:
        for rnd in range(24):
            # Theta
            C = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
            D = [C[(x - 1) % 5] ^ rotl(C[(x + 1) % 5], 1) for x in range(5)]
            for x in range(5):
                for y in range(5):
                    state[x][y] ^= D[x]
            # Rho + Pi
            B = [[0] * 5 for _ in range(5)]
            for x in range(5):
                for y in range(5):
                    B[y][(2 * x + 3 * y) % 5] = rotl(state[x][y], R[x][y])
            # Chi
            for x in range(5):
                for y in range(5):
                    state[x][y] = B[x][y] ^ ((~B[(x + 1) % 5][y]) & B[(x + 2) % 5][y]) & 0xFFFFFFFFFFFFFFFF
            # Iota
            state[0][0] ^= RC[rnd]
        return state

    rate = 1088
    rate_bytes = rate // 8
    state = [[0] * 5 for _ in range(5)]

    padded = message + b"\x01"
    while len(padded) % rate_bytes != rate_bytes - 1:
        padded += b"\x00"
    padded += b"\x80"

    for offset in range(0, len(padded), rate_bytes):
        block = padded[offset:offset + rate_bytes]
        for i in range(rate_bytes // 8):
            word = int.from_bytes(block[i * 8:(i + 1) * 8], "little")
            x, y = i % 5, i // 5
            state[x][y] ^= word
        state = keccak_f(state)

    out = bytearray()
    while len(out) < 32:
        for y in range(5):
            for x in range(5):
                if len(out) >= 32:
                    break
                out.extend(state[x][y].to_bytes(8, "little"))
    return bytes(out[:32])


# ──────────────── JSON-RPC client ────────────────

class RPCError(RuntimeError):
    pass


def rpc_call(rpc_url: str, method: str, params: list, *, request_id: int = 1, timeout: int = 30) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": request_id}).encode()
    req = urllib.request.Request(
        rpc_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        raise RPCError(f"HTTP {e.code} from RPC: {e.read().decode()[:200]}") from e
    except urllib.error.URLError as e:
        raise RPCError(f"RPC unreachable: {e}") from e
    if "error" in payload:
        raise RPCError(f"RPC error {payload['error'].get('code')}: {payload['error'].get('message')}")
    return payload.get("result")


def eth_call(rpc_url: str, to: str, data: str, *, block: str = "latest") -> str:
    """Make an eth_call and return raw hex result."""
    return rpc_call(rpc_url, "eth_call", [{"to": to, "data": data}, block])


def eth_get_code(rpc_url: str, address: str, *, block: str = "latest") -> str:
    return rpc_call(rpc_url, "eth_getCode", [address, block])


# ──────────────── ABI encoding (minimal — fixed signatures only) ────────────────

# Function selectors (first 4 bytes of keccak256 signature)
SELECTORS = {
    "getRoleMemberCount(bytes32)": "0xca15c873",
    "getRoleMember(bytes32,uint256)": "0x9010d07c",
    "getRoleAdmin(bytes32)": "0x248a9ca3",
    "hasRole(bytes32,address)": "0x91d14854",
    "owner()": "0x8da5cb5b",
    "totalSupply()": "0x18160ddd",
    "cap()": "0x355274ea",
    "name()": "0x06fdde03",
    "symbol()": "0x95d89b41",
    "decimals()": "0x313ce567",
    "paused()": "0x5c975abb",
    "minDelay()": "0xf27a0c92",
    "getOwners()": "0xa0e67e2b",
    "getThreshold()": "0xe75235b8",
    "VERSION()": "0xffa1ad74",
    "implementation()": "0x5c60da1b",
    "proxiableUUID()": "0x52d1902d",
}

# Well-known role hashes (precomputed to avoid keccak dependency at runtime when possible)
KNOWN_ROLES = {
    "DEFAULT_ADMIN_ROLE": "0x" + "00" * 32,
    "MINTER_ROLE": "0x9f2df0fed2c77648de5860a4cc508cd0818c85b8b8a1ab4ceeef8d981c8956a6",
    "PAUSER_ROLE": "0x65d7a28e3265b37a6474929f336521b332c1681b933f6cb9f3376673440d862a",
    "UPGRADER_ROLE": "0x189ab7a9244df0848122154315af71fe140f3db0fe014031783b0946b8c9d2e3",
    "BURNER_ROLE": "0x3c11d16cbaffd01df69ce1c404f6340ee057498f5f00246190ea54220576a848",
    "GOVERNOR_ROLE": "0x7935bd0ae54bc31f548c14dba4d37c5c64b3f8ca900cb468fb8abd54d5894f55",
    "OPERATOR_ROLE": "0x97667070c54ef182b0f5858b034beac1b6f3089aa2d3188bb1e8929f4fa9b929",
}


def hash_role(role_name: str) -> str:
    """Compute keccak256 of role name as hex string."""
    if role_name in KNOWN_ROLES:
        return KNOWN_ROLES[role_name]
    h = _keccak256(role_name.encode())
    return "0x" + h.hex()


def encode_call(signature: str, *args) -> str:
    """Encode a function call with simple types (bytes32, address, uint256)."""
    selector = SELECTORS.get(signature)
    if selector is None:
        # Derive selector from signature on the fly
        selector = "0x" + _keccak256(signature.encode())[:4].hex()
    encoded = selector[2:]
    for arg in args:
        if isinstance(arg, str) and arg.startswith("0x"):
            # bytes32 / address — pad left to 32 bytes
            hex_val = arg[2:]
            encoded += hex_val.rjust(64, "0")
        elif isinstance(arg, int):
            encoded += format(arg, "064x")
        else:
            raise ValueError(f"Unsupported arg type for ABI encoding: {type(arg)}")
    return "0x" + encoded


def decode_uint(hex_result: str) -> int:
    if not hex_result or hex_result == "0x":
        return 0
    return int(hex_result, 16)


def decode_address(hex_result: str) -> str:
    if not hex_result or hex_result == "0x":
        return "0x" + "00" * 20
    # Take last 20 bytes
    return "0x" + hex_result[-40:]


def decode_string(hex_result: str) -> str:
    """Decode ABI-encoded dynamic string."""
    if not hex_result or hex_result == "0x":
        return ""
    h = hex_result[2:]
    if len(h) < 128:
        return ""
    try:
        # offset (32 bytes) + length (32 bytes) + data
        length = int(h[64:128], 16)
        data_hex = h[128:128 + length * 2]
        return bytes.fromhex(data_hex).decode("utf-8", errors="replace")
    except Exception:
        return ""


def decode_address_array(hex_result: str) -> List[str]:
    """Decode ABI-encoded dynamic address[]."""
    if not hex_result or hex_result == "0x":
        return []
    h = hex_result[2:]
    if len(h) < 128:
        return []
    try:
        length = int(h[64:128], 16)
        addresses = []
        for i in range(length):
            start = 128 + i * 64
            addresses.append("0x" + h[start + 24:start + 64])
        return addresses
    except Exception:
        return []


# ──────────────── Classification logic ────────────────

# Gnosis Safe MasterCopy bytecode signatures (incomplete; heuristic check)
GNOSIS_SAFE_NAME_SIGNATURES = ["GnosisSafe", "Safe"]
# OpenZeppelin TimelockController has VERSION constant — used as heuristic

@dataclass
class AddressClassification:
    address: str
    code_size: int
    kind: str  # "EOA" / "GnosisSafe" / "TimelockController" / "UnknownContract"
    details: Dict[str, Any] = field(default_factory=dict)


def classify_address(rpc_url: str, address: str) -> AddressClassification:
    """Determine if address is EOA / Gnosis Safe / Timelock / other contract."""
    code = eth_get_code(rpc_url, address)
    code_size = (len(code) - 2) // 2 if code and code.startswith("0x") else 0

    if code_size == 0:
        return AddressClassification(address=address, code_size=0, kind="EOA")

    details: Dict[str, Any] = {"code_size": code_size}
    kind = "UnknownContract"

    # Probe Gnosis Safe (getOwners + getThreshold)
    try:
        owners_raw = eth_call(rpc_url, address, encode_call("getOwners()"))
        threshold_raw = eth_call(rpc_url, address, encode_call("getThreshold()"))
        owners = decode_address_array(owners_raw)
        threshold = decode_uint(threshold_raw)
        if owners and 0 < threshold <= len(owners):
            kind = "GnosisSafe"
            details["safe_owners"] = owners
            details["safe_threshold"] = threshold
            details["safe_owner_count"] = len(owners)
            return AddressClassification(address=address, code_size=code_size, kind=kind, details=details)
    except RPCError:
        pass

    # Probe TimelockController (minDelay)
    try:
        delay_raw = eth_call(rpc_url, address, encode_call("minDelay()"))
        delay = decode_uint(delay_raw)
        if delay > 0:
            kind = "TimelockController"
            details["timelock_min_delay_seconds"] = delay
            details["timelock_min_delay_hours"] = delay / 3600.0
            return AddressClassification(address=address, code_size=code_size, kind=kind, details=details)
    except RPCError:
        pass

    # Probe owner() for Ownable contracts that proxy to a multisig
    try:
        owner_raw = eth_call(rpc_url, address, encode_call("owner()"))
        owner_addr = decode_address(owner_raw)
        if owner_addr != "0x" + "00" * 20:
            details["delegates_owner_to"] = owner_addr
    except RPCError:
        pass

    return AddressClassification(address=address, code_size=code_size, kind=kind, details=details)


# ──────────────── Main scan logic ────────────────

@dataclass
class RoleHolders:
    role_name: str
    role_hash: str
    member_count: int
    members: List[AddressClassification] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class TokenReport:
    address: str
    rpc_url: str
    name: str = ""
    symbol: str = ""
    decimals: int = 0
    total_supply: int = 0
    cap: Optional[int] = None
    paused: Optional[bool] = None
    legacy_owner: Optional[str] = None
    legacy_owner_classification: Optional[AddressClassification] = None
    roles: List[RoleHolders] = field(default_factory=list)
    risk_findings: List[Dict[str, str]] = field(default_factory=list)
    risk_score: int = 0  # 0-100; 100 = max risk


def scan_token_metadata(rpc_url: str, token: str, report: TokenReport) -> None:
    try:
        report.name = decode_string(eth_call(rpc_url, token, encode_call("name()")))
    except RPCError:
        pass
    try:
        report.symbol = decode_string(eth_call(rpc_url, token, encode_call("symbol()")))
    except RPCError:
        pass
    try:
        report.decimals = decode_uint(eth_call(rpc_url, token, encode_call("decimals()")))
    except RPCError:
        pass
    try:
        report.total_supply = decode_uint(eth_call(rpc_url, token, encode_call("totalSupply()")))
    except RPCError:
        pass
    try:
        cap_raw = eth_call(rpc_url, token, encode_call("cap()"))
        report.cap = decode_uint(cap_raw)
    except RPCError:
        report.cap = None
    try:
        paused_raw = eth_call(rpc_url, token, encode_call("paused()"))
        report.paused = bool(decode_uint(paused_raw))
    except RPCError:
        report.paused = None
    try:
        owner_raw = eth_call(rpc_url, token, encode_call("owner()"))
        owner_addr = decode_address(owner_raw)
        if owner_addr != "0x" + "00" * 20:
            report.legacy_owner = owner_addr
            report.legacy_owner_classification = classify_address(rpc_url, owner_addr)
    except RPCError:
        pass


def scan_role(rpc_url: str, token: str, role_name: str) -> RoleHolders:
    role_hash = hash_role(role_name)
    holders = RoleHolders(role_name=role_name, role_hash=role_hash, member_count=0)

    try:
        count_raw = eth_call(rpc_url, token, encode_call("getRoleMemberCount(bytes32)", role_hash))
        holders.member_count = decode_uint(count_raw)
    except RPCError as e:
        holders.error = f"getRoleMemberCount failed (contract may not implement AccessControlEnumerable): {e}"
        return holders

    for i in range(holders.member_count):
        try:
            member_raw = eth_call(rpc_url, token, encode_call("getRoleMember(bytes32,uint256)", role_hash, i))
            member_addr = decode_address(member_raw)
            holders.members.append(classify_address(rpc_url, member_addr))
        except RPCError as e:
            holders.members.append(AddressClassification(
                address=f"<error at index {i}>", code_size=0, kind="Error",
                details={"error": str(e)}
            ))

    return holders


def assess_risk(report: TokenReport) -> None:
    """Score centralization risk and attach findings."""
    findings = report.risk_findings
    score = 0

    # Find admin / minter / upgrader holders
    admin_holders = next((r for r in report.roles if r.role_name == "DEFAULT_ADMIN_ROLE"), None)
    minter_holders = next((r for r in report.roles if r.role_name == "MINTER_ROLE"), None)
    upgrader_holders = next((r for r in report.roles if r.role_name == "UPGRADER_ROLE"), None)
    pauser_holders = next((r for r in report.roles if r.role_name == "PAUSER_ROLE"), None)

    # Helper: count EOA holders of a role
    def eoa_count(role: Optional[RoleHolders]) -> int:
        if not role:
            return 0
        return sum(1 for m in role.members if m.kind == "EOA")

    # Critical: single EOA admin
    if admin_holders and admin_holders.member_count == 1 and eoa_count(admin_holders) == 1:
        findings.append({
            "severity": "critical",
            "id": "single_eoa_admin",
            "message": f"DEFAULT_ADMIN_ROLE held by single EOA: {admin_holders.members[0].address}. "
                       "Echo-pattern primary precondition.",
        })
        score += 40

    # Critical: single EOA minter
    if minter_holders and eoa_count(minter_holders) >= 1 and minter_holders.member_count <= 2:
        eoa_minters = [m.address for m in minter_holders.members if m.kind == "EOA"]
        findings.append({
            "severity": "critical",
            "id": "eoa_minter",
            "message": f"MINTER_ROLE held by EOA(s): {eoa_minters}. "
                       "Unconstrained mint possible on key compromise.",
        })
        score += 30

    # High: legacy owner() is EOA (covers non-AccessControl tokens)
    if report.legacy_owner_classification and report.legacy_owner_classification.kind == "EOA":
        findings.append({
            "severity": "high",
            "id": "legacy_eoa_owner",
            "message": f"owner() is EOA: {report.legacy_owner}. "
                       "Legacy Ownable pattern with EOA control.",
        })
        score += 25

    # Critical: no supply cap with mintable roles present
    if report.cap is None and minter_holders and minter_holders.member_count > 0:
        findings.append({
            "severity": "critical",
            "id": "no_supply_cap",
            "message": "No cap() function detected AND MINTER_ROLE assigned. "
                       "Unbounded mint capacity on compromise.",
        })
        score += 20

    # High: low-threshold multisig
    for role in [admin_holders, minter_holders, upgrader_holders]:
        if not role:
            continue
        for m in role.members:
            if m.kind == "GnosisSafe":
                threshold = m.details.get("safe_threshold", 0)
                owner_count = m.details.get("safe_owner_count", 0)
                if owner_count > 0 and threshold <= 2:
                    findings.append({
                        "severity": "high",
                        "id": "low_threshold_multisig",
                        "message": f"Gnosis Safe {m.address} on role {role.role_name}: "
                                   f"threshold {threshold}/{owner_count}. Low Byzantine fault tolerance.",
                    })
                    score += 15

    # High: admin is NOT a TimelockController
    if admin_holders and admin_holders.member_count > 0:
        has_timelock = any(m.kind == "TimelockController" for m in admin_holders.members)
        if not has_timelock:
            findings.append({
                "severity": "high",
                "id": "no_timelock_on_admin",
                "message": "DEFAULT_ADMIN_ROLE not gated by TimelockController. "
                           "Role changes execute instantly.",
            })
            score += 15

    # Medium: pauser = admin
    if pauser_holders and admin_holders:
        admin_addrs = {m.address for m in admin_holders.members}
        pauser_addrs = {m.address for m in pauser_holders.members}
        if admin_addrs == pauser_addrs and admin_addrs:
            findings.append({
                "severity": "medium",
                "id": "pauser_equals_admin",
                "message": "PAUSER_ROLE held by same addresses as DEFAULT_ADMIN_ROLE. "
                           "No independent guardian; compromised admin = no pause defense.",
            })
            score += 10

    report.risk_score = min(score, 100)


def format_summary(report: TokenReport) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"Token: {report.symbol or '<unknown>'} ({report.name or '<unknown>'})")
    lines.append(f"Address: {report.address}")
    lines.append(f"totalSupply: {report.total_supply} (decimals: {report.decimals})")
    if report.cap is not None:
        lines.append(f"cap: {report.cap}")
    else:
        lines.append("cap: <none> (no cap() function)")
    if report.paused is not None:
        lines.append(f"paused: {report.paused}")
    if report.legacy_owner:
        kind = report.legacy_owner_classification.kind if report.legacy_owner_classification else "?"
        lines.append(f"owner() (legacy): {report.legacy_owner} [{kind}]")
    lines.append("")

    lines.append("Roles:")
    for role in report.roles:
        lines.append(f"  {role.role_name} ({role.role_hash[:10]}...) — {role.member_count} holder(s)")
        if role.error:
            lines.append(f"    ERROR: {role.error}")
            continue
        for m in role.members:
            extra = ""
            if m.kind == "GnosisSafe":
                extra = f" [Safe {m.details.get('safe_threshold')}/{m.details.get('safe_owner_count')}]"
            elif m.kind == "TimelockController":
                extra = f" [Timelock {m.details.get('timelock_min_delay_hours', 0):.1f}h]"
            lines.append(f"    {m.address}  →  {m.kind}{extra}")
    lines.append("")

    lines.append(f"Risk score: {report.risk_score}/100")
    if report.risk_findings:
        lines.append("Findings:")
        for f in report.risk_findings:
            lines.append(f"  [{f['severity'].upper()}] {f['id']}: {f['message']}")
    else:
        lines.append("Findings: none")
    lines.append("=" * 72)
    return "\n".join(lines)


# ──────────────── CLI ────────────────

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rpc", required=True, help="JSON-RPC URL of the chain")
    parser.add_argument("--token", required=True, action="append",
                        help="Token contract address (can be repeated)")
    parser.add_argument("--extra-role", action="append", default=[],
                        help="Additional role name to scan (e.g., BRIDGE_OPERATOR)")
    parser.add_argument("--out", help="Output JSON path; if omitted, stdout summary only")
    parser.add_argument("--quiet", action="store_true", help="Suppress human-readable summary")
    args = parser.parse_args(argv)

    default_roles = [
        "DEFAULT_ADMIN_ROLE",
        "MINTER_ROLE",
        "PAUSER_ROLE",
        "UPGRADER_ROLE",
        "BURNER_ROLE",
    ]
    all_roles = default_roles + list(args.extra_role)

    all_reports = []
    for token_addr in args.token:
        report = TokenReport(address=token_addr, rpc_url=args.rpc)
        try:
            scan_token_metadata(args.rpc, token_addr, report)
            for role_name in all_roles:
                report.roles.append(scan_role(args.rpc, token_addr, role_name))
            assess_risk(report)
        except RPCError as e:
            print(f"[ERROR] Token {token_addr}: {e}", file=sys.stderr)
            continue

        if not args.quiet:
            print(format_summary(report))

        all_reports.append(report)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = []
        for r in all_reports:
            d = asdict(r)
            serializable.append(d)
        out_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        print(f"\nWrote {len(all_reports)} token report(s) → {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
