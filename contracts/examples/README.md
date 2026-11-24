# API contract examples (interface 2)

One example response per endpoint, used by the frontend mock API (P4) and the evaluation (P5).
The endpoint list is in [docs/ARCHITECTURE.md §5](../../docs/ARCHITECTURE.md).

**Rules**
- Whoever changes a response updates its example here in the same commit and tells the team.
- Times are ISO-8601 UTC with `Z`. IDs `id` are internal DuckDB IDs; `event_id` is the ID from the log line.
- Lists are paginated: `{"items": [...], "total": n, "limit": l, "offset": o}`.
- Values come from the real log package (`JOB-2003` chain on 24 Nov). Counts in `stats.json` are from the preliminary analysis and will change after the first full ingest.

| File | Endpoint | Owner |
|---|---|---|
| `health.json` | `GET /api/health` | P1 |
| `stats.json` | `GET /api/stats` | P1 |
| `sources.json` | `GET /api/sources` | P1 |
| `events.json` | `GET /api/events?job_id=JOB-2003` | P1 |
| `event.json` | `GET /api/events/{id}` | P1 |
| `event_context.json` | `GET /api/events/{id}/context?n=3` | P1 |
| `ingest_progress.sse.txt` | `GET /api/ingest/progress` (SSE) | P1 |
| *to add by P2* | `/api/analysis/*`, `/api/trace/{key}` | P2 |
| *to add by P3* | `POST /api/chat` (SSE), `GET /api/chat/{conversation_id}` | P3 |
| *to add by P5* | `/api/eval/*` | P5 |
