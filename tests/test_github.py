from __future__ import annotations

import pytest

from omai.github_tools import GitHubError, make_github_tools

TOKEN = "ghp_test"


class FakeGitHub:
    def __init__(self, responses):
        self.responses = dict(responses)  # (method, path_prefix) -> value or Exception
        self.calls = []

    def __call__(self, token, method, path, body=None):
        self.calls.append((token, method, path, body))
        for (m, prefix), val in self.responses.items():
            if m == method and path.startswith(prefix):
                if isinstance(val, Exception):
                    raise val
                return val
        raise AssertionError(f"unhandled call {method} {path}")


def tools(fake):
    return {t.name: t for t in make_github_tools(TOKEN, call=fake)}


def test_list_repos_uses_token_and_formats(monkeypatch):
    fake = FakeGitHub({("GET", "/user/repos"): [
        {"full_name": "aditya/omai", "private": True, "updated_at": "2026-09-01T00:00:00Z"}
    ]})
    out = tools(fake)["github_list_repos"].handler({})
    assert "aditya/omai" in out and "private=True" in out
    assert fake.calls[0][0] == TOKEN


def test_list_repos_empty():
    fake = FakeGitHub({("GET", "/user/repos"): []})
    assert tools(fake)["github_list_repos"].handler({}) == "No repositories."


def test_list_issues_filters_out_pull_requests():
    fake = FakeGitHub({("GET", "/repos/a/b/issues"): [
        {"number": 1, "title": "Bug", "state": "open", "user": {"login": "x"}},
        {"number": 2, "title": "A PR", "state": "open", "user": {"login": "x"}, "pull_request": {}},
    ]})
    out = tools(fake)["github_list_issues"].handler({"repo": "a/b"})
    assert "#1" in out and "#2" not in out


def test_list_commits():
    fake = FakeGitHub({("GET", "/repos/a/b/commits"): [
        {"sha": "abcdef1234", "commit": {"message": "Fix bug\n\ndetails", "author": {"name": "Aditya"}}}
    ]})
    out = tools(fake)["github_list_commits"].handler({"repo": "a/b"})
    assert "abcdef1" in out and "Fix bug" in out and "details" not in out


def test_create_issue_is_confirm_risk_and_posts_body():
    fake = FakeGitHub({("POST", "/repos/a/b/issues"): {"number": 5, "html_url": "https://github.com/a/b/issues/5"}})
    t = tools(fake)["github_create_issue"]
    from omai.tools import Risk
    assert t.risk is Risk.CONFIRM
    out = t.handler({"repo": "a/b", "title": "Hi", "body": "details"})
    assert "#5" in out and "issues/5" in out
    assert fake.calls[0][3] == {"title": "Hi", "body": "details"}
    assert "CREATE GITHUB ISSUE" in t.summarize({"repo": "a/b", "title": "Hi", "body": "details"})


def test_api_error_propagates_as_tool_error():
    fake = FakeGitHub({("GET", "/user/repos"): GitHubError("boom")})
    with pytest.raises(GitHubError):
        tools(fake)["github_list_repos"].handler({})
