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
| `ingest_status.json` | `GET /api/ingest/status`, also the `202` body of `POST /api/ingest` (`{"mode": "full" \| "incremental"}`; `409` if one runs) | P1 |
| `ingest_progress.sse.txt` | `GET /api/ingest/progress` (SSE events `state`, `started`, `progress`, `new_file`, `done`, `error`; read with `EventSource`) | P1 |
| `suggestions.json` | `GET /api/suggestions?lang=en\|de&limit=8` (questions from the logs, `scope: logs`); with `&event_id=…` questions about one event (`scope: event`, `404` if unknown). Not paginated. Show `question` and `reason` as they are; `kind` may get new values | P1 |
| `incidents.json` | `GET /api/analysis/incidents?q=JOB-2003` (filters `from, to, server, status, q, event_id`; newest first). `incident_id` is stable: the ID of the trigger group's first event | P2 |
| `incident.json` | `GET /api/analysis/incidents/{id}`: plus `steps` in time order, `links`, `anomalies` (lists shortened here) | P2 |
| `anomalies.json` | `GET /api/analysis/anomalies` (filters `from, to, server`) | P2 |
| `analysis_status.json` | `GET /api/analysis/status`, also the `202` body of `POST /api/analysis/run` (`409` if busy) | P2 |
| like `events.json` | `GET /api/trace/{key}` (trace ID, else job ID; `404` if unknown) | P2 |
| `chat_request.json` | `POST /api/chat` (request body) | P3 |
| `chat_stream.sse` | `POST /api/chat` (SSE: `token`, `step`, `answer`, `done`, `error`) | P3 |
| `chat_answer.json` | the `answer` event's data (interface 3, `assistant/answer.py`) | P3 |
| `chat_history.json` | `GET /api/chat/{conversation_id}` | P3 |
| *to add by P5* | `/api/eval/*` | P5 |
