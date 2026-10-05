from __future__ import annotations

from dataclasses import replace

import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from omai.agent import Agent
from omai.audit import AuditLog
from omai.builtin_tools import make_memory_tools
from omai.config import Config
from omai.llm import AnthropicBackend
from omai.memory import MemoryStore
from omai.permissions import PermissionManager
from omai.tools import ToolRegistry


def msg(content, stop_reason="end_turn"):
    return Message(
        id="msg_test",
        content=content,
        model="test-model",
        role="assistant",
        stop_reason=stop_reason,
        stop_sequence=None,
        type="message",
        usage=Usage(input_tokens=1, output_tokens=1),
    )


def text(s, citations=None):
    return TextBlock(type="text", text=s, citations=citations)


def tool_use(name, tool_input, id="tu_1"):
    return ToolUseBlock(type="tool_use", id=id, name=name, input=tool_input)


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic(); records every request."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        # snapshot the message list (the agent mutates it after the call)
        snap = dict(kwargs)
        snap["messages"] = list(kwargs["messages"])
        self.calls.append(snap)
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


@pytest.fixture
def config(tmp_path):
    return Config(
        api_key="test",
        model="test-model",
        data_dir=tmp_path,
        web_search=True,
        web_search_max_uses=3,
        max_history_turns=20,
        max_tool_rounds=5,
        max_tokens=1000,
    )


@pytest.fixture
def make_agent(config, tmp_path):
    def _make(responses, confirm=lambda summary: True, **cfg_overrides):
        cfg = replace(config, **cfg_overrides) if cfg_overrides else config
        memory = MemoryStore(tmp_path / "memory.db")
        audit = AuditLog(tmp_path / "audit.db")
        registry = ToolRegistry(make_memory_tools(memory))
        confirms = []

        def confirm_fn(summary):
            confirms.append(summary)
            return confirm(summary)

        perms = PermissionManager(confirm_fn, audit)
        client = FakeClient(responses)
        agent = Agent(AnthropicBackend(client, cfg), cfg, registry, memory, perms, audit)
        return agent, client, memory, audit, confirms

    return _make
