"""Tool registry. Every capability OMAI gains in later phases (Gmail, WhatsApp, ...) is a Tool.

`risk` decides what the permission gate does:
  SAFE    - runs immediately (read-only or trivially reversible); still audit-logged.
  CONFIRM - the human must approve every call (send, post, delete, ...). Enforced in code,
            so it holds even if the model is tricked by a malicious email or web page.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Callable


class Risk(enum.Enum):
    SAFE = "safe"
    CONFIRM = "confirm"


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict], str]
    risk: Risk = Risk.SAFE
    # Human-readable one-liner shown in the confirmation prompt.
    describe: Callable[[dict], str] | None = None

    def api_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def summarize(self, tool_input: dict[str, Any]) -> str:
        if self.describe:
            return self.describe(tool_input)
        return f"{self.name}({tool_input})"


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None):
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def api_schemas(self) -> list[dict]:
        return [t.api_schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools)
