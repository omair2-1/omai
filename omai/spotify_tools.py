"""Spotify tools: search only (no playback control).

Spotify's playback-control endpoints (play/pause/skip/queue) require a Premium subscription and
a full user-login OAuth flow; free accounts are rejected by Spotify's own API, not by anything
here. So this gives search + a link to tap, using the much simpler Client Credentials flow (an
app-level token - no user login, no browser step, no redirect URI).
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .tools import Tool

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_ROOT = "https://api.spotify.com/v1"


class SpotifyError(RuntimeError):
    pass


class SpotifyAuth:
    """Caches the app-level token in memory and refreshes it just before it expires."""

    def __init__(self, client_id: str, client_secret: str, fetch_token=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._fetch_token = fetch_token or self._default_fetch_token
        self._token: str | None = None
        self._expires_at: float = 0.0

    def _default_fetch_token(self) -> tuple[str, int]:
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        req = urllib.request.Request(
            TOKEN_URL,
            method="POST",
            data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise SpotifyError(f"Spotify auth error {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise SpotifyError(f"Could not reach Spotify: {exc}") from exc
        return data["access_token"], int(data.get("expires_in", 3600))

    def token(self) -> str:
        if self._token is None or time.monotonic() >= self._expires_at:
            self._token, expires_in = self._fetch_token()
            self._expires_at = time.monotonic() + max(60, expires_in - 60)  # refresh a minute early
        return self._token


def default_call(auth: SpotifyAuth, path: str, **params) -> dict:
    url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {auth.token()}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SpotifyError(f"Spotify API error {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise SpotifyError(f"Could not reach Spotify: {exc}") from exc


def make_spotify_tools(client_id: str, client_secret: str, call=default_call, auth: SpotifyAuth | None = None) -> list[Tool]:
    auth = auth or SpotifyAuth(client_id, client_secret)

    def search(args: dict) -> str:
        kind = args.get("type", "track")
        n = max(1, min(int(args.get("max_results", 5)), 15))
        data = call(auth, "search", q=args["query"], type=kind, limit=n)
        items = data.get(f"{kind}s", {}).get("items", [])
        if not items:
            return "No results."
        lines = []
        for it in items:
            if kind == "track":
                artists = ", ".join(a["name"] for a in it.get("artists", []))
                lines.append(f"{it['name']} - {artists}  {it['external_urls']['spotify']}")
            elif kind == "artist":
                lines.append(f"{it['name']}  {it['external_urls']['spotify']}")
            else:  # playlist, album
                owner = it.get("owner", {}).get("display_name") or ", ".join(
                    a["name"] for a in it.get("artists", [])
                )
                lines.append(f"{it['name']} - {owner}  {it['external_urls']['spotify']}")
        return "\n".join(lines)

    return [
        Tool(
            name="spotify_search",
            description=(
                "Search Spotify for a track, artist, album or playlist and return a link the owner "
                "can open to play it themselves. This CANNOT start playback directly - that needs "
                "Spotify Premium, which the owner does not have - it only finds things and links to them."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "type": {"type": "string", "enum": ["track", "artist", "album", "playlist"], "description": "default track"},
                    "max_results": {"type": "integer", "description": "1-15, default 5"},
                },
                "required": ["query"],
            },
            handler=search,
        ),
    ]
