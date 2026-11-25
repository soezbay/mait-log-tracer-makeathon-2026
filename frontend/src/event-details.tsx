import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { Modal } from '@mantine/core'
import { Link } from 'react-router-dom'
import { Feedback, firstLine, formatTime, useData } from './data'
import type { Mode } from './data'
import { demoContext, entries } from './demo'
import type { Entry, EventPage, SourceContext } from './demo'
import { useI18n } from './i18n'
import { importedContext } from './import-zip'
import type { ImportedLogs } from './import-zip'
import { IncidentDetail } from './IncidentDetail'
import { EventIncident } from './incidents'
import { buildProcesses } from './processes'
import { EventQuestions } from './suggestions'
import { InfoTip, LevelBadge } from './ui'

type ViewProps = { id: number; mode: Mode; logs: ImportedLogs | null; open: (id: number) => void; close: () => void }

const CHAIN_GAP_MS = 30 * 60 * 1000 // a longer pause means another run with the same ID

/** Details of one log entry. Uses almost the whole window but stays a dialog (Esc closes it). */
export function EventModal({ id, ...props }: Omit<ViewProps, 'id'> & { id: number | null }) {
  const { t } = useI18n()
  return <Modal opened={id !== null} onClose={props.close} size="100%" xOffset="1.25rem" yOffset="1.25rem" radius="md" padding={0}
    title={t('details.title', { id: id ?? '' })} closeButtonProps={{ 'aria-label': t('details.close') }}
    classNames={{ content: 'event-modal', header: 'event-modal-header', body: 'event-modal-body' }}>
    {id !== null && <EventView key={id} id={id} {...props} />}
  </Modal>
}

function Source({ id, mode, logs }: { id: number; mode: Mode; logs: ImportedLogs | null }) {
  const { t } = useI18n()
  const [lines, setLines] = useState(10)
  const entry = entries.find(item => item.id === id)
  const result = useData<SourceContext | undefined>('/events/' + id + '/context?n=' + lines, mode, mode === 'import' && logs ? importedContext(logs, id) : entry ? demoContext(entry) : undefined)
  return <section className="event-source">
    <div className="section-title"><h3>{t('incident.originalLog')} <InfoTip text={t('details.sourceInfo')} /></h3>
      {mode === 'live' && <label className="inline-label">{t('details.lines')}<select value={lines} onChange={event => setLines(Number(event.target.value))}>{[5, 10, 25, 50].map(count => <option key={count} value={count}>± {count}</option>)}</select></label>}</div>
    <Feedback {...result} />
    {result.data && <><p className="filepath">{result.data.path}</p><div className="source">{result.data.lines.map(line => <div key={line.line} className={line.line >= result.data!.line_start && line.line <= result.data!.line_end ? 'selected-line' : ''}><span>{line.line}</span><code>{line.text}</code></div>)}</div></>}
  </section>
}

function Facts({ entry, close }: { entry: Entry; close: () => void }) {
  const { t } = useI18n()
  const meta = entry.meta
  const timeline = (field: string, value: string) => <Link to={'/timeline?' + new URLSearchParams({ [field]: value })} onClick={close}>{value}</Link>
  const facts: [string, ReactNode][] = [[t('events.timestamp'), formatTime(entry.ts_utc)]]
  if (meta?.clock_offset_s) facts.push([t('details.clock'), t('incidents.clockCorrected', { seconds: meta.clock_offset_s })])
  if (meta?.ts_raw && (meta.clock_offset_s || meta.tz_assumed)) facts.push([t('details.originalTime'), meta.ts_raw + (meta.tz_assumed ? ' · ' + t('details.zoneAssumed') : '')])
  facts.push([t('filter.server'), timeline('server', entry.host)], [t('filter.component'), entry.component || '—'])
  if (entry.job_id) facts.push([t('filter.job'), timeline('job_id', entry.job_id)])
  if (entry.trace_id) facts.push([t('filter.trace'), timeline('trace_id', entry.trace_id)])
  if (meta?.event_id) facts.push([t('details.eventId'), meta.event_id])
  if (meta?.session_id) facts.push([t('details.session'), meta.session_id])
  if (entry.source) facts.push([t('details.file'), <>{entry.source}{entry.source_line !== undefined && ':' + entry.source_line + (entry.source_line_end !== undefined && entry.source_line_end !== entry.source_line ? '–' + entry.source_line_end : '')}{meta?.format && <small>{meta.format}{meta.encoding ? ' · ' + meta.encoding : ''}</small>}</>])
  const notes = [meta?.duplicate_of && t('details.duplicate', { id: meta.duplicate_of }), meta?.is_late && t('details.late'), meta?.parse_error && t('details.unparsed', { error: meta.parse_error })].filter(Boolean)
  const attributes = Object.entries(meta?.attrs ?? {}).filter(([, value]) => value !== null && value !== '')
  return <section className="event-card"><h3>{t('details.facts')}</h3>
    <dl className="facts">{facts.map(([label, value]) => [<dt key={label}>{label}</dt>, <dd key={label + '-value'}>{value}</dd>])}</dl>
    {notes.map(note => <p className="notice" key={String(note)}>{note}</p>)}
    {attributes.length > 0 && <><h3>{t('details.attributes')}</h3><dl className="facts">{attributes.map(([key, value]) => [<dt key={key}>{key}</dt>, <dd key={key + '-value'}>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd>])}</dl></>}
  </section>
}

