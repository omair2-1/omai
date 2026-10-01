import pytest

from omai import web_tools as wt


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "ftp://example.com/x", "http://localhost:11434/api", "http://127.0.0.1/",
    "http://10.0.0.5/admin", "http://192.168.1.1/", "http://169.254.169.254/latest/meta-data/",
    "http://[::1]/", "http://0.0.0.0/", "not a url", "http:///nohost",
])
def test_check_url_blocks_unsafe(url):
    with pytest.raises(ValueError):
        wt.check_url(url)


def test_check_url_allows_public_ip():
    wt.check_url("http://93.184.216.34/")   # literal public IP: no DNS needed


def test_redirect_to_private_address_is_blocked():
    import urllib.request
    handler = wt._SafeRedirect()
    req = urllib.request.Request("http://93.184.216.34/")
    with pytest.raises(ValueError):
        handler.redirect_request(req, None, 302, "Found", {}, "http://127.0.0.1:8080/secret")


def test_html_to_text_strips_scripts_and_styles():
    html = "<html><head><title>T</title><style>p{}</style></head><body><script>evil()</script><h1>Head</h1><p>Some   text</p></body></html>"
    out = wt.html_to_text(html)
    assert "evil" not in out and "p{}" not in out
    assert out.splitlines() == ["Head", "Some text"]


def test_fetch_page_wraps_and_truncates():
    tools = {t.name: t for t in wt.make_web_tools(
        search_fn=lambda q, n: [],
        fetch_fn=lambda u: ("text/plain", "x" * 50_000))}
    out = tools["fetch_page"].handler({"url": "https://example.com"})
    assert out.startswith("[UNTRUSTED WEB PAGE from https://example.com")
    assert "[page truncated]" in out and len(out) < 13_000


def test_fetch_page_rejects_binary():
    tools = {t.name: t for t in wt.make_web_tools(fetch_fn=lambda u: ("application/pdf", "%PDF"))}
    assert "Cannot read" in tools["fetch_page"].handler({"url": "https://example.com/a.pdf"})


def test_search_formats_and_handles_empty():
    tools = {t.name: t for t in wt.make_web_tools(search_fn=lambda q, n: [])}
    assert tools["web_search"].handler({"query": "x"}) == "No results."
    tools = {t.name: t for t in wt.make_web_tools(
        search_fn=lambda q, n: [{"title": "T", "href": "https://a.b", "body": "snippet"}])}
    out = tools["web_search"].handler({"query": "x"})
    assert "UNTRUSTED" in out and "https://a.b" in out and "snippet" in out
