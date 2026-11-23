import json
import re
import time
from urllib.parse import parse_qs, urlparse

import httpx

from .config import get_settings
from .models import Comment, VideoMeta

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PATH_PREFIXES = ("shorts", "embed", "live", "v")

OEMBED_URL = "https://www.youtube.com/oembed"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


class FetchError(Exception):
    code = "fetch_failed"
    status = 502

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidURL(FetchError):
    code = "invalid_url"
    status = 400


class CommentsDisabled(FetchError):
    code = "comments_disabled"
    status = 422


class VideoUnavailable(FetchError):
    code = "video_unavailable"
    status = 404


class RateLimited(FetchError):
    code = "rate_limited"
    status = 429


def parse_video_id(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise InvalidURL("Paste a YouTube video URL.")

    if ID_RE.match(raw):
        return raw

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")

    if host == "youtu.be":
        vid = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path.rstrip("/") == "/watch":
            vid = (parse_qs(parsed.query).get("v") or [""])[0]
        else:
            parts = [p for p in parsed.path.split("/") if p]
            vid = parts[1] if len(parts) > 1 and parts[0] in PATH_PREFIXES else ""
    else:
        vid = ""

    if not ID_RE.match(vid):
        raise InvalidURL("That does not look like a YouTube video URL.")
    return vid


def fetch_meta(video_id: str, timeout: float = 10.0, api_key: str | None = None) -> VideoMeta:
    if api_key is None:
        try:
            api_key = get_settings().youtube_api_key
        except Exception:
            api_key = ""

    url = f"https://www.youtube.com/watch?v={video_id}"
    meta = VideoMeta(video_id=video_id, url=url)

    # 1. Try official Google YouTube Data API v3 if API key is provided
    if api_key:
        try:
            resp = httpx.get(
                f"{YOUTUBE_API_BASE}/videos",
                params={"part": "snippet", "id": video_id, "key": api_key},
                timeout=timeout,
            )
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if items:
                    snippet = items[0].get("snippet", {})
                    meta.title = snippet.get("title", "")
                    meta.author = snippet.get("channelTitle", "")
                    return meta
                raise VideoUnavailable("Video not found, private, or age-restricted.")
            if resp.status_code == 404:
                raise VideoUnavailable("Video not found, private, or age-restricted.")
        except VideoUnavailable:
            raise
        except Exception:
            pass  # Fall back to oembed

    # 2. Fall back to standard YouTube OEMBED
    try:
        resp = httpx.get(
            OEMBED_URL,
            params={"url": url, "format": "json"},
            timeout=timeout,
            follow_redirects=True,
        )
        if resp.status_code == 404:
            raise VideoUnavailable("Video not found, private, or age-restricted.")
        if resp.status_code == 200:
            data = resp.json()
            meta.title = data.get("title", "")
            meta.author = data.get("author_name", "")
    except VideoUnavailable:
        raise
    except httpx.HTTPError:
        pass
    return meta


def _to_int(value: object) -> int:
    if isinstance(value, int):
        return value
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


class CommentSource:
    name = "base"

    def fetch(self, video_id: str, limit: int, order: str, deadline: float) -> list[Comment]:
        raise NotImplementedError


class YouTubeApiSource(CommentSource):
    """Official Google YouTube Data API v3 source (no scraping, zero rate limits)."""

    name = "google-api"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def fetch(self, video_id: str, limit: int, order: str, deadline: float) -> list[Comment]:
        if not self.api_key:
            raise FetchError("Google YouTube API key is missing.")

        sort_order = "time" if order == "recent" else "relevance"
        out: list[Comment] = []
        page_token: str | None = None

        while len(out) < limit and time.monotonic() < deadline:
            batch_size = min(100, limit - len(out))
            params: dict[str, str | int] = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": batch_size,
                "order": sort_order,
                "textFormat": "plainText",
                "key": self.api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            try:
                resp = httpx.get(
                    f"{YOUTUBE_API_BASE}/commentThreads",
                    params=params,
                    timeout=min(15.0, max(3.0, deadline - time.monotonic())),
                )
            except httpx.HTTPError as exc:
                raise FetchError(f"YouTube API request failed: {exc}") from exc

            if resp.status_code == 403:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                err_items = data.get("error", {}).get("errors", [])
                reasons = [e.get("reason", "") for e in err_items]
                if "commentsDisabled" in reasons:
                    raise CommentsDisabled("Comments are turned off for this video.")
                if "quotaExceeded" in reasons or "dailyLimitExceeded" in reasons:
                    raise RateLimited("Google YouTube API daily quota exceeded.")
                msg = data.get("error", {}).get("message", "YouTube API permission or quota error.")
                raise FetchError(f"YouTube API error: {msg}")

            if resp.status_code == 404:
                raise VideoUnavailable("Video not found or private.")

            if resp.status_code == 400:
                data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                msg = data.get("error", {}).get("message", "Invalid request or YouTube API key.")
                raise FetchError(f"YouTube API error: {msg}")

            if resp.status_code != 200:
                raise FetchError(f"YouTube API HTTP {resp.status_code}")

            data = resp.json()
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                top = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = str(top.get("textOriginal") or top.get("textDisplay") or "").strip()
                if not text:
                    continue
                author = str(top.get("authorDisplayName") or "").strip()
                likes = _to_int(top.get("likeCount", 0))
                published = str(top.get("publishedAt") or "")
                out.append(
                    Comment(
                        text=text,
                        author=author,
                        likes=likes,
                        published=published,
                        is_reply=False,
                    )
                )
                if len(out) >= limit:
                    break

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return out


class InnertubeSource(CommentSource):
    """Fallback scraping source for environments without an API key."""

    name = "innertube"

    def fetch(self, video_id: str, limit: int, order: str, deadline: float) -> list[Comment]:
        from youtube_comment_downloader import (
            SORT_BY_POPULAR,
            SORT_BY_RECENT,
            YoutubeCommentDownloader,
        )

        downloader = YoutubeCommentDownloader()
        sort = SORT_BY_RECENT if order == "recent" else SORT_BY_POPULAR
        out: list[Comment] = []
        try:
            for item in downloader.get_comments(video_id, sort_by=sort):
                out.append(
                    Comment(
                        text=str(item.get("text", "")).strip(),
                        author=str(item.get("author", "")).strip(),
                        likes=_to_int(item.get("votes")),
                        published=str(item.get("time", "")),
                        is_reply=bool(item.get("reply")),
                    )
                )
                if len(out) >= limit or time.monotonic() > deadline:
                    break
        except Exception as exc:  # noqa: BLE001 - surface as typed error
            err_str = str(exc)
            if "Expecting value" in err_str or "char 0" in err_str or "429" in err_str:
                raise RateLimited("YouTube returned an empty or rate-limited response.") from exc
            raise FetchError(f"Comment fetch failed: {exc}") from exc
        return out


def fetch_comments(
    video_id: str,
    limit: int,
    order: str,
    budget: float,
    api_key: str | None = None,
) -> list[Comment]:
    if api_key is None:
        try:
            api_key = get_settings().youtube_api_key
        except Exception:
            api_key = ""

    deadline = time.monotonic() + budget
    errors: list[str] = []
    saw_rate_limit = False

    sources: list[CommentSource] = []
    if api_key:
        sources.append(YouTubeApiSource(api_key))
    sources.append(InnertubeSource())

    for source in sources:
        try:
            comments = source.fetch(video_id, limit, order, deadline)
        except (CommentsDisabled, VideoUnavailable):
            raise
        except RateLimited as exc:
            saw_rate_limit = True
            errors.append(f"{source.name}: {exc.message}")
            continue
        except FetchError as exc:
            if "rate-limit" in exc.message.lower() or "429" in exc.message.lower():
                saw_rate_limit = True
            errors.append(f"{source.name}: {exc.message}")
            continue
        if comments:
            return comments
        errors.append(f"{source.name}: returned no comments")

    if saw_rate_limit:
        raise RateLimited(
            "YouTube is rate-limiting this machine. Set a Google YouTube Data API key (YOUTUBE_API_KEY) in .env to eliminate rate limits."
        )
    raise FetchError("Could not fetch comments. " + " | ".join(errors))
