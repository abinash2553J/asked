import json
import re

import httpx

from .config import Settings
from .models import Comment, ContentIdea, QuestionCluster

LEAD_RE = re.compile(
    r"^(how do i|how do you|how can i|how to|how does|how is|what's|what is|what are|"
    r"why is|why does|why do|can you|could you|does anyone know|anyone know|is there|"
    r"where can i|where do i|should i|when will|when is|which)\b[ :,-]*",
    re.IGNORECASE,
)

PROMPT = """You name audience question groups and draft video ideas for a creator.
Return JSON only: {"groups":[{"id":<int>,"question":"<canonical question, <=120 chars>","ideas":[{"title":"<video title, <=80 chars>","angle":"<one sentence>"}]}]}
Write 1-2 ideas per group. Keep the creator's language. Do not invent facts.
"""


def _topic(canonical: str) -> str:
    text = canonical.strip().rstrip("?").strip()
    text = LEAD_RE.sub("", text).strip(" .,:;-")
    return text or canonical.strip()


def template_ideas(canonical: str) -> list[ContentIdea]:
    topic = _topic(canonical)
    short = topic[:1].upper() + topic[1:]
    return [
        ContentIdea(title=f"{short} — explained properly", angle="Direct answer to the question people keep asking."),
        ContentIdea(title=f"Common mistakes with {topic[:60]}", angle="Correct the wrong answers already circulating in the comments."),
    ]


def _parse(payload: str, clusters: list[QuestionCluster]) -> dict[int, dict] | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", payload, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    out: dict[int, dict] = {}
    for item in data.get("groups", []):
        try:
            idx = int(item["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= idx < len(clusters):
            continue
        ideas = [
            ContentIdea(title=str(i.get("title", "")).strip(), angle=str(i.get("angle", "")).strip())
            for i in item.get("ideas", [])
            if str(i.get("title", "")).strip()
        ]
        out[idx] = {"question": str(item.get("question", "")).strip(), "ideas": ideas}
    return out or None


def enrich(clusters: list[QuestionCluster], settings: Settings) -> bool:
    """Rewrite the top clusters with an LLM. Returns True when it succeeded."""
    if not settings.llm_enabled or not clusters:
        return False

    top = clusters[: settings.llm_top_k]
    groups = [
        {"id": i, "question": c.canonical, "count": c.count, "examples": [e.text for e in c.examples[:3]]}
        for i, c in enumerate(top)
    ]
    body = {
        "model": settings.llm_model,
        "temperature": 0.4,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": json.dumps({"groups": groups}, ensure_ascii=False)},
        ],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}

    for attempt in range(2):
        try:
            resp = httpx.post(
                f"{settings.llm_base_url}/chat/completions",
                json=body,
                headers=headers,
                timeout=25,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"LLM HTTP {resp.status_code}")
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = _parse(content, top)
            if not parsed:
                raise RuntimeError("LLM returned no usable groups")
        except Exception:  # noqa: BLE001 - any failure falls back to templates
            if attempt == 0:
                continue
            return False

        for idx, item in parsed.items():
            cluster = top[idx]
            if item["question"]:
                cluster.canonical = item["question"][:200]
            if item["ideas"]:
                cluster.ideas = item["ideas"][:3]
                cluster.source = "llm"
        return True

    return False
