import time
from datetime import datetime, timezone

from .cluster import canonical_text, cluster_indices
from .config import Settings
from .ideas import enrich, template_ideas
from .models import AnalysisResult, QuestionCluster, Stats
from .questions import is_question, normalize
from .youtube import fetch_comments, fetch_meta, parse_video_id

MAX_GROUPS = 25


def _examples(members, limit: int = 3):
    ordered = sorted(members, key=lambda c: c.likes, reverse=True)
    out, seen = [], set()
    for comment in ordered:
        key = comment.text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(comment)
        if len(out) >= limit:
            break
    return out


def analyze(url: str, max_comments: int, order: str, settings: Settings) -> AnalysisResult:
    started = time.monotonic()
    video_id = parse_video_id(url)
    meta = fetch_meta(video_id, timeout=settings.request_timeout)

    raw = fetch_comments(video_id, max_comments, order, settings.fetch_budget)
    comments = normalize(raw)
    questions = [c for c in comments if is_question(c.text)[0]]

    groups = cluster_indices([c.text for c in questions])
    clusters: list[QuestionCluster] = []
    for group in groups:
        if len(group) < settings.min_group_size:
            continue
        members = [questions[i] for i in group]
        clusters.append(
            QuestionCluster(
                canonical=canonical_text([c.text for c in members]),
                count=len(members),
                likes=sum(c.likes for c in members),
                examples=_examples(members),
            )
        )

    clusters.sort(key=lambda c: (c.count, c.likes), reverse=True)
    clusters = clusters[:MAX_GROUPS]
    for rank, cluster in enumerate(clusters, start=1):
        cluster.rank = rank
        cluster.ideas = template_ideas(cluster.canonical)

    llm_used = enrich(clusters, settings)

    stats = Stats(
        comments_fetched=len(raw),
        comments_analyzed=len(comments),
        questions=len(questions),
        groups=len(clusters),
        capped=len(raw) >= max_comments,
        llm=llm_used,
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
    return AnalysisResult(
        video=meta,
        clusters=clusters,
        stats=stats,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
