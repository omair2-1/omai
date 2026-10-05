"""Configuration, loaded from environment variables (and an optional .env file).

Secrets are never hard-coded: API keys come from the environment only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader. Does not override variables already set in the environment."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Preset:
    base_url: str | None
    key_env: str | None      # env var holding the key (None = no key needed, e.g. local Ollama)
    model: str | None        # default model (None = must be set via OMAI_MODEL)
    note: str = ""


# Model names change often - if a default stops working, run `omai --models` and set OMAI_MODEL.
PRESETS: dict[str, Preset] = {
    "gemini": Preset(
        "https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY", "gemini-2.5-flash",
        "Free tier via Google AI Studio (aistudio.google.com/apikey).",
    ),
    "groq": Preset(
        "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile",
        "Free tier via console.groq.com.",
    ),
    "openrouter": Preset(
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", None,
        "Set OMAI_MODEL to a model whose id ends in ':free'.",
    ),
    "ollama": Preset(
        "http://localhost:11434/v1", None, "llama3.1:8b",
        "Fully local and free. Install from ollama.com, then: ollama pull llama3.1:8b",
    ),
    "openai": Preset(None, "OMAI_API_KEY", None, "Any OpenAI-compatible server: set OMAI_BASE_URL and OMAI_MODEL."),
    "anthropic": Preset(None, "ANTHROPIC_API_KEY", "claude-sonnet-5", "Paid Anthropic API."),
}


# Fallback chain only supports these OpenAI-compatible, free providers (same message format,
# so switching mid-conversation is safe). Anthropic and custom "openai" servers are excluded.
_FALLBACK_ELIGIBLE = {"gemini", "groq", "openrouter", "ollama"}


@dataclass(frozen=True)
class ResolvedProvider:
    name: str
    api_key: str
    model: str
    base_url: str


@dataclass(frozen=True)
class Config:
    api_key: str | None
    model: str | None
    data_dir: Path
    web_search: bool
    web_search_max_uses: int
    max_history_turns: int
    max_tool_rounds: int
    max_tokens: int
    provider: str = "anthropic"
    base_url: str | None = None
    gmail_client_id: str | None = None
    gmail_client_secret: str | None = None
    telegram_token: str | None = None
    telegram_user_id: int | None = None
    github_token: str | None = None
    youtube_api_key: str | None = None
    fallback_provider_names: tuple[str, ...] = ()
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None

    @classmethod
    def load(cls, env_file: str = ".env") -> "Config":
        _load_dotenv(env_file)
        provider = os.environ.get("OMAI_PROVIDER", "gemini").strip().lower()
        preset = PRESETS.get(provider)
        if preset is None:
            raise ValueError(f"Unknown OMAI_PROVIDER {provider!r}. Choose one of: {', '.join(PRESETS)}")

        if preset.key_env:
            api_key = os.environ.get(preset.key_env) or None
        else:
            api_key = "not-needed"  # the OpenAI SDK insists on a non-empty key even for local servers
        data_dir = Path(os.environ.get("OMAI_DATA_DIR", "~/.omai")).expanduser()
        return cls(
            api_key=api_key,
            model=os.environ.get("OMAI_MODEL") or preset.model,
            data_dir=data_dir,
            web_search=_flag("OMAI_WEB_SEARCH", True),
            web_search_max_uses=int(os.environ.get("OMAI_WEB_SEARCH_MAX_USES", "5")),
            max_history_turns=int(os.environ.get("OMAI_MAX_HISTORY_TURNS", "20")),
            max_tool_rounds=int(os.environ.get("OMAI_MAX_TOOL_ROUNDS", "12")),
            max_tokens=int(os.environ.get("OMAI_MAX_TOKENS", "4096")),
            provider=provider,
            base_url=os.environ.get("OMAI_BASE_URL") or preset.base_url,
            gmail_client_id=os.environ.get("GMAIL_CLIENT_ID") or None,
            gmail_client_secret=os.environ.get("GMAIL_CLIENT_SECRET") or None,
            telegram_token=os.environ.get("OMAI_TELEGRAM_TOKEN") or None,
            telegram_user_id=(
                int(os.environ["OMAI_TELEGRAM_USER_ID"])
                if os.environ.get("OMAI_TELEGRAM_USER_ID", "").strip()
                else None
            ),
            github_token=os.environ.get("GITHUB_TOKEN") or None,
            youtube_api_key=os.environ.get("YOUTUBE_API_KEY") or None,
            fallback_provider_names=tuple(
                p.strip().lower()
                for p in os.environ.get("OMAI_FALLBACK_PROVIDERS", "").split(",")
                if p.strip()
            ),
            whatsapp_token=os.environ.get("WHATSAPP_TOKEN") or None,
            whatsapp_phone_number_id=os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or None,
            spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID") or None,
            spotify_client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET") or None,
        )

    @property
    def gmail_configured(self) -> bool:
        return bool(self.gmail_client_id and self.gmail_client_secret)

    @property
    def telegram_configured(self) -> bool:
        return bool(self.telegram_token and self.telegram_user_id)

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token)

    @property
    def youtube_configured(self) -> bool:
        return bool(self.youtube_api_key)

    @property
    def whatsapp_configured(self) -> bool:
        return bool(self.whatsapp_token and self.whatsapp_phone_number_id)

    @property
    def spotify_configured(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret)

    def resolve_provider(self, name: str) -> "ResolvedProvider | None":
        """Resolve a provider name to (api_key, model, base_url) using its own env vars.

        Returns None if the name isn't fallback-eligible, or it has no api key / model available -
        callers should silently skip those rather than error, since fallback is best-effort.
        """
        name = name.lower()
        if name not in _FALLBACK_ELIGIBLE:
            return None
        preset = PRESETS[name]
        api_key = (os.environ.get(preset.key_env) if preset.key_env else "not-needed") or None
        if not api_key:
            return None
        model = os.environ.get(f"OMAI_MODEL_{name.upper()}") or preset.model
        if not model:
            return None
        return ResolvedProvider(name=name, api_key=api_key, model=model, base_url=preset.base_url)

    @property
    def fallback_chain(self) -> list["ResolvedProvider"]:
        """Resolved, de-duplicated fallback providers (excluding the primary), in configured order."""
        seen = {self.provider}
        chain: list[ResolvedProvider] = []
        for name in self.fallback_provider_names:
            if name in seen:
                continue
            seen.add(name)
            resolved = self.resolve_provider(name)
            if resolved is not None:
                chain.append(resolved)
        return chain

    def telegram_problem(self) -> str | None:
        if not self.telegram_token:
            return "OMAI_TELEGRAM_TOKEN is not set in .env (get one from @BotFather on Telegram)."
        if not self.telegram_user_id:
            return "OMAI_TELEGRAM_USER_ID is not set in .env (get your id from @userinfobot on Telegram)."
        return None

    def problem(self) -> str | None:
        """Return a human-readable configuration problem, or None if good to go."""
        preset = PRESETS[self.provider]
        if not self.api_key:
            return (
                f"{preset.key_env} is not set (provider: {self.provider}). {preset.note}\n"
                "Copy .env.example to .env and add the key."
            )
        if not self.model:
            return f"No model chosen for provider {self.provider!r}. Run `omai --models`, then set OMAI_MODEL in .env."
        if self.provider != "anthropic" and not self.base_url:
            return "OMAI_BASE_URL is not set for the 'openai' provider."
        return None
