# -*- coding: utf-8 -*-
"""T11 (Harness as Generator) — an OBJECTIVE detector of "whether to take a fuzzer generator on this target".

Why (operator, 2026-07-29): T11 is not a hook and not "on every hunt" — it is expensive (a harness = hours). Previously
the take/skip decision hung on taste. This script makes it a FACT: reads the target + the model,
checks three objective trigger conditions (mythos T11) and issues a verdict. It is called at phase `J-M`
RIGHT after the T10 model (T11 consumes the `I-NN` from it) — not a hook, but a phase check inside the skill.

Three conditions (all YES → APPLICABLE):
  (1) BUILD  — the codebase compiles (there is foundry.toml / hardhat / Anchor.toml / Cargo+proptest)
              → determines the ENGINE (Foundry-invariant/Echidna/Medusa · Trident · proptest).
  (2) STATEFUL — invariant-heavy value-accounting (balances/shares/reserves/supply/deposit/withdraw…)
              → there is something to conserve, something to break in a sequence.
  (3) MOVEMENT — >=1 `I-NN` in system_model.md that CANNOT be checked by reading (multi-step /
              order-dependent / cumulative). That is exactly what the fuzzer generates.

Verdict:
  APPLICABLE   — all three → build a harness from the order-dependent I-NN, engine in the engine field.
  MAYBE        — BUILD+STATEFUL present, but the model is empty/has no order-dependent I-NN → finish T10, then
                 re-check (not a skip: invariant-heavy stateful is exactly T11's home).
  SKIP         — no BUILD (nothing to fuzz: web2/frontend/docs-only) OR not STATEFUL (a stateless parser
                 → that is T8 differential, not T11).

Usage:  py -3 -X utf8 t11_applicable.py <target_dir> [--model <system_model.md>]
Fail-open in the spirit of the methodology: not found — prints SKIP with a reason, does not crash.
"""
import os
import re
import sys
import json
import glob


# --- (1) BUILD: build config → fuzzing engine --------------------------------------------------
def detect_engine(root):
    """Return (engine, evidence) or (None, None)."""
    def has(pat):
        return bool(glob.glob(os.path.join(root, "**", pat), recursive=True))

    # EVM
    if has("foundry.toml"):
        return ("Foundry-invariant / Echidna / Medusa (EVM)", "foundry.toml")
    if has("hardhat.config.js") or has("hardhat.config.ts"):
        return ("Echidna / Medusa (EVM, crytic-compile)", "hardhat.config")
    # Solana
    if has("Anchor.toml"):
        return ("Trident (Solana/Anchor)", "Anchor.toml")
    # Rust proptest/quickcheck
    for cargo in glob.glob(os.path.join(root, "**", "Cargo.toml"), recursive=True):
        try:
            with open(cargo, "r", encoding="utf-8", errors="replace") as f:
                c = f.read().lower()
            if "proptest" in c or "quickcheck" in c or "arbitrary" in c:
                return ("proptest / quickcheck (Rust)", os.path.relpath(cargo, root))
        except Exception:
            continue
    # a bare Cargo without a proptest dep is still fuzzed (we add the dev-dep)
    if has("Cargo.toml"):
        return ("proptest (Rust, add dev-dep)", "Cargo.toml")
    return (None, None)


# --- (2) STATEFUL: invariant-heavy value-accounting -------------------------------------------
# Value-conservation/accounting signatures — their presence = there is an invariant that can be broken by
# a call sequence. Kept broad (EVM Solidity + Solana Rust), counting UNIQUE hits.
_STATEFUL_SIGNALS = [
    r"\btotalSupply\b", r"\bbalanceOf\b", r"mapping\s*\(\s*address\s*=>\s*uint",
    r"\btotalAssets\b", r"\btotalShares\b", r"\b_shares\b", r"\bshares\b",
    r"\breserve[0-9]?\b", r"\bliquidity\b", r"\bdeposit\b", r"\bwithdraw\b",
    r"\bredeem\b", r"\bborrow\b", r"\brepay\b", r"\bcollateral\b", r"\bdebt\b",
    r"\bmint\b", r"\bburn\b", r"\baccrue\b", r"\bcheckpoint\b", r"\brewardPerToken\b",
    # Solana
    r"#\[account\]", r"\blamports\b", r"token::(transfer|mint_to|burn)",
    r"pub\s+amount", r"pub\s+balance",
]
_CODE_EXT = (".sol", ".rs", ".vy", ".cairo", ".move")


