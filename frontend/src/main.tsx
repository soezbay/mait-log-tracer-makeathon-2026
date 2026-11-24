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
import { I18nProvider, useI18n } from './i18n'
import { browserTimeZone, currentLocalDateTime, isValidDateTimeLocal, localDateTimeToUtcIso, utcDateTimeToEpoch, utcDateTimeToLocal } from './time'

type Mode = 'demo' | 'live' | 'import'
const offline = window.location.protocol === 'file:'
const formatTime = (timestamp: string) => timestamp.replace('T', ' ').replace(/(?:\.\d+)?Z$/, ' UTC')
const errorText = (error: unknown) => error instanceof Error ? error.message : String(error)
type AssistantTarget = { question: string; jobIds: string[] }

function assistantTarget(question: string): AssistantTarget {
  const normalized = question.trim().replace(/\s+/g, ' ').toLowerCase()
  const jobIds = [...new Set((normalized.match(/\b[a-z][a-z0-9]*[-_ ]\d+[a-z0-9._-]*\b/g) ?? []).map(id => id.replace(/[\s_]+/g, '-')))]
  return { question: normalized, jobIds }
}

function sameAssistantTarget(first: AssistantTarget, second: AssistantTarget) {
  return first.question === second.question || first.jobIds.some(id => second.jobIds.includes(id))
}

function useData<T>(path: string, mode: Mode, sample: T) {
  const { language } = useI18n()
  const [result, setResult] = useState<{ path: string; data?: T; error?: string }>()
  useEffect(() => {
    if (mode !== 'live') return
    const controller = new AbortController()
    setResult(undefined)
    request<T>(path, { signal: controller.signal }, language).then(
      data => setResult({ path, data }),
      error => { if (!controller.signal.aborted) setResult({ path, error: errorText(error) }) },
    )
    return () => controller.abort()
  }, [path, mode, language])
  if (mode !== 'live') return { data: sample, pending: false, error: undefined }
  const current = result?.path === path ? result : undefined
  return { ...current, pending: !current }
}

function Feedback({ pending, error }: { pending: boolean; error?: string }) {
  const { t } = useI18n()
  return error ? <p className="notice error" role="alert">{error}</p> : pending ? <p className="notice" role="status">{t('loading.data')}</p> : null
}

