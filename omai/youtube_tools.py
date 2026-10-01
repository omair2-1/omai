"""YouTube tools (spec Phase 7, read-only half): free API key, no OAuth.

Search and video-info are public data (Risk.SAFE). Playlist/upload management would need OAuth
like Gmail's and is left for later since it's rarely needed for a personal research assistant.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from .tools import Tool

API_ROOT = "https://www.googleapis.com/youtube/v3"


class YouTubeError(RuntimeError):
    pass


def default_call(api_key: str, path: str, **params) -> dict:
    params["key"] = api_key
    url = f"{API_ROOT}/{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise YouTubeError(f"YouTube API error {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise YouTubeError(f"Could not reach YouTube: {exc}") from exc


def make_youtube_tools(api_key: str, call=default_call) -> list[Tool]:
    def search(args: dict) -> str:
        n = max(1, min(int(args.get("max_results", 5)), 15))
        data = call(
            api_key, "search", part="snippet", q=args["query"], type="video", maxResults=n, order="relevance"
        )
        items = data.get("items", [])
        if not items:
            return "No results."
        lines = []
        for it in items:
            vid = it["id"]["videoId"]
            sn = it["snippet"]
            lines.append(f"{sn['title']}  by {sn['channelTitle']}  https://youtu.be/{vid}")
        return "\n".join(lines)

    def video_info(args: dict) -> str:
        data = call(api_key, "videos", part="snippet,statistics,contentDetails", id=args["video_id"])
        items = data.get("items", [])
        if not items:
            return "Video not found."
        v = items[0]
        sn, stats = v["snippet"], v.get("statistics", {})
        return (
            f"Title: {sn['title']}\nChannel: {sn['channelTitle']}\nPublished: {sn['publishedAt']}\n"
            f"Views: {stats.get('viewCount', '?')}  Likes: {stats.get('likeCount', '?')}\n\n"
            f"{sn.get('description', '')[:1500]}"
        )

    return [
        Tool(
            name="youtube_search",
            description="Search YouTube for videos. Returns title, channel and link.",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "description": "1-15, default 5"},
                },
                "required": ["query"],
            },
            handler=search,
        ),
        Tool(
            name="youtube_video_info",
            description="Get details (title, channel, views, description) for a specific YouTube video id.",
            input_schema={
                "type": "object",
                "properties": {"video_id": {"type": "string", "description": "the id from a youtu.be/<id> link"}},
                "required": ["video_id"],
            },
            handler=video_info,
        ),
    ]