def detect_stateful(root):
    """Return (is_stateful, hit_signals[])."""
    hits = set()
    scanned = 0
    for dp, _dn, fn in os.walk(root):
        # skip junk/dependency trees
        low = dp.replace("\\", "/").lower()
        if any(x in low for x in ("/node_modules/", "/.git/", "/lib/forge-std",
                                  "/target/", "/out/", "/artifacts/", "/cache/")):
            continue
        for name in fn:
            if not name.endswith(_CODE_EXT):
                continue
            scanned += 1
            if scanned > 4000:
                break
            try:
                with open(os.path.join(dp, name), "r", encoding="utf-8", errors="replace") as f:
                    txt = f.read()
            except Exception:
                continue
            for sig in _STATEFUL_SIGNALS:
                if sig not in hits and re.search(sig, txt):
                    hits.add(sig)
    # >=3 distinct accounting signals = value-accounting stateful (a lone mint/burn = weak)
    return (len(hits) >= 3, sorted(hits))


# --- (3) MOVEMENT: order-dependent I-NN from the model ----------------------------------------
# An I-NN that cannot be checked by a single read — multi-step / order-dependent / cumulative.
# A heuristic over the check:/pred:/the invariant's own wording text in system_model.md.
# The Cyrillic alternatives below are logic (they match Russian-language model text): KEEP verbatim.
# Rough meaning: sequence | call order | multi-step | between calls | accumulation | accumulator | ...
# | repeated call | two-phase | invariant is conserved | sum is conserved | risk-free cycle.
# (Russian alternatives below are logic: they match Russian-language model text — "sequence", "call order", "multi-step", "accumulation", "repeated call", "two-phase", "invariant is conserved", "risk-free cycle". KEEP.)
_MOVEMENT_RE = re.compile(
    r"последовательн|порядок\s+вызов|многошаг|между\s+вызов|накоплен|аккумул"
    r"|per-?block|checkpoint|reentr|повторн\w+\s+вызов|two-?phase|двухфаз"
    r"|\bsequence\b|\border\b|monoton|инвариант\s+сохран|сумм\w*\s+сохран"
    r"|no[\s-]*free[\s-]*mint|conservation|drain|цикл\w*\s+без\s+риск",
    re.I)
_I_LINE_RE = re.compile(r"\bI-\d+\b")


def detect_movement(model_path):
    """Return (has_movement, count_total_I, movement_examples[]). No model → (False, 0, [])."""
    if not model_path or not os.path.exists(model_path):
        return (False, 0, [])
    try:
        with open(model_path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:
        return (False, 0, [])
    total = len(set(_I_LINE_RE.findall(txt)))
    examples = []
    # look at lines/blocks that have an I-NN AND a movement signal (in the line itself or nearby)
    lines = txt.splitlines()
    for i, ln in enumerate(lines):
        if not _I_LINE_RE.search(ln):
            continue
        window = " ".join(lines[i:i + 4])  # the invariant + its check/pred lines below it
        if _MOVEMENT_RE.search(window):
            iid = _I_LINE_RE.search(ln).group(0)
            if iid not in [e[0] for e in examples]:
                examples.append((iid, ln.strip()[:90]))
    return (len(examples) > 0, total, examples[:6])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else "."
    model_path = None
    if "--model" in sys.argv:
        idx = sys.argv.index("--model")
        if idx + 1 < len(sys.argv):
            model_path = sys.argv[idx + 1]
    if model_path is None:
        # auto: system_model.md next to the target or in sessions/{slug}/
        cand = os.path.join(root, "system_model.md")
        model_path = cand if os.path.exists(cand) else None

    engine, ev = detect_engine(root)
    stateful, sigs = detect_stateful(root)
    movement, n_inv, mov_ex = detect_movement(model_path)

    if not engine or not stateful:
        why = ("no build config (nothing to compile/fuzz → web2/frontend/docs-only)"
               if not engine else
               "not invariant-heavy (stateless — if it parses a wire format/2+ clients → that is T8 "
               "differential, not T11)")
        verdict, engine_out = "SKIP", engine
    elif movement:
        why = ("all three conditions ✓ — build a harness from the order-dependent I-NN (listed), "
               "run it BEFORE a hypothesis, the sequence found = a machine-origin D-NN")
        verdict, engine_out = "APPLICABLE", engine
    else:
        why = ("BUILD+STATEFUL present, but the model has no order-dependent I-NN "
               + ("(model is empty — T10 first)" if n_inv == 0 else "(%d I-NN, all checkable by reading)" % n_inv)
               + ". Finish T10 with an order/sequence invariant → re-run. NOT a skip: invariant-heavy "
                 "stateful is T11's home")
        verdict, engine_out = "MAYBE", engine

    out = {
        "verdict": verdict,
        "engine": engine_out,
        "build_evidence": ev,
        "stateful": stateful,
        "stateful_signals": [s.strip("\\b") for s in sigs][:12],
        "model_invariants_total": n_inv,
        "order_dependent_I": [{"id": a, "line": b} for a, b in mov_ex],
        "reason": why,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # exit code: 0=APPLICABLE, 2=MAYBE, 3=SKIP (for a script branch in the skill)
    sys.exit({"APPLICABLE": 0, "MAYBE": 2, "SKIP": 3}[verdict])


if __name__ == "__main__":
    main()
