import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, NavLink, Route, Routes, useSearchParams } from 'react-router-dom'
import { MantineProvider, Drawer } from '@mantine/core'
import '@mantine/core/styles.css'
import './style.css'
import { chat, request } from './api'
import { demoAnswer, demoContext, entries, groups } from './demo'
import type { Answer, Entry, EventPage, Group, SourceContext, Stats } from './demo'
import { importZip, importedContext } from './import-zip'
import { ProcessMonitor } from './ProcessMonitor'
import { IncidentDetail } from './IncidentDetail'
import { buildProcesses } from './processes'
import type { ImportedLogs } from './import-zip'

type Mode = 'demo' | 'live' | 'import'
const offline = window.location.protocol === 'file:'
const formatTime = (timestamp: string) => timestamp.replace('T', ' ').replace(/(?:\.\d+)?Z$/, ' UTC')
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)

function useData<T>(path: string, mode: Mode, sample: T) {
  const [result, setResult] = useState<{ path: string; data?: T; error?: string }>()
  useEffect(() => {
    if (mode !== 'live') return
    const controller = new AbortController()
    setResult(undefined)
    request<T>(path, { signal: controller.signal }).then(
      data => setResult({ path, data }),
      error => { if (!controller.signal.aborted) setResult({ path, error: errorText(error) }) },
    )
    return () => controller.abort()
  }, [path, mode])
  if (mode !== 'live') return { data: sample, pending: false, error: undefined }
  const current = result?.path === path ? result : undefined
  return { ...current, pending: !current }
}

function Feedback({ pending, error }: { pending: boolean; error?: string }) {
  return error ? <p className="notice error" role="alert">{error}</p> : pending ? <p className="notice" role="status">Daten werden geladen …</p> : null
}

function Overview({ mode, logs, onImport, onViewImport, pending, importError, open }: { mode: Mode; logs: ImportedLogs | null; onImport: (file: File) => void; onViewImport: () => void; pending: boolean; importError: string; open: (id: number) => void }) {
  const localEvents = mode === 'import' && logs ? logs.entries : entries
  const processResult = useData<EventPage>('/events?limit=100&offset=0', mode, { items: localEvents, total: localEvents.length, limit: 100, offset: 0 })
  const processEvents = processResult.data?.items
  const sample: Stats = mode === 'import' && logs
    ? { sources: logs.sources.size, unique_sources: logs.sources.size, duplicate_sources: 0, duplicate_events: logs.duplicates, events: logs.entries.length, levels: { ERROR: logs.entries.filter(entry => entry.level === 'ERROR').length } }
    : { sources: new Set(entries.map(entry => entry.source)).size, unique_sources: new Set(entries.map(entry => entry.source)).size, duplicate_sources: 0, events: entries.length, levels: { ERROR: entries.filter(entry => entry.level === 'ERROR').length } }
  const result = useData<Stats>('/stats', mode, sample)
  const data = result.data
  return <>
    <Heading caption="LOG TRACER" title="Prozessüberwachung">Konvertierungsaufträge, Verarbeitungszeiten und Fehlerquellen über mehrere Systeme hinweg.</Heading>
    {mode === 'demo' && <p className="notice">Demo-Daten · Die Fälle zeigen den getrennten FMS-Fehler bei JOB-2003, die fehlende Baugruppenreferenz bei JOB-2010 und einen erfolgreichen Retry.</p>}
    <section className="panel upload">
      <h2>Log-ZIP hochladen</h2>
      <p>Wähle ein ZIP-Archiv mit Logdateien. Die Dateien bleiben in diesem Browser.</p>
      <label>ZIP-Datei auswählen<input type="file" accept=".zip,application/zip,application/x-zip-compressed" disabled={pending} onChange={event => {
        const file = event.currentTarget.files?.[0]
        event.currentTarget.value = ''
        if (file) onImport(file)
      }} /></label>
      {pending && <p role="status">ZIP wird eingelesen …</p>}
      {importError && <p className="notice error" role="alert">{importError}</p>}
      {logs && <div role="status"><p><strong>{logs.filename}</strong> · {logs.entries.length.toLocaleString('de-DE')} Ereignisse · {logs.sources.size} Quellen</p>
        {(logs.skipped > 0 || logs.unparsed > 0) && <p>{logs.skipped} Logdateien ohne neue lesbare Ereignisse · {logs.unparsed} Einträge nicht erkannt.</p>}
        <NavLink to="/timeline" onClick={() => onViewImport()}>Importierte Logs ansehen</NavLink></div>}
    </section>
    {mode !== 'live' && <ProcessMonitor key={mode === 'import' ? logs?.filename : mode} events={mode === 'import' && logs ? logs.entries : entries} open={open} />}
    <Feedback {...result} />
    {mode === 'live' && data && <div className="metrics">{[
      ['Logquellen', data.sources], ['Ereignisse', data.events], ['Fehlerereignisse', data.levels?.ERROR ?? 0], ['Doppelte Quellen', data.duplicate_sources ?? 0],
    ].map(([label, value]) => <section className="metric" key={label}><span>{label}</span><strong>{typeof value === 'number' ? value.toLocaleString('de-DE') : '—'}</strong></section>)}</div>}
    {mode === 'live' && <><Feedback {...processResult} />{processEvents && <>
      {processResult.data && processResult.data.total > processResult.data.limit && <p className="process-note">Die Übersicht gruppiert die erste Ereignisseite ({processResult.data.limit.toLocaleString('de-DE')} von {processResult.data.total.toLocaleString('de-DE')} Ereignissen). Für die vollständige Suche nutze die Zeitleiste.</p>}
      <ProcessMonitor key="live" events={processEvents} open={open} />
    </>}</>}
    <section className="panel"><h2>Untersuchung starten</h2><div className="shortcuts">
      <NavLink to="/timeline">Logs durchsuchen<span>Ereignisse nach System, Zeitraum und Job filtern</span></NavLink>
      <NavLink to="/groups">Fehlergruppen ansehen<span>Fehlgeschlagene Jobs und erfolgreiche Retries prüfen</span></NavLink>
      <NavLink to="/chat">Assistent öffnen<span>Eine Hypothese mit Logbelegen untersuchen</span></NavLink>
    </div></section>
  </>
}

