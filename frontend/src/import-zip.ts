import { unzip, gunzipSync } from 'fflate'
import type { Entry, SourceContext } from './demo'

export type ImportedLogs = {
  filename: string
  entries: Entry[]
  sources: Map<string, string[]>
  references: Map<number, { path: string; start: number; end: number }>
  skipped: number
  unparsed: number
  duplicates: number
}

type Fields = Record<string, unknown>
const extensions = /\.(?:log|txt|csv|jsonl|xml)(?:\.gz)?$/i
const limit = 128 * 1024 * 1024
const timestamp = /^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+/
const header = /^(DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL|CRITICAL|SEVERE|TRACE)\b/i

function expand(bytes: Uint8Array<ArrayBuffer>): Promise<Record<string, Uint8Array>> {
  let size = 0
  let tooLarge = false
  return new Promise((resolve, reject) => {
    unzip(bytes, {
      filter: file => {
        if (!extensions.test(file.name) || /(^|\/)(?:__MACOSX|README\.txt$)/i.test(file.name)) return false
        size += file.originalSize
        if (size > limit) tooLarge = true
        return !tooLarge
      },
    }, (error, files) => {
      if (tooLarge) reject(new Error('Die Logdateien im ZIP überschreiten das Browser-Limit von 128 MiB. Bitte teile das Archiv auf.'))
      else if (error) reject(new Error('Das ZIP konnte nicht geöffnet werden. Prüfe, ob es beschädigt oder verschlüsselt ist.'))
      else resolve(files)
    })
  })
}

function decode(bytes: Uint8Array) {
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    return new TextDecoder('windows-1252').decode(bytes)
  }
}

function json(text: string): Fields | null {
  try {
    const value = JSON.parse(text)
    return value && typeof value === 'object' && !Array.isArray(value) ? value : null
  } catch {
    return null
  }
}

function parseLine(text: string): Fields | null {
  if (text.trimStart().startsWith('{')) return json(text)
  const date = timestamp.exec(text)
  if (!date) return null
  const remaining = text.slice(date[0].length)
  const parts = /^(?:\[([^\]]+)\]|([^\s]+))\s*(.*)$/.exec(remaining)
  const level = parts?.[1] ?? parts?.[2] ?? ''
  if (!parts || !header.test(level)) return null
  const separator = parts[3].indexOf('|')
  if (separator < 0) return { timestamp: date[1], level, message: parts[3] }
  const metadata = parts[3].slice(0, separator)
  const body = parts[3].slice(separator + 1).trim()
  return {
    ...Object.fromEntries([...metadata.matchAll(/([\w-]+)=([^\s]+)/g)].map(([, key, value]) => [key, value])),
    ...(body.startsWith('{') ? json(body) ?? { message: body } : { message: body }),
    timestamp: date[1], level,
  }
}

function csv(line: string, delimiter: string) {
  const values: string[] = []
  let quoted = false
  let field = ''
  for (let index = 0; index < line.length; index++) {
    const char = line[index]
    if (char === '"') {
      if (quoted && line[index + 1] === '"') { field += '"'; index++ }
      else quoted = !quoted
    } else if (char === delimiter && !quoted) {
      values.push(field)
      field = ''
    } else field += char
  }
  values.push(field)
  return { values, quoted }
}

function utc(value: unknown) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}/.test(value)) return null
  const text = value.trim().replace(' ', 'T').replace(',', '.')
  const parsed = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(text) ? text : text + 'Z')
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : null
}

