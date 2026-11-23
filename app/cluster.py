import re

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize
from scipy.sparse import hstack

DEFAULT_THRESHOLD = 0.38


def _matrix(texts: list[str]):
    word = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=1)
    return normalize(hstack([word.fit_transform(texts), char.fit_transform(texts)]).tocsr())


def _greedy(sim: np.ndarray, threshold: float) -> list[list[int]]:
    remaining = list(range(sim.shape[0]))
    groups: list[list[int]] = []
    while remaining:
        seed = remaining.pop(0)
        group = [seed]
        rest = []
        for idx in remaining:
            if sim[seed, idx] >= threshold:
                group.append(idx)
            else:
                rest.append(idx)
        remaining = rest
        groups.append(group)
    return groups


def cluster_indices(texts: list[str], threshold: float = DEFAULT_THRESHOLD) -> list[list[int]]:
    if not texts:
        return []
    if len(texts) == 1:
        return [[0]]

    try:
        matrix = _matrix(texts)
        sim = (matrix @ matrix.T).toarray()
    except ValueError:
        return [[i] for i in range(len(texts))]

    if len(texts) < 4:
        return _greedy(sim, threshold)

    try:
        model = AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="average",
            distance_threshold=1.0 - threshold,
        )
        labels = model.fit_predict(1.0 - sim)
    except Exception:  # noqa: BLE001 - clustering is best-effort
        return _greedy(sim, threshold)

    groups: dict[int, list[int]] = {}
    for idx, label in enumerate(labels):
        groups.setdefault(int(label), []).append(idx)
    return list(groups.values())


_SPACE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([?!.,:;])")


def _tidy(text: str) -> str:
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", _SPACE.sub(" ", text)).strip()
    return text.rstrip(" .") or text


def canonical_text(members: list[str], max_chars: int = 160) -> str:
    counts: dict[str, int] = {}
    for text in members:
        counts[text] = counts.get(text, 0) + 1
    best = _tidy(max(counts.items(), key=lambda kv: (kv[1], len(kv[0])))[0])
    if len(best) <= max_chars:
        return best
    return best[: max_chars - 1].rstrip() + "…"
