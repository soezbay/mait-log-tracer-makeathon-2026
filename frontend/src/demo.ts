import type { Language } from './i18n'

export type Entry = {
  id: number
  ts_utc: string
  host: string
  component: string
  level: string
  job_id: string
  trace_id: string
  message: string
  workflow?: string
  status?: string
  job_duration_ms?: number
  source?: string
  source_line?: number
  source_line_end?: number
  is_duplicate?: boolean
  meta?: EntryMeta
}
/** Further fields of GET /api/events/{id}. */
export type EntryMeta = { event_id: string | null; session_id: string | null; ts_raw: string | null; tz_assumed: boolean; clock_offset_s: number; duplicate_of: number | null; is_late: boolean; parse_error: string | null; format: string | null; encoding: string | null; attrs: Record<string, unknown> }
export type Group = { id: number; label: string; status: string; event_ids: number[] }
export type EventPage = { items: Entry[]; total: number; limit: number; offset: number }
export type Stats = { servers?: number; sources: number; unique_sources?: number; duplicate_sources?: number; duplicate_events?: number; events: number; unparsed_events?: number; levels: Record<string, number>; time_range?: { from: string; to: string }; last_ingest_at?: string | null }
export type Answer = { reply?: string; summary: string; causal_chain: { step: number; server: string; text: string }[]; affected_systems: string[]; evidence: { event_id: number; file: string; line: number; ts: string }[]; confidence?: number; uncertainty: string; counter_evidence?: string[]; verification_steps: string[] }
export type SourceContext = { path: string; lines: { line: number; text: string }[]; line_start: number; line_end: number }

// The examples mirror the separate challenge cases documented for 24 Nov.
// JOB-2003 is an FMS permission failure after a successful conversion;
// JOB-2010 is an unrelated missing assembly reference.
export const entries: Entry[] = [
  { id: 1, ts_utc: '2026-11-24T08:29:55Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/workflow', level: 'INFO', job_id: 'JOB-2003', trace_id: 'trace-2003', workflow: 'NX → JT · Publish', message: 'Publish workflow started; target=DEMO-301.jt', source: 'mait_linux1_teamcenter_app/logs/teamcenter/workflow/creative_job2003.jsonl', source_line: 87 },
  { id: 2, ts_utc: '2026-11-24T08:30:00Z', host: 'mait_win03_cad_converter', component: 'converter/nx_jt', level: 'INFO', job_id: 'JOB-2003', trace_id: 'trace-2003', workflow: 'NX → JT · Publish', message: 'Conversion succeeded; JT output=DEMO-301.jt', source: 'mait_win03_cad_converter/logs/converter/nx_jt/creative_job2003.csv', source_line: 5 },
  { id: 3, ts_utc: '2026-11-24T08:30:08Z', host: 'mait_linux1_teamcenter_app', component: 'fms/fsc', level: 'ERROR', job_id: 'JOB-2003', trace_id: 'trace-2003', workflow: 'NX → JT · Publish', message: 'Upload rejected; access policy lacks target volume write permission', source: 'mait_linux1_teamcenter_app/logs/teamcenter/fms/creative_job2003.txt', source_line: 22 },
  { id: 4, ts_utc: '2026-11-24T08:30:12Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/workflow', level: 'ERROR', job_id: 'JOB-2003', trace_id: 'trace-2003', workflow: 'NX → JT · Publish', message: 'Publish task failed: no registered result; converter status=SUCCESS', source: 'mait_linux1_teamcenter_app/logs/teamcenter/workflow/creative_job2003.jsonl', source_line: 88 },
  { id: 5, ts_utc: '2026-11-24T11:00:56Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/workflow', level: 'INFO', job_id: 'JOB-2010', trace_id: 'trace-2010', workflow: 'NX → JT · Baugruppe', message: 'Workflow started for DEMO-Seal-17/C', source: 'mait_linux1_teamcenter_app/logs/teamcenter/workflow/creative_job2010.jsonl', source_line: 103 },
  { id: 6, ts_utc: '2026-11-24T11:00:58Z', host: 'mait_win03_cad_converter', component: 'nx/batch', level: 'ERROR', job_id: 'JOB-2010', trace_id: 'trace-2010', workflow: 'NX → JT · Baugruppe', message: 'Required child DEMO-Seal-17/C not resolved', source: 'mait_win03_cad_converter/logs/nx/batch/creative_job2010.log', source_line: 316 },
  { id: 7, ts_utc: '2026-11-24T11:00:59Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/soa', level: 'ERROR', job_id: 'JOB-2010', trace_id: 'trace-2010', workflow: 'NX → JT · Baugruppe', message: 'Reference target absent from exported input package', source: 'mait_linux1_teamcenter_app/logs/teamcenter/soa/creative_job2010.log', source_line: 53 },
  { id: 8, ts_utc: '2026-11-24T11:01:01Z', host: 'mait_win03_cad_converter', component: 'converter/nx_jt', level: 'ERROR', job_id: 'JOB-2010', trace_id: 'trace-2010', workflow: 'NX → JT · Baugruppe', message: 'Export aborted because required reference is missing\nCaused by: com.teamcenter.soa.strong.ReferenceNotFoundException: DEMO-Seal-17/C\n    at com.mait.nx.Export.run(Export.java:218)', source: 'mait_win03_cad_converter/logs/converter/nx_jt/creative_job2010.log', source_line: 317, source_line_end: 319 },
  { id: 9, ts_utc: '2026-11-24T11:03:18Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/sync', level: 'ERROR', job_id: 'SYNC-312', trace_id: 'trace-sync-312', workflow: 'PLM-Synchronisation', message: 'Downstream timeout; retry scheduled', source: 'mait_linux1_teamcenter_app/logs/teamcenter/sync/creative_sync.jsonl', source_line: 41 },
  { id: 10, ts_utc: '2026-11-24T11:03:22Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/sync', level: 'ERROR', job_id: 'SYNC-312', trace_id: 'trace-sync-312', workflow: 'PLM-Synchronisation', message: 'Transient retry recovered', source: 'mait_linux1_teamcenter_app/logs/teamcenter/sync/creative_sync.jsonl', source_line: 42 },
  { id: 11, ts_utc: '2026-11-24T11:03:23Z', host: 'mait_linux1_teamcenter_app', component: 'teamcenter/sync', level: 'INFO', job_id: 'SYNC-312', trace_id: 'trace-sync-312', workflow: 'PLM-Synchronisation', message: 'Retry succeeded after 4 s', source: 'mait_linux1_teamcenter_app/logs/teamcenter/sync/creative_sync.jsonl', source_line: 43 },
]