export async function importZip(file: File): Promise<ImportedLogs> {
  if (file.size > limit) throw new Error('Das ZIP ist größer als 128 MiB. Bitte teile es für den Browser-Import auf.')
  const files = await expand(new Uint8Array(await file.arrayBuffer()))
  const result: ImportedLogs = { filename: file.name, entries: [], sources: new Map(), references: new Map(), skipped: 0, unparsed: 0, duplicates: 0 }
  const seen = new Set<string>()
  let totalBytes = 0
  for (const [path, compressed] of Object.entries(files)) {
    let bytes: Uint8Array = compressed
    if (path.toLowerCase().endsWith('.gz')) {
      try {
        if (bytes.byteLength < 18) throw new Error('Ungültiger Gzip-Header')
        const advertised = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(bytes.byteLength - 4, true)
        if (advertised > limit - totalBytes) { result.skipped++; continue }
        bytes = gunzipSync(compressed, { out: new Uint8Array(advertised) })
      } catch {
        result.skipped++
        continue
      }
    }
    totalBytes += bytes.byteLength
    if (totalBytes > limit) throw new Error('Die entpackten Logs überschreiten 128 MiB. Bitte teile das Archiv auf.')
    const lines = decode(bytes).split(/\r\n|\n|\r/)
    const originalCount = result.entries.length
    const parts = path.split('/')
    const logs = parts.lastIndexOf('logs')
    const host = logs > 0 ? parts[logs - 1] : parts.at(-2) ?? 'Unbekannt'
    const component = logs >= 0 ? parts[logs + 2] : ''
    function add(fields: Fields, start: number, end: number) {
      const time = utc(fields.timestamp ?? fields.ts_utc ?? fields.time)
      if (!time) { result.unparsed++; return }
      const level = String(fields.level ?? fields.severity ?? 'INFO').toUpperCase()
      const attrs = typeof fields.attrs === 'string' ? json(fields.attrs) : fields.attrs
      const meta = attrs && typeof attrs === 'object' ? attrs as Fields : {}
      const duration = fields.job_duration_ms ?? fields.workflow_duration_ms ?? fields.processing_time_ms ?? meta.job_duration_ms ?? meta.workflow_duration_ms ?? meta.processing_time_ms
      const measured = typeof duration === 'number' || (typeof duration === 'string' && duration.trim()) ? Number(duration) : NaN
      const message = String(fields.message ?? fields.msg ?? lines[start - 1])
      const jobFromMessage = /\b(?:job(?:[_ -]?id)?|workflow[_ -]?id|conversion[_ -]?id)\s*(?:[:=#]\s*|\s+)([\w.-]*\d[\w.-]*)/i.exec(message)?.[1]
      const entry: Entry = {
        id: result.entries.length + 1, ts_utc: time,
        host: String(fields.host ?? fields.server ?? host), component: String(fields.component ?? component ?? ''),
        level: ({ WARNING: 'WARN', CRITICAL: 'FATAL', SEVERE: 'FATAL' } as Record<string, string>)[level] ?? level,
        job_id: String(fields.job_id ?? fields.workflow_id ?? fields.conversion_id ?? meta.job_id ?? jobFromMessage ?? ''),
        trace_id: String(fields.trace_id ?? meta.trace_id ?? ''),
        message,
        workflow: String(fields.workflow_template ?? fields.workflow_name ?? fields.workflow ?? meta.workflow_template ?? meta.workflow ?? ''),
        status: String(fields.job_status ?? fields.workflow_status ?? fields.status ?? meta.job_status ?? meta.workflow_status ?? meta.status ?? ''),
        job_duration_ms: Number.isFinite(measured) && measured >= 0 ? measured : undefined,
      }
      const key = JSON.stringify([entry.host, entry.component, time, entry.level, fields.event_id ?? '', entry.job_id, entry.trace_id, entry.message, entry.workflow, entry.status, entry.job_duration_ms])
      if (seen.has(key)) { result.duplicates++; return }
      seen.add(key)
      result.entries.push(entry)
      result.references.set(entry.id, { path, start, end })
    }
    if (/\.csv(?:\.gz)?$/i.test(path)) {
      const first = lines.findIndex(line => !!line.trim())
      if (first < 0) { result.skipped++; continue }
      const delimiter = lines[first].includes(';') ? ';' : ','
      const headers = csv(lines[first], delimiter).values.map(value => value.trim().toLowerCase())
      for (let index = first + 1; index < lines.length; index++) {
        if (!lines[index].trim()) continue
        const start = index
        let record = lines[index]
        let parsed = csv(record, delimiter)
        while (parsed.quoted && index + 1 < lines.length) {
          record += '\n' + lines[++index]
          parsed = csv(record, delimiter)
        }
        if (parsed.quoted || parsed.values.length !== headers.length) { result.unparsed++; continue }
        add(Object.fromEntries(headers.map((key, column) => [key, parsed.values[column]])), start + 1, index + 1)
      }
    } else if (/\.xml(?:\.gz)?$/i.test(path)) {
      const source = lines.join('\n')
      let previous = 0
      let line = 1
      for (const event of source.matchAll(/<Event(?:\s[^>]*)?>[\s\S]*?<\/Event>/gi)) {
        line += source.slice(previous, event.index).split('\n').length - 1
        const end = line + event[0].split('\n').length - 1
        const parsed = new DOMParser().parseFromString(event[0], 'application/xml')
        if (parsed.querySelector('parsererror')) result.unparsed++
        else add(Object.fromEntries(Array.from(parsed.documentElement.children, field => [field.localName.toLowerCase(), field.textContent ?? ''])), line, end)
        previous = event.index
      }
    } else {
      const structured = /\.jsonl(?:\.gz)?$/i.test(path)
      for (let index = 0; index < lines.length; index++) {
        if (!lines[index].trim()) continue
        const fields = parseLine(lines[index])
        if (!fields) { result.unparsed++; continue }
        const start = index
        while (!structured && index + 1 < lines.length && lines[index + 1].trim() && !timestamp.test(lines[index + 1]) && /^\s|^(?:Caused by:|Suppressed:)/.test(lines[index + 1])) {
          fields.message = String(fields.message ?? '') + '\n' + lines[++index]
        }
        add(fields, start + 1, index + 1)
      }
    }
    if (result.entries.length > originalCount) result.sources.set(path, lines)
    else result.skipped++
  }
  if (!result.entries.length) throw new Error('Keine unterstützten Logereignisse gefunden. ZIP mit CSV-, JSONL-, LOG-, TXT- oder XML-Logs auswählen.')
  return result
}

export function importedContext(logs: ImportedLogs, id: number): SourceContext | undefined {
  const reference = logs.references.get(id)
  if (!reference) return undefined
  const { path, start, end } = reference
  const source = logs.sources.get(path)!
  const offset = Math.max(0, start - 11)
  return { path, line_start: start, line_end: end, lines: source.slice(offset, end + 10).map((text, index) => ({ line: offset + index + 1, text })) }
}



