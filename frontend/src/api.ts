import type { Answer, Entry, EventPage, SourceContext } from './demo'

type JsonObject = Record<string, unknown>

function object(value: unknown): value is JsonObject {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function numeric(value: unknown, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function normalizeEntry(value: unknown): Entry {
  const row = object(value) ? value : {}
  const attrs = object(row.attrs) ? row.attrs : {}
  const sourceLine = row.line_start ?? row.source_line
  const sourceLineEnd = row.line_end ?? row.source_line_end
  const duration = row.job_duration_ms ?? attrs.job_duration_ms ?? attrs.duration_ms
  return {
    id: numeric(row.id),
    ts_utc: String(row.ts_utc ?? ''),
    host: String(row.host ?? row.server ?? ''),
    component: String(row.component ?? ''),
    level: String(row.level ?? row.level_raw ?? 'INFO'),
    job_id: String(row.job_id ?? ''),
    trace_id: String(row.trace_id ?? ''),
    message: String(row.message ?? ''),
    workflow: typeof row.workflow === 'string' ? row.workflow : typeof attrs.workflow === 'string' ? attrs.workflow : undefined,
    status: typeof row.status === 'string' ? row.status : typeof attrs.status === 'string' ? attrs.status : undefined,
    job_duration_ms: duration === undefined ? undefined : numeric(duration),
    source: typeof row.source_path === 'string' ? row.source_path : typeof row.source === 'string' ? row.source : undefined,
    source_line: sourceLine === undefined ? undefined : numeric(sourceLine),
    source_line_end: sourceLineEnd === undefined ? undefined : numeric(sourceLineEnd),
  }
}

function normalizeEventList(value: unknown): Entry[] | EventPage {
  if (Array.isArray(value)) return value.map(normalizeEntry)
  if (!object(value) || !Array.isArray(value.items)) return value as Entry[]
  return {
    items: value.items.map(normalizeEntry),
    total: numeric(value.total, value.items.length),
    limit: numeric(value.limit ?? value.page_size, value.items.length),
    offset: numeric(value.offset),
  }
}

function normalizeContext(value: unknown): SourceContext {
  const context = object(value) ? value : {}
  const lines = Array.isArray(context.lines) ? context.lines : []
  return {
    path: String(context.path ?? context.source_path ?? ''),
    line_start: numeric(context.line_start),
    line_end: numeric(context.line_end),
    lines: lines.filter(object).map(line => ({
      line: numeric(line.line ?? line.no),
      text: String(line.text ?? ''),
    })),
  }
}

function normalizeResponse(path: string, value: unknown) {
  const route = path.split('?')[0]
  if (route === '/events' || route.startsWith('/trace/')) return normalizeEventList(value)
  if (/^\/events\/\d+\/context$/.test(route)) return normalizeContext(value)
  if (/^\/events\/\d+$/.test(route)) return normalizeEntry(value)
  return value
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch('/api' + path, options)
  if (!response.ok) {
    let detail = ''
    try {
      const payload = await response.clone().json() as { detail?: unknown; message?: unknown }
      const message = typeof payload.detail === 'string' ? payload.detail : typeof payload.message === 'string' ? payload.message : ''
      if (message) detail = ' · ' + message
    } catch {
      // Keep non-JSON server errors readable by reporting their HTTP status.
    }
    throw new Error('Backend ' + path + ': HTTP ' + response.status + detail)
  }
  return normalizeResponse(path, await response.json()) as T
}

export async function chat(question: string, onStep: (step: string) => void, signal: AbortSignal): Promise<Answer> {
  const response = await fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question }), signal,
  })
  if (!response.ok || !response.body) throw new Error('Chat konnte nicht gestartet werden (HTTP ' + response.status + ').')
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  let answer: Answer | undefined
  function consume(frame: string) {
    const lines = frame.split(/\r?\n/)
    const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
    const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
    if (event === 'step') {
      try {
        const step = JSON.parse(data) as string | { message?: string; text?: string }
        onStep(typeof step === 'string' ? step : step.message ?? step.text ?? 'Logs werden durchsucht')
      } catch {
        onStep(data)
      }
    }
    if (event === 'answer') answer = JSON.parse(data) as Answer
    if (event === 'error') throw new Error(data || 'Der Chat-Stream meldet einen Fehler.')
  }
  try {
    while (!answer) {
      const chunk = await reader.read()
      buffer += chunk.value ?? ''
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() ?? ''
      frames.forEach(consume)
      if (chunk.done) {
        if (buffer.trim()) consume(buffer)
        break
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
  if (!answer) throw new Error('Der Chat-Stream endete ohne Antwort.')
  return answer
}
