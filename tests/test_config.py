import pytest

from omai.config import PRESETS, Config


def _clean(monkeypatch):
    for v in ("OMAI_PROVIDER", "OMAI_MODEL", "OMAI_BASE_URL", "OMAI_API_KEY", "GEMINI_API_KEY",
              "GROQ_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(v, raising=False)


def test_default_is_free_gemini(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    c = Config.load(str(tmp_path / "none.env"))
    assert c.provider == "gemini" and c.api_key == "k" and "generativelanguage" in c.base_url
    assert c.problem() is None


def test_missing_key_message(monkeypatch, tmp_path):
    _clean(monkeypatch)
    c = Config.load(str(tmp_path / "none.env"))
    assert "GEMINI_API_KEY" in c.problem()


def test_ollama_needs_no_key(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("OMAI_PROVIDER", "ollama")
    c = Config.load(str(tmp_path / "none.env"))
    assert c.problem() is None and c.base_url.startswith("http://localhost:11434")


def test_openrouter_requires_model(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("OMAI_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    assert "OMAI_MODEL" in Config.load(str(tmp_path / "none.env")).problem()


def test_custom_openai_needs_base_url(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("OMAI_PROVIDER", "openai")
    monkeypatch.setenv("OMAI_API_KEY", "k")
    monkeypatch.setenv("OMAI_MODEL", "m")
    assert "OMAI_BASE_URL" in Config.load(str(tmp_path / "none.env")).problem()


def test_unknown_provider(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("OMAI_PROVIDER", "nope")
    with pytest.raises(ValueError):
        Config.load(str(tmp_path / "none.env"))


def test_env_file_is_read_but_env_wins(monkeypatch, tmp_path):
    _clean(monkeypatch)
    f = tmp_path / ".env"
    f.write_text("OMAI_PROVIDER=groq\nGROQ_API_KEY=fromfile\n# c\n")
    monkeypatch.setenv("GROQ_API_KEY", "fromenv")
    c = Config.load(str(f))
    assert c.provider == "groq" and c.api_key == "fromenv"
    monkeypatch.delenv("OMAI_PROVIDER"); monkeypatch.delenv("GROQ_API_KEY")


def test_all_presets_are_consistent():
    for name, p in PRESETS.items():
        assert name == "anthropic" or name == "openai" or p.base_url


def test_gmail_configured_flag(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GMAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("GMAIL_CLIENT_SECRET", raising=False)
    c = Config.load(str(tmp_path / "none.env"))
    assert c.gmail_configured is False

    monkeypatch.setenv("GMAIL_CLIENT_ID", "id")
    monkeypatch.setenv("GMAIL_CLIENT_SECRET", "secret")
    c2 = Config.load(str(tmp_path / "none.env"))
    assert c2.gmail_configured is True


def test_telegram_configured_flag_and_problems(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    for v in ("OMAI_TELEGRAM_TOKEN", "OMAI_TELEGRAM_USER_ID"):
        monkeypatch.delenv(v, raising=False)
    c = Config.load(str(tmp_path / "none.env"))
    assert c.telegram_configured is False
    assert "OMAI_TELEGRAM_TOKEN" in c.telegram_problem()

    monkeypatch.setenv("OMAI_TELEGRAM_TOKEN", "t")
    c2 = Config.load(str(tmp_path / "none.env"))
    assert "OMAI_TELEGRAM_USER_ID" in c2.telegram_problem()

    monkeypatch.setenv("OMAI_TELEGRAM_USER_ID", "12345")
    c3 = Config.load(str(tmp_path / "none.env"))
    assert c3.telegram_configured is True and c3.telegram_user_id == 12345
    assert c3.telegram_problem() is None


def test_github_youtube_configured_flags(monkeypatch, tmp_path):
    _clean(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    for v in ("GITHUB_TOKEN", "YOUTUBE_API_KEY"):
        monkeypatch.delenv(v, raising=False)
    c = Config.load(str(tmp_path / "none.env"))
    assert c.github_configured is False and c.youtube_configured is False

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("YOUTUBE_API_KEY", "yt_x")
    c2 = Config.load(str(tmp_path / "none.env"))
    assert c2.github_configured is True and c2.youtube_configured is True
