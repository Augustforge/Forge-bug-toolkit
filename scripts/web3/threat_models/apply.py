#!/usr/bin/env python3
"""
apply.py — Threat-model engine.

Loads all *.yaml in this directory (skip _*.yaml), matches against target
context (chain.json + optional _tags.txt), emits markdown with instantiated
hypotheses + optional executable_checks results.

Usage:
  python3 apply.py --target sessions/$TARGET --output sessions/$TARGET/threat_model_hypotheses.md
  python3 apply.py --list                                 # list loaded models
  python3 apply.py --target sessions/$T --quick           # quick mode: filter severity_floor >= medium
  python3 apply.py --target sessions/$T --protocol-class bridge --tags tss,mpc  # CLI override

Features:
- E1 hash-pinning: model_id@sha256(yaml)[:8] in output
- E3 severity_floor filtering for quick mode
- E7 last_validated_against passthrough to output
- E8 negative_match support

Output format: markdown sections per matched model.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML required. Install: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


MODELS_DIR = Path(__file__).parent
SEVERITY_ORDER = {"low": 0, "medium": 1, "med": 1, "high": 2, "critical": 3}


def load_models() -> list[tuple[Path, dict, str]]:
    """Returns list of (path, model_dict, sha8_hash) for all valid YAML files."""
    out = []
    for yml in sorted(MODELS_DIR.glob("*.yaml")):
        if yml.name.startswith("_"):
            continue
        try:
            content = yml.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if not isinstance(data, dict) or "id" not in data:
                print(f"WARN: {yml.name} missing 'id' field, skipping", file=sys.stderr)
                continue
            sha8 = hashlib.sha256(content.encode()).hexdigest()[:8]
            out.append((yml, data, sha8))
        except yaml.YAMLError as e:
            print(f"WARN: {yml.name} YAML error: {e}", file=sys.stderr)
            continue
    return out


def load_target_context(target: Path, cli_protocol_class: str | None,
                        cli_tags: list[str] | None) -> dict:
    """Build target context from chain.json + _tags.txt + CLI overrides."""
    ctx = {
        "chain": "unknown",
        "protocol_class": None,
        "tags": set(),
        "source_path": None,
    }
    chain_json = target / "chain.json"
    if chain_json.exists():
        try:
            data = json.loads(chain_json.read_text(encoding="utf-8"))
            ctx["chain"] = data.get("chain", "unknown")
            ctx["source_path"] = data.get("source_path")
            if "framework" in data and data["framework"]:
                ctx["tags"].add(data["framework"])
        except Exception as e:
            print(f"WARN: failed to read chain.json: {e}", file=sys.stderr)

    tags_txt = target / "_tags.txt"
    if tags_txt.exists():
        try:
            for line in tags_txt.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("protocol_class:"):
                    # Special line: protocol_class:bridge → sets ctx["protocol_class"]
                    pc = line.split(":", 1)[1].strip().lower()
                    if pc and ctx["protocol_class"] is None:
                        ctx["protocol_class"] = pc
                else:
                    ctx["tags"].add(line.lower())
        except Exception:
            pass

    if cli_protocol_class:
        ctx["protocol_class"] = cli_protocol_class.lower()
    if cli_tags:
        ctx["tags"].update(t.strip().lower() for t in cli_tags if t.strip())

    return ctx


def matches(model: dict, ctx: dict) -> tuple[bool, str]:
    """Returns (matched, reason). Reason is human-readable diagnostic."""
    applies = model.get("applies_when", {})
    if not isinstance(applies, dict):
        return False, "applies_when missing or malformed"

    pc_list = applies.get("protocol_class", [])
    if pc_list and "any" not in pc_list:
        if ctx["protocol_class"] is None:
            return False, "target protocol_class unknown — set via --protocol-class or _tags.txt"
        if ctx["protocol_class"] not in pc_list:
            return False, f"protocol_class mismatch: target={ctx['protocol_class']}, model wants {pc_list}"

    tag_list = applies.get("tags", [])
    if tag_list and "any" not in tag_list:
        tag_set = set(t.lower() for t in tag_list)
        overlap = ctx["tags"] & tag_set
        if not overlap:
            return False, f"no tag overlap: target={sorted(ctx['tags'])} vs model wants any of {sorted(tag_set)}"

    chain_list = applies.get("chain", ["any"])
    if chain_list and "any" not in chain_list:
        if ctx["chain"] not in chain_list:
            return False, f"chain mismatch: target={ctx['chain']}, model wants {chain_list}"

    neg = model.get("negative_match") or {}
    neg_tags = set(t.lower() for t in neg.get("tags", []))
    if neg_tags & ctx["tags"]:
        return False, f"negative_match: target has {sorted(neg_tags & ctx['tags'])}"
    neg_pc = neg.get("protocol_class", [])
    if ctx["protocol_class"] and ctx["protocol_class"] in neg_pc:
        return False, f"negative_match: protocol_class={ctx['protocol_class']}"

    return True, "matched"


def filter_severity(models: list, mode: str) -> list:
    """In quick mode — only models with severity_floor >= medium."""
    if mode != "quick":
        return models
    out = []
    for path, m, h in models:
        floor = SEVERITY_ORDER.get(str(m.get("severity_floor", "low")).lower(), 0)
        if floor >= 1:                                       # medium+
            out.append((path, m, h))
    return out


def run_executable_checks(model: dict, ctx: dict) -> list[dict]:
    """Run grep/regex_count checks against source_path. Returns hit list."""
    hits = []
    checks = model.get("executable_checks") or []
    src = ctx.get("source_path")
    if not checks or not src or not Path(src).is_dir():
        return hits

    src_path = Path(src)
    lang_exts = {
        "go": [".go"], "rust": [".rs"], "sol": [".sol"],
        "ts": [".ts", ".tsx"], "js": [".js", ".jsx"], "py": [".py"],
    }

    for check in checks:
        ctype = check.get("type")
        if ctype == "grep":
            pattern = check.get("pattern", "")
            if not pattern:
                continue
            langs = check.get("languages", [])
            exts = set()
            for lng in langs:
                exts.update(lang_exts.get(lng, []))
            if not exts:
                continue
            try:
                regex = re.compile(pattern)
            except re.error:
                continue
            count = 0
            samples = []
            for ext in exts:
                for f in src_path.rglob(f"*{ext}"):
                    try:
                        for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                            if regex.search(line):
                                count += 1
                                if len(samples) < 3:
                                    samples.append(f"{f.relative_to(src_path)}:{i}: {line.strip()[:120]}")
                    except Exception:
                        continue
            if count > 0:
                hits.append({
                    "check": ctype,
                    "pattern": pattern,
                    "count": count,
                    "samples": samples,
                    "severity": check.get("severity_if_match", "low"),
                    "note": check.get("note", ""),
                })
        elif ctype == "regex_count":
            pattern = check.get("pattern", "")
            threshold = check.get("threshold_below")
            if not pattern or threshold is None:
                continue
            langs = check.get("languages", [])
            exts = set()
            for lng in langs:
                exts.update(lang_exts.get(lng, []))
            try:
                regex = re.compile(pattern)
            except re.error:
                continue
            total = 0
            for ext in exts:
                for f in src_path.rglob(f"*{ext}"):
                    try:
                        text = f.read_text(encoding="utf-8", errors="ignore")
                        total += len(regex.findall(text))
                    except Exception:
                        continue
            if total < threshold:
                hits.append({
                    "check": ctype,
                    "pattern": pattern,
                    "count": total,
                    "threshold_below": threshold,
                    "severity": check.get("severity_if_match", "medium"),
                    "note": check.get("note", "") + f" (found {total}, threshold {threshold})",
                })
        elif ctype == "cast_call":
            hits.append({
                "check": ctype,
                "cmd": check.get("cmd", ""),
                "severity": "manual",
                "note": "STUB — run manually if target on-chain: " + check.get("note", ""),
            })
    return hits


def render(matched: list, ctx: dict, target_path: Path) -> str:
    """Build markdown output."""
    lines = []
    lines.append(f"# Threat Model Hypotheses — {target_path.name}")
    lines.append("")
    lines.append(f"_Generated: {datetime.now(timezone.utc).isoformat()}_")
    lines.append(f"_Target context: chain={ctx['chain']}, protocol_class={ctx['protocol_class']}, tags={sorted(ctx['tags']) or '(none)'}_")
    lines.append("")
    lines.append("> Each section below = matched threat model applied to this target.")
    lines.append("> Hypotheses are templates — Claude must instantiate for specific code elements.")
    lines.append("> After review — run `prompts/hypothesis_triage.md` to filter REFUTED.")
    lines.append("")

    if not matched:
        lines.append("**No threat models matched current target context.**")
        lines.append("")
        lines.append("Possible reasons:")
        lines.append("- `--protocol-class` not specified and `chain.json` lacks framework info")
        lines.append("- No `_tags.txt` in session — Claude must set tags after initial reading")
        lines.append("- Genuinely no model fits this target class (good news — write a new YAML if you find a bug here)")
        return "\n".join(lines)

    for path, model, sha8 in matched:
        lines.append("---")
        lines.append("")
        lines.append(f"## {model.get('name', model['id'])}")
        lines.append(f"`{model['id']}@{sha8}` — `{path.name}`")
        lines.append("")
        sf = model.get("severity_floor", "?")
        sc = model.get("severity_ceiling", "?")
        lines.append(f"**Severity range**: {sf} → {sc}")
        lines.append("")

        lines.append("**Assumption violated**:")
        lines.append("")
        lines.append("> " + (model.get("assumption_violated") or "").strip().replace("\n", "\n> "))
        lines.append("")

        actors = model.get("actors") or []
        if actors:
            lines.append("**Actors**:")
            for a in actors:
                lines.append(f"- `{a.get('role', '?')}` — {a.get('capability', '')}")
            lines.append("")

        attack = (model.get("attack_vector") or "").strip()
        if attack:
            lines.append("**Attack vector**:")
            lines.append("")
            lines.append("> " + attack.replace("\n", "\n> "))
            lines.append("")

        hyps = model.get("hypotheses_template") or []
        if hyps:
            lines.append("**Hypotheses to instantiate** (for this target's code):")
            for i, h in enumerate(hyps, 1):
                lines.append(f"{i}. {h}")
            lines.append("")

        cs = model.get("case_studies") or []
        if cs:
            lines.append(f"**Case studies**: {', '.join(cs)}")
            lines.append("")

        rc = model.get("related_checklists") or []
        rp = model.get("related_prompts") or []
        if rc or rp:
            if rc:
                lines.append("**Related checklists**:")
                for c in rc:
                    lines.append(f"- `{c}`")
            if rp:
                lines.append("**Related prompts**:")
                for p in rp:
                    lines.append(f"- `{p}`")
            lines.append("")

        lv = model.get("last_validated_against") or {}
        if lv:
            lines.append(f"**Last validated**: {lv.get('date', '?')} on {lv.get('targets') or '(none)'} — {lv.get('outcome', '?')}")
            lines.append("")

        hits = run_executable_checks(model, ctx)
        if hits:
            lines.append("**Executable checks ran**:")
            for h in hits:
                lines.append(f"- `{h['check']}` ({h.get('severity', '?')}): {h.get('note', '')}")
                if h.get("samples"):
                    for s in h["samples"]:
                        lines.append(f"  - `{s}`")
                elif h.get("cmd"):
                    lines.append(f"  - `{h['cmd']}`")
            lines.append("")
        elif model.get("executable_checks"):
            lines.append("_Executable checks defined but produced no hits (no source available or patterns didn't match)._")
            lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Apply threat models to target session.")
    ap.add_argument("--target", help="Session directory (sessions/$TARGET)")
    ap.add_argument("--output", help="Output markdown file (default: <target>/threat_model_hypotheses.md)")
    ap.add_argument("--list", action="store_true", help="List loaded models and exit")
    ap.add_argument("--quick", action="store_true", help="Quick mode — filter severity_floor >= medium")
    ap.add_argument("--protocol-class", help="Override protocol class (bridge/amm/lending/...)")
    ap.add_argument("--tags", help="Comma-separated tags (override/append to _tags.txt)")
    args = ap.parse_args()

    models = load_models()
    if args.list:
        print(f"Loaded {len(models)} threat models:")
        for path, m, h in models:
            sf = m.get("severity_floor", "?")
            sc = m.get("severity_ceiling", "?")
            print(f"  - {m['id']}@{h}  [{sf}→{sc}]  {path.name}")
        return

    if not args.target:
        ap.error("--target required (or --list to inspect models)")

    target = Path(args.target)
    if not target.is_dir():
        ap.error(f"Target dir not found: {target}")

    tags = args.tags.split(",") if args.tags else None
    ctx = load_target_context(target, args.protocol_class, tags)

    mode = "quick" if args.quick else "deep"
    models = filter_severity(models, mode)

    matched = []
    skipped = []
    for path, m, sha8 in models:
        ok, reason = matches(m, ctx)
        if ok:
            matched.append((path, m, sha8))
        else:
            skipped.append((m["id"], reason))

    out_md = render(matched, ctx, target)
    out_path = Path(args.output) if args.output else target / "threat_model_hypotheses.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_md, encoding="utf-8")

    print(f"Matched {len(matched)} model(s), skipped {len(skipped)}.")
    print(f"Output: {out_path}")
    if skipped and "--verbose" in sys.argv:
        print("Skipped:")
        for mid, reason in skipped:
            print(f"  - {mid}: {reason}")


if __name__ == "__main__":
    main()
