from omai.audit import AuditLog
from omai.permissions import PermissionManager
from omai.tools import Risk, Tool


def _tool(risk, calls):
    return Tool("t", "d", {"type": "object", "properties": {}}, lambda a: calls.append(a) or "ok",
                risk=risk, describe=lambda a: f"do thing {a}")


def test_safe_tool_auto_allowed_no_prompt(tmp_path):
    audit = AuditLog(tmp_path / "a.db")
    prompts = []
    pm = PermissionManager(lambda s: prompts.append(s) or True, audit)
    d = pm.authorize(_tool(Risk.SAFE, []), {"x": 1})
    assert d.allowed and prompts == []
    assert audit.recent(1)[0]["outcome"] == "auto-allowed"


def test_confirm_tool_prompts_and_logs(tmp_path):
    audit = AuditLog(tmp_path / "a.db")
    pm = PermissionManager(lambda s: False, audit)
    d = pm.authorize(_tool(Risk.CONFIRM, []), {"x": 1})
    assert not d.allowed
    row = audit.recent(1)[0]
    assert row["outcome"] == "denied" and "do thing" in row["details"]


def test_confirm_fails_closed_on_eof(tmp_path):
    def boom(_):
        raise EOFError
    pm = PermissionManager(boom, AuditLog(tmp_path / "a.db"))
    assert pm.authorize(_tool(Risk.CONFIRM, []), {}).allowed is False


def test_audit_truncates_huge_values(tmp_path):
    audit = AuditLog(tmp_path / "a.db")
    audit.log("tool_call", "x", {"body": "A" * 100_000}, "ok")
    assert len(audit.recent(1)[0]["details"]) < 1000