function Overview({ mode, logs, onImport, onViewImport, pending, importError, open }: { mode: Mode; logs: ImportedLogs | null; onImport: (file: File) => void; onViewImport: () => void; pending: boolean; importError: string; open: (id: number) => void }) {
  const { language, t } = useI18n()
  const fileInput = React.useRef<HTMLInputElement>(null)
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const localEvents = mode === 'import' && logs ? logs.entries : entries
  const processResult = useData<EventPage>('/events?limit=100&offset=0', mode, { items: localEvents, total: localEvents.length, limit: 100, offset: 0 })
  const processEvents = processResult.data?.items
  const sample: Stats = mode === 'import' && logs
    ? { sources: logs.sources.size, unique_sources: logs.sources.size, duplicate_sources: 0, duplicate_events: logs.duplicates, events: logs.entries.length, levels: { ERROR: logs.entries.filter(entry => entry.level === 'ERROR').length } }
    : { sources: new Set(entries.map(entry => entry.source)).size, unique_sources: new Set(entries.map(entry => entry.source)).size, duplicate_sources: 0, events: entries.length, levels: { ERROR: entries.filter(entry => entry.level === 'ERROR').length } }
  const result = useData<Stats>('/stats', mode, sample)
  const data = result.data
  return <>
    <Heading caption={t('overview.caption')} title={t('overview.title')}>{t('overview.description')}</Heading>
    {mode === 'demo' && <p className="notice">{t('overview.demoNote')}</p>}
    <section className="panel upload">
      <h2>{t('upload.title')}</h2>
      <p>{t('upload.description')}</p>
      <div className="file-picker">
        <button type="button" className="secondary" disabled={pending} onClick={() => fileInput.current?.click()}>{t('upload.select')}</button>
        <input ref={fileInput} type="file" aria-label={t('upload.select')} tabIndex={-1} accept=".zip,application/zip,application/x-zip-compressed" disabled={pending} onChange={event => {
          const file = event.currentTarget.files?.[0]
          event.currentTarget.value = ''
          if (file) onImport(file)
        }} />
      </div>
      {pending && <p role="status">{t('upload.reading')}</p>}
      {importError && <p className="notice error" role="alert">{importError}</p>}
      {logs && <div role="status"><p><strong>{logs.filename}</strong> · {t('upload.filesSummary', { events: logs.entries.length.toLocaleString(locale), sources: logs.sources.size.toLocaleString(locale) })}</p>
        {(logs.skipped > 0 || logs.unparsed > 0) && <p>{t('upload.skippedSummary', { skipped: logs.skipped.toLocaleString(locale), unparsed: logs.unparsed.toLocaleString(locale) })}</p>}
        <NavLink to="/timeline" onClick={() => onViewImport()}>{t('upload.view')}</NavLink></div>}
    </section>
    {mode !== 'live' && <ProcessMonitor key={mode === 'import' ? logs?.filename : mode} events={mode === 'import' && logs ? logs.entries : entries} open={open} />}
    <Feedback {...result} />
    {mode === 'live' && data && <div className="metrics">{[
      [t('metric.sources'), data.sources], [t('metric.events'), data.events], [t('metric.errors'), data.levels?.ERROR ?? 0], [t('metric.duplicates'), data.duplicate_sources ?? 0],
    ].map(([label, value]) => <section className="metric" key={label}><span>{label}</span><strong>{typeof value === 'number' ? value.toLocaleString(locale) : '—'}</strong></section>)}</div>}
    {mode === 'live' && <><Feedback {...processResult} />{processEvents && <>
      {processResult.data && processResult.data.total > processResult.data.limit && <p className="process-note">{t('overview.firstPage', { shown: processResult.data.limit.toLocaleString(locale), total: processResult.data.total.toLocaleString(locale) })}</p>}
      <ProcessMonitor key="live" events={processEvents} open={open} />
    </>}</>}
    <section className="panel"><h2>{t('overview.start')}</h2><div className="shortcuts">
      <NavLink to="/timeline">{t('overview.search')}<span>{t('overview.searchDescription')}</span></NavLink>
      <NavLink to="/groups">{t('overview.groups')}<span>{t('overview.groupsDescription')}</span></NavLink>
      <NavLink to="/chat">{t('overview.assistant')}<span>{t('overview.assistantDescription')}</span></NavLink>
    </div></section>
  </>
}

function Heading({ caption, title, children }: React.PropsWithChildren<{ caption: string; title: string }>) {
  return <header className="heading"><span>{caption}</span><h1>{title}</h1><p>{children}</p></header>
}