export const groups: Group[] = [
  { id: 1, label: 'JOB-2003 · FMS-Volume-Schreibrecht', status: 'failed', event_ids: [1, 2, 3, 4] },
  { id: 2, label: 'JOB-2010 · Baugruppenreferenz fehlt', status: 'failed', event_ids: [5, 6, 7, 8] },
  { id: 3, label: 'SYNC-312 · Retry erfolgreich', status: 'recovered', event_ids: [9, 10, 11] },
]

export function demoContext(entry: Entry): SourceContext {
  const path = entry.source ?? `${entry.host}/logs/${entry.component}/demo.log`
  const source = entries.filter(item => item.source === path)
  const lines = source.map(item => ({
    line: item.source_line ?? source.indexOf(item) + 1,
    text: [item.ts_utc, item.level, item.job_id, item.message].join(' '),
  })).sort((a, b) => a.line - b.line)
  const line = entry.source_line ?? source.findIndex(item => item.id === entry.id) + 1
  return { path, line_start: line, line_end: entry.source_line_end ?? line, lines }
}

export function demoAnswer(question: string, language: Language = 'en'): Answer {
  const sync = /retry|timeout|sync|erholt/i.test(question)
  const reference = !sync && /2010|seal|referenz|assembly|baugruppe/i.test(question)
  const selected = sync ? entries.slice(8) : reference ? entries.slice(4, 8) : entries.slice(0, 4)
  const answers = language === 'en'
    ? sync
      ? {
        summary: 'The sync job recovered after the downstream timeout. The following events confirm a successful retry.',
        uncertainty: 'The timeout is documented, but the available lines do not show what delayed the downstream service.',
        verification_steps: ['Check the downstream dependency latency and availability around 11:03 UTC.', 'Check whether other jobs were affected during the same period.'],
        counter_evidence: ['Two messages have ERROR level, but the later retry message confirms recovery.'],
        confidence: 0.9,
      }
      : reference
        ? {
          summary: 'The logs point to a missing assembly reference: DEMO-Seal-17/C could not be resolved or found in the export package, so the NX/JT export stopped.',
          uncertainty: 'The logs confirm the missing reference, but do not show why DEMO-Seal-17/C is absent from the export package.',
          verification_steps: ['Check the assembly structure and whether DEMO-Seal-17/C exists in Teamcenter.', 'Check the export package and reference resolution before the NX/JT run.'],
          counter_evidence: [],
          confidence: 0.86,
        }
        : {
          summary: 'The logs point to missing write permission on the FMS target volume. The converter created the JT file successfully, but the upload was rejected, so the publish workflow could not register a result.',
          uncertainty: 'The rejection identifies missing write permission, but not the affected service account or access policy.',
          verification_steps: ['Check the FMS access policy and the service account write permission for the target volume.', 'Check whether DEMO-301.jt is present on the target volume and registered in the workflow.'],
          counter_evidence: ['The converter reports SUCCESS. That status applies to conversion and does not contradict the later FMS upload failure.'],
          confidence: 0.91,
        }
    : sync
      ? {
        summary: 'Der Sync-Job hat sich nach dem Downstream-Timeout erholt. Die Folgeeinträge belegen einen erfolgreichen Retry.',
        uncertainty: 'Der Timeout ist dokumentiert, aber die verfügbaren Zeilen zeigen nicht, wodurch der Downstream verzögert wurde.',
        verification_steps: ['Latenz und Verfügbarkeit der Downstream-Abhängigkeit um 11:03 UTC prüfen.', 'Kontrollieren, ob weitere Jobs im selben Zeitraum betroffen waren.'],
        counter_evidence: ['Zwei Meldungen haben ERROR-Level; die spätere Retry-Meldung belegt trotzdem die Erholung.'],
        confidence: 0.9,
      }
      : reference
        ? {
          summary: 'Die Logs sprechen für eine fehlende Baugruppenreferenz: DEMO-Seal-17/C wurde nicht aufgelöst, im Exportpaket nicht gefunden und der NX/JT-Export deshalb abgebrochen.',
          uncertainty: 'Die Protokolle belegen den fehlenden Verweis, aber nicht, warum DEMO-Seal-17/C im Exportpaket fehlt.',
          verification_steps: ['Baugruppenstruktur und Existenz von DEMO-Seal-17/C in Teamcenter prüfen.', 'Exportpaket und Referenzauflösung vor dem NX/JT-Lauf kontrollieren.'],
          counter_evidence: [],
          confidence: 0.86,
        }
        : {
          summary: 'Die Logs sprechen für fehlendes Schreibrecht auf dem FMS-Zielvolume. Der Konverter erzeugte die JT-Datei erfolgreich; der Upload wurde anschließend abgewiesen, sodass der Publish-Workflow kein Ergebnis registrieren konnte.',
          uncertainty: 'Die Ablehnung nennt das fehlende Schreibrecht, aber nicht das betroffene Dienstkonto oder die maßgebliche Zugriffsrichtlinie.',
          verification_steps: ['FMS-Zugriffsrichtlinie und Schreibrecht des ausführenden Dienstkontos für das Zielvolume prüfen.', 'Kontrollieren, ob DEMO-301.jt nach dem fehlgeschlagenen Upload im Zielvolume liegt und im Workflow registriert wurde.'],
          counter_evidence: ['Der Konverter meldet SUCCESS. Dieser Status betrifft die Konvertierung und widerspricht nicht dem späteren FMS-Upload-Fehler.'],
          confidence: 0.91,
        }
  return {
    ...answers,
    causal_chain: selected.map((item, index) => ({ step: index + 1, server: item.host, text: item.message })),
    affected_systems: [...new Set(selected.map(item => item.host))],
    evidence: selected.map(item => {
      const context = demoContext(item)
      return { event_id: item.id, file: context.path, line: context.line_start, ts: item.ts_utc }
    }),
  }
}
