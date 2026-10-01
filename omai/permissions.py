"""Permission gate + confirmation UX (spec sections 1 Phase 11 and 5).

Anything with Risk.CONFIRM must be approved by the human before its handler runs.
The decision is made here in ordinary code - the model cannot skip or talk its way past it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .audit import AuditLog
from .tools import Risk, Tool

# confirm_fn(summary) -> True to allow, False to deny
ConfirmFn = Callable[[str], bool]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


class PermissionManager:
    def __init__(self, confirm_fn: ConfirmFn, audit: AuditLog):
        self._confirm = confirm_fn
        self._audit = audit

    def authorize(self, tool: Tool, tool_input: dict[str, Any]) -> Decision:
        if tool.risk is Risk.SAFE:
            self._audit.log("permission", tool.name, {"input": tool_input}, "auto-allowed")
            return Decision(True, "auto-allowed")

        summary = tool.summarize(tool_input)
        try:
            approved = bool(self._confirm(summary))
        except (EOFError, KeyboardInterrupt):
            approved = False  # fail closed
        outcome = "allowed" if approved else "denied"
        self._audit.log("permission", tool.name, {"summary": summary}, outcome)
        return Decision(approved, outcome)
