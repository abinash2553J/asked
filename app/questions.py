import re

from .models import Comment

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"@[\w.-]+")
SPACE_RE = re.compile(r"\s+")

INTERROGATIVE_START = {
    "how", "why", "what", "when", "where", "which", "who", "whose",
    "can", "could", "do", "does", "did", "is", "are", "was", "were",
    "should", "would", "will", "anyone", "anybody",
}

PHRASES = (
    "how do i", "how to", "how can i", "how does", "what's the difference",
    "what is the difference", "can you", "could you", "does anyone",
    "any idea", "anyone know", "is there a", "where can i", "where do i",
    "what happens if", "why does", "why is", "should i",
)


def clean(text: str) -> str:
    text = URL_RE.sub(" ", text or "")
    text = MENTION_RE.sub(" ", text)
    return SPACE_RE.sub(" ", text).strip()


def is_question(text: str) -> tuple[bool, float]:
    cleaned = clean(text)
    if len(cleaned) < 4:
        return False, 0.0

    lowered = cleaned.lower()
    tokens = re.findall(r"[a-z']+", lowered)
    if not tokens:
        return False, 0.0

    score = 0.0
    if "?" in cleaned:
        score += 0.6
    if tokens[0] in INTERROGATIVE_START:
        score += 0.4
    elif any(tok in INTERROGATIVE_START for tok in tokens[:4]):
        score += 0.3
    if any(phrase in lowered for phrase in PHRASES):
        score += 0.3

    return score >= 0.55, min(score, 1.0)


def normalize(comments: list[Comment]) -> list[Comment]:
    seen: set[tuple[str, str]] = set()
    out: list[Comment] = []
    for comment in comments:
        text = clean(comment.text)
        if len(text) < 4:
            continue
        if not re.search(r"[a-zA-Z]", text):
            continue
        # Repeat questions from different people are the signal; only drop the
        # same author posting the same text twice.
        key = (comment.author.lower(), text.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(comment.model_copy(update={"text": text}))
    return out


def question_comments(comments: list[Comment]) -> list[Comment]:
    return [c for c in comments if is_question(c.text)[0]]