function Timeline({ mode, open, logs }: { mode: Mode; open: (id: number) => void; logs: ImportedLogs | null }) {
  const { language, t } = useI18n()
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const latestDateTime = currentLocalDateTime()
  const timeZone = browserTimeZone()
  const filters = [
    ['q', t('filter.text'), t('filter.textPlaceholder')], ['server', t('filter.server'), t('filter.serverPlaceholder')],
    ['component', t('filter.component'), t('filter.componentPlaceholder')], ['job_id', t('filter.job'), t('filter.jobPlaceholder')],
    ['trace_id', t('filter.trace'), t('filter.tracePlaceholder')], ['from', t('filter.from', { zone: timeZone }), ''], ['to', t('filter.to', { zone: timeZone }), ''],
  ] as const
  const [params, update] = useSearchParams()
  const query = new URLSearchParams(params)
  const page = Math.max(1, Math.trunc(Number(params.get('page'))) || 1)
  function set(name: string, value: string) {
    const next = new URLSearchParams(params)
    if (name !== 'page') next.delete('page')
    if (value && (name === 'from' || name === 'to')) {
      next.set(name, isValidDateTimeLocal(value, latestDateTime) ? localDateTimeToUtcIso(value) : '')
    } else if (value) next.set(name, value)
    else next.delete(name)
    if (next.get(name) === '') next.delete(name)
    update(next, { replace: true })
  }
  for (const field of ['from', 'to']) {
    const date = params.get(field)
    const timestamp = utcDateTimeToEpoch(date)
    if (timestamp !== undefined && timestamp <= Date.now()) query.set(field, new Date(timestamp).toISOString())
    else query.delete(field)
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
    <Heading caption={t('timeline.caption')} title={t('timeline.title')}>{t('timeline.description')}</Heading>
    <div className="panel filters">
      {filters.map(([name, label, placeholder]) => {
        const dateField = name === 'from' || name === 'to'
        const value = params.get(name)
        const localValue = dateField ? utcDateTimeToLocal(value) : value
        return <label key={name}>{label}<input type={dateField ? 'datetime-local' : 'text'} max={dateField ? latestDateTime : undefined} placeholder={placeholder} value={dateField ? (isValidDateTimeLocal(localValue, latestDateTime) ? localValue : '') : value ?? ''} onChange={e => {
          const nextValue = e.currentTarget.value
          set(name, dateField && nextValue && !isValidDateTimeLocal(nextValue, latestDateTime) ? '' : nextValue)
        }} onBlur={e => {
          const nextValue = e.currentTarget.value
          if (dateField && nextValue && !isValidDateTimeLocal(nextValue, latestDateTime)) set(name, '')
        }} /></label>
      })}
      <label>{t('filter.level')}<select value={params.get('level') ?? ''} onChange={e => set('level', e.target.value)}><option value="">{t('filter.all')}</option>{['DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL'].map(level => <option key={level}>{level}</option>)}</select></label>
      <button type="button" className="secondary" onClick={() => update({})} disabled={!params.size}>{t('filter.clear')}</button>
    </div>
    <Feedback {...result} />
    {list && <section className="panel">
      <h2>{t('events.title')} <small>{t('events.onPage', { count: visible.length.toLocaleString(locale) })}</small></h2>
      {visible.length ? <div className="table"><table><thead><tr><th>{t('events.timestamp')}</th><th>{t('filter.level')}</th><th>{t('events.serverComponent')}</th><th>{t('events.job')}</th><th>{t('events.message')}</th></tr></thead>
      <tbody>{visible.map(entry => <tr key={entry.id}>
        <td>{formatTime(entry.ts_utc)}</td><td><span className={'badge ' + entry.level.toLowerCase()}>{entry.level}</span></td><td>{entry.host}<small>{entry.component}</small></td><td>{entry.job_id || '—'}</td>
        <td><button className="link" onClick={() => open(entry.id)}>{entry.message}</button></td>
      </tr>)}</tbody></table></div> : <p>{t('events.empty')}</p>}
      {(page > 1 || hasNext) && <div className="actions"><button disabled={page <= 1} onClick={() => set('page', String(page - 1))}>{t('page.previous')}</button><span>{t('page.current', { page })}</span><button disabled={!hasNext} onClick={() => set('page', String(page + 1))}>{t('page.next')}</button></div>}
    </section>}
  </>
}

function ErrorGroups({ mode, open }: { mode: Mode; open: (id: number) => void }) {
  const { t } = useI18n()
  const result = useData<Group[] | { items: Group[] }>('/analysis/groups', mode, mode === 'import' ? [] : groups)
  const list = Array.isArray(result.data) ? result.data : result.data?.items
  return <>
    <Heading caption={t('groups.caption')} title={t('groups.title')}>{t('groups.description')}</Heading>
    <Feedback {...result} />
    {list?.length === 0 && <p className="notice">{mode === 'import' ? t('groups.importNotice') : t('groups.empty')}</p>}
    {list?.map(group => <section className="panel" key={group.id}><div className="section-title"><h2>{group.label}</h2><span className={'badge ' + (group.status === 'recovered' ? 'info' : group.status === 'failed' ? 'error' : '')}>{group.status === 'recovered' ? t('groups.recovered') : group.status === 'failed' ? t('groups.failed') : group.status}</span></div>
      <div className="actions">{group.event_ids?.map(id => <button className="secondary" key={id} onClick={() => open(id)}>{t('groups.event', { id })}</button>)}</div></section>)}
  </>
}

function Assistant({ mode, open }: { mode: Mode; open: (id: number) => void }) {
  const { language, t } = useI18n()
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<{ question: string; answer: Answer } | null>(null)
  const [step, setStep] = useState('')
  const [error, setError] = useState('')
  const active = React.useRef<{ target: AssistantTarget; controller: AbortController } | null>(null)
  const lastOpened = React.useRef<AssistantTarget | null>(null)
  useEffect(() => () => { active.current?.controller.abort(); active.current = null }, [])
  function isAlreadyOpen(prompt: string) {
    const target = assistantTarget(prompt)
    return !!lastOpened.current && sameAssistantTarget(lastOpened.current, target)
  }
  async function ask(prompt: string, clearComposer = false) {
    const cleanPrompt = prompt.trim()
    const target = assistantTarget(cleanPrompt)
    if (!cleanPrompt || (lastOpened.current && sameAssistantTarget(lastOpened.current, target))) return
    if (clearComposer) setQuestion('')
    active.current?.controller.abort()
    const controller = new AbortController()
    const request = { target, controller }
    active.current = request
    lastOpened.current = target
    setResult(null)
    setError('')
    setStep(t('assistant.searching'))
    try {
      const answer = mode === 'demo'
        ? demoAnswer(cleanPrompt, language)
        : await chat(cleanPrompt, message => { if (active.current === request) setStep(message) }, controller.signal)
      if (active.current === request) setResult({ question: cleanPrompt, answer })
    } catch (error) {
      if (!controller.signal.aborted && active.current === request) {
        lastOpened.current = null
        setError(errorText(error))
      }
    } finally {
      if (active.current === request) {
        active.current = null
        setStep('')
      }
    }
  }
  return <>
    <Heading caption={t('assistant.caption')} title={t('assistant.title')}>{mode === 'demo' ? t('assistant.demoDescription') : t('assistant.liveDescription')}</Heading>
    <div className="actions">{[t('assistant.prompt2003'), t('assistant.prompt2010'), t('assistant.promptSync')].map(prompt => <button type="button" key={prompt} className="secondary" disabled={isAlreadyOpen(prompt)} onClick={() => void ask(prompt)}>{prompt}</button>)}</div>
    {result && <article className="panel answer">
      <p className="question">{result.question}</p><h2>{t('assistant.hypothesis')}</h2><p>{result.answer.summary}</p>
      <h3>{t('assistant.causalChain')}</h3><ol>{result.answer.causal_chain.map(item => <li key={item.step}><strong>{item.server}</strong> · {item.text}</li>)}</ol>
      <h3>{t('assistant.evidence')}</h3><div className="evidence">{result.answer.evidence.map((item, index) => <button key={index} className="secondary" onClick={() => open(item.event_id)} title={item.file}>{item.file.split('/').at(-1)}:{item.line} <small>{formatTime(item.ts)}</small></button>)}</div>
      <h3>{t('assistant.uncertainty')}{typeof result.answer.confidence === 'number' ? ' · ' + t('assistant.confidence', { percent: Math.round(result.answer.confidence * 100) }) : ''}</h3><p>{result.answer.uncertainty}</p>
      {!!result.answer.counter_evidence?.length && <><h3>{t('assistant.counterEvidence')}</h3><ul>{result.answer.counter_evidence.map(text => <li key={text}>{text}</li>)}</ul></>}
      <h3>{t('assistant.verification')}</h3><ul>{result.answer.verification_steps.map(text => <li key={text}>{text}</li>)}</ul>
    </article>}
    <Feedback pending={false} error={error} />
    {step && <p className="notice" role="status">{step}</p>}
    <form className="panel composer" onSubmit={event => { event.preventDefault(); void ask(question, true) }}>
      <label>{t('assistant.question')}<input value={question} onChange={event => setQuestion(event.target.value)} placeholder={t('assistant.placeholder')} /></label>
      <button disabled={!question.trim() || isAlreadyOpen(question)}>{t('assistant.ask')}</button>
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
  const { language, setLanguage, t } = useI18n()
  const [mode, setMode] = useState<Mode>(offline ? 'demo' : 'live')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [logs, setLogs] = useState<ImportedLogs | null>(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  async function loadLogs(file: File) {
    setImporting(true)
    setImportError('')
    try {
      const imported = await importZip(file, language)
      setLogs(imported)
      switchMode('import')
    } catch (error) {
      setImportError(errorText(error))
    } finally {
      setImporting(false)
    }
  }
  const [id, setId] = useState<number | null>(null)
  const [health, setHealth] = useState(offline ? t('backend.offlineDemo') : t('backend.checking'))
  const [check, setCheck] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    if (offline) return
    setHealth(t('backend.checking'))
    const timeout = setTimeout(() => { setHealth(t('backend.unreachable')); controller.abort() }, 3500)
    request<{ status?: string; version?: string; log_root_found?: boolean; db_found?: boolean }>('/health', { signal: controller.signal }, language).then(
      data => setHealth(data.status && data.status !== 'ok'
        ? t('backend.reported', { status: data.status })
        : t('backend.reachable') + ' · ' + (data.log_root_found ? t('backend.logsReady') : t('backend.logsMissing')) + ' · ' + (data.db_found ? t('backend.databaseReady') : t('backend.databaseMissing'))),
      () => { if (!controller.signal.aborted) setHealth(t('backend.unreachable')) },
    ).finally(() => clearTimeout(timeout))
    return () => { clearTimeout(timeout); controller.abort() }
  }, [check, language, t])
  function switchMode(next: Mode) { setId(null); setMode(next); if (next === 'live') setCheck(value => value + 1) }
  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon" aria-hidden="true">⌁</span><div>Log Tracer<small>MAIT MAKEATHON</small></div></div>
      <nav aria-label={t('nav.primary')}><NavLink to="/" end>{t('nav.overview')}</NavLink><NavLink to="/timeline">{t('nav.timeline')}</NavLink><NavLink to="/groups">{t('nav.groups')}</NavLink><NavLink to="/chat">{t('nav.assistant')}</NavLink></nav>
      <div className="sidebar-settings">
        <div className="settings-panel" id="settings-panel" hidden={!settingsOpen}>
          <label htmlFor="language-select">{t('settings.language')}</label>
          <select id="language-select" value={language} onChange={event => setLanguage(event.target.value as 'en' | 'de')}>
            <option value="en">{t('settings.english')}</option>
            <option value="de">{t('settings.german')}</option>
          </select>
        </div>
        <button type="button" className="settings-trigger" aria-expanded={settingsOpen} aria-controls="settings-panel" aria-label={t(settingsOpen ? 'settings.close' : 'settings.open')} onClick={() => setSettingsOpen(value => !value)}>
          <span aria-hidden="true">⚙</span><span>{t('settings.title')}</span>
        </button>
      </div>
    </aside>
    <div className="workspace">
      <div className="topbar"><button className="health secondary" disabled={offline} onClick={() => setCheck(value => value + 1)} title={t('backend.recheck')} aria-live="polite">{health}</button>
        <div className="modes" role="group" aria-label={t('mode.source')}><button aria-pressed={mode === 'demo'} onClick={() => switchMode('demo')}>{t('mode.demo')}</button>{logs && <button aria-pressed={mode === 'import'} onClick={() => switchMode('import')}>{t('mode.import')}</button>}<button aria-pressed={mode === 'live'} disabled={offline} onClick={() => switchMode('live')}>{t('mode.live')}</button></div></div>
      <main><Routes><Route path="/" element={<Overview mode={mode} logs={logs} onImport={file => void loadLogs(file)} onViewImport={() => switchMode('import')} pending={importing} importError={importError} open={setId} />} /><Route path="/timeline" element={<Timeline mode={mode} open={setId} logs={logs} />} /><Route path="/groups" element={<ErrorGroups mode={mode} open={setId} />} /><Route path="/chat" element={mode === 'import' ? <p className="notice">{t('assistant.importNotice')}</p> : <Assistant key={mode} mode={mode} open={setId} /> } /><Route path="*" element={<p className="notice">{t('route.notFound')} <NavLink to="/">{t('route.goHome')}</NavLink></p>} /></Routes></main>
    </div>
    <Drawer opened={id !== null} onClose={() => setId(null)} position="right" size="min(1150px, 100%)" title={t('details.title', { id: id ?? '' })}>{id !== null && <EventDetail id={id} mode={mode} logs={logs} open={setId} />}</Drawer>
  </div>
}

createRoot(document.getElementById('root')!).render(<MantineProvider><I18nProvider><HashRouter><App /></HashRouter></I18nProvider></MantineProvider>)





