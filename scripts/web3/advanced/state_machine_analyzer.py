#!/usr/bin/env python3
"""
state_machine_analyzer.py — extract state machines from Solidity.

Finds enums representing states + transition sites (assignments to a state var).
Output: unreachable states, missing transitions, state-changing functions w/o auth.

ALSO (liveness lens, see hypothesis_generation.md Lens 10): finds exit functions
(withdraw/refund/claim/redeem/collect/unlock) whose reachability is gated by a state
var or modifier, then checks WHO can write that gate. If the only writers are `internal`
(reachable from a single activity that can cease) or `onlyOwner`/privilege-gated, the
exit can be permanently frozen — the HONG class ($2M trapped 9y: `refundMyIcoInvestment`
is `notLocked`-gated, and the lock state advances only inside `internal tryToLockFund()`
called solely from `createTokenProxy()` — once ICO buying stopped, the fund parked forever).
"""
import argparse
import json
import re
import sys
from pathlib import Path


ENUM_DEF = re.compile(r"enum\s+(\w+)\s*\{([^}]+)\}", re.DOTALL)
STATE_VAR = re.compile(r"(\w+)\s+(?:public\s+|private\s+|internal\s+)?(\w+)\s*;")
ASSIGNMENT = re.compile(r"(\w+(?:\.\w+)?)\s*=\s*(\w+)\.(\w+)\s*;")
FUNC_WITH_BODY = re.compile(r"function\s+(\w+)[^{]*\{", re.MULTILINE)

# --- liveness lens ---
EXIT_NAME = re.compile(
    r"withdraw|refund|claim|redeem|collect|unlock|exit|cashout|payout|release|harvest",
    re.IGNORECASE,
)
# function signature up to the opening brace: name, params, modifiers/returns
FUNC_SIG = re.compile(r"function\s+(\w+)\s*\(([^)]*)\)([^{};]*)[{;]", re.DOTALL)
# a bare identifier used as a guard inside the function body / modifier list
IDENT = re.compile(r"\b([a-zA-Z_]\w*)\b")
GATE_HINT = re.compile(
    r"locked|unlocked|released|finalized|finalised|distribut|ready|active|enabled|"
    r"frozen|freeze|claimable|withdrawable|matured|settled|phase|state|stage|kicked|harvest",
    re.IGNORECASE,
)


