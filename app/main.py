import logging
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import get_settings
from .pipeline import analyze
from .report import render_markdown
from .youtube import FetchError

log = logging.getLogger("brief")
logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).parent / "static"
CACHE_TTL = 15 * 60
CACHE_MAX = 32
THROTTLE_LIMIT = 5
THROTTLE_WINDOW = 60

app = FastAPI(title="Comment → Brief", docs_url="/api/docs", openapi_url="/api/openapi.json")

_cache: "OrderedDict[tuple, tuple[float, dict]]" = OrderedDict()
_hits: dict[str, deque[float]] = defaultdict(deque)


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1)
    max_comments: int | None = None
    order: Literal["relevance", "recent"] = "relevance"


def _throttled(ip: str) -> bool:
    now = time.monotonic()
    bucket = _hits[ip]
    while bucket and now - bucket[0] > THROTTLE_WINDOW:
        bucket.popleft()
    if len(bucket) >= THROTTLE_LIMIT:
        return True
    bucket.append(now)
    return False


def _cached(key: tuple) -> dict | None:
    entry = _cache.get(key)
    if not entry:
        return None
    stored, payload = entry
    if time.monotonic() - stored > CACHE_TTL:
        _cache.pop(key, None)
        return None
    _cache.move_to_end(key)
    return payload


def _store(key: tuple, payload: dict) -> None:
    _cache[key] = (time.monotonic(), payload)
    _cache.move_to_end(key)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


@app.exception_handler(FetchError)
async def _fetch_error(_: Request, exc: FetchError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "server_error", "message": "Something broke on our side. Try again."}},
    )


@app.get("/api/health")
async def health() -> dict:
    settings = get_settings()
    return {"ok": True, "llm": settings.llm_enabled}


@app.post("/api/analyze")
async def analyze_endpoint(body: AnalyzeRequest, request: Request) -> JSONResponse:
    settings = get_settings()
    ip = (request.client.host if request.client else "unknown") or "unknown"
    if _throttled(ip):
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "too_many_requests",
                    "message": "That is a lot of videos at once. Wait a minute and try again.",
                }
            },
        )

    limit = body.max_comments or settings.max_comments_default
    limit = max(20, min(limit, settings.max_comments_cap))

    from .youtube import parse_video_id

    video_id = parse_video_id(body.url)
    key = (video_id, limit, body.order)

    payload = _cached(key)
    if payload is None:
        result = await run_in_threadpool(analyze, body.url, limit, body.order, settings)
        payload = {
            "video": result.video.model_dump(),
            "clusters": [c.model_dump() for c in result.clusters],
            "stats": result.stats.model_dump(),
            "generated_at": result.generated_at,
            "markdown": render_markdown(result),
        }
        _store(key, payload)

    return JSONResponse(payload)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
