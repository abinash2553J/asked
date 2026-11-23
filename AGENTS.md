# AGENTS.md

FastAPI app that turns a YouTube comment section into a ranked question brief. No database,
no build step; the frontend is three static files.

## Commands

```bash
uv sync                                  # install
uv run uvicorn app.main:app --port 12000 # serve (static files mount at /)
uv run pytest                            # 28 tests, ~1s
```

## Layout

- `app/pipeline.py` — the whole flow: parse → fetch → normalise → question filter → cluster →
  rank → ideas. Start here when behaviour is wrong.
- `app/youtube.py` — Google YouTube Data API v3 (primary when YOUTUBE_API_KEY is configured), then InnerTube fallback.
- `app/questions.py` — normalisation and the question heuristic.
- `app/cluster.py` — TF-IDF + average-linkage agglomeration, `DEFAULT_THRESHOLD = 0.38`.
- `app/ideas.py` — deterministic templates, optional OpenAI-compatible phrasing.
- `app/static/` — `index.html`, `styles.css`, `app.js`, self-hosted fonts.

## Things that bite

- Do **not** collapse duplicate comment text in `normalize()`: repeat questions from different
  people are the product's signal. Only same-author duplicates are dropped.
- Clustering threshold trades precision for recall; 0.45 splits obvious paraphrases, 0.30 merges
  unrelated questions ("export" with "import"). 0.38 is the tested compromise.
- YouTube's `reply` flag from the InnerTube payload is unreliable (often always true) — don't
  filter on it.
- Tests never hit the network; `tests/test_api.py` stubs the fetcher.
