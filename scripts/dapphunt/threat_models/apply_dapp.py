#!/usr/bin/env python3
"""
apply_dapp.py — Threat-model application engine for dApp hunts.

Reads all YAML threat models in this directory, evaluates `applies_when` against
target session tags, and emits `threat_model_hypotheses.md` with instantiated
hypothesis text + verification steps for each matched model.

YAML tags come from:
- sessions/$DOMAIN/_tags.txt (manual, one tag per line)
- Auto-derived tags from artifact presence (see _autotag_session below)

Usage:
    python3 apply_dapp.py --target sessions/$DOMAIN
    python3 apply_dapp.py --target sessions/$DOMAIN --quick   # high+critical models only
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


# ── Minimal YAML reader (avoids PyYAML dependency for portability) ──
# Supports the subset used by our threat models: scalars, lists, nested dicts.
def _parse_yaml(text: str) -> dict:
    """Parse a strict subset of YAML used by threat-model files. No anchors, no tags."""
    lines = text.splitlines()
    return _parse_block(lines, 0, 0)[0]


def _parse_block(lines: List[str], start: int, indent: int) -> tuple:
    """Return (parsed_value, next_line_index)."""
    result: Dict = {}
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            i += 1
            continue
        cur_indent = len(stripped) - len(stripped.lstrip())
        if cur_indent < indent:
            break
        if cur_indent > indent:
            i += 1
            continue
        content = stripped.lstrip()

        if content.startswith("- "):
            # List item at this indent level — switch to list mode
            return _parse_list(lines, i, indent), i  # caller handles

        # key: value or key:
        if ":" in content:
            key, _, rest = content.partition(":")
            key = key.strip()
            rest = rest.strip()
            if rest == "" or rest.startswith("#"):
                # nested block — find children with indent > cur_indent
                child, ni = _parse_nested(lines, i + 1, cur_indent + 2)
                result[key] = child
                i = ni
            elif rest == "|":
                # multiline literal
                block, ni = _parse_literal_block(lines, i + 1, cur_indent + 2)
                result[key] = block
                i = ni
            elif rest.startswith("[") and rest.endswith("]"):
                # inline list
                inner = rest[1:-1].strip()
                items = [s.strip().strip("'\"") for s in inner.split(",") if s.strip()]
                result[key] = items
                i += 1
            else:
                # scalar
                result[key] = _coerce_scalar(rest.strip("'\""))
                i += 1
        else:
            i += 1
    return result, i


def _parse_nested(lines: List[str], start: int, indent: int) -> tuple:
    """Parse a nested block at given indent — could be dict or list of dicts."""
    if start >= len(lines):
        return {}, start
    # Look ahead to first non-empty non-comment line
    j = start
    while j < len(lines):
        s = lines[j].rstrip()
        if not s or s.lstrip().startswith("#"):
            j += 1
            continue
        break
    if j >= len(lines):
        return {}, j
    cur_indent = len(lines[j]) - len(lines[j].lstrip())
    content = lines[j].lstrip()
    if content.startswith("- "):
        return _parse_list(lines, j, cur_indent)
    return _parse_block(lines, j, cur_indent)


def _parse_list(lines: List[str], start: int, indent: int) -> tuple:
    items: List = []
    i = start
    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            i += 1
            continue
        cur_indent = len(stripped) - len(stripped.lstrip())
        if cur_indent < indent:
            break
        if cur_indent > indent:
            i += 1
            continue
        content = stripped.lstrip()
        if not content.startswith("- "):
            break
        item_text = content[2:].strip()
        if ":" in item_text and not item_text.endswith(":"):
            # First field of an inline dict
            key, _, rest = item_text.partition(":")
            sub: Dict = {key.strip(): _coerce_scalar(rest.strip().strip("'\""))}
            # Look for more keys at indent + 2
            j = i + 1
            while j < len(lines):
                ln = lines[j].rstrip()
                if not ln or ln.lstrip().startswith("#"):
                    j += 1
                    continue
                ji = len(ln) - len(ln.lstrip())
                if ji <= indent:
                    break
                c = ln.lstrip()
                if c.startswith("- "):
                    break
                if ":" in c:
                    k2, _, r2 = c.partition(":")
                    r2 = r2.strip()
                    if r2 == "" or r2 == "|":
                        child, nj = _parse_literal_block(lines, j + 1, ji + 2) if r2 == "|" else _parse_nested(lines, j + 1, ji + 2)
                        sub[k2.strip()] = child
                        j = nj
                    elif r2.startswith("[") and r2.endswith("]"):
                        inner = r2[1:-1].strip()
                        sub[k2.strip()] = [s.strip().strip("'\"") for s in inner.split(",") if s.strip()]
                        j += 1
                    else:
                        sub[k2.strip()] = _coerce_scalar(r2.strip("'\""))
                        j += 1
                else:
                    j += 1
            items.append(sub)
            i = j
        elif item_text.endswith(":"):
            # bare nested dict
            child, nj = _parse_nested(lines, i + 1, indent + 2)
            items.append(child)
            i = nj
        else:
            items.append(_coerce_scalar(item_text.strip("'\"")))
            i += 1
    return items, i


def _parse_literal_block(lines: List[str], start: int, indent: int) -> tuple:
    out_lines: List[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            out_lines.append("")
            i += 1
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent < indent:
            break
        out_lines.append(line[indent:])
        i += 1
    return "\n".join(out_lines).rstrip() + "\n", i


def _coerce_scalar(s: str):
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


# ── Threat-model evaluation ──
@dataclass
class MatchedModel:
    model_id: str
    title: str
    class_name: str
    severity_ceiling: str
    severity_floor: str
    matched_tags: List[str]
    hypotheses_instantiated: List[str] = field(default_factory=list)


def _autotag_session(session_dir: Path) -> Set[str]:
    """Derive tags from artifact presence."""
    tags: Set[str] = set()
    # auth_provider_config presence → tag each provider key
    cfg_path = session_dir / "auth_provider_config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                for k in cfg.keys():
                    tags.add(k.lower())
                # Wildcard detection in any field
                blob = json.dumps(cfg)
                if re.search(r"\*\.[a-z0-9-]+\.[a-z]{2,}", blob, re.IGNORECASE):
                    tags.add("has_auth_wildcard")
        except Exception:
            pass

    # crtsh subdomain count
    crt = session_dir / "crtsh.json"
    if crt.exists():
        try:
            data = json.loads(crt.read_text(encoding="utf-8"))
            if isinstance(data, list) and len(data) > 5:
                tags.add("has_many_subdomains")
            elif isinstance(data, dict) and any(len(v) > 5 for v in data.values() if isinstance(v, list)):
                tags.add("has_many_subdomains")
        except Exception:
            pass

    # iframe trust matrix → tag if any host missing headers
    iframe = session_dir / "iframe_trust_matrix.json"
    if iframe.exists():
        try:
            data = json.loads(iframe.read_text(encoding="utf-8"))
            blob = json.dumps(data)
            if "x-frame-options" not in blob.lower():
                tags.add("missing_frame_headers")
            if "clone" in blob.lower():
                tags.add("has_clone")
        except Exception:
            pass

    # clones.json
    if (session_dir / "clones.json").exists():
        tags.add("has_clone")

    # postmessage audit
    pm = session_dir / "postmessage_audit.json"
    if pm.exists():
        try:
            data = json.loads(pm.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("handlers"):
                tags.add("has_postmessage_listener")
        except Exception:
            pass

    # ai prompt-injection probe → tag if an LLM/AI feature was detected
    ai = session_dir / "ai_prompt_injection_probe.json"
    if ai.exists():
        try:
            data = json.loads(ai.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if data.get("has_ai_feature"):
                    tags.add("has_ai_feature")
                guess = (data.get("provider_guess") or "").lower()
                if guess == "anthropic":
                    tags.add("anthropic_sdk")
                elif guess == "openai":
                    tags.add("openai_sdk")
                if data.get("agentic_risk"):
                    tags.add("agentic_wallet")
        except Exception:
            pass

    # tokenlist
    if (session_dir / "tokenlist_audit.json").exists():
        tags.add("fetches_tokenlist")
    if (session_dir / "indexer_endpoints.json").exists():
        tags.add("uses_third_party_indexer")

    return tags


def _load_manual_tags(session_dir: Path) -> Set[str]:
    tags_file = session_dir / "_tags.txt"
    if not tags_file.exists():
        return set()
    return {ln.strip().lower() for ln in tags_file.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")}


def _model_applies(model: dict, tags: Set[str]) -> tuple[bool, List[str]]:
    applies_when = model.get("applies_when", {})
    matched: List[str] = []
    any_tag = applies_when.get("any_tag") or []
    if isinstance(any_tag, list):
        for t in any_tag:
            if t.lower() in tags:
                matched.append(t.lower())
    if not matched:
        return False, []
    return True, matched


def _instantiate(model: dict, session_dir: Path) -> List[str]:
    """Instantiate hypothesis text with target-specific values where possible."""
    out: List[str] = []
    hypotheses = model.get("hypotheses") or []
    if not isinstance(hypotheses, list):
        return out
    # Substitute target name
    target_name = session_dir.name
    for hyp in hypotheses:
        if not isinstance(hyp, dict):
            continue
        text = hyp.get("text", "")
        if isinstance(text, str):
            text = text.replace("{base_domain}", "<base_domain>")
            text = text.replace("{primary_host}", target_name)
            text = text.replace("{clone_host}", "<clone_host>")
        hid = hyp.get("id", "?")
        sev = hyp.get("severity_estimate", "?")
        verification = hyp.get("verification") or []
        verif_lines = "\n".join(f"  - {v}" for v in verification if isinstance(v, str))
        out.append(
            f"### {hid} (severity_estimate={sev})\n\n{text}\n\n**Verification**:\n{verif_lines}"
        )
    return out


def apply_models(session_dir: Path, models_dir: Path, quick_mode: bool = False) -> List[MatchedModel]:
    tags = _load_manual_tags(session_dir) | _autotag_session(session_dir)
    matched: List[MatchedModel] = []
    for yaml_path in sorted(models_dir.glob("*.yaml")):
        try:
            text = yaml_path.read_text(encoding="utf-8")
            model = _parse_yaml(text)
        except Exception as exc:
            print(f"warn: could not parse {yaml_path.name}: {exc}", file=sys.stderr)
            continue

        applies, matched_tags = _model_applies(model, tags)
        if not applies:
            continue

        ceiling = (model.get("severity_ceiling") or "").lower()
        if quick_mode and ceiling not in ("high", "critical"):
            continue

        m = MatchedModel(
            model_id=model.get("id", yaml_path.stem),
            title=model.get("title", ""),
            class_name=model.get("class", ""),
            severity_ceiling=ceiling or "",
            severity_floor=(model.get("severity_floor") or "").lower(),
            matched_tags=matched_tags,
            hypotheses_instantiated=_instantiate(model, session_dir),
        )
        matched.append(m)
    return matched


def write_report(matched: List[MatchedModel], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# Threat-Model Hypotheses\n")
    lines.append(f"Matched models: {len(matched)}\n")
    if not matched:
        lines.append("No threat models applied. Possible reasons:\n")
        lines.append("- `_tags.txt` missing or empty\n")
        lines.append("- Auto-tag artifacts not yet generated (run Phase 2-4 first)\n")
        lines.append("- Target genuinely does not match any modeled class\n")
        output.write_text("\n".join(lines), encoding="utf-8")
        return

    for m in matched:
        lines.append(f"## {m.model_id} — {m.title}\n")
        lines.append(f"- class: `{m.class_name}`")
        lines.append(f"- severity range: `{m.severity_floor}` → `{m.severity_ceiling}`")
        lines.append(f"- matched tags: {', '.join(m.matched_tags)}\n")
        for h in m.hypotheses_instantiated:
            lines.append(h)
            lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--target", type=Path, required=True, help="sessions/$DOMAIN/")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory holding threat-model YAML files",
    )
    parser.add_argument("--quick", action="store_true", help="High/critical models only")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.target.is_dir():
        print(f"error: session dir not found: {args.target}", file=sys.stderr)
        return 2

    matched = apply_models(args.target, args.models_dir, quick_mode=args.quick)
    output = args.output or (args.target / "threat_model_hypotheses.md")
    write_report(matched, output)

    print(f"Threat models matched: {len(matched)}")
    for m in matched:
        print(f"  {m.model_id}  ({m.severity_floor}→{m.severity_ceiling})  tags={','.join(m.matched_tags)}")
    print(f"Report written: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
