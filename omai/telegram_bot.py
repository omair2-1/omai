"""Telegram front-end: chat with OMAI from your phone. Long-polling, no server/webhook needed.

Only messages from the configured owner's numeric Telegram user id are processed; everyone else
is silently ignored (and logged), so the bot never answers a stranger even if they find its @handle.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Callable

from .agent import Agent, AgentError
from .audit import AuditLog
from .memory import MemoryStore

API_ROOT = "https://api.telegram.org/bot{token}/{method}"
MAX_MESSAGE_CHARS = 3500          # stay under Telegram's 4096-char limit with room to spare
LONG_POLL_TIMEOUT = 30            # seconds Telegram holds the connection open waiting for a message
CONFIRM_TIMEOUT = 180             # seconds to wait for a yes/no reply before treating it as "no"

CallFn = Callable[[str, str], dict]  # (token, method, **params) -> Telegram API "result"


class TelegramError(RuntimeError):
    pass


def default_call(token: str, method: str, **params) -> dict:
    url = API_ROOT.format(token=token, method=method)
    req = urllib.request.Request(
        url, data=json.dumps(params).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=LONG_POLL_TIMEOUT + 10) as resp:
            body = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise TelegramError(f"Could not reach Telegram: {exc}") from exc
    if not body.get("ok"):
        raise TelegramError(f"Telegram API error: {body}")
    return body["result"]


def _split(text: str) -> list[str]:
    text = text or "(no text in response)"
    return [text[i : i + MAX_MESSAGE_CHARS] for i in range(0, len(text), MAX_MESSAGE_CHARS)]


class TelegramBot:
    def __init__(self, token: str, allowed_user_id: int, audit: AuditLog, call: CallFn = default_call):
        self.token = token
        self.allowed_user_id = allowed_user_id
        self.audit = audit
        self._call = call
        self._offset = 0

    # ---------------------------------------------------------------- low level
    def send(self, chat_id: int, text: str) -> None:
        for chunk in _split(text):
            self._call(self.token, "sendMessage", chat_id=chat_id, text=chunk)

    def _get_updates(self, timeout: int) -> list[dict]:
        return self._call(self.token, "getUpdates", offset=self._offset, timeout=timeout)

    def _next_owner_text(self, timeout_seconds: int) -> str | None:
        """Block (via long-poll) until the owner sends a text message, or the timeout elapses."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            remaining = max(1, min(LONG_POLL_TIMEOUT, int(deadline - time.monotonic())))
            for upd in self._get_updates(timeout=remaining):
                self._offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                if msg.get("from", {}).get("id") == self.allowed_user_id and msg.get("text"):
                    return msg["text"]
        return None

    # ---------------------------------------------------------------- permission confirm hook
    def make_confirm_fn(self, chat_id: int) -> Callable[[str], bool]:
        def confirm(summary: str) -> bool:
            self.send(chat_id, f"Approve this action?\n\n{summary}\n\nReply yes or no.")
            reply = self._next_owner_text(CONFIRM_TIMEOUT)
            approved = bool(reply) and reply.strip().lower() in {"y", "yes"}
            self.send(chat_id, "Approved." if approved else "Not approved - cancelled.")
            return approved

        return confirm

    # ---------------------------------------------------------------- main loop
    def run(self, build_agent: Callable[[Callable[[str], bool]], tuple[Agent, MemoryStore, AuditLog]]) -> None:
        """build_agent(confirm_fn) -> (agent, memory, audit). Runs forever; Ctrl+C to stop."""
        agent, memory, _ = build_agent(self.make_confirm_fn(self.allowed_user_id))
        print(f"Telegram bot listening (only user id {self.allowed_user_id} will get responses). Ctrl+C to stop.")
        while True:
            try:
                updates = self._get_updates(timeout=LONG_POLL_TIMEOUT)
            except TelegramError as exc:
                print(f"[telegram] {exc}; retrying in 5s")
                time.sleep(5)
                continue
            for upd in updates:
                if upd["update_id"] < self._offset:
                    continue  # already consumed by a nested confirm() poll
                self._offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                text, chat_id, frm = msg.get("text"), msg.get("chat", {}).get("id"), msg.get("from", {})
                if not text or chat_id is None:
                    continue
                if frm.get("id") != self.allowed_user_id:
                    self.audit.log("telegram", "blocked_sender", {"from": frm}, "denied")
                    continue
                self._handle(agent, chat_id, text)

    def _handle(self, agent: Agent, chat_id: int, text: str) -> None:
        text = text.strip()
        if text in {"/start", "/help"}:
            self.send(chat_id, "OMAI is ready. Just send a message. /reset clears the conversation.")
            return
        if text == "/reset":
            agent.reset()
            self.send(chat_id, "Conversation cleared.")
            return
        try:
            reply = agent.chat(text)
        except AgentError as exc:
            self.send(chat_id, f"[error] {exc}")
            return
        except Exception as exc:  # provider/network errors: keep the bot alive
            self.send(chat_id, f"[provider error] {type(exc).__name__}: {exc}")
            return
        out = reply.text or "(no text in response)"
        if reply.sources:
            out += "\n\nSources:\n" + "\n".join(f"- {t}: {u}" for t, u in reply.sources)
        self.send(chat_id, out)