/** The records around the selected one without a longer pause, in time order. */
function chainAround(records: Entry[], selected: Entry) {
  const sorted = [...records.filter(entry => entry.id !== selected.id), selected].sort((a, b) => Date.parse(a.ts_utc) - Date.parse(b.ts_utc) || a.id - b.id)
  const at = sorted.findIndex(entry => entry.id === selected.id)
  const pause = (index: number) => Date.parse(sorted[index].ts_utc) - Date.parse(sorted[index - 1].ts_utc) > CHAIN_GAP_MS
  let first = at, last = at
  while (first > 0 && !pause(first)) first--
  while (last < sorted.length - 1 && !pause(last + 1)) last++
  return sorted.slice(first, last + 1)
}

function EventView({ id, mode, logs, open, close }: ViewProps) {
  const { t } = useI18n()
  const local = mode === 'import' ? logs?.entries : entries
  const result = useData<Entry | undefined>('/events/' + id, mode, undefined)
  const localProcess = useMemo(() => mode === 'live' ? undefined : buildProcesses(local ?? []).find(process => process.logs.some(entry => entry.id === id)), [local, mode, id])
  const selected = mode === 'live' ? result.data : localProcess?.logs.find(entry => entry.id === id) ?? local?.find(entry => entry.id === id)
  const key = mode === 'live' ? selected?.trace_id || selected?.job_id || '' : ''
  const trace = useData<Entry[] | EventPage | undefined>('/trace/' + encodeURIComponent(key), key ? 'live' : 'demo', undefined)
  const records = Array.isArray(trace.data) ? trace.data : trace.data?.items
  const chain = useMemo(() => mode === 'live'
    ? selected && records ? { logs: chainAround(records, selected), trace: selected.trace_id, job: selected.job_id, acrossServers: true } : undefined
    : localProcess, [mode, selected, records, localProcess])
  const source = <Source id={id} mode={mode} logs={logs} />
  if (!selected) return <div className="event-view"><Feedback {...result} />{mode !== 'live' && source}</div>
  const events = chain?.logs ?? [selected]
  const at = events.findIndex(entry => entry.id === id)
  const [title, ...rest] = [firstLine(selected.message), selected.message.slice(firstLine(selected.message).length).trim()]
  return <div className="event-view">
    <header className="event-head">
      <div><p><LevelBadge level={selected.level} /> <span>{formatTime(selected.ts_utc)}</span> · <span>{selected.host}</span>{selected.component && <> · <span>{selected.component}</span></>}{selected.job_id && <> · <span>{selected.job_id}</span></>}</p>
        <h2>{title}</h2>{rest[0] && <pre>{rest[0]}</pre>}</div>
      {events.length > 1 && <div className="event-steps"><button type="button" className="secondary" disabled={at <= 0} onClick={() => open(events[at - 1].id)} aria-label={t('details.previous')} title={t('details.previous')}>←</button>
        <span>{at + 1} / {events.length}</span>
        <button type="button" className="secondary" disabled={at >= events.length - 1} onClick={() => open(events[at + 1].id)} aria-label={t('details.next')} title={t('details.next')}>→</button></div>}
    </header>
    <div className="event-columns">
      <div className="event-main">{key && !records && <Feedback pending={trace.pending} error={trace.error} />}
        <IncidentDetail selected={selected} process={chain} onSelect={open}>{source}</IncidentDetail></div>
      <aside className="event-side">
        {mode === 'live' && <EventIncident eventId={id} close={close} />}
        <Facts entry={selected} close={close} />
        <EventQuestions id={id} />
      </aside>
    </div>
  </div>
}
