import pytest
from fastapi.testclient import TestClient

from app import main
from app.ideas import template_ideas
from app.models import Comment, VideoMeta
from app.pipeline import analyze
from app.report import render_markdown
from app.config import Settings

VID = "dQw4w9WgXcQ"


@pytest.fixture
def client():
    main._cache.clear()
    main._hits.clear()
    return TestClient(main.app)


@pytest.fixture
def fake_sources(monkeypatch):
    comments = [
        Comment(text="How do I export to mp4?", author="ana", likes=12),
        Comment(text="how do i export to mp4", author="bo", likes=3),
        Comment(text="What export settings do you use?", author="cy", likes=9),
        Comment(text="what export settings should i use for youtube", author="di", likes=1),
        Comment(text="How do I export", author="ed", likes=5),
        Comment(text="Nice video", author="fay", likes=0),
        Comment(text="why is my audio out of sync", author="gus", likes=7),
        Comment(text="Why is audio out of sync?", author="hal", likes=2),
    ]
    monkeypatch.setattr(
        "app.pipeline.fetch_meta",
        lambda video_id, timeout=10.0: VideoMeta(
            video_id=video_id, url=f"https://www.youtube.com/watch?v={video_id}", title="Export like a pro", author="Studio"
        ),
    )
    monkeypatch.setattr(
        "app.pipeline.fetch_comments",
        lambda video_id, limit, order, budget: comments[:limit],
    )
    return comments


def test_pipeline_ranks_and_keeps_evidence(fake_sources):
    result = analyze(f"https://youtu.be/{VID}", 500, "relevance", Settings())
    assert result.video.title == "Export like a pro"
    assert result.stats.questions >= 5
    assert result.clusters, "expected at least one group"
    top = result.clusters[0]
    assert top.count >= 2
    assert top.examples, "every ranked item must carry example comments"
    assert top.ideas, "fallback ideas must be produced without a key"
    assert top.source == "template"


def test_markdown_has_header_ledger_and_ideas(fake_sources):
    result = analyze(VID, 500, "relevance", Settings())
    markdown = render_markdown(result)
    assert "# Export like a pro" in markdown
    assert "## What people keep asking" in markdown
    assert "## Content ideas" in markdown
    assert "× asked" in markdown


def test_api_analyze_ok(client, fake_sources):
    response = client.post("/api/analyze", json={"url": f"https://youtu.be/{VID}", "max_comments": 500})
    assert response.status_code == 200
    body = response.json()
    assert body["video"]["video_id"] == VID
    assert body["markdown"].startswith("# Export like a pro")
    assert body["stats"]["groups"] >= 1


def test_api_invalid_url(client):
    response = client.post("/api/analyze", json={"url": "https://example.com/nope"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_url"


def test_api_missing_body(client):
    assert client.post("/api/analyze", json={}).status_code == 422


def test_api_caches_repeat_requests(client, fake_sources, monkeypatch):
    calls = {"n": 0}
    original = main.analyze

    def counted(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(main, "analyze", counted)
    for _ in range(2):
        assert client.post("/api/analyze", json={"url": VID}).status_code == 200
    assert calls["n"] == 1


def test_template_ideas_use_topic():
    ideas = template_ideas("How do I export a project?")
    assert "export a project" in ideas[0].title.lower()
    assert len(ideas) == 2


def test_health(client):
    body = client.get("/api/health").json()
    assert body["ok"] is True
