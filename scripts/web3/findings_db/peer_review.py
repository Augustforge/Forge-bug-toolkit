#!/usr/bin/env python3
"""
peer_review.py — Generate adversarial review prompts for Claude to fill.

NOT a fully automated review — it is a **prompt scaffold**. Hunter copies output
to Claude session, gets verdict, pastes back via --record-review.

Two-frame review:
  - claude_adversarial — "find 3 reasons it might be FP"
  - claude_dev_frame — "as senior dev on this project, push back on this"

After both verdicts in — automatic consensus computed.

Usage:
  python3 peer_review.py --finding-id fd_abc12345        # show prompts
  python3 peer_review.py --finding-id fd_abc12345 --record-review \\
      --reviewer claude_adversarial --verdict plausible --confidence 0.7 \\
      --rationale "..." --fp-reasons "...,..." --valid-reasons "..."
  python3 peer_review.py --finding-id fd_abc12345 --compute-consensus
"""
import argparse
import json
import sys
import time
from pathlib import Path

DB_DIR = Path.home() / ".bbt" / "kb" / "findings_db"
FINDINGS_FILE = DB_DIR / "findings.jsonl"
REVIEWS_FILE = DB_DIR / "reviews.jsonl"


ADVERSARIAL_PROMPT = """\
# Adversarial Peer Review

You're an adversarial reviewer of a bug-bounty finding. Your job: **prove it's a false positive**.

## Finding details
- **finding_id**: {finding_id}
- **target**: {target}
- **class**: {cls}
- **severity claimed**: {severity}
- **threat models**: {tms}

## Pre-review text
{text}

## Tasks
1. **3 reasons it might be FP** (concrete, code-aware if possible)
2. **3 reasons it might be valid** (steelman the hunter's case)
3. **Verdict**: refuted | plausible | interesting | needs_deep | needs_human
4. **Confidence** in verdict (0-1 float)
5. **Rationale**: one paragraph summary

## Output format

```
FP-1: ...
FP-2: ...
FP-3: ...
VALID-1: ...
VALID-2: ...
VALID-3: ...
VERDICT: <one of: refuted | plausible | interesting | needs_deep | needs_human>
CONFIDENCE: 0.7
RATIONALE: <one paragraph>
```

After generation — copy this block into `peer_review.py --record-review` to persist.
"""

DEV_FRAME_PROMPT = """\
# Project Senior Dev Frame Review

You're the senior developer **on the team that wrote this code**. Hunter submitted finding below.
Your job: **defend the design choice**. Find why hunter is wrong.

> Note: this frame is DIFFERENT from adversarial-reviewer above. Adversarial tries
> general FP angles. Dev frame uses project-specific knowledge.

## Finding details
- **finding_id**: {finding_id}
- **target**: {target}
- **class**: {cls}
- **severity claimed**: {severity}

## Pre-review text
{text}

## Tasks
1. **3 design reasons it's not a bug** (was intended, fits architecture, design decision)
2. **3 lurking issues hunter missed**: if you actually pushed this through review, what additional issues might exist?
3. **Verdict**: same enum as adversarial
4. **Confidence** in verdict (0-1)
5. **Rationale**: one paragraph

## Output format
Same as adversarial — different reasoning.
"""


def load_finding(finding_id: str) -> tuple[dict | None, int]:
    if not FINDINGS_FILE.exists():
        return None, -1
    lines = FINDINGS_FILE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            e = json.loads(line)
            if e.get("finding_id") == finding_id:
                return e, i
        except Exception:
            continue
    return None, -1


def save_finding(entry: dict, idx: int):
    lines = FINDINGS_FILE.read_text(encoding="utf-8").splitlines()
    lines[idx] = json.dumps(entry, ensure_ascii=False)
    FINDINGS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def show_prompts(entry: dict):
    ctx = {
        "finding_id": entry["finding_id"],
        "target": entry.get("target", "?"),
        "cls": entry.get("class", "?"),
        "severity": entry.get("severity_claimed", "?"),
        "tms": ", ".join(entry.get("threat_models", [])) or "(none)",
        "text": entry.get("pre_review_text", "")[:2000],
    }
    print("=" * 70)
    print("ADVERSARIAL FRAME")
    print("=" * 70)
    print(ADVERSARIAL_PROMPT.format(**ctx))
    print()
    print("=" * 70)
    print("DEV FRAME")
    print("=" * 70)
    print(DEV_FRAME_PROMPT.format(**ctx))


def record_review(entry: dict, idx: int, args):
    review = {
        "reviewer": args.reviewer,
        "verdict": args.verdict,
        "confidence": float(args.confidence) if args.confidence else None,
        "rationale": args.rationale or "",
        "fp_reasons": [r.strip() for r in (args.fp_reasons or "").split("|") if r.strip()],
        "valid_reasons": [r.strip() for r in (args.valid_reasons or "").split("|") if r.strip()],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    entry.setdefault("peer_review", []).append(review)
    save_finding(entry, idx)
    REVIEWS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REVIEWS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"finding_id": entry["finding_id"], **review}, ensure_ascii=False) + "\n")
    print(f"[ok] review recorded for {entry['finding_id']} (reviewer={args.reviewer})")


def compute_consensus(entry: dict, idx: int):
    reviews = entry.get("peer_review", [])
    if len(reviews) < 2:
        print(f"[i] need ≥2 reviews; have {len(reviews)}")
        return
    verdicts = [r["verdict"] for r in reviews]
    if all(v == "refuted" for v in verdicts):
        consensus = "refuted"
    elif "refuted" in verdicts and "plausible" in verdicts:
        consensus = "needs_human_review"
    elif any(v == "needs_human" for v in verdicts):
        consensus = "needs_human_review"
    elif all(v in ("plausible", "interesting", "needs_deep") for v in verdicts):
        scores = {"plausible": 1, "interesting": 2, "needs_deep": 1}
        total = sum(scores.get(v, 0) for v in verdicts)
        if any(v == "interesting" for v in verdicts) and total >= 2:
            consensus = "interesting"
        else:
            consensus = "plausible"
    else:
        consensus = "needs_human_review"

    entry["consensus"] = consensus
    save_finding(entry, idx)
    print(f"[ok] consensus = {consensus}")
    print(f"     verdicts in: {verdicts}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finding-id", required=True)
    ap.add_argument("--record-review", action="store_true")
    ap.add_argument("--reviewer", choices=["claude_adversarial", "claude_dev_frame", "human"])
    ap.add_argument("--verdict", choices=["refuted", "plausible", "interesting", "needs_deep", "needs_human"])
    ap.add_argument("--confidence", help="0.0-1.0")
    ap.add_argument("--rationale")
    ap.add_argument("--fp-reasons", help="Pipe-separated list (reason1|reason2|...)")
    ap.add_argument("--valid-reasons", help="Pipe-separated list")
    ap.add_argument("--compute-consensus", action="store_true")
    args = ap.parse_args()

    entry, idx = load_finding(args.finding_id)
    if not entry:
        print(f"[err] finding {args.finding_id} not found in {FINDINGS_FILE}", file=sys.stderr)
        sys.exit(1)

    if args.compute_consensus:
        compute_consensus(entry, idx)
        return

    if args.record_review:
        if not args.reviewer or not args.verdict:
            ap.error("--record-review requires --reviewer and --verdict")
        record_review(entry, idx, args)
        return

    show_prompts(entry)


if __name__ == "__main__":
    main()
