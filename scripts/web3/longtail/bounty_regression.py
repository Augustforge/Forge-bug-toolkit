#!/usr/bin/env python3
"""
bounty_regression.py — Given a paid bounty writeup (Verichains/rekt/Solodit/etc.),
extract root-cause CLASS and generate sibling-variant hypotheses for current target.

Premise (Thorchain 2022→2026 lesson): paid bounty fixes are often narrow — patch
specific exploit variant, but root-cause class remains alive. Sibling variants
(same C, different code path) exploited later.

Usage:
  # From URL (rekt/Verichains/blog post)
  python3 bounty_regression.py --bounty-url https://verichains.io/tsshock/ \\
      --target /path/to/repo --output sessions/$TARGET/bounty_regression.md

  # Fallback when URL paywalled/unavailable (E5)
  python3 bounty_regression.py --manual-text "summary of writeup..." \\
      --class-hint "tss_signature_extraction" \\
      --target /path/to/repo --output sessions/$TARGET/bounty_regression.md

  # Search Solodit for siblings of a known class (no specific URL)
  python3 bounty_regression.py --class-hint signature_replay \\
      --target /path/to/repo --output ...

Output: markdown with 3-5 sibling-variant hypotheses + Foundry test pointers.

Reuses scripts/web3/solodit_search.py to find sibling cases.
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

REPO_ROOT = Path(__file__).resolve().parents[3]
SOLODIT_MOD = REPO_ROOT / "scripts" / "web3" / "solodit_search.py"

# Crude class keywords for root-cause extraction
CLASS_KEYWORDS = {
    "tss_signature_extraction": ["tss", "tss-lib", "GG18", "GG20", "Paillier", "dlnproof", "TSSHOCK", "FROST"],
    "signature_replay": ["replay", "nonce", "signature verification", "EIP-712", "permit"],
    "reentrancy": ["reentrancy", "reenter", "callback", "Checks-Effects-Interactions"],
    "oracle_manipulation": ["oracle", "Chainlink", "Pyth", "TWAP", "price feed", "stale"],
    "flashloan_attack": ["flash loan", "flashloan", "atomic", "Aave loan", "Balancer loan"],
    "governance_takeover": ["governance", "multisig", "threshold", "signer compromise", "Ronin"],
    "cross_chain_bridge": ["bridge", "DVN", "LayerZero", "Wormhole", "VAA", "guardian"],
    "access_control": ["onlyOwner", "missing modifier", "access control", "role check"],
    "math_overflow": ["overflow", "underflow", "rounding", "precision loss", "SafeMath"],
    "proxy_storage": ["proxy", "storage collision", "initializer", "delegatecall"],
}

# Sibling hypothesis templates per class
SIBLING_TEMPLATES = {
    "tss_signature_extraction": [
        "If patch addressed α-shuffle, check sibling variants (c-split / c-guess / BitForge Paillier) explicitly.",
        "Verify Paillier biprime validation in ALL paths (keygen + signing + re-sharing) not just one.",
        "Check ZK proof iteration count — hardcoded ≥128 vs configurable (downgrade attack).",
        "Check forks of this tss-lib version — did they merge the patch? Or diverged earlier?",
    ],
    "signature_replay": [
        "Verify replay protection in ALL signed-message paths, not just the patched one.",
        "Check cross-chain replay — same payload accepted on multiple deployments?",
        "Permit / Permit2 / EIP-712: chainId + verifyingContract in domain separator everywhere?",
    ],
    "reentrancy": [
        "Read-only reentrancy: does patched function call external before state finalized?",
        "Cross-function reentrancy: A locks, B unlocked but reads stale state from A?",
        "Cross-contract reentrancy: token hook (ERC-777, ERC-1155 onReceived) callback?",
    ],
    "oracle_manipulation": [
        "If patch added staleness check on one oracle, check siblings — do all oracle reads have the same protection?",
        "Single source → manipulate cheap. N-of-M aggregation present?",
        "Patch addressed TWAP — single-block manipulation still works on spot?",
    ],
    "flashloan_attack": [
        "If patch added reentrancy guard on one entrypoint — do all entrypoints have the same protection?",
        "Flashloan + governance: can attacker borrow → vote → repay?",
        "Cross-protocol flashloan: borrow from A, exploit B, repay A — A's patch does not help if B vulnerable.",
    ],
    "governance_takeover": [
        "Multisig threshold — ≥4-of-7 for serious DeFi? Patch increased threshold? Check actual signer count.",
        "Timelock delay ≥48h? Patch added timelock? What if emergency bypass exists?",
        "Cross-protocol governance attack: compromise via dependency vote?",
    ],
    "cross_chain_bridge": [
        "If patch added DVN to one path — other paths same DVN config?",
        "VAA / message replay across chains — payload distinguishes destinations?",
        "Patch added source-chain validation — check other entry points (mint, lock, redeem) same?",
    ],
    "access_control": [
        "Patch added modifier — siblings of patched function same modifier?",
        "Role assignment paths — can role be set by lower-privileged actor?",
        "Multi-sig role rotation — patch fixed one, others same vulnerability?",
    ],
    "math_overflow": [
        "Patch used SafeMath / unchecked → siblings of patched arithmetic same precision?",
        "Rounding direction — favours protocol vs user? Vault inflation attack class.",
        "Conversion math — uint256 to uint8 truncations in other functions same path?",
    ],
    "proxy_storage": [
        "Patch reordered storage layout — did all upgrades since respected ordering?",
        "Initializer reentrancy / double-init in other proxy contracts in same protocol?",
        "delegatecall to attacker-controlled address — patch one entry point, siblings same?",
    ],
}


def fetch_url_text(url: str) -> str | None:
    """Best-effort URL fetch. Returns None on failure (E5 fallback)."""
    if requests is None:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": "BBT/1.0"}, timeout=20)
        if r.status_code == 200:
            return r.text
        print(f"[warn] {url}: HTTP {r.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"[warn] fetch {url}: {e}", file=sys.stderr)
    return None


def strip_html(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_class(text: str, hint: str | None) -> str:
    if hint and hint in SIBLING_TEMPLATES:
        return hint
    t = text.lower()
    scores = {}
    for cls, keywords in CLASS_KEYWORDS.items():
        scores[cls] = sum(1 for k in keywords if k.lower() in t)
    if not any(scores.values()):
        return "unknown"
    return max(scores.items(), key=lambda x: x[1])[0]


def search_target_for_class(target: Path, cls: str) -> list[str]:
    """Crude grep target source for class-related code surface."""
    if not target.is_dir():
        return []
    keywords = CLASS_KEYWORDS.get(cls, [])
    if not keywords:
        return []
    hits = []
    exts = [".sol", ".rs", ".go", ".ts"]
    for ext in exts:
        for f in target.rglob(f"*{ext}"):
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    ll = line.lower()
                    if any(k.lower() in ll for k in keywords):
                        hits.append(f"{f.relative_to(target)}:{i}: {line.strip()[:120]}")
                        if len(hits) >= 10:
                            return hits
            except Exception:
                continue
    return hits


def render(cls: str, source: str, raw_excerpt: str, hits: list[str], output: Path | None) -> str:
    lines = []
    lines.append(f"# Bounty Regression — Class: `{cls}`")
    lines.append("")
    lines.append(f"**Source**: {source}")
    lines.append("")
    if raw_excerpt:
        lines.append(f"**Excerpt** (first 500 chars):")
        lines.append("")
        lines.append("> " + raw_excerpt[:500].replace("\n", " "))
        lines.append("")

    lines.append("## Sibling-variant hypotheses for current target")
    lines.append("")
    templates = SIBLING_TEMPLATES.get(cls, [])
    if not templates:
        lines.append("_No sibling templates registered for this class. Either:_")
        lines.append("- Class is novel → consider authoring new threat_model YAML")
        lines.append("- Class hint was unclear → re-run with `--class-hint <known_class>`")
    else:
        for i, t in enumerate(templates, 1):
            lines.append(f"{i}. {t}")
    lines.append("")

    if hits:
        lines.append("## Code surface in target matching this class")
        lines.append("")
        for h in hits:
            lines.append(f"- `{h}`")
        lines.append("")
        lines.append("> Each hit = location to apply sibling-variant hypotheses above.")
    else:
        lines.append("## Code surface")
        lines.append("")
        lines.append("_No matching code surface found in target (or target not provided)._")
        lines.append("")

    lines.append("## Next steps")
    lines.append("- Treat hypotheses above as input for J1 (invariant discovery)")
    lines.append("- Apply `prompts/hypothesis_triage.md` for filtering")
    lines.append("- For confirmed siblings → consider authoring new threat_model YAML")
    lines.append(f"- Solodit search for class siblings: `python3 scripts/web3/solodit_search.py --query \"{cls}\"`")

    md = "\n".join(lines)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md, encoding="utf-8")
        print(f"[ok] {output}")
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bounty-url", help="Writeup URL (rekt/Verichains/blog)")
    ap.add_argument("--manual-text", help="Paste raw writeup text (E5 fallback when URL fails)")
    ap.add_argument("--class-hint", help="Explicit class label, e.g. 'tss_signature_extraction', 'oracle_manipulation'")
    ap.add_argument("--target", help="Path to target source repo (for sibling code surface grep)")
    ap.add_argument("--output", help="Output markdown path")
    args = ap.parse_args()

    text = ""
    source = "(none)"
    if args.bounty_url:
        html = fetch_url_text(args.bounty_url)
        if html:
            text = strip_html(html)
            source = args.bounty_url
        else:
            print(f"[err] failed to fetch {args.bounty_url} — rerun with --manual-text", file=sys.stderr)
            sys.exit(2)
    elif args.manual_text:
        text = args.manual_text
        source = "(manual text input)"
    elif args.class_hint:
        text = ""
        source = f"(no writeup — direct class={args.class_hint})"
    else:
        ap.error("Provide --bounty-url OR --manual-text OR --class-hint")

    cls = detect_class(text, args.class_hint)
    print(f"[info] detected class: {cls}")

    hits = []
    if args.target:
        t = Path(args.target)
        hits = search_target_for_class(t, cls)
        print(f"[info] {len(hits)} code surface hits in target")

    output = Path(args.output) if args.output else None
    md = render(cls, source, text, hits, output)
    if not output:
        print(md)


if __name__ == "__main__":
    main()
