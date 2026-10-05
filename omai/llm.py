"""LLM backends. The agent only talks to this small interface, so the brain is swappable.

* OpenAICompatBackend - any OpenAI-compatible endpoint: Google Gemini (free tier), Groq (free tier),
                        OpenRouter, Ollama (fully local and free), ...
* AnthropicBackend    - Claude via the Anthropic API (paid), with Anthropic's built-in web search.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .config import Config


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    error: str | None = None  # set when the model produced unparseable arguments


@dataclass
class ToolResult:
    id: str
    content: str
    is_error: bool = False


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[ToolCall]
    stop: str                       # "end" | "tool_use" | "pause" | "max_tokens"
    assistant_message: dict         # exactly what to append to the history
    sources: list[tuple[str, str]] = field(default_factory=list)   # (title, url)


class LLMBackend(ABC):
    #: True if the provider runs web search server-side (so OMAI needn't register local web tools)
    builtin_web_search: bool = False

    @abstractmethod
    def user_message(self, text: str) -> dict: ...

    @abstractmethod
    def generate(self, system: str, history: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse: ...

    @abstractmethod
    def tool_result_messages(self, results: list[ToolResult]) -> list[dict]: ...

    def list_models(self) -> list[str]:
        raise NotImplementedError("This backend cannot list models.")


# --------------------------------------------------------------------------- OpenAI-compatible
class OpenAICompatBackend(LLMBackend):
    def __init__(self, client: Any, model: str):
        self.client = client
        self.model = model

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def generate(self, system, history, tools, max_tokens) -> LLMResponse:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=[{"role": "system", "content": system}, *history],
            max_tokens=max_tokens,
        )
        if tools:  # some servers reject an empty tools list
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["input_schema"],
                    },
                }
                for t in tools
            ]
        resp = self.client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        text = msg.content or ""

        calls: list[ToolCall] = []
        raw_calls: list[dict] = []
        for i, tc in enumerate(msg.tool_calls or []):
            # Round-trip the provider's own dict (keeps extras such as Gemini's thought signatures).
            raw = tc.model_dump(exclude_none=True)
            raw.setdefault("id", f"call_{i}")
            raw.setdefault("type", "function")
            raw_calls.append(raw)
            fn = raw.get("function", {})
            args_str = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_str)
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
                calls.append(ToolCall(raw["id"], fn.get("name", ""), args))
            except ValueError as exc:  # weaker models sometimes emit broken JSON
                calls.append(ToolCall(raw["id"], fn.get("name", ""), {}, error=f"Invalid JSON arguments: {exc}"))

        assistant: dict[str, Any] = {"role": "assistant", "content": text or None}
        if raw_calls:
            assistant["tool_calls"] = raw_calls

        if calls:
            stop = "tool_use"
        elif choice.finish_reason == "length":
            stop = "max_tokens"
        else:
            stop = "end"
        return LLMResponse(text=text, tool_calls=calls, stop=stop, assistant_message=assistant)

    def tool_result_messages(self, results):
        return [{"role": "tool", "tool_call_id": r.id, "content": r.content} for r in results]

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self.client.models.list())


# --------------------------------------------------------------------------- Anthropic
class AnthropicBackend(LLMBackend):
    builtin_web_search = True

    def __init__(self, client: Any, config: Config):
        self.client = client
        self.config = config
        self.builtin_web_search = bool(config.web_search)

    def user_message(self, text: str) -> dict:
        return {"role": "user", "content": text}

    def generate(self, system, history, tools, max_tokens) -> LLMResponse:
        tools = list(tools)
        if self.config.web_search:
            tools.append(
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self.config.web_search_max_uses,
                }
            )
        resp = self.client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=history,
        )
        parts: list[str] = []
        sources: dict[str, str] = {}
        calls: list[ToolCall] = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                parts.append(block.text)
                for cite in getattr(block, "citations", None) or []:
                    url = getattr(cite, "url", None)
                    if url and url not in sources:
                        sources[url] = getattr(cite, "title", None) or url
            elif btype == "tool_use":
                calls.append(ToolCall(block.id, block.name, block.input))

        if resp.stop_reason == "tool_use":
            stop = "tool_use"
        elif resp.stop_reason == "pause_turn":
            stop = "pause"
        elif resp.stop_reason == "max_tokens":
            stop = "max_tokens"
        else:
            stop = "end"
        return LLMResponse(
            text="".join(parts).strip(),
            tool_calls=calls,
            stop=stop,
            assistant_message={"role": "assistant", "content": resp.content},
            sources=[(t, u) for u, t in sources.items()],
        )

    def tool_result_messages(self, results):
        blocks = []
        for r in results:
            b = {"type": "tool_result", "tool_use_id": r.id, "content": r.content}
            if r.is_error:
                b["is_error"] = True
            blocks.append(b)
        return [{"role": "user", "content": blocks}]


# --------------------------------------------------------------------------- fallback chain
def _is_retryable(exc: Exception) -> bool:
    """True for rate-limit / server-overload style errors worth trying the next provider for.

    Checked by status_code (not isinstance of a specific SDK exception class) so this also works
    with any OpenAI-compatible server and with plain exceptions carrying a status_code attribute.
    """
    status = getattr(exc, "status_code", None)
    if status in {429, 500, 502, 503, 529}:
        return True
    name = type(exc).__name__
    return name in {"RateLimitError", "APIConnectionError", "APITimeoutError", "InternalServerError"}


class FallbackOpenAIBackend(LLMBackend):
    """Tries each OpenAI-compatible backend in order; on a rate-limit/overload error, tries the
    next. Remembers which one last worked and tries that one first next time, so a healthy
    provider isn't re-probed through a dead one on every single turn.

    All wrapped backends must be OpenAICompatBackend (or share its message format) since history
    is shared across them within one conversation - this is NOT safe to mix with AnthropicBackend.
    """

    builtin_web_search = False

    def __init__(self, backends: list[tuple[str, OpenAICompatBackend]]):
        if not backends:
            raise ValueError("FallbackOpenAIBackend needs at least one backend.")
        self._backends = backends
        self._active = 0
        self.last_used: str = backends[0][0]

    def user_message(self, text: str) -> dict:
        return self._backends[0][1].user_message(text)

    def tool_result_messages(self, results):
        return self._backends[0][1].tool_result_messages(results)

    def generate(self, system, history, tools, max_tokens) -> LLMResponse:
        last_exc: Exception | None = None
        n = len(self._backends)
        for offset in range(n):
            idx = (self._active + offset) % n
            name, backend = self._backends[idx]
            try:
                resp = backend.generate(system, history, tools, max_tokens)
            except Exception as exc:
                if _is_retryable(exc):
                    last_exc = exc
                    continue
                raise  # a non-retryable error (bad auth, bad request, ...) surfaces immediately
            self._active = idx
            self.last_used = name
            return resp
        assert last_exc is not None
        raise last_exc
