from __future__ import annotations

import pytest

from omai.tools import Risk
from omai.whatsapp_tools import WhatsAppError, _normalize, make_whatsapp_tools

TOKEN, PHONE_ID = "tok", "1234567890"


class FakeSend:
    def __init__(self, result=None, error=None):
        self.result = result or {"messages": [{"id": "wamid.ABC"}]}
        self.error = error
        self.calls = []

    def __call__(self, token, phone_number_id, to, message):
        self.calls.append((token, phone_number_id, to, message))
        if self.error:
            raise self.error
        return self.result


def tools(fake):
    return {t.name: t for t in make_whatsapp_tools(TOKEN, PHONE_ID, send=fake)}


def test_normalize_strips_formatting():
    assert _normalize("+91 98765-43210") == "919876543210"
    assert _normalize("(987) 654-3210") == "9876543210"


def test_normalize_rejects_empty():
    with pytest.raises(WhatsAppError):
        _normalize("not a number")


def test_send_is_confirm_risk():
    t = tools(FakeSend())["whatsapp_send"]
    assert t.risk is Risk.CONFIRM


def test_send_passes_token_and_phone_id_and_formats_result():
    fake = FakeSend()
    out = tools(fake)["whatsapp_send"].handler({"to": "+919876543210", "message": "hi mom"})
    assert "wamid.ABC" in out
    assert fake.calls[0] == (TOKEN, PHONE_ID, "+919876543210", "hi mom")


def test_describe_shows_recipient_and_message():
    t = tools(FakeSend())["whatsapp_send"]
    summary = t.summarize({"to": "+919876543210", "message": "hi mom"})
    assert "SEND WHATSAPP MESSAGE" in summary and "+919876543210" in summary and "hi mom" in summary


def test_api_error_propagates():
    fake = FakeSend(error=WhatsAppError("boom"))
    with pytest.raises(WhatsAppError):
        tools(fake)["whatsapp_send"].handler({"to": "+919876543210", "message": "hi"})


def test_allowlist_error_gets_helpful_hint(monkeypatch):
    import json
    import urllib.error

    from omai import whatsapp_tools as wt

    body = json.dumps({"error": {"code": 131030, "message": "Recipient not in allowed list"}}).encode()

    def fake_urlopen(req, timeout=15):
        raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, None)

    class FakeHTTPError(urllib.error.HTTPError):
        def read(self):
            return body

    def raiser(req, timeout=15):
        raise FakeHTTPError(req.full_url, 400, "Bad Request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", raiser)
    with pytest.raises(wt.WhatsAppError) as exc_info:
        wt.default_send(TOKEN, PHONE_ID, "+919876543210", "hi")
    assert "allowed test-recipient list" in str(exc_info.value)
