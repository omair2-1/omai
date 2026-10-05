from __future__ import annotations

import pytest

from omai.llm import FallbackOpenAIBackend, LLMResponse, ToolResult


class BoomStatus(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class RateLimitError(Exception):
    pass


class StubBackend:
    """Mimics OpenAICompatBackend's interface for testing without hitting a real API."""

    def __init__(self, name, script):
        self.name = name
        self.script = list(script)  # list of exceptions or LLMResponse to return, in order
        self.calls = 0

    def user_message(self, text):
        return {"role": "user", "content": f"[{self.name}] {text}"}

    def tool_result_messages(self, results):
        return [{"role": "tool", "tool_call_id": r.id, "content": r.content} for r in results]

    def generate(self, system, history, tools, max_tokens):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def ok(text="hi"):
    return LLMResponse(text=text, tool_calls=[], stop="end", assistant_message={"role": "assistant", "content": text})


def test_falls_through_on_rate_limit_to_second_backend():
    a = StubBackend("a", [BoomStatus(429)])
    b = StubBackend("b", [ok("from b")])
    fb = FallbackOpenAIBackend([("a", a), ("b", b)])
    resp = fb.generate("sys", [], [], 100)
    assert resp.text == "from b" and fb.last_used == "b"
    assert a.calls == 1 and b.calls == 1


def test_sticky_active_backend_tried_first_next_call():
    a = StubBackend("a", [BoomStatus(503)])
    b = StubBackend("b", [ok("first call from b"), ok("second call from b")])
    fb = FallbackOpenAIBackend([("a", a), ("b", b)])
    fb.generate("sys", [], [], 100)  # a fails, b succeeds -> active becomes b
    fb.generate("sys", [], [], 100)  # should try b first this time, not a
    assert b.calls == 2 and a.calls == 1


def test_non_retryable_error_propagates_immediately():
    class AuthError(Exception):
        status_code = 401

    a = StubBackend("a", [AuthError()])
    b = StubBackend("b", [ok("should not be reached")])
    fb = FallbackOpenAIBackend([("a", a), ("b", b)])
    with pytest.raises(AuthError):
        fb.generate("sys", [], [], 100)
    assert b.calls == 0  # never tried - bad auth isn't a capacity problem


def test_all_backends_exhausted_raises_last_error():
    a = StubBackend("a", [BoomStatus(429)])
    b = StubBackend("b", [BoomStatus(503)])
    fb = FallbackOpenAIBackend([("a", a), ("b", b)])
    with pytest.raises(BoomStatus) as exc_info:
        fb.generate("sys", [], [], 100)
    assert exc_info.value.status_code == 503


def test_named_exception_classes_are_retryable():
    a = StubBackend("a", [RateLimitError("slow down")])
    b = StubBackend("b", [ok("from b")])
    fb = FallbackOpenAIBackend([("a", a), ("b", b)])
    assert fb.generate("sys", [], [], 100).text == "from b"


def test_single_backend_still_works():
    a = StubBackend("a", [ok("solo")])
    fb = FallbackOpenAIBackend([("a", a)])
    assert fb.generate("sys", [], [], 100).text == "solo"


def test_requires_at_least_one_backend():
    with pytest.raises(ValueError):
        FallbackOpenAIBackend([])


def test_delegates_message_formatting_to_first_backend():
    a = StubBackend("a", [])
    b = StubBackend("b", [])
    fb = FallbackOpenAIBackend([("a", a), ("b", b)])
    assert fb.user_message("hello")["content"] == "[a] hello"
    msgs = fb.tool_result_messages([ToolResult(id="t1", content="ok")])
    assert msgs[0]["tool_call_id"] == "t1"
