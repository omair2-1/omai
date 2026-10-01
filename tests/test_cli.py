from omai import cli
from omai.llm import AnthropicBackend
from tests.conftest import FakeClient, msg, text, tool_use


def test_cli_end_to_end(config, monkeypatch, capsys):
    client = FakeClient([
        msg([tool_use("remember", {"text": "Owner lives in Basti"})], "tool_use"),
        msg([text("Noted.")]),
        msg([tool_use("forget", {"memory_id": 1})], "tool_use"),
        msg([text("Deleted it.")]),
    ])
    agent, memory, audit = cli.build_agent(config, AnthropicBackend(client, config))

    # 1) chat -> remember (no prompt), 2) /memory, 3) chat -> forget (prompts; answer 'y'), 4) /audit
    answers = iter(["y"])
    monkeypatch.setattr("builtins.input", lambda *_: next(answers))

    cli.print_reply(agent.chat("remember where I live"))
    assert memory.count() == 1
    cli.handle_command("/memory", agent, memory, audit)
    cli.print_reply(agent.chat("forget that"))
    assert memory.count() == 0
    cli.handle_command("/audit 10", agent, memory, audit)

    out = capsys.readouterr().out
    assert "Noted." in out
    assert "Owner lives in Basti" in out           # shown by /memory and in the approval box
    assert "OMAI needs your approval" in out
    assert "permission" in out and "allowed" in out


def test_cli_quit_and_unknown(config, capsys):
    agent, memory, audit = cli.build_agent(config, AnthropicBackend(FakeClient([]), config))
    assert cli.handle_command("/nope", agent, memory, audit) is False
    assert cli.handle_command("/quit", agent, memory, audit) is True
    assert "Unknown command" in capsys.readouterr().out


def test_main_requires_api_key(monkeypatch, tmp_path, capsys):
    for var in ("OMAI_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    assert cli.main([]) == 1
    err = capsys.readouterr().err
    assert "GEMINI_API_KEY" in err and "aistudio.google.com/apikey" in err


def test_build_agent_registers_local_web_tools_only_when_needed(config):
    from dataclasses import replace
    from tests.test_openai_backend import FakeOpenAI
    from omai.llm import OpenAICompatBackend

    cfg = replace(config, provider="gemini", web_search=True)
    agent, *_ = cli.build_agent(cfg, OpenAICompatBackend(FakeOpenAI([]), "m"))
    assert {"web_search", "fetch_page"} <= set(agent.registry.names())

    agent2, *_ = cli.build_agent(config, AnthropicBackend(FakeClient([]), config))   # built-in search
    assert "fetch_page" not in agent2.registry.names()

    cfg3 = replace(cfg, web_search=False)
    agent3, *_ = cli.build_agent(cfg3, OpenAICompatBackend(FakeOpenAI([]), "m"))
    assert "web_search" not in agent3.registry.names()


def test_build_agent_registers_gmail_tools_only_when_configured(config, monkeypatch, tmp_path):
    from dataclasses import replace
    from omai.llm import AnthropicBackend

    backend = AnthropicBackend(FakeClient([]), config)
    agent, *_ = cli.build_agent(config, backend)
    assert "gmail_list" not in agent.registry.names()

    cfg2 = replace(config, gmail_client_id="id", gmail_client_secret="secret")
    agent2, *_ = cli.build_agent(cfg2, AnthropicBackend(FakeClient([]), cfg2))
    assert {"gmail_list", "gmail_read"} <= set(agent2.registry.names())


def test_main_telegram_mode_requires_config(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    for v in ("OMAI_TELEGRAM_TOKEN", "OMAI_TELEGRAM_USER_ID"):
        monkeypatch.delenv(v, raising=False)
    assert cli.main(["--telegram"]) == 1
    assert "OMAI_TELEGRAM_TOKEN" in capsys.readouterr().err


def test_main_telegram_mode_runs_bot(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("OMAI_TELEGRAM_TOKEN", "t")
    monkeypatch.setenv("OMAI_TELEGRAM_USER_ID", "42")
    monkeypatch.setenv("OMAI_DATA_DIR", str(tmp_path / "data"))

    calls = {}

    class FakeBot:
        def __init__(self, token, user_id, audit):
            calls["init"] = (token, user_id)

        def run(self, build_agent):
            calls["ran"] = True
            build_agent(lambda s: True)  # exercise the closure without a real backend

    class FakeBackend:
        builtin_web_search = True

    import omai.cli as climod
    monkeypatch.setattr(climod, "build_backend", lambda cfg: FakeBackend())
    monkeypatch.setattr("omai.telegram_bot.TelegramBot", FakeBot)

    assert climod.main(["--telegram"]) == 0
    assert calls["ran"] is True and calls["init"] == ("t", 42)


def test_build_agent_registers_github_and_youtube_only_when_configured(config):
    from dataclasses import replace
    from omai.llm import AnthropicBackend

    agent, *_ = cli.build_agent(config, AnthropicBackend(FakeClient([]), config))
    assert "github_list_repos" not in agent.registry.names()
    assert "youtube_search" not in agent.registry.names()

    cfg2 = replace(config, github_token="ghp_x", youtube_api_key="yt_x")
    agent2, *_ = cli.build_agent(cfg2, AnthropicBackend(FakeClient([]), cfg2))
    names = agent2.registry.names()
    assert {"github_list_repos", "github_list_issues", "github_list_commits", "github_create_issue"} <= set(names)
    assert {"youtube_search", "youtube_video_info"} <= set(names)
