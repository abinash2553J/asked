import pytest

from app.cluster import cluster_indices
from app.models import Comment
from app.questions import is_question, normalize, question_comments
from app.youtube import InvalidURL, parse_video_id

VID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://youtube.com/watch?v={VID}&t=42s",
        f"https://youtu.be/{VID}",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/embed/{VID}",
        f"https://m.youtube.com/watch?v={VID}",
        VID,
    ],
)
def test_parse_video_id_forms(url):
    assert parse_video_id(url) == VID


@pytest.mark.parametrize("bad", ["", "not a url", "https://vimeo.com/12345", "https://youtube.com/watch?v=short"])
def test_parse_video_id_rejects(bad):
    with pytest.raises(InvalidURL):
        parse_video_id(bad)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("How do I install this on Windows?", True),
        ("why does the audio cut out at 2:00", True),
        ("can you make a follow-up video", True),
        ("Great video, thanks!", False),
        ("", False),
        ("🔥🔥🔥", False),
    ],
)
def test_question_detection(text, expected):
    assert is_question(text)[0] is expected


def test_normalize_drops_noise_and_keeps_repeat_questions():
    comments = [
        Comment(text="How do I export? https://example.com", author="ana"),
        Comment(text="how do i export?", author="bo"),
        Comment(text="how do i export?", author="ana"),
        Comment(text="   "),
        Comment(text="!!!???"),
    ]
    out = normalize(comments)
    assert [c.text for c in out] == ["How do I export?", "how do i export?"]


def test_cluster_recovers_planted_groups():
    texts = [
        "how do i export a project",
        "how do i export a project to mp4",
        "how do i export my project",
        "how do i export",
        "why is my audio out of sync",
        "why is my audio out of sync in my video",
        "why is my audio out of sync",
        "what microphone do you use",
        "which mic is that",
        "what mic do you use",
    ]
    groups = cluster_indices(texts)
    sizes = sorted((len(g) for g in groups), reverse=True)
    assert sizes[0] == 4
    assert sizes[1] == 3
    assert sum(sizes) == len(texts)


def test_question_comments_filters():
    comments = [
        Comment(text="How do I export?"),
        Comment(text="Nice video"),
        Comment(text="Why is audio out of sync"),
    ]
    assert len(question_comments(comments)) == 2


def test_youtube_api_source_parses_items(monkeypatch):
    from app.youtube import YouTubeApiSource
    import httpx

    fake_response = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": "How do I deploy to cloud?",
                            "authorDisplayName": "Developer",
                            "likeCount": 15,
                            "publishedAt": "2026-01-01T00:00:00Z",
                        }
                    }
                }
            }
        ]
    }

    def fake_get(url, params, **kwargs):
        return httpx.Response(200, json=fake_response, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    source = YouTubeApiSource(api_key="fake-key")
    comments = source.fetch("dQw4w9WgXcQ", limit=10, order="relevance", deadline=9999999999.0)
    assert len(comments) == 1
    assert comments[0].text == "How do I deploy to cloud?"
    assert comments[0].author == "Developer"
    assert comments[0].likes == 15