function Heading({ caption, title, children }: React.PropsWithChildren<{ caption: string; title: string }>) {
  return <header className="heading"><span>{caption}</span><h1>{title}</h1><p>{children}</p></header>
}

const filters = [
  ['q', 'Textsuche', 'Meldung durchsuchen'], ['server', 'Server', 'z. B. cad-converter'], ['component', 'Komponente', 'z. B. nx_jt'],
  ['job_id', 'Job-ID', 'z. B. JT-4711'], ['trace_id', 'Trace-ID', 'z. B. demo-jt'], ['from', 'Von (UTC)', ''], ['to', 'Bis (UTC)', ''],
] as const

function Timeline({ mode, open, logs }: { mode: Mode; open: (id: number) => void; logs: ImportedLogs | null }) {
  const [params, update] = useSearchParams()
  const query = new URLSearchParams(params)
  const page = Math.max(1, Math.trunc(Number(params.get('page'))) || 1)
  function set(name: string, value: string) {
    const next = new URLSearchParams(params)
    if (name !== 'page') next.delete('page')
    if (value) next.set(name, value)
    else next.delete(name)
    update(next, { replace: true })
  }
  for (const field of ['from', 'to']) {
    const date = params.get(field)
    if (date && Number.isFinite(Date.parse(date + 'Z'))) query.set(field, new Date(date + 'Z').toISOString())
  }
  const localPageSize = 100
  const apiQuery = new URLSearchParams(query)
  if (mode === 'live') {
    apiQuery.delete('page')
    apiQuery.set('limit', String(localPageSize))
    apiQuery.set('offset', String((page - 1) * localPageSize))
  }
  const filtered = (mode === 'import' ? logs?.entries ?? [] : entries).filter(entry => {
    const exact: Record<string, string> = { server: entry.host, component: entry.component, job_id: entry.job_id, trace_id: entry.trace_id, level: entry.level }
    return Object.entries(exact).every(([key, value]) => value.toLowerCase().includes((params.get(key) ?? '').trim().toLowerCase()))
      && entry.message.toLowerCase().includes((params.get('q') ?? '').trim().toLowerCase())
      && (!query.has('from') || Date.parse(entry.ts_utc) >= Date.parse(query.get('from')!))
      && (!query.has('to') || Date.parse(entry.ts_utc) <= Date.parse(query.get('to')!))
  })
  const result = useData<Entry[] | EventPage>('/events?' + apiQuery, mode, filtered)
  const list = Array.isArray(result.data) ? result.data : result.data?.items
  const sorted = [...(list ?? [])].sort((a, b) => a.ts_utc.localeCompare(b.ts_utc))
  const visible = mode === 'live' ? sorted : sorted.slice((page - 1) * localPageSize, page * localPageSize)
  const hasNext = mode === 'live'
    ? result.data && !Array.isArray(result.data) && result.data.offset + result.data.items.length < result.data.total
    : page * localPageSize < sorted.length
  return <>
    <Heading caption="LOGS" title="Zeitleiste">Zeitlich sortierte Ereignisse mit Zugriff auf ihre Quelldatei.</Heading>
    <div className="panel filters">
      {filters.map(([name, label, placeholder]) => <label key={name}>{label}<input type={name === 'from' || name === 'to' ? 'datetime-local' : 'text'} placeholder={placeholder} value={params.get(name) ?? ''} onChange={e => set(name, e.target.value)} /></label>)}
      <label>Level<select value={params.get('level') ?? ''} onChange={e => set('level', e.target.value)}><option value="">Alle</option>{['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'].map(level => <option key={level}>{level}</option>)}</select></label>
      <button type="button" className="secondary" onClick={() => update({})} disabled={!params.size}>Filter zurücksetzen</button>
    </div>
    <Feedback {...result} />
    {list && <section className="panel">
      <h2>Logereignisse <small>{visible.length} auf dieser Seite</small></h2>
      {visible.length ? <div className="table"><table><thead><tr><th>Zeitpunkt</th><th>Level</th><th>Server / Komponente</th><th>Job</th><th>Meldung</th></tr></thead>
      <tbody>{visible.map(entry => <tr key={entry.id}>
        <td>{formatTime(entry.ts_utc)}</td><td><span className={'badge ' + entry.level.toLowerCase()}>{entry.level}</span></td><td>{entry.host}<small>{entry.component}</small></td><td>{entry.job_id || '—'}</td>
        <td><button className="link" onClick={() => open(entry.id)}>{entry.message}</button></td>
      </tr>)}</tbody></table></div> : <p>Keine Ereignisse für diese Filter.</p>}
      {(page > 1 || hasNext) && <div className="actions"><button disabled={page <= 1} onClick={() => set('page', String(page - 1))}>Zurück</button><span>Seite {page}</span><button disabled={!hasNext} onClick={() => set('page', String(page + 1))}>Weiter</button></div>}
    </section>}
  </>
}

