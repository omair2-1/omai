from __future__ import annotations

import pytest

from omai.youtube_tools import YouTubeError, make_youtube_tools

KEY = "yt_test"


class FakeYouTube:
    def __init__(self, responses):
        self.responses = dict(responses)  # path -> value or Exception
        self.calls = []

    def __call__(self, api_key, path, **params):
        self.calls.append((api_key, path, params))
        val = self.responses[path]
        if isinstance(val, Exception):
            raise val
        return val


def tools(fake):
    return {t.name: t for t in make_youtube_tools(KEY, call=fake)}


def test_search_formats_results_and_passes_key():
    fake = FakeYouTube({"search": {"items": [
        {"id": {"videoId": "abc123"}, "snippet": {"title": "Cool Video", "channelTitle": "ChanX"}}
    ]}})
    out = tools(fake)["youtube_search"].handler({"query": "python tutorial"})
    assert "Cool Video" in out and "ChanX" in out and "youtu.be/abc123" in out
    assert fake.calls[0][0] == KEY and fake.calls[0][2]["q"] == "python tutorial"


def test_search_empty():
    fake = FakeYouTube({"search": {"items": []}})
    assert tools(fake)["youtube_search"].handler({"query": "x"}) == "No results."


def test_search_clamps_max_results():
    fake = FakeYouTube({"search": {"items": []}})
    tools(fake)["youtube_search"].handler({"query": "x", "max_results": 999})
    assert fake.calls[0][2]["maxResults"] == 15


def test_video_info_formats_and_truncates_description():
    fake = FakeYouTube({"videos": {"items": [{
        "snippet": {"title": "T", "channelTitle": "C", "publishedAt": "2026-01-01", "description": "d" * 2000},
        "statistics": {"viewCount": "100", "likeCount": "10"},
    }]}})
    out = tools(fake)["youtube_video_info"].handler({"video_id": "abc"})
    assert "Title: T" in out and "Views: 100" in out
    assert len(out) < 1700  # description capped well under 2000 chars


def test_video_info_not_found():
    fake = FakeYouTube({"videos": {"items": []}})
    assert tools(fake)["youtube_video_info"].handler({"video_id": "x"}) == "Video not found."


def test_api_error_propagates():
    fake = FakeYouTube({"search": YouTubeError("boom")})
    with pytest.raises(YouTubeError):
        tools(fake)["youtube_search"].handler({"query": "x"})
