"""GitHub tools (spec Phase 8): personal access token, no OAuth dance needed.

Reads (list repos/issues/commits) are Risk.SAFE. Creating an issue writes to a real repo the
owner can see, so it is Risk.CONFIRM even though it's not very destructive.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .tools import Risk, Tool

API_ROOT = "https://api.github.com"
USER_AGENT = "OMAI-personal-agent/0.1"


class GitHubError(RuntimeError):
    pass


def default_call(token: str, method: str, path: str, body: dict | None = None) -> dict | list:
    req = urllib.request.Request(
        f"{API_ROOT}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise GitHubError(f"GitHub API error {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"Could not reach GitHub: {exc}") from exc


def make_github_tools(token: str, call=default_call) -> list[Tool]:
    def list_repos(args: dict) -> str:
        repos = call(token, "GET", "/user/repos?per_page=50&sort=updated")
        if not repos:
            return "No repositories."
        return "\n".join(f"{r['full_name']}  (private={r['private']}, updated={r['updated_at']})" for r in repos)

    def list_issues(args: dict) -> str:
        repo = args["repo"]
        state = args.get("state", "open")
        issues = call(token, "GET", f"/repos/{repo}/issues?state={state}&per_page=30")
        if not issues:
            return f"No {state} issues in {repo}."
        lines = []
        for i in issues:
            if "pull_request" in i:
                continue  # GitHub's issues endpoint also returns PRs; skip those here
            lines.append(f"#{i['number']}  {i['title']!r}  (state={i['state']}, by {i['user']['login']})")
        return "\n".join(lines) if lines else f"No {state} issues in {repo}."

    def list_commits(args: dict) -> str:
        repo = args["repo"]
        limit = max(1, min(int(args.get("max_results", 10)), 30))
        commits = call(token, "GET", f"/repos/{repo}/commits?per_page={limit}")
        lines = []
        for c in commits:
            msg = c["commit"]["message"].splitlines()[0]
            lines.append(f"{c['sha'][:7]}  {msg}  ({c['commit']['author']['name']})")
        return "\n".join(lines) if lines else f"No commits in {repo}."

    def create_issue(args: dict) -> str:
        repo, title = args["repo"], args["title"]
        body = args.get("body", "")
        issue = call(token, "POST", f"/repos/{repo}/issues", {"title": title, "body": body})
        return f"Created issue #{issue['number']}: {issue['html_url']}"

    def describe_create_issue(args: dict) -> str:
        return f"CREATE GITHUB ISSUE in {args.get('repo')}\nTitle: {args.get('title')}\n\n{args.get('body', '')}"

    return [
        Tool(
            name="github_list_repos",
            description="List the owner's own GitHub repositories, most recently updated first.",
            input_schema={"type": "object", "properties": {}},
            handler=list_repos,
        ),
        Tool(
            name="github_list_issues",
            description="List issues in a repo the owner has access to.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "owner/repo, e.g. 'octocat/hello-world'"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "default open"},
                },
                "required": ["repo"],
            },
            handler=list_issues,
        ),
        Tool(
            name="github_list_commits",
            description="List recent commits on a repo's default branch.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "max_results": {"type": "integer", "description": "1-30, default 10"},
                },
                "required": ["repo"],
            },
            handler=list_commits,
        ),
        Tool(
            name="github_create_issue",
            description="Create a new issue in a repo the owner has write access to. The user must approve.",
            input_schema={
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["repo", "title"],
            },
            handler=create_issue,
            risk=Risk.CONFIRM,
            describe=describe_create_issue,
        ),
    ]
