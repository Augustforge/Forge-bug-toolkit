# Findings DB — Structured Records with Claude-as-Peer-Reviewer

## Why it is needed

`_knowledge_base.py` is an append-only log. **No validation, no reputation weighting, no peer review**. Without this:
- The same false positive repeats for months
- Real findings do not stand out from the noise
- No measure of hunting quality over time

Findings DB solves this: every serious finding goes through structured adversarial review, accumulates a reputation score, gives the signal "how often this hunter is right per class".

## Architecture

```
~/.bbt/kb/
├── findings.jsonl                  # existing (KB)
├── threat_models.jsonl             # existing (Phase 1)
└── findings_db/                    # NEW
    ├── findings.jsonl              # append-only structured records
    ├── reviews.jsonl               # per-finding review history
    └── reputation.json             # cached per-class reputation
```

## Workflow

1. **Hunter records preliminary finding** in quick KB via `_knowledge_base.py record`
2. **Promote to findings_db**: `_knowledge_base.py promote --kb-id X --to findings_db`
3. **Pre-review** (`add_finding.py`): hunter fills required fields (severity, class, target, exploit description, PoC reference)
4. **Adversarial review** (`peer_review.py`):
   - Round 1: Claude as adversarial reviewer — 3 reasons FP, 3 reasons valid, verdict + confidence
   - Round 2: Claude with different frame (e.g., "as the project's senior dev") — independent review
   - Consensus computed
5. **Optional submission** to bounty platform (tracked via `_crm.py`)
6. **CRM outcome feeds back** — `reputation.py` recomputes per-class scores when CRM status changes
7. **Dispute mechanism** (`dispute.py`): if CRM says "rejected" but hunter disagrees — formal dispute record

## Honest limit

**Solo hunter setting**: peer-reviewer is Claude, not human. Not a real peer review. But **better than nothing**:
- Adversarial framing catches obvious FPs hunter missed
- Multi-frame review reduces single-perspective blind spots
- Structured record + reputation score gives quantifiable progress signal

For true peer review (>1 human reviewer) — Tier 3+. See `export.py` for PGP-signed bundle export to trusted peers.

## Schema (per finding)

See `schema.json`. Key fields:

```json
{
  "finding_id": "fd_<8hex>",
  "timestamp": "2026-05-18T...",
  "kb_id": "kb_xxx",                  // bridge to existing KB
  "target": "uniswap-v3",
  "severity_claimed": "high",
  "severity_after_review": null,       // filled by peer_review
  "class": "oracle_manipulation",
  "threat_models": ["tss_validator_extraction"],
  "pre_review_text": "...",
  "peer_review": [
    {"reviewer": "claude_adversarial", "verdict": "plausible", "confidence": 0.7, "rationale": "..."},
    {"reviewer": "claude_dev_frame", "verdict": "refuted", "confidence": 0.4, "rationale": "..."}
  ],
  "consensus": "needs_human_review",
  "crm_id": null,
  "crm_status": null,
  "reputation_impact": null,           // populated after CRM outcome
  "related_findings": []
}
```

## Per-class reputation

Each class (reentrancy, oracle, governance...) is tracked separately. Computed from CRM outcomes:

- `+10` for paid bounty
- `+3` for accepted (no payout)
- `-2` for rejected
- `-1` for confirmed duplicate
- `+1 / -1` adjustments for dispute resolution

Per-class score visible via `reputation.py --update --show`.

Used as **confidence signal** in future: if hunter has high reputation in "oracle_manipulation", new oracle findings get boosted in triage.

## Integration

- `deephunt.md` J9 — mandatory `add_finding.py --pre-review` BEFORE submit
- Weekly cron: `python3 reputation.py --update`
- Daily digest shows: "reputation week-over-week, top-3 successful threat_models"
- `_crm.py` callbacks: when status changes → automatic `reputation.py` update + optional `dispute.py` trigger

## Anti-pattern

**Don't** treat Claude peer-review as authoritative. It's a filter, not a verdict. Confirmed by:
- Real exploitation (PoC running)
- Project's response (if submitted)
- Counter-evidence from other sources

**Don't** lower confidence in your own findings just because Claude flagged FP. Adversarial reviewer's job is to challenge. But hunter's judgment with code in front of him > Claude's reading without seeing protocol context.

## Output integration with rest of toolkit

- Hunter's reputation per class → boost factor in `hypothesis_triage.md` (future iteration)
- Successful threat_models tracked via `record-threat-model` — feeds `daily_digest.py`
- Failures feed back to `failure_analysis.py` (existing)
