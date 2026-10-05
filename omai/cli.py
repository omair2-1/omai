"""Local command-line interface. Runs on your own machine, so only you can reach it."""
from __future__ import annotations

import argparse
import sys

from .agent import Agent, AgentError, Reply
from .audit import AuditLog
from .builtin_tools import make_memory_tools
from .config import Config
from .llm import AnthropicBackend, LLMBackend, OpenAICompatBackend
from .memory import MemoryStore
from .permissions import PermissionManager
from .tools import ToolRegistry
from .web_tools import make_web_tools

HELP = """\
Commands:
  /memory [query]   list recent memories, or search them
  /forget <id>      delete a memory
  /audit [n]        show the last n audit-log entries (default 15)
  /reset            clear this conversation (long-term memory is kept)
  /help             show this help
  /quit             exit
Anything else is sent to OMAI."""


def cli_confirm(summary: str) -> bool:
    print("\n  ┌─ OMAI needs your approval")
    for line in summary.splitlines() or [""]:
        print(f"  │ {line}")
    print("  └─")
    answer = input("  Allow this? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def build_backend(config: Config) -> LLMBackend:
    """Create the LLM backend for the configured provider (SDKs are imported lazily).

    For OpenAI-compatible providers, if OMAI_FALLBACK_PROVIDERS names other configured free
    providers, wraps them all in a FallbackOpenAIBackend so a rate-limited provider automatically
    hands off to the next one. Anthropic is never part of a fallback chain (different message format).
    """
    if config.provider == "anthropic":
        import anthropic

        return AnthropicBackend(anthropic.Anthropic(api_key=config.api_key), config)

    import openai

    from .llm import FallbackOpenAIBackend

    primary = OpenAICompatBackend(openai.OpenAI(api_key=config.api_key, base_url=config.base_url), config.model)
    chain = config.fallback_chain
    if not chain:
        return primary

    backends: list[tuple[str, OpenAICompatBackend]] = [(config.provider, primary)]
    for rp in chain:
        client = openai.OpenAI(api_key=rp.api_key, base_url=rp.base_url)
        backends.append((rp.name, OpenAICompatBackend(client, rp.model)))
    return FallbackOpenAIBackend(backends)


def build_agent(config: Config, backend: LLMBackend, confirm_fn=cli_confirm):
    memory = MemoryStore(config.data_dir / "memory.db")
    audit = AuditLog(config.data_dir / "audit.db")
    registry = ToolRegistry(make_memory_tools(memory))
    if config.web_search and not backend.builtin_web_search:
        for tool in make_web_tools():
            registry.register(tool)
    if config.gmail_configured:
        from .gmail_tools import make_gmail_tools

        _gmail_service = {}  # lazy singleton: no browser/network until the tool is actually used

        def get_service():
            if "svc" not in _gmail_service:
                from googleapiclient.discovery import build

                from .gmail_auth import get_credentials

                creds = get_credentials(
                    config.gmail_client_id, config.gmail_client_secret, config.data_dir / "gmail_token.json"
                )
                _gmail_service["svc"] = build("gmail", "v1", credentials=creds)
            return _gmail_service["svc"]

        for tool in make_gmail_tools(get_service):
            registry.register(tool)
    if config.github_configured:
        from .github_tools import make_github_tools

        for tool in make_github_tools(config.github_token):
            registry.register(tool)
    if config.youtube_configured:
        from .youtube_tools import make_youtube_tools

        for tool in make_youtube_tools(config.youtube_api_key):
            registry.register(tool)
    if config.whatsapp_configured:
        from .whatsapp_tools import make_whatsapp_tools

        for tool in make_whatsapp_tools(config.whatsapp_token, config.whatsapp_phone_number_id):
            registry.register(tool)
    if config.spotify_configured:
        from .spotify_tools import make_spotify_tools

        for tool in make_spotify_tools(config.spotify_client_id, config.spotify_client_secret):
            registry.register(tool)
    permissions = PermissionManager(confirm_fn, audit)
    agent = Agent(backend, config, registry, memory, permissions, audit)
    return agent, memory, audit


def print_reply(reply: Reply) -> None:
    print(f"\n{reply.text}\n" if reply.text else "\n(no text in response)\n")
    if reply.truncated:
        print("[response was cut off - ask me to continue]\n")
    if reply.sources:
        print("Sources:")
        for i, (title, url) in enumerate(reply.sources, 1):
            print(f"  [{i}] {title} - {url}")
        print()


def handle_command(line: str, agent: Agent, memory: MemoryStore, audit: AuditLog) -> bool:
    """Returns True if the loop should exit."""
    cmd, _, arg = line.partition(" ")
    arg = arg.strip()
    if cmd in {"/quit", "/exit"}:
        return True
    if cmd == "/help":
        print(HELP)
    elif cmd == "/reset":
        agent.reset()
        print("Conversation cleared.")
    elif cmd == "/memory":
        items = memory.search(arg, limit=20) if arg else memory.recent(20)
        if not items:
            print("No memories." if not arg else "No matching memories.")
        for m in items:
            print(f"  #{m.id} ({m.created_at[:10]}): {m.text}")
    elif cmd == "/forget":
        if arg.isdigit():
            print("Deleted." if memory.delete(int(arg)) else "No such memory.")
            audit.log("tool_call", "forget", {"memory_id": int(arg), "via": "cli"}, "ok")
        else:
            print("Usage: /forget <id>")
    elif cmd == "/audit":
        n = int(arg) if arg.isdigit() else 15
        for r in reversed(audit.recent(n)):
            print(f"  {r['ts']}  {r['kind']:<10} {r['name']:<12} {r['outcome']:<12} {r['details']}")
    else:
        print(f"Unknown command {cmd}. Try /help.")
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omai", description="OMAI - your private personal AI agent")
    parser.add_argument("--models", action="store_true", help="list models offered by the configured provider and exit")
    parser.add_argument("--telegram", action="store_true", help="run as a Telegram bot instead of the local CLI")
    args = parser.parse_args(argv)

    try:
        config = Config.load()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    problem = config.problem()
    if problem and not (args.models and config.api_key):
        print(problem, file=sys.stderr)
        return 1

    backend = build_backend(config)

    if args.models:
        try:
            for name in backend.list_models():
                print(name)
        except Exception as exc:  # network/auth problems
            print(f"Could not list models: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.telegram:
        tg_problem = config.telegram_problem()
        if tg_problem:
            print(tg_problem, file=sys.stderr)
            return 1
        from .telegram_bot import TelegramBot

        audit = AuditLog(config.data_dir / "audit.db")
        bot = TelegramBot(config.telegram_token, config.telegram_user_id, audit)
        try:
            bot.run(lambda confirm_fn: build_agent(config, backend, confirm_fn))
        except KeyboardInterrupt:
            print()
        return 0

    agent, memory, audit = build_agent(config, backend)
    web = "built-in" if backend.builtin_web_search else ("DuckDuckGo" if config.web_search else "off")
    gmail = "on" if config.gmail_configured else "off"
    github = "on" if config.github_configured else "off"
    youtube = "on" if config.youtube_configured else "off"
    whatsapp = "on" if config.whatsapp_configured else "off"
    spotify = "on" if config.spotify_configured else "off"
    from .llm import FallbackOpenAIBackend

    fallback = f", fallback: {[n for n, _ in backend._backends]}" if isinstance(backend, FallbackOpenAIBackend) else ""
    print(
        f"OMAI ready  (provider: {config.provider}, model: {config.model}, web search: {web}{fallback}, "
        f"gmail: {gmail}, github: {github}, youtube: {youtube}, whatsapp: {whatsapp}, "
        f"spotify: {spotify}, memories: {memory.count()}).  /help for commands."
    )
    while True:
        try:
            line = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line.startswith("/"):
            if handle_command(line, agent, memory, audit):
                break
            continue
        try:
            print_reply(agent.chat(line))
        except KeyboardInterrupt:
            print("\n(cancelled)")
        except AgentError as exc:
            print(f"\n[error] {exc}\n")
        except Exception as exc:  # provider/network errors: keep the session alive
            print(f"\n[provider error] {type(exc).__name__}: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