function ErrorGroups({ mode, open }: { mode: Mode; open: (id: number) => void }) {
  const result = useData<Group[] | { items: Group[] }>('/analysis/groups', mode, mode === 'import' ? [] : groups)
  const list = Array.isArray(result.data) ? result.data : result.data?.items
  return <>
    <Heading caption="ANALYSE" title="Fehlergruppen">Zusammengehörige Meldungen und der Ausgang des Jobs.</Heading>
    <Feedback {...result} />
    {list?.length === 0 && <p className="notice">{mode === 'import' ? 'Die Fehlergruppen für importierte Logs werden im FastAPI-Backend berechnet. Hier kannst du die Einträge in der Zeitleiste prüfen.' : 'Keine Fehlergruppen vorhanden.'}</p>}
    {list?.map(group => <section className="panel" key={group.id}><div className="section-title"><h2>{group.label}</h2><span className={'badge ' + (group.status === 'recovered' ? 'info' : group.status === 'failed' ? 'error' : '')}>{({ recovered: 'Erholt', failed: 'Fehlgeschlagen' } as Record<string, string>)[group.status] ?? group.status}</span></div>
      <div className="actions">{group.event_ids?.map(id => <button className="secondary" key={id} onClick={() => open(id)}>Ereignis #{id}</button>)}</div></section>)}
  </>
}

function Assistant({ mode, open }: { mode: Mode; open: (id: number) => void }) {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<{ question: string; answer: Answer }[]>([])
  const [step, setStep] = useState('')
  const [error, setError] = useState('')
  const active = React.useRef<AbortController>()
  useEffect(() => () => active.current?.abort(), [])
  async function ask(prompt: string) {
    if (!prompt.trim() || active.current) return
    const controller = new AbortController()
    active.current = controller
    setError('')
    setStep('Logs werden durchsucht …')
    try {
      const answer = mode === 'demo' ? demoAnswer(prompt) : await chat(prompt, setStep, controller.signal)
      setHistory(previous => [...previous, { question: prompt, answer }])
      setQuestion('')
    } catch (error) {
      if (!controller.signal.aborted) setError(errorText(error))
    } finally {
      active.current = undefined
      setStep('')
    }
  }
  return <>
    <Heading caption="ASSISTENT" title="Ursachen untersuchen">{mode === 'demo' ? 'Frage nach Ursache, Belegen, Unsicherheit und nächsten Prüfschritten.' : 'Stelle eine Frage zu den importierten Logs.'}</Heading>
    <div className="actions">{['Warum wurde JOB-2003 nicht veröffentlicht?', 'Warum ist JOB-2010 abgebrochen?', 'Hat sich SYNC-312 nach dem Timeout erholt?'].map(prompt => <button type="button" key={prompt} className="secondary" disabled={!!step} onClick={() => void ask(prompt)}>{prompt}</button>)}</div>
    {history.map(({ question: asked, answer }, index) => <article className="panel answer" key={index}>
      <p className="question">{asked}</p><h2>Hypothese</h2><p>{answer.summary}</p>
      <h3>Kausalkette</h3><ol>{answer.causal_chain.map(item => <li key={item.step}><strong>{item.server}</strong> · {item.text}</li>)}</ol>
      <h3>Logbelege</h3><div className="evidence">{answer.evidence.map((item, index) => <button key={index} className="secondary" onClick={() => open(item.event_id)} title={item.file}>{item.file.split('/').at(-1)}:{item.line} <small>{formatTime(item.ts)}</small></button>)}</div>
      <h3>Unsicherheit{typeof answer.confidence === 'number' ? ' · Konfidenz ' + Math.round(answer.confidence * 100) + ' %' : ''}</h3><p>{answer.uncertainty}</p>
      {!!answer.counter_evidence?.length && <><h3>Gegenbelege</h3><ul>{answer.counter_evidence.map(text => <li key={text}>{text}</li>)}</ul></>}
      <h3>Prüfschritte</h3><ul>{answer.verification_steps.map(text => <li key={text}>{text}</li>)}</ul>
    </article>)}
    <Feedback pending={false} error={error} />
    {step && <p className="notice" role="status">{step}</p>}
    <form className="panel composer" onSubmit={event => { event.preventDefault(); void ask(question) }}>
      <label>Frage zu den Logs<input value={question} onChange={event => setQuestion(event.target.value)} placeholder="z. B. Warum ist dieser Job fehlgeschlagen?" /></label>
      <button disabled={!question.trim() || !!step}>Frage stellen</button>
    </form>
  </>
}

function Source({ id, mode, logs }: { id: number; mode: Mode; logs: ImportedLogs | null }) {
  const entry = entries.find(item => item.id === id)
  const result = useData<SourceContext | undefined>('/events/' + id + '/context?n=10', mode, mode === 'import' && logs ? importedContext(logs, id) : entry ? demoContext(entry) : undefined)
  return <><Feedback {...result} />{result.data && <><p className="filepath">{result.data.path}</p><div className="source">{result.data.lines.map(line => <div key={line.line} className={line.line >= result.data!.line_start && line.line <= result.data!.line_end ? 'selected-line' : ''}><span>{line.line}</span><code>{line.text}</code></div>)}</div></>}</>
}

function EventDetail({ id, mode, logs, open }: { id: number; mode: Mode; logs: ImportedLogs | null; open: (id: number) => void }) {
  const local = mode === 'import' ? logs?.entries : entries
  const context = useData<Entry | undefined>('/events/' + id, mode, undefined)
  const localProcesses = React.useMemo(() => mode === 'live' ? [] : buildProcesses(local ?? []), [local, mode])
  const localProcess = localProcesses.find(process => process.logs.some(entry => entry.id === id))
  const selected = mode === 'live' ? context.data : localProcess?.logs.find(entry => entry.id === id) ?? local?.find(entry => entry.id === id)
  const trace = selected?.trace_id
  const timelinePath = trace ? '/trace/' + encodeURIComponent(trace) : ''
  const live = useData<Entry[] | { items: Entry[] } | undefined>(timelinePath, timelinePath && mode === 'live' ? 'live' : 'demo', undefined)
  const records = Array.isArray(live.data) ? live.data : live.data?.items
  const liveProcess = selected && records?.length
    ? buildProcesses(records.some(entry => entry.id === selected.id) ? records : [...records, selected]).find(process => process.logs.some(entry => entry.id === id))
    : undefined
  const original = <Source key={id} id={id} mode={mode} logs={logs} />
  if (!selected) return <><Feedback {...context} />{original}</>
  return <>
    {mode === 'live' && <Feedback {...live} />}
    <IncidentDetail selected={selected} process={mode === 'live' ? liveProcess : localProcess} onSelect={open}>{original}</IncidentDetail>
  </>
}

function App() {
  const [mode, setMode] = useState<Mode>(offline ? 'demo' : 'live')
  const [logs, setLogs] = useState<ImportedLogs | null>(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  async function loadLogs(file: File) {
    setImporting(true)
    setImportError('')
    try {
      const imported = await importZip(file)
      setLogs(imported)
      switchMode('import')
    } catch (error) {
      setImportError(errorText(error))
    } finally {
      setImporting(false)
    }
  }
  const [id, setId] = useState<number | null>(null)
  const [health, setHealth] = useState(offline ? 'Offline-Demo' : 'Backend wird geprüft …')
  const [check, setCheck] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    if (offline) return
    setHealth('Backend wird geprüft …')
    const timeout = setTimeout(() => { setHealth('Backend nicht erreichbar'); controller.abort() }, 3500)
    request<{ status?: string; version?: string; log_root_found?: boolean; db_found?: boolean }>('/health', { signal: controller.signal }).then(
      data => setHealth(data.status && data.status !== 'ok'
        ? 'Backend meldet: ' + data.status
        : 'Backend erreichbar · Logs ' + (data.log_root_found ? 'bereit' : 'nicht gefunden') + ' · Datenbank ' + (data.db_found ? 'bereit' : 'nicht gefunden')),
      () => { if (!controller.signal.aborted) setHealth('Backend nicht erreichbar') },
    ).finally(() => clearTimeout(timeout))
    return () => { clearTimeout(timeout); controller.abort() }
  }, [check])
  function switchMode(next: Mode) { setId(null); setMode(next); if (next === 'live') setCheck(value => value + 1) }
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon" aria-hidden="true">⌁</span><div>Log Tracer<small>MAIT MAKEATHON</small></div></div>
      <nav aria-label="Hauptnavigation"><NavLink to="/" end>Prozessüberwachung</NavLink><NavLink to="/timeline">Zeitleiste</NavLink><NavLink to="/groups">Fehlergruppen</NavLink><NavLink to="/chat">Assistent</NavLink></nav>
    </aside>
    <div className="workspace">
      <div className="topbar"><button className="health secondary" disabled={offline} onClick={() => setCheck(value => value + 1)} title="Backend erneut prüfen" aria-live="polite">{health}</button>
        <div className="modes" role="group" aria-label="Datenquelle"><button aria-pressed={mode === 'demo'} onClick={() => switchMode('demo')}>Demo</button>{logs && <button aria-pressed={mode === 'import'} onClick={() => switchMode('import')}>ZIP-Import</button>}<button aria-pressed={mode === 'live'} disabled={offline} onClick={() => switchMode('live')}>Live</button></div></div>
      <main><Routes><Route path="/" element={<Overview mode={mode} logs={logs} onImport={file => void loadLogs(file)} onViewImport={() => switchMode('import')} pending={importing} importError={importError} open={setId} />} /><Route path="/timeline" element={<Timeline mode={mode} open={setId} logs={logs} />} /><Route path="/groups" element={<ErrorGroups mode={mode} open={setId} />} /><Route path="/chat" element={mode === 'import' ? <p className="notice">Der Assistent analysiert lokale ZIP-Imports nicht. Für eine KI-Analyse importiere die Logs im Team-Backend und wechsle in den Live-Modus.</p> : <Assistant key={mode} mode={mode} open={setId} />} /><Route path="*" element={<p className="notice">Seite nicht gefunden. <NavLink to="/">Zur Prozessüberwachung</NavLink></p>} /></Routes></main>
    </div>
    <Drawer opened={id !== null} onClose={() => setId(null)} position="right" size="min(1150px, 100%)" title={'Meldungsdetails · Ereignis #' + id}>{id !== null && <EventDetail id={id} mode={mode} logs={logs} open={setId} />}</Drawer>
  </div>
}

createRoot(document.getElementById('root')!).render(<MantineProvider><HashRouter><App /></HashRouter></MantineProvider>)





