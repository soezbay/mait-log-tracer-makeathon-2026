import type { Entry } from './demo'

export type Process = {
  key: string
  job: string
  trace: string
  workflow: string
  conversion: boolean
  hosts: string[]
  logs: Entry[]
  status: 'Fehlgeschlagen' | 'Erholt' | 'Erfolgreich' | 'Läuft' | 'Unklar'
  start?: string
  end?: string
  duration?: number
  durationSource?: 'Auftrag' | 'Start/Ende'
  first: string
  last: string
  errors: Entry[]
}

const startSignal = /\b(?:workflow|job|conversion|process|task)\s+(?:started|starting|began)\b|\b(?:start(?:ed|ing)?)\s+(?:workflow|job|conversion)\b/i
const failureSignal = /\b(?:failed|failure|aborted|cancelled|canceled)\b|\bno (?:registered .*(?:result|output)|output|result)\b/i
const recoverySignal = /\b(?:retry (?:succeeded|successful|recovered)|recovered after retry)\b/i
const successSignal = /\b(?:workflow|job|conversion|process|publish)\s+(?:completed|succeeded|finished|successful)\b|\bresult (?:registered|published)\b/i
const conversionSignal = /\b(?:convert\w*|konvert\w*|jt|nx|pdf|publish|me10|solid.edge)\b/i
const badLevel = (entry: Entry) => entry.level === 'ERROR' || entry.level === 'FATAL'

export function buildProcesses(events: Entry[]): Process[] {
  const groups = new Map<string, Entry[]>()
  const chronological = [...events].sort((a, b) => Date.parse(a.ts_utc) - Date.parse(b.ts_utc))
  for (const entry of chronological) {
    const job = entry.job_id.trim()
    const trace = entry.trace_id.trim()
    if (!job && !trace) continue
    // Keep untraced display IDs scoped to a host and cut sessions after an idle gap.
    const base = JSON.stringify(trace ? ['trace', trace] : ['job', entry.host, job])
    const previous = groups.get(base)
    if (!previous) {
      groups.set(base, [entry])
      continue
    }
    if (Date.parse(entry.ts_utc) - Date.parse(previous.at(-1)!.ts_utc) > 30 * 60 * 1000) {
      groups.set(JSON.stringify([base, previous[0].id]), previous)
      groups.set(base, [entry])
    } else previous.push(entry)
  }
  return [...groups.values()].map(logs => summarize(logs))
}

function summarize(logs: Entry[]): Process {
  const first = logs[0]
  const last = logs.at(-1)!
  const errors = logs.filter(badLevel)
  let start: Entry | undefined
  let terminal: Entry | undefined
  let reported: number | undefined
  let status: Process['status'] = 'Unklar'
  for (const entry of logs) {
    const state = entry.status?.trim().toLowerCase() ?? ''
    const scope = [entry.component, entry.workflow ?? '', entry.message].join(' ')
    if (!start && (['started', 'running', 'in_progress'].includes(state) || startSignal.test(entry.message))) start = entry
    if (typeof entry.job_duration_ms === 'number' && Number.isFinite(entry.job_duration_ms) && entry.job_duration_ms >= 0) reported = entry.job_duration_ms
    const recovered = recoverySignal.test(entry.message) || state === 'recovered'
    const failed = !recovered && (['failed', 'failure', 'aborted', 'cancelled', 'canceled'].includes(state) || (badLevel(entry) && failureSignal.test(entry.message)))
    const converter = /convert|konvert|nx_jt/i.test(entry.component)
    const finished = recovered || successSignal.test(entry.message) || (!converter && ['completed', 'success', 'succeeded', 'finished'].includes(state) && /workflow|job|publish|dispatch/i.test(scope))
    if (failed || finished) {
      terminal = entry
      status = failed ? 'Fehlgeschlagen' : recovered || errors.some(error => error.id !== entry.id && Date.parse(error.ts_utc) <= Date.parse(entry.ts_utc)) ? 'Erholt' : 'Erfolgreich'
    }
  }
  if (!terminal && start && !errors.length) status = 'Läuft'
  const calculated = start && terminal ? Date.parse(terminal.ts_utc) - Date.parse(start.ts_utc) : undefined
  const measured = calculated !== undefined && calculated >= 0 ? calculated : undefined
  const workflow = logs.find(entry => entry.workflow)?.workflow ?? ''
  const conversion = logs.some(entry => conversionSignal.test([entry.job_id, entry.component, entry.workflow, entry.message].join(' ').replace(/_/g, ' ')))
  return {
    key: String(first.id), job: logs.find(entry => entry.job_id)?.job_id ?? '', trace: first.trace_id,
    workflow, conversion, hosts: [...new Set(logs.map(entry => entry.host))],
    logs, status, start: start?.ts_utc, end: terminal?.ts_utc, duration: reported ?? measured,
    durationSource: reported !== undefined ? 'Auftrag' : measured !== undefined ? 'Start/Ende' : undefined,
    first: first.ts_utc, last: last.ts_utc, errors,
  }
}

