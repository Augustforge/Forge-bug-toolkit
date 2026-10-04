"""
responders.py — Disposition layer for matched mempool patterns.

Three tiers:
- alert_only       — Telegram/Discord webhook (no consequences)
- tip_protocol     — auto-DM protocol security contact (gated by manual approval)
- flashbots_protect — protective tx via Flashbots private bundle (NEVER auto)

Each tier writes to ~/.bbt/audit.log.
"""
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

AUDIT_LOG = Path.home() / ".bbt" / "audit.log"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK")

# Protocol security contacts — populate from on-chain SECURITY.txt / Immunefi / hardcoded
PROTOCOL_CONTACTS = {
    # protocol_name → security contact (Discord webhook, email, or @handle)
    # Pre-populate via _knowledge_base or manual edits
    # Example: "aave-v3": "https://discord.com/api/webhooks/.../aave_security"
}


def _audit(entry: dict):
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _format_alert_text(event: dict) -> str:
    return (
        f"🚨 [{event.get('pattern', '?')}] on {event.get('chain', '?')}\n"
        f"Tx: `{event.get('tx_hash', '?')}`\n"
        f"From: `{event.get('from', '?')}`\n"
        f"To: `{event.get('to', '?')}`\n"
        f"Selector: `{event.get('selector', '?')}`\n"
        f"Disposition: {event.get('disposition', '?')}\n"
        f"Reasons: {', '.join(event.get('reasons', []))}"
    )


def alert_only(event: dict) -> dict:
    """Tier 1: Telegram + Discord notification. Always safe."""
    result = {"telegram": False, "discord": False}
    text = _format_alert_text(event)

    if requests and TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
                timeout=10,
            )
            result["telegram"] = r.status_code == 200
        except Exception as e:
            print(f"[warn] telegram alert failed: {e}", file=sys.stderr)

    if requests and DISCORD_WEBHOOK:
        try:
            r = requests.post(
                DISCORD_WEBHOOK,
                json={"content": text},
                timeout=10,
            )
            result["discord"] = r.status_code in (200, 204)
        except Exception as e:
            print(f"[warn] discord alert failed: {e}", file=sys.stderr)

    _audit({**event, "responder": "alert_only", "result": result,
            "responder_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return result


def tip_protocol(event: dict, protocol_name: str = None, manual_approved: bool = False) -> dict:
    """Tier 2: Auto-DM protocol security contact. Gated."""
    if not manual_approved:
        return {"status": "gated", "reason": "tip_protocol requires manual_approved=True"}

    contact = PROTOCOL_CONTACTS.get(protocol_name) if protocol_name else None
    if not contact:
        return {"status": "no_contact", "reason": f"no security contact in PROTOCOL_CONTACTS for {protocol_name}"}

    text = (
        f"WHITE-HAT SECURITY ALERT (automated, via bug-bounty-toolkit watcher)\n\n"
        f"Pattern matched: {event.get('pattern')}\n"
        f"Chain: {event.get('chain')}\n"
        f"Suspect tx (in mempool, not yet mined):\n{event.get('tx_hash')}\n\n"
        f"Pattern reasons: {event.get('reasons')}\n\n"
        f"This is an automated notification. Please verify and respond. — bug-bounty-toolkit"
    )

    result = {"status": "failed", "contact": contact}
    if requests and contact.startswith("https://discord.com/api/webhooks/"):
        try:
            r = requests.post(contact, json={"content": text}, timeout=10)
            result["status"] = "sent" if r.status_code in (200, 204) else "failed"
            result["http"] = r.status_code
        except Exception as e:
            result["error"] = str(e)
    else:
        result["status"] = "unsupported_contact_type"
        result["note"] = "Only Discord webhook contacts supported in v1"

    _audit({**event, "responder": "tip_protocol", "protocol": protocol_name,
            "manual_approved": True, "result": result,
            "responder_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return result


def flashbots_protect(event: dict, protective_tx_hex: str = None,
                      manual_approved: bool = False, gpg_signed: bool = False) -> dict:
    """Tier 3: Protective tx via Flashbots private bundle. NEVER auto.

    Requires:
    - manual_approved=True (the operator approval per-event)
    - protective_tx_hex (pre-signed tx, NOT generated from memory)
    - gpg_signed=True (acknowledges legal posture)
    """
    if not (manual_approved and gpg_signed and protective_tx_hex):
        return {
            "status": "gated",
            "reason": "flashbots_protect requires manual_approved=True AND gpg_signed=True AND protective_tx_hex",
            "_safety_doc": "scripts/web3/mempool/_safety.md",
        }

    # Real impl would POST to https://relay.flashbots.net
    # Stubbed here — implementation depends on operational setup
    print("[CRITICAL] flashbots_protect would submit protective tx now", file=sys.stderr)
    print(f"  Pre-signed tx (truncated): {protective_tx_hex[:80]}...", file=sys.stderr)

    result = {
        "status": "STUBBED — implementation requires Flashbots wallet setup",
        "next_steps": [
            "1. POST tx_hex to https://relay.flashbots.net/v1/bundle",
            "2. Monitor bundle inclusion via flashbots API",
            "3. Audit on-chain result"
        ]
    }

    _audit({**event, "responder": "flashbots_protect", "manual_approved": True,
            "gpg_signed": True, "result": result,
            "responder_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    return result


# Dispatcher used by watcher.py
def dispatch_disposition(event: dict, dry_run: bool = False) -> dict:
    if dry_run:
        return {"status": "dry_run"}
    disposition = event.get("disposition", "alert_only")
    if disposition == "alert_only":
        return alert_only(event)
    elif disposition == "tip_protocol":
        # gated by default — manual approval needed
        return tip_protocol(event, manual_approved=False)
    elif disposition == "flashbots_protect":
        return flashbots_protect(event, manual_approved=False)
    else:
        return {"status": "unknown_disposition", "disposition": disposition}
