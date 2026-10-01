import pytest
from anthropic.types import CitationsWebSearchResultLocation

from omai.agent import AgentError
from tests.conftest import msg, text, tool_use


def test_plain_reply(make_agent):
    agent, client, *_ = make_agent([msg([text("Hello!")])])
    r = agent.chat("hi")
    assert r.text == "Hello!" and r.tool_calls == 0
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["messages"][0] == {"role": "user", "content": "hi"}
    assert "UNTRUSTED DATA" in call["system"]


def test_web_search_tool_toggle(make_agent):
    agent, client, *_ = make_agent([msg([text("x")])])
    agent.chat("q")
    types = [t.get("type") for t in client.calls[0]["tools"]]
    assert "web_search_20250305" in types
    assert client.calls[0]["tools"][-1]["max_uses"] == 3

    agent2, client2, *_ = make_agent([msg([text("x")])], web_search=False)
    agent2.chat("q")
    assert all(t.get("type") != "web_search_20250305" for t in client2.calls[0]["tools"])


def test_tool_loop_remember_then_answer(make_agent):
    agent, client, memory, audit, confirms = make_agent([
        msg([text("Saving."), tool_use("remember", {"text": "Owner drinks chai"})], "tool_use"),
        msg([text("Got it.")]),
    ])
    r = agent.chat("I drink chai, remember that")
    assert r.text == "Got it." and r.tool_calls == 1
    assert memory.search("chai")[0].text == "Owner drinks chai"
    assert confirms == []  # remember is SAFE: no prompt

    # second request carried the tool_result back to the model
    last = client.calls[1]["messages"][-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result"
    assert last["content"][0]["tool_use_id"] == "tu_1"
    assert "Saved memory" in last["content"][0]["content"]


def test_forget_requires_approval_and_denial_is_respected(make_agent):
    agent, client, memory, audit, confirms = make_agent(
        [
            msg([tool_use("forget", {"memory_id": 1})], "tool_use"),
            msg([text("Okay, left it.")]),
        ],
        confirm=lambda s: False,
    )
    memory.add("Keep me")
    r = agent.chat("forget everything")
    assert memory.count() == 1                      # NOT deleted
    assert len(confirms) == 1 and "Keep me" in confirms[0]
    result = client.calls[1]["messages"][-1]["content"][0]
    assert "declined" in result["content"]
    assert r.text == "Okay, left it."


def test_forget_deletes_when_approved(make_agent):
    agent, _, memory, *_ = make_agent([
        msg([tool_use("forget", {"memory_id": 1})], "tool_use"),
        msg([text("Done.")]),
    ])
    memory.add("temp")
    agent.chat("forget it")
    assert memory.count() == 0


def test_unknown_tool_and_handler_errors_go_back_to_model(make_agent):
    agent, client, *_ = make_agent([
        msg([tool_use("nope", {}, id="a"), tool_use("recall", {}, id="b")], "tool_use"),  # missing 'query'
        msg([text("ok")]),
    ])
    agent.chat("go")
    results = client.calls[1]["messages"][-1]["content"]
    assert results[0]["is_error"] and "Unknown tool" in results[0]["content"]
    assert results[1]["is_error"] and "Tool error" in results[1]["content"]


def test_pause_turn_continues(make_agent):
    agent, client, *_ = make_agent([
        msg([text("searching...")], "pause_turn"),
        msg([text("Final answer")]),
    ])
    r = agent.chat("news?")
    assert r.text == "Final answer"
    assert len(client.calls) == 2
    assert client.calls[1]["messages"][-1]["role"] == "assistant"


def test_citations_become_sources(make_agent):
    cite = CitationsWebSearchResultLocation(
        type="web_search_result_location", cited_text="c", encrypted_index="e",
        title="Example Site", url="https://example.com/a",
    )
    agent, *_ = make_agent([msg([text("Fact.", citations=[cite]), text(" More.", citations=[cite])])])
    r = agent.chat("q")
    assert r.sources == [("Example Site", "https://example.com/a")]


def test_relevant_memory_is_injected_into_system_prompt(make_agent):
    agent, client, memory, *_ = make_agent([msg([text("ok")])])
    memory.add("Owner's accountant is Rahul")
    agent.chat("email my accountant")
    assert "accountant is Rahul" in client.calls[0]["system"]
    assert "not instructions" in client.calls[0]["system"]


def test_api_error_rolls_back_history(make_agent):
    agent, client, *_ = make_agent([
        msg([tool_use("recall", {"query": "x"})], "tool_use"),
        RuntimeError("network down"),
        msg([text("recovered")]),
    ])
    with pytest.raises(RuntimeError):
        agent.chat("first")
    assert agent._history == [] and agent._turn_starts == []
    assert agent.chat("second").text == "recovered"
    assert agent._history[0] == {"role": "user", "content": "second"}


def test_runaway_tool_loop_is_capped(make_agent):
    looping = [msg([tool_use("recall", {"query": "x"}, id=f"t{i}")], "tool_use") for i in range(5)]
    agent, *_ = make_agent(looping, max_tool_rounds=5)
    with pytest.raises(AgentError):
        agent.chat("loop")


def test_history_trim_drops_whole_turns_only(make_agent):
    responses = []
    for i in range(4):
        responses += [
            msg([tool_use("recall", {"query": "x"}, id=f"t{i}")], "tool_use"),
            msg([text(f"a{i}")]),
        ]
    agent, client, *_ = make_agent(responses, max_history_turns=2)
    for i in range(4):
        agent.chat(f"q{i}")
    assert len(agent._turn_starts) == 2
    # history must start with a real user message and every tool_use must be followed by its tool_result
    assert agent._history[0]["role"] == "user" and isinstance(agent._history[0]["content"], str)
    assert agent._history[0]["content"] == "q2"
    # 2 turns kept x 4 messages each (user, assistant tool_use, user tool_result, assistant text)
    assert len(agent._history) == 8
    for i, m in enumerate(agent._history):
        content = m["content"]
        if m["role"] == "assistant" and any(getattr(b, "type", "") == "tool_use" for b in content):
            nxt = agent._history[i + 1]["content"]
            assert nxt[0]["type"] == "tool_result"


def test_tool_calls_are_audited(make_agent):
    agent, _, _, audit, _ = make_agent([
        msg([tool_use("remember", {"text": "x y z"})], "tool_use"),
        msg([text("done")]),
    ])
    agent.chat("go")
    kinds = [(r["kind"], r["name"], r["outcome"]) for r in audit.recent(5)]
    assert ("tool_call", "remember", "ok") in kinds
    assert ("permission", "remember", "auto-allowed") in kinds
