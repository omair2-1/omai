from __future__ import annotations

import pytest

from omai.spotify_tools import SpotifyAuth, SpotifyError, make_spotify_tools

CID, CSECRET = "cid", "csecret"


class FakeTokenFetcher:
    def __init__(self, tokens):
        self.tokens = list(tokens)  # list of (token, expires_in) or Exception
        self.calls = 0

    def __call__(self):
        self.calls += 1
        item = self.tokens.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeCall:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, auth, path, **params):
        self.calls.append((auth.token(), path, params))
        return self.response


def test_token_is_cached_across_calls():
    fetcher = FakeTokenFetcher([("tok1", 3600)])
    auth = SpotifyAuth(CID, CSECRET, fetch_token=fetcher)
    assert auth.token() == "tok1"
    assert auth.token() == "tok1"
    assert fetcher.calls == 1  # second call reused the cached token


def test_token_refetched_once_expired(monkeypatch):
    fetcher = FakeTokenFetcher([("tok1", 100), ("tok2", 3600)])
    auth = SpotifyAuth(CID, CSECRET, fetch_token=fetcher)
    assert auth.token() == "tok1"
    monkeypatch.setattr("omai.spotify_tools.time.monotonic", lambda: 1_000_000)  # force expiry
    assert auth.token() == "tok2"
    assert fetcher.calls == 2


def test_track_search_formats_with_artists_and_link():
    resp = {"tracks": {"items": [{
        "name": "Song A", "artists": [{"name": "Artist X"}, {"name": "Artist Y"}],
        "external_urls": {"spotify": "https://open.spotify.com/track/123"},
    }]}}
    fake = FakeCall(resp)
    tools = {t.name: t for t in make_spotify_tools(CID, CSECRET, call=fake, auth=SpotifyAuth(CID, CSECRET, fetch_token=FakeTokenFetcher([("t", 3600)])))}
    out = tools["spotify_search"].handler({"query": "song a"})
    assert "Song A" in out and "Artist X, Artist Y" in out and "open.spotify.com/track/123" in out
    assert fake.calls[0][2]["type"] == "track"


def test_playlist_search_shows_owner():
    resp = {"playlists": {"items": [{
        "name": "Chill Mix", "owner": {"display_name": "Someone"},
        "external_urls": {"spotify": "https://open.spotify.com/playlist/abc"},
    }]}}
    fake = FakeCall(resp)
    tools = {t.name: t for t in make_spotify_tools(CID, CSECRET, call=fake, auth=SpotifyAuth(CID, CSECRET, fetch_token=FakeTokenFetcher([("t", 3600)])))}
    out = tools["spotify_search"].handler({"query": "chill", "type": "playlist"})
    assert "Chill Mix" in out and "Someone" in out


def test_empty_results():
    fake = FakeCall({"tracks": {"items": []}})
    tools = {t.name: t for t in make_spotify_tools(CID, CSECRET, call=fake, auth=SpotifyAuth(CID, CSECRET, fetch_token=FakeTokenFetcher([("t", 3600)])))}
    assert tools["spotify_search"].handler({"query": "x"}) == "No results."


def test_max_results_clamped():
    fake = FakeCall({"tracks": {"items": []}})
    tools = {t.name: t for t in make_spotify_tools(CID, CSECRET, call=fake, auth=SpotifyAuth(CID, CSECRET, fetch_token=FakeTokenFetcher([("t", 3600)])))}
    tools["spotify_search"].handler({"query": "x", "max_results": 999})
    assert fake.calls[0][2]["limit"] == 15


def test_tool_description_clarifies_no_playback():
    tools = {t.name: t for t in make_spotify_tools(CID, CSECRET)}
    assert "CANNOT start playback" in tools["spotify_search"].description


def test_auth_error_propagates():
    fetcher = FakeTokenFetcher([SpotifyError("bad credentials")])
    auth = SpotifyAuth(CID, CSECRET, fetch_token=fetcher)
    with pytest.raises(SpotifyError):
        auth.token()
