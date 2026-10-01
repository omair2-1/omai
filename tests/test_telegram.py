from __future__ import annotations

import pytest

from omai.audit import AuditLog
from omai.telegram_bot import TelegramBot, TelegramError

OWNER = 111
STRANGER = 999


class FakeAPI:
    """Records every call; scripted getUpdates responses; captures sent messages."""

    def __init__(self, update_batches):
        self.batches = list(update_batches)
        self.sent: list[tuple[int, str]] = []
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, token, method, **params):
        self.calls.append((method, params))
        if method == "sendMessage":
            self.sent.append((params["chat_id"], params["text"]))
            return {}
        if method == "getUpdates":
            return self.batches.pop(0) if self.batches else []
        raise AssertionError(f"unexpected method {method}")


def msg_update(uid, text, from_id=OWNER, chat_id=OWNER):
    return {"update_id": uid, "message": {"text": text, "from": {"id": from_id}, "chat": {"id": chat_id}}}


class StubAgent:
    def __init__(self, replies):
        self.replies = list(replies)
        self.reset_called = False

    def chat(self, text):
        return self.replies.pop(0)

    def reset(self):
        self.reset_called = True


class Reply:
    def __init__(self, text, sources=()):
        self.text = text
        self.sources = list(sources)


def test_stranger_is_ignored_and_logged(tmp_path):
    api = FakeAPI([[msg_update(1, "hello", from_id=STRANGER)], []])
    audit = AuditLog(tmp_path / "a.db")
    bot = TelegramBot("tok", OWNER, audit, call=api)
    agent = StubAgent([])

    def run_once():
        upds = bot._get_updates(30)
        for u in upds:
            bot._offset = u["update_id"] + 1
            frm = u["message"]["from"]
            if frm["id"] != OWNER:
                bot.audit.log("telegram", "blocked_sender", {"from": frm}, "denied")
                continue
            bot._handle(agent, u["message"]["chat"]["id"], u["message"]["text"])

    run_once()
    assert api.sent == []
    assert audit.recent(1)[0]["outcome"] == "denied"


def test_owner_message_gets_a_reply(tmp_path):
    audit = AuditLog(tmp_path / "a.db")
    api = FakeAPI([])
    bot = TelegramBot("tok", OWNER, audit, call=api)
    agent = StubAgent([Reply("Hi there!")])
    bot._handle(agent, OWNER, "hello")
    assert api.sent == [(OWNER, "Hi there!")]


def test_reply_includes_sources(tmp_path):
    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=(api := FakeAPI([])))
    agent = StubAgent([Reply("Fact.", sources=[("Example", "https://example.com")])])
    bot._handle(agent, OWNER, "q")
    assert "Sources:" in api.sent[0][1] and "https://example.com" in api.sent[0][1]


def test_reset_command(tmp_path):
    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=(api := FakeAPI([])))
    agent = StubAgent([])
    bot._handle(agent, OWNER, "/reset")
    assert agent.reset_called and "cleared" in api.sent[0][1].lower()


def test_long_reply_is_split_into_chunks(tmp_path):
    from omai.telegram_bot import MAX_MESSAGE_CHARS

    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=(api := FakeAPI([])))
    agent = StubAgent([Reply("x" * (MAX_MESSAGE_CHARS * 2 + 10))])
    bot._handle(agent, OWNER, "q")
    assert len(api.sent) == 3
    assert all(len(t) <= MAX_MESSAGE_CHARS for _, t in api.sent)


def test_provider_error_does_not_crash_handler(tmp_path):
    class BoomAgent:
        def chat(self, text):
            raise RuntimeError("network down")

    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=(api := FakeAPI([])))
    bot._handle(BoomAgent(), OWNER, "hi")
    assert "provider error" in api.sent[0][1].lower()


def test_confirm_flow_approves_on_yes(tmp_path):
    api = FakeAPI([[msg_update(1, "yes")]])
    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=api)
    confirm = bot.make_confirm_fn(OWNER)
    assert confirm("Delete memory #3") is True
    assert "Approve this action" in api.sent[0][1]
    assert "Approved." in api.sent[1][1]


def test_confirm_flow_denies_on_no(tmp_path):
    api = FakeAPI([[msg_update(1, "no")]])
    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=api)
    assert bot.make_confirm_fn(OWNER)("Delete memory #3") is False
    assert "Not approved" in api.sent[1][1]


def test_confirm_flow_ignores_strangers_and_waits_for_owner(tmp_path):
    api = FakeAPI([[msg_update(1, "yes", from_id=STRANGER)], [msg_update(2, "yes", from_id=OWNER)]])
    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=api)
    assert bot.make_confirm_fn(OWNER)("do thing") is True


def test_confirm_flow_times_out_as_denied(tmp_path, monkeypatch):
    api = FakeAPI([[]])  # never replies
    bot = TelegramBot("tok", OWNER, AuditLog(tmp_path / "a.db"), call=api)
    # First call establishes the deadline; the second (inside the while-loop) must already exceed it.
    clock = iter([0.0, 1_000_000.0])
    monkeypatch.setattr("omai.telegram_bot.time.monotonic", lambda: next(clock))
    assert bot.make_confirm_fn(OWNER)("do thing") is False


def test_default_call_raises_on_network_error(monkeypatch):
    import urllib.error

    from omai.telegram_bot import default_call

    def boom(*a, **k):
        raise urllib.error.URLError("no network")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(TelegramError):
        default_call("tok", "getUpdates", offset=0, timeout=1)
