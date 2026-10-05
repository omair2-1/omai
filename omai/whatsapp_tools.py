"""WhatsApp tools (spec Phase 5): Meta's free test number + a manually-allowlisted recipients
(up to 5, e.g. family). No business verification needed for this path - see README.

Sending a message is a real-world action visible to another person, so it is Risk.CONFIRM.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .tools import Risk, Tool

API_ROOT = "https://graph.facebook.com/v22.0"


class WhatsAppError(RuntimeError):
    pass


def _normalize(number: str) -> str:
    """Strip spaces/dashes/leading + - Meta's API wants digits only, country code first."""
    digits = re.sub(r"[^\d]", "", number)
    if not digits:
        raise WhatsAppError(f"Not a valid phone number: {number!r}")
    return digits


def default_send(token: str, phone_number_id: str, to: str, body: str) -> dict:
    url = f"{API_ROOT}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize(to),
        "type": "text",
        "text": {"body": body},
    }
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        hint = ""
        if '"code":131030' in detail or "131030" in detail:
            hint = (
                " (this usually means the recipient's number has not been added to the allowed "
                "test-recipient list in Meta's dashboard yet - see the README)"
            )
        raise WhatsAppError(f"WhatsApp API error {exc.code}: {detail[:300]}{hint}") from exc
    except urllib.error.URLError as exc:
        raise WhatsAppError(f"Could not reach WhatsApp: {exc}") from exc


def make_whatsapp_tools(token: str, phone_number_id: str, send=default_send) -> list[Tool]:
    def send_message(args: dict) -> str:
        result = send(token, phone_number_id, args["to"], args["message"])
        msg_id = (result.get("messages") or [{}])[0].get("id", "unknown")
        return f"Sent (message id {msg_id})."

    def describe(args: dict) -> str:
        return f"SEND WHATSAPP MESSAGE to {args.get('to')}\n\n{args.get('message', '')}"

    return [
        Tool(
            name="whatsapp_send",
            description=(
                "Send a WhatsApp text message to one of the owner's pre-approved contacts (e.g. "
                "family). Only numbers the owner has already allowlisted in Meta's dashboard can "
                "receive messages - sending to any other number will fail. The user must approve."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient's phone number, with country code."},
                    "message": {"type": "string"},
                },
                "required": ["to", "message"],
            },
            handler=send_message,
            risk=Risk.CONFIRM,
            describe=describe,
        ),
    ]