def _extract_body(text: str, brace_open: int) -> str:
    """Return the {...} body starting at brace_open (index of '{')."""
    depth = 0
    for i in range(brace_open, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[brace_open : i + 1]
    return text[brace_open:]


def parse_functions(text: str) -> list:
    """List of {name, params, header, modifiers, body}. header = text between ) and { ."""
    funcs = []
    for m in FUNC_SIG.finditer(text):
        name, params, header = m.group(1), m.group(2), m.group(3)
        body = ""
        if text[m.end() - 1] == "{":
            body = _extract_body(text, m.end() - 1)
        mods = [w for w in IDENT.findall(header) if w not in ("public", "external", "internal", "private", "returns", "view", "pure", "payable", "constant", "memory", "storage", "calldata", "bool", "uint", "uint256", "address", "string", "bytes")]
        vis = "public"
        for v in ("internal", "external", "private", "public"):
            if re.search(rf"\b{v}\b", header):
                vis = v
                break
        funcs.append({"name": name, "params": params, "header": header.strip(), "visibility": vis, "modifiers": mods, "body": body})
    return funcs


def _norm_gate(s: str) -> str:
    """Strip boolean-prefix noise so modifier names match state vars.
    notLocked / onlyLocked / isFundLocked -> 'locked' / 'fundlocked'."""
    s = s.lower()
    for p in ("only", "not", "is", "are", "has", "have", "get", "set", "_"):
        if s.startswith(p) and len(s) > len(p) + 2:
            s = s[len(p):]
    return s.lstrip("_")


def _gate_matches(term: str, var: str) -> bool:
    a, b = _norm_gate(term), _norm_gate(var)
    return a == b or a in b or b in a


def analyze_liveness(text: str, funcs: list) -> list:
    """Flag exit functions whose gate can be permanently withheld."""
    # map: state var -> set of (writer_name, writer_visibility, writer_has_owner_guard)
    writers = {}
    for f in funcs:
        owner_guarded = bool(re.search(r"onlyOwner|onlyManag|onlyAdmin|isFromManaged", f["header"]))
        for wm in re.finditer(r"\b([a-zA-Z_]\w*)\s*=\s*[^=]", f["body"]):
            var = wm.group(1)
            if GATE_HINT.search(var):
                writers.setdefault(var, set()).add((f["name"], f["visibility"], owner_guarded))

    flags = []
    for f in funcs:
        if not EXIT_NAME.search(f["name"]) or not f["body"]:
            continue
        # gate identifiers: modifiers + state-looking idents read in the body's guards
        gate_terms = set(t for t in f["modifiers"] if GATE_HINT.search(t))
        for gm in re.finditer(r"(?:require|if)\s*\(([^)]*)\)", f["body"]):
            for ident in IDENT.findall(gm.group(1)):
                if GATE_HINT.search(ident):
                    gate_terms.add(ident)
        if not gate_terms:
            continue
        # for each gate term, who writes the underlying state var?
        risk = []
        for term in gate_terms:
            ws = set()
            for var, wset in writers.items():
                if _gate_matches(term, var):
                    ws |= wset
            if not ws:
                risk.append({"gate": term, "writers": [], "why": "no writer found in scope - gate may never flip (constructor-only / cross-contract)"})
                continue
            vis_set = {w[1] for w in ws}
            owner_only = all(w[2] for w in ws)
            if vis_set <= {"internal", "private"} or owner_only:
                risk.append({
                    "gate": term,
                    "writers": [f"{w[0]}({w[1]}{'+owner' if w[2] else ''})" for w in ws],
                    "why": "exit gate flips only via internal/privileged path - if that path stops firing or is withheld, exit freezes (HONG / DoS-to-freeze class)",
                })
        if risk:
            flags.append({"exit_function": f["name"], "visibility": f["visibility"], "gated_by": sorted(gate_terms), "risks": risk})
    return flags


def scan_file(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}

    funcs = parse_functions(text)
    liveness = analyze_liveness(text, funcs)

    enums = {}
    for m in ENUM_DEF.finditer(text):
        ename = m.group(1)
        values = [v.strip() for v in m.group(2).split(",") if v.strip()]
        enums[ename] = values

    if not enums and not liveness:
        return {}

    state_vars = {}
    for ename in enums:
        for m in re.finditer(rf"\b{ename}\s+(?:public\s+|private\s+|internal\s+)?(\w+)\s*[;=]", text):
            state_vars[m.group(1)] = ename

    transitions = []
    for m in ASSIGNMENT.finditer(text):
        lhs, etype, val = m.group(1), m.group(2), m.group(3)
        if etype in enums and val in enums[etype]:
            line = text[: m.start()].count("\n") + 1
            transitions.append({"line": line, "var": lhs, "enum": etype, "to_state": val})

    reachable = {e: set() for e in enums}
    for t in transitions:
        reachable[t["enum"]].add(t["to_state"])

    unreachable = {}
    for e, vals in enums.items():
        missing = [v for v in vals if v not in reachable[e]]
        if missing:
            unreachable[e] = missing

    return {
        "file": str(path),
        "enums": enums,
        "state_vars": state_vars,
        "transitions": transitions,
        "unreachable_states": unreachable,
        "liveness_flags": liveness,
    }


# ── web2 branch (FDE Plan 5, Task 6) ────────────────────────────────────────────────────────────
# Separate domain from the Solidity enum/liveness analysis above (that stays untouched): this is
# UI-flow business-logic state analysis (statem/replay/skip candidates), not enum-transition
# analysis. Canonical implementation lives in scripts/web2/business_logic.py (BL-NN candidate
# generator, shared with the agent doing the hunt) -- delegated here so the state-machine analyzer
# has one entrypoint for both Solidity-state and UI-flow-state work. Lazy + fail-open import: the
# web3 .sol CLI path (scan_file/main below) must keep working even if scripts/web2/ is absent.
def _load_business_logic():
    try:
        import importlib.util
        bl_path = Path(__file__).resolve().parents[2] / "web2" / "business_logic.py"
        spec = importlib.util.spec_from_file_location("business_logic", str(bl_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def analyze_business_flow(flow_steps):
    """web2 branch: UI-flow step sequence -> list[dict] of BL-NN candidates (race/replay/skip).
    Delegates to scripts/web2/business_logic.analyze_business_flow -- see that module for the
    detection logic. Returns [] if the web2 module is unavailable (fail-open; never breaks the
    web3 .sol CLI path)."""
    bl = _load_business_logic()
    if bl is None:
        return []
    return bl.analyze_business_flow(flow_steps)


def main():
    ap = argparse.ArgumentParser(description="Extract Solidity state machines + find unreachable states")
    ap.add_argument("--target", required=True)
    ap.add_argument("--output", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    files = [target] if target.is_file() else list(target.rglob("*.sol")) if target.is_dir() else []
    if not files:
        print(f"[!] Target not found: {target}", file=sys.stderr)
        sys.exit(1)

    results = []
    for f in files:
        if "/test" in str(f).replace("\\", "/").lower():
            continue
        r = scan_file(f)
        if r and (r.get("enums") or r.get("liveness_flags")):
            results.append(r)

    if not args.quiet:
        print(f"[+] State machines / liveness scanned in {len(results)} files")
        for r in results:
            for ename, vals in r.get("enums", {}).items():
                ur = r["unreachable_states"].get(ename, [])
                marker = f"  [!] unreachable: {ur}" if ur else ""
                print(f"  {Path(r['file']).name}: {ename}({len(vals)} states, {len([t for t in r['transitions'] if t['enum']==ename])} transitions){marker}")
            for lf in r.get("liveness_flags", []):
                gates = ",".join(lf["gated_by"])
                print(f"  [FREEZE?] {Path(r['file']).name}: {lf['exit_function']}() gated by [{gates}]")
                for rk in lf["risks"]:
                    print(f"             gate '{rk['gate']}' <- {rk['writers'] or 'NO WRITER'}: {rk['why']}")

    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "state_machine.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
