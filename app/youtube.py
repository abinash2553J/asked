import json
import re
import shutil
import subprocess
import time
from urllib.parse import parse_qs, urlparse

import httpx

from .models import Comment, VideoMeta

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PATH_PREFIXES = ("shorts", "embed", "live", "v")

OEMBED_URL = "https://www.youtube.com/oembed"


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


def fetch_meta(video_id: str, timeout: float = 10.0) -> VideoMeta:
    url = f"https://www.youtube.com/watch?v={video_id}"
    meta = VideoMeta(video_id=video_id, url=url)
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


class InnertubeSource(CommentSource):
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
            raise FetchError(f"Comment fetch failed: {exc}") from exc
        return out


class YtDlpSource(CommentSource):
    name = "yt-dlp"

    def fetch(self, video_id: str, limit: int, order: str, deadline: float) -> list[Comment]:
        if not shutil.which("yt-dlp"):
            raise FetchError("yt-dlp is not installed.")
        timeout = max(5.0, min(deadline - time.monotonic(), 60.0))
        cmd = [
            "yt-dlp",
            "--write-comments",
            "--skip-download",
            "--extractor-args",
            f"youtube:comment_sort={'new' if order == 'recent' else 'top'};max_comments={limit},all,100",
            "-J",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise FetchError("Comment fetch timed out.") from exc

        if proc.returncode != 0:
            err = (proc.stderr or "").lower()
            if "comments are turned off" in err or "comments disabled" in err:
                raise CommentsDisabled("Comments are turned off for this video.")
            if "private video" in err or "video unavailable" in err:
                raise VideoUnavailable("Video not found, private, or age-restricted.")
            if "429" in err or "too many requests" in err:
                raise RateLimited("YouTube is rate-limiting this machine. Try again shortly.")
            raise FetchError("yt-dlp could not fetch this video.")

        data = json.loads(proc.stdout or "{}")
        out: list[Comment] = []
        for item in (data.get("comments") or [])[:limit]:
            out.append(
                Comment(
                    text=str(item.get("text", "")).strip(),
                    author=str(item.get("author", "")).strip(),
                    likes=_to_int(item.get("like_count")),
                    published=str(item.get("_time_text") or item.get("timestamp") or ""),
                    is_reply=bool(item.get("parent")),
                )
            )
        return out


def fetch_comments(
    video_id: str,
    limit: int,
    order: str,
    budget: float,
) -> list[Comment]:
    deadline = time.monotonic() + budget
    errors: list[str] = []
    for source in (InnertubeSource(), YtDlpSource()):
        try:
            comments = source.fetch(video_id, limit, order, deadline)
        except CommentsDisabled:
            raise
        except FetchError as exc:
            errors.append(f"{source.name}: {exc.message}")
            continue
        if comments:
            return comments
        errors.append(f"{source.name}: returned no comments")
    raise FetchError("Could not fetch comments. " + " | ".join(errors))
