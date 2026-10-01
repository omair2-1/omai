from __future__ import annotations

from dataclasses import replace

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage, ChatCompletionMessageFunctionToolCall
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_function_tool_call import Function

from omai.agent import Agent
from omai.audit import AuditLog
from omai.builtin_tools import make_memory_tools
from omai.llm import OpenAICompatBackend
from omai.memory import MemoryStore
from omai.permissions import PermissionManager
from omai.tools import ToolRegistry
from omai.web_tools import make_web_tools


def completion(content=None, tool_calls=None, finish="stop"):
    return ChatCompletion(
        id="c1", created=0, model="m", object="chat.completion",
        choices=[Choice(index=0, finish_reason=finish,
                        message=ChatCompletionMessage(role="assistant", content=content, tool_calls=tool_calls))],
    )


def call(name, args_json, id="call_1", **extra):
    return ChatCompletionMessageFunctionToolCall(
        id=id, type="function", function=Function(name=name, arguments=args_json), **extra
    )


class FakeOpenAI:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        snap = dict(kw)
        snap["messages"] = list(kw["messages"])
        self.calls.append(snap)
        return self.responses.pop(0)


@pytest.fixture
def make(config, tmp_path):
    def _make(responses, search_results=None, confirm=lambda s: True):
        cfg = replace(config, provider="gemini", web_search=True)
        memory = MemoryStore(tmp_path / "m.db")
        audit = AuditLog(tmp_path / "a.db")
        reg = ToolRegistry(make_memory_tools(memory))
        fake_search = lambda q, n: search_results or []
        for t in make_web_tools(search_fn=fake_search, fetch_fn=lambda u: ("text/html", "<html><body><p>Hello page</p></body></html>")):
            reg.register(t)
        client = FakeOpenAI(responses)
        agent = Agent(OpenAICompatBackend(client, "test-model"), cfg, reg, memory,
                      PermissionManager(confirm, audit), audit)
        return agent, client, memory
    return _make


def test_plain_reply_and_request_shape(make):
    agent, client, _ = make([completion("Hi there")])
    r = agent.chat("hello")
    assert r.text == "Hi there"
    kw = client.calls[0]
    assert kw["model"] == "test-model"
    assert kw["messages"][0]["role"] == "system" and kw["messages"][1] == {"role": "user", "content": "hello"}
    names = [t["function"]["name"] for t in kw["tools"]]
    assert {"remember", "recall", "forget", "web_search", "fetch_page"} <= set(names)
    assert kw["tools"][0]["type"] == "function" and "parameters" in kw["tools"][0]["function"]


def test_tool_loop_with_search(make):
    agent, client, _ = make(
        [
            completion(None, [call("web_search", '{"query": "python release"}')], finish="tool_calls"),
            completion("Python 3.13 is out. https://python.org"),
        ],
        search_results=[{"title": "Python", "href": "https://python.org", "body": "Latest release"}],
    )
    r = agent.chat("latest python?")
    assert r.tool_calls == 1 and "3.13" in r.text
    msgs = client.calls[1]["messages"]
    assert msgs[-2]["role"] == "assistant" and msgs[-2]["tool_calls"][0]["function"]["name"] == "web_search"
    assert msgs[-1]["role"] == "tool" and msgs[-1]["tool_call_id"] == "call_1"
    assert "UNTRUSTED" in msgs[-1]["content"] and "https://python.org" in msgs[-1]["content"]


def test_finish_reason_stop_with_tool_calls_still_runs_tools(make):
    """Ollama and some others report finish_reason='stop' even when tool_calls are present."""
    agent, client, memory = make([
        completion("", [call("remember", '{"text": "likes chai"}')], finish="stop"),
        completion("Saved."),
    ])
    assert agent.chat("remember I like chai").text == "Saved."
    assert memory.count() == 1


def test_malformed_json_arguments_go_back_to_model(make):
    agent, client, memory = make([
        completion(None, [call("remember", '{"text": "oops')], finish="tool_calls"),
        completion(None, [call("remember", '{"text": "fixed"}', id="call_2")], finish="tool_calls"),
        completion("ok"),
    ])
    agent.chat("go")
    err = client.calls[1]["messages"][-1]
    assert err["role"] == "tool" and "Invalid JSON" in err["content"]
    assert memory.count() == 1 and memory.recent(1)[0].text == "fixed"


def test_provider_extras_are_round_tripped(make):
    """Gemini 3 requires the thought signature echoed back on the next request."""
    extra = {"google": {"thought_signature": "sig123"}}
    agent, client, _ = make([
        completion(None, [call("recall", '{"query": "x"}', extra_content=extra)], finish="tool_calls"),
        completion("done"),
    ])
    agent.chat("go")
    echoed = client.calls[1]["messages"][-2]["tool_calls"][0]
    assert echoed["extra_content"] == extra


def test_length_finish_marks_truncated(make):
    agent, *_ = make([completion("cut off mid", finish="length")])
    assert agent.chat("long").truncated is True


def test_confirm_gate_applies_with_openai_backend(make):
    agent, client, memory = make(
        [completion(None, [call("forget", '{"memory_id": 1}')], finish="tool_calls"), completion("ok")],
        confirm=lambda s: False,
    )
    memory.add("keep me")
    agent.chat("forget it")
    assert memory.count() == 1
    assert "declined" in client.calls[1]["messages"][-1]["content"]
