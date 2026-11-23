# Comment → Brief

Paste a YouTube URL. Get back a ranked shortlist of the questions your audience keeps asking,
with the comments that prove it, plus draft ideas you can film next.

No key, no sign-up, no database. One process, two endpoints, one page.

## Run it

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 12000
```

Open <http://localhost:12000>. Or drive the API directly:

```bash
curl -s -X POST localhost:12000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://www.youtube.com/watch?v=VIDEO_ID","max_comments":500}'
```

`GET /api/health` returns `{"ok": true, "llm": false}`.

## How the brief is built

1. **Fetch** — video metadata over oEmbed, comments over YouTube's InnerTube API
   (`youtube-comment-downloader` as fallback, `yt-dlp` after that). Hard caps: 2000 comments,
   45 s fetch budget.
2. **Filter** — drop spam, links-only and emoji-only comments; keep the rest verbatim.
3. **Find questions** — heuristic: question mark, interrogative opener, or a "how do I…" shape.
4. **Cluster** — TF-IDF (word + char n-grams) with average-linkage agglomerative clustering at
   cosine 0.38. Groups smaller than 2 are dropped, so every row you see repeated at least twice.
5. **Rank** — by how many people asked, then by total likes on those comments. Counts are real
   comment counts, never estimates. The top 25 groups are kept.
6. **Ideas** — two per group (a direct answer, a common-mistakes video). Deterministic templates
   by default; set `LLM_API_KEY` to have a model phrase the titles instead. The prompt is told to
   use only the quoted comments and to never invent a count.

Every quote in the UI and in the Markdown export is a real comment, shown with its author and
like count. Rows expand to show the rest of the evidence.

## Configuration

Copy `.env.example` to `.env`. Everything is optional:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAX_COMMENTS_DEFAULT` | 500 | Comments fetched when the request doesn't say |
| `MAX_COMMENTS_CAP` | 2000 | Hard ceiling |
| `REQUEST_TIMEOUT` | 20 | Seconds per network call |
| `FETCH_BUDGET` | 45 | Seconds for the whole fetch step |
| `MIN_GROUP_SIZE` | 2 | Smallest group shown |
| `LLM_API_KEY` | — | Enables phrased idea titles |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `LLM_MODEL` | `gpt-4o-mini` | Model used for phrasing |

## Tests

```bash
uv run pytest
```

Covers question detection, normalisation, clustering on planted groups, idea generation, the
Markdown export, and the HTTP API (health, validation, throttle, happy path with a stubbed
fetcher).

## Known limits

- YouTube can throttle or block anonymous comment reads. The app says so instead of retrying
  forever.
- Clustering is lexical. "mic" and "microphone" land in different groups; an LLM pass would fix
  that but is not required for the brief to be useful.
- Comment order is whatever YouTube returns for the chosen sort — the top of a huge thread is
  chatter, so the default relevance order sometimes yields few repeated questions. The empty
  state suggests raising the cap or switching order.
- One analysis is held in memory (15 min TTL, 40 entries). No history, no accounts.
