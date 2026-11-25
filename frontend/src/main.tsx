import React, { useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { HashRouter, Navigate, NavLink, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom'
import { MantineProvider, Tooltip } from '@mantine/core'
import '@mantine/core/styles.css'
import './theme.css'
import './style.css'
import './layout.css'
import { request } from './api'
import { TurnView, useConversation } from './conversation'
import type { Conversation } from './conversation'
import { errorText, Feedback, formatTime, offline, useData } from './data'
import type { Mode } from './data'
import { entries, groups } from './demo'
import type { Entry, EventPage, Group, Stats } from './demo'
import { EventModal } from './event-details'
import { importZip } from './import-zip'
import { getDataset, restoreOriginal, uploadDataset, waitForDataset } from './dataset'
import type { DatasetState } from './dataset'
import { AnomalyStrip, IncidentPage, IncidentsPage, LatestIncidents } from './incidents'
import { JobList } from './jobs'
import { ProcessMonitor } from './ProcessMonitor'
import type { ImportedLogs } from './import-zip'
import { I18nProvider, useI18n } from './i18n'
import { AssistantLinkContext, SuggestionPanel, useSavedQuestions } from './suggestions'
import { SourcesPage } from './sources'
import { PageTitle } from './ui'
import { browserTimeZone, currentLocalDateTime, isValidDateTimeLocal, localDateTimeToUtcIso, utcDateTimeToEpoch, utcDateTimeToLocal } from './time'

type AssistantTarget = { question: string; jobIds: string[] }

function assistantTarget(question: string): AssistantTarget {
  const normalized = question.trim().replace(/\s+/g, ' ').toLowerCase()
  const jobIds = [...new Set((normalized.match(/\b[a-z][a-z0-9]*[-_ ]\d+[a-z0-9._-]*\b/g) ?? []).map(id => id.replace(/[\s_]+/g, '-')))]
  return { question: normalized, jobIds }
}

function sameAssistantTarget(first: AssistantTarget, second: AssistantTarget) {
  return first.question === second.question || first.jobIds.some(id => second.jobIds.includes(id))
}

type ServerJob = { state: 'idle' | 'uploading' | 'ingesting' | 'done' | 'error'; message?: string }

function Overview({ mode, logs, onImport, onViewImport, pending, importError, open, server, onAnalyze }: { mode: Mode; logs: ImportedLogs | null; onImport: (file: File) => void; onViewImport: () => void; pending: boolean; importError: string; open: (id: number) => void; server: ServerJob; onAnalyze: () => void }) {
  const { language, t } = useI18n()
  const fileInput = React.useRef<HTMLInputElement>(null)
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const sample: Stats = mode === 'import' && logs
    ? { sources: logs.sources.size, unique_sources: logs.sources.size, duplicate_sources: 0, duplicate_events: logs.duplicates, events: logs.entries.length, levels: { ERROR: logs.entries.filter(entry => entry.level === 'ERROR').length } }
    : { sources: new Set(entries.map(entry => entry.source)).size, unique_sources: new Set(entries.map(entry => entry.source)).size, duplicate_sources: 0, events: entries.length, levels: { ERROR: entries.filter(entry => entry.level === 'ERROR').length } }
  const result = useData<Stats>('/stats', mode, sample)
  const data = result.data
  return <>
    <PageTitle title={t('overview.title')} info={t('overview.description')} />
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
        <NavLink to="/timeline" onClick={() => onViewImport()}>{t('upload.view')}</NavLink>
        {!offline && <div className="server-analyze">
          <button type="button" className="secondary" disabled={server.state === 'uploading' || server.state === 'ingesting'} onClick={onAnalyze}>{t('upload.analyze')}</button>
          <span className="muted">{t('upload.analyzeInfo')}</span>
          {(server.state === 'uploading' || server.state === 'ingesting') && <p role="status">{t(server.state === 'uploading' ? 'upload.uploading' : 'upload.ingesting')}</p>}
          {server.state === 'done' && <p role="status">{t('upload.analyzed')}</p>}
          {server.state === 'error' && <p className="notice error" role="alert">{server.message}</p>}
        </div>}</div>}
    </section>
    {mode !== 'live' && <ProcessMonitor key={mode === 'import' ? logs?.filename : mode} events={mode === 'import' && logs ? logs.entries : entries} open={open} />}
    <Feedback {...result} />
    {mode === 'live' && data && <div className="metrics">{[
      [t('metric.sources'), data.sources], [t('metric.events'), data.events], [t('metric.errors'), data.levels?.ERROR ?? 0], [t('metric.duplicates'), data.duplicate_sources ?? 0],
    ].map(([label, value]) => <section className="metric" key={label}><span>{label}</span><strong>{typeof value === 'number' ? value.toLocaleString(locale) : '—'}</strong></section>)}</div>}
    {mode === 'live' && <LatestIncidents />}
    {mode === 'live' && <JobList open={open} />}
    <section className="panel"><h2>{t('overview.start')}</h2><div className="shortcuts">
      <NavLink to="/timeline">{t('overview.search')}<span>{t('overview.searchDescription')}</span></NavLink>
      <NavLink to="/incidents">{t('overview.groups')}<span>{t('overview.groupsDescription')}</span></NavLink>
      <NavLink to="/chat">{t('overview.assistant')}<span>{t('overview.assistantDescription')}</span></NavLink>
    </div></section>
  </>
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
  function showAnomaly(server: string, from: string, to: string) {
    update(new URLSearchParams({ server, from, to, level: 'ERROR' }))
  }
  const localPageSize = 100
  const apiQuery = new URLSearchParams(query)
  if (mode === 'live') {
    apiQuery.delete('page')
    apiQuery.delete('source')
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
    <PageTitle title={t('timeline.title')} info={t('timeline.description')} />
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
      {mode === 'live' && <label className="check-label"><input type="checkbox" checked={params.get('include_duplicates') === 'true'} onChange={e => set('include_duplicates', e.target.checked ? 'true' : '')} />{t('timeline.duplicates')}</label>}
    </div>
    {mode === 'live' && params.get('source_id') && <p className="notice file-notice">{t('timeline.oneFile', { file: params.get('source') ?? '#' + params.get('source_id') })} <button type="button" className="link" onClick={() => { const next = new URLSearchParams(params); next.delete('source_id'); next.delete('source'); next.delete('page'); update(next, { replace: true }) }}>{t('timeline.allFiles')}</button></p>}
    {mode === 'live' && <AnomalyStrip server={params.get('server') ?? ''} from={query.get('from')} to={query.get('to')} select={showAnomaly} />}
    <Feedback {...result} />
    {list && <section className="panel">
      <h2>{t('events.title')} <small>{t('events.onPage', { count: visible.length.toLocaleString(locale) })}</small></h2>
      {visible.length ? <div className="table"><table><thead><tr><th>{t('events.timestamp')}</th><th>{t('filter.level')}</th><th>{t('events.serverComponent')}</th><th>{t('events.job')}</th><th>{t('events.message')}</th></tr></thead>
      <tbody>{visible.map(entry => <tr key={entry.id}>
        <td>{formatTime(entry.ts_utc)}</td><td><span className={'badge ' + entry.level.toLowerCase()}>{entry.level}</span>{entry.is_duplicate && <small>{t('timeline.duplicate')}</small>}</td><td>{entry.host}<small>{entry.component}</small></td><td>{entry.job_id || '—'}</td>
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
    <PageTitle title={t('groups.title')} info={t('groups.description')} />
    <Feedback {...result} />
    {list?.length === 0 && <p className="notice">{mode === 'import' ? t('groups.importNotice') : t('groups.empty')}</p>}
    {list?.map(group => <section className="panel" key={group.id}><div className="section-title"><h2>{group.label}</h2><span className={'badge ' + (group.status === 'recovered' ? 'ok' : group.status === 'failed' ? 'error' : '')}>{group.status === 'recovered' ? t('groups.recovered') : group.status === 'failed' ? t('groups.failed') : group.status}</span></div>
      <div className="actions">{group.event_ids?.map(id => <button className="secondary" key={id} onClick={() => open(id)}>{t('groups.event', { id })}</button>)}</div></section>)}
  </>
}

type AssistantProps = { mode: Mode; conversation: Conversation; open: (id: number) => void; contextId: number | null; clearContext: () => void; requested: string | null; clearRequested: () => void }

function Assistant({ mode, conversation, open, contextId, clearContext, requested, clearRequested }: AssistantProps) {
  const { t } = useI18n()
  const { turns, running } = conversation
  const last = turns.at(-1)
  const [question, setQuestion] = useState('')
  const saved = useSavedQuestions()
  const [expanded, setExpanded] = useState(turns.length === 0)
  // Demo has one prepared answer per case. In a live chat only the very same question is blocked.
  function isOpen(prompt: string) {
    if (!last || last.error) return false
    const target = assistantTarget(prompt), shown = assistantTarget(last.question)
    return mode === 'demo' ? sameAssistantTarget(shown, target) : shown.question === target.question && (running || !!last.answer)
  }
  function ask(prompt: string, remember = true) {
    const text = prompt.trim()
    if (text.length < 3 || isOpen(text)) return
    if (mode === 'live') {
      if (remember) saved.recent.add(text)
      setExpanded(false)
    }
    void conversation.ask(text)
  }
  useEffect(() => {
    if (requested === null) return
    clearRequested()
    ask(requested)
  }, [requested])
  const draft = question.trim()
  const draftSaved = saved.favorites.has(draft)
  const followUps = [t('chat.simpler'), t('chat.checkFirst'), t('chat.howOften')]
  return <>
    <PageTitle title={t('assistant.title')} info={mode === 'demo' ? t('assistant.demoDescription') : t('assistant.liveDescription')}>
      {mode === 'live' && turns.length > 0 && <button type="button" className="secondary" onClick={() => { conversation.reset(); setExpanded(true) }}>{t('chat.new')}</button>}
    </PageTitle>
    {mode === 'live' && <SuggestionPanel contextId={contextId} clearContext={clearContext} saved={saved} isOpen={isOpen} ask={ask} expanded={expanded} setExpanded={setExpanded} />}
    {mode === 'demo' && <div className="actions">{[t('assistant.prompt2003'), t('assistant.prompt2010'), t('assistant.promptSync')].map(prompt => <button type="button" key={prompt} className="secondary" disabled={isOpen(prompt)} onClick={() => ask(prompt)}>{prompt}</button>)}</div>}
    {turns.map(turn => <TurnView key={turn.id} turn={turn} latest={turn === last} open={open} />)}
    {mode === 'live' && last?.answer && <div className="follow-ups" role="group" aria-label={t('chat.followUps')}>{followUps.map(text => <button type="button" className="secondary" key={text} disabled={isOpen(text)} onClick={() => ask(text, false)}>{text}</button>)}</div>}
    <form className={'panel composer' + (mode === 'live' ? ' composer-live' : '')} onSubmit={event => { event.preventDefault(); if (draft.length >= 3 && !isOpen(draft)) { ask(draft); setQuestion('') } }}>
      <label>{t(turns.length && mode === 'live' ? 'chat.followUp' : 'assistant.question')}<input value={question} maxLength={2000} onChange={event => setQuestion(event.target.value)} placeholder={t(turns.length && mode === 'live' ? 'chat.placeholder' : 'assistant.placeholder')} /></label>
      {mode === 'live' && <button type="button" className="secondary" disabled={!draft} aria-pressed={!!draft && draftSaved} onClick={() => draftSaved ? saved.favorites.remove(draft) : saved.favorites.add(draft)}>{draftSaved && draft ? '★' : '☆'} {t('suggest.saveDraft')}</button>}
      {running && !draft ? <button type="button" onClick={conversation.stop}>{t('chat.stop')}</button>
        : <button disabled={draft.length < 3 || isOpen(draft)}>{t('assistant.ask')}</button>}
    </form>
  </>
}

type Health = { state: 'ok' | 'warn' | 'error' | 'checking'; label: string; detail: string }
const modeLabel = { live: 'mode.live', demo: 'mode.demo', import: 'mode.importShort' } as const
const modeInfo = { live: 'mode.liveInfo', demo: 'mode.demoInfo', import: 'mode.importInfo' } as const

function App() {
  const { language, setLanguage, t } = useI18n()
  const [mode, setMode] = useState<Mode>(offline ? 'demo' : 'live')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [logs, setLogs] = useState<ImportedLogs | null>(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [server, setServer] = useState<ServerJob>({ state: 'idle' })
  const [dataset, setDataset] = useState<DatasetState | null>(null)
  const [restoring, setRestoring] = useState(false)
  const [datasetError, setDatasetError] = useState('')
  const [dataVersion, setDataVersion] = useState(0)
  async function loadLogs(file: File) {
    setImporting(true)
    setImportError('')
    try {
      const imported = await importZip(file, language)
      setLogs(imported)
      setUploadFile(file)
      setServer({ state: 'idle' })
      switchMode('import')
    } catch (error) {
      setImportError(errorText(error))
    } finally {
      setImporting(false)
    }
  }
  const navigate = useNavigate()
  const [id, setId] = useState<number | null>(null)
  const [contextId, setContextId] = useState<number | null>(null)
  const [requested, setRequested] = useState<string | null>(null)
  const liveChat = useConversation('live')
  const demoChat = useConversation('demo')
  const open = React.useCallback((next: number) => { setId(next); setContextId(next) }, [])
  const assistantLink = React.useMemo(() => ({
    live: mode === 'live',
    ask: (question: string) => { setId(null); setRequested(question); navigate('/chat') },
    setContext: setContextId,
  }), [mode, navigate])
  const [health, setHealth] = useState<Health>({ state: 'checking', label: '', detail: '' })
  const [check, setCheck] = useState(0)
  useEffect(() => {
    if (offline) return setHealth({ state: 'checking', label: t('backend.offlineDemo'), detail: t('mode.demoInfo') })
    // Checked at once, then again in the background (every 3 s while unreachable, every 15 s while
    // fine), so a backend that starts later or restarts after a pull shows up without a click.
    const recheck = ' ' + t('backend.recheckHint')
    const unreachable: Health = { state: 'error', label: t('backend.offline'), detail: t('backend.unreachable') + '.' + recheck }
    let controller: AbortController | null = null
    let next: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    const run = (first: boolean) => {
      const current = new AbortController()
      controller = current
      if (first) setHealth({ state: 'checking', label: t('backend.checking'), detail: t('backend.checking') })
      let result: Health = unreachable
      const timeout = setTimeout(() => current.abort(), 3500)
      request<{ status?: string; version?: string; log_root_found?: boolean; db_found?: boolean }>('/health', { signal: current.signal }, language).then(
        data => {
          const ready = (!data.status || data.status === 'ok') && !!data.log_root_found && !!data.db_found
          result = {
            state: ready ? 'ok' : 'warn',
            label: t(ready ? 'backend.online' : 'backend.incomplete'),
            detail: (data.status && data.status !== 'ok'
              ? t('backend.reported', { status: data.status })
              : t('backend.reachable') + ' · ' + (data.log_root_found ? t('backend.logsReady') : t('backend.logsMissing')) + ' · ' + (data.db_found ? t('backend.databaseReady') : t('backend.databaseMissing'))) + '.' + recheck,
          }
        },
        () => undefined,
      ).finally(() => {
        clearTimeout(timeout)
        if (stopped) return
        setHealth(result)
        next = setTimeout(() => run(false), result.state === 'ok' ? 15000 : 3000)
      })
    }
    run(true)
    return () => { stopped = true; clearTimeout(next); controller?.abort() }
  }, [check, language, t])
  useEffect(() => {
    if (offline || mode !== 'live') return
    const controller = new AbortController()
    getDataset(language, controller.signal).then(setDataset, () => undefined)
    return () => controller.abort()
  }, [check, mode, language])
  // Send the imported ZIP to the backend; when it has imported and analyzed it, show it in Live.
  async function analyzeOnServer() {
    if (!uploadFile) return
    setServer({ state: 'uploading' })
    try {
      await uploadDataset(uploadFile, language)
      setServer({ state: 'ingesting' })
      setDataset(await waitForDataset(language))
      setServer({ state: 'done' })
      setDataVersion(value => value + 1)
      switchMode('live')
      navigate('/')
    } catch (error) {
      setServer({ state: 'error', message: errorText(error) })
    }
  }
  async function backToOriginal() {
    setRestoring(true)
    setDatasetError('')
    try {
      await restoreOriginal(language)
      setDataset(await waitForDataset(language))
      setDataVersion(value => value + 1)
      setCheck(value => value + 1)
      navigate('/')
    } catch (error) {
      setDatasetError(errorText(error))
    } finally {
      setRestoring(false)
    }
  }
  function switchMode(next: Mode) { setId(null); setContextId(null); setRequested(null); setMode(next); if (next === 'live') setCheck(value => value + 1) }
  return <AssistantLinkContext.Provider value={assistantLink}><div className="shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-icon" aria-hidden="true">⌁</span><div>Log Tracer<small>MAIT MAKEATHON</small></div></div>
      <nav aria-label={t('nav.primary')}><NavLink to="/" end>{t('nav.overview')}</NavLink><NavLink to="/timeline">{t('nav.timeline')}</NavLink><NavLink to="/incidents">{t('nav.groups')}</NavLink><NavLink to="/chat">{t('nav.assistant')}</NavLink><NavLink to="/sources">{t('nav.sources')}</NavLink></nav>
      <div className="sidebar-tools">
        <div className="mode-switch" role="group" aria-label={t('mode.source')}>{(['live', 'demo', ...(logs ? ['import'] : [])] as Mode[]).map(value =>
          <Tooltip key={value} label={t(modeInfo[value])} multiline maw={240} position="right" withArrow><button type="button" aria-pressed={mode === value} disabled={value === 'live' && offline} onClick={() => switchMode(value)}>{t(modeLabel[value])}</button></Tooltip>)}</div>
        <Tooltip label={health.detail} multiline maw={240} position="right" withArrow><button type="button" className={'backend-status ' + health.state} disabled={offline} onClick={() => setCheck(value => value + 1)} aria-label={health.label + '. ' + health.detail} aria-live="polite"><span className="status-dot" aria-hidden="true" />{health.label}</button></Tooltip>
        {mode === 'live' && dataset && <div className="dataset-status" role="status">
          <span>{t('dataset.label')}: {dataset.dataset.kind === 'upload' ? t('dataset.uploaded', { name: dataset.dataset.name }) : t('dataset.original')}</span>
          {dataset.dataset.kind === 'upload' && <button type="button" className="dataset-restore" disabled={restoring} onClick={() => void backToOriginal()}>{t(restoring ? 'dataset.restoring' : 'dataset.restore')}</button>}
          {datasetError && <span className="dataset-error" role="alert">{datasetError}</span>}
        </div>}
      </div>
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
      <main key={dataVersion}><Routes><Route path="/" element={<Overview mode={mode} logs={logs} onImport={file => void loadLogs(file)} onViewImport={() => switchMode('import')} pending={importing} importError={importError} open={open} server={server} onAnalyze={() => void analyzeOnServer()} />} /><Route path="/timeline" element={<Timeline mode={mode} open={open} logs={logs} />} /><Route path="/incidents" element={mode === 'live' ? <IncidentsPage /> : <ErrorGroups mode={mode} open={open} />} /><Route path="/incidents/:id" element={mode === 'live' ? <IncidentPage open={open} /> : <Navigate to="/incidents" replace />} /><Route path="/sources" element={mode === 'live' ? <SourcesPage /> : <p className="notice">{t('sources.liveOnly')}</p>} /> <Route path="/groups" element={<Navigate to="/incidents" replace />} /><Route path="/chat" element={mode === 'import' ? <p className="notice">{t('assistant.importNotice')}</p> : <Assistant key={mode} mode={mode} conversation={mode === 'demo' ? demoChat : liveChat} open={open} contextId={contextId} clearContext={() => setContextId(null)} requested={requested} clearRequested={() => setRequested(null)} /> } /><Route path="*" element={<p className="notice">{t('route.notFound')} <NavLink to="/">{t('route.goHome')}</NavLink></p>} /></Routes></main>
    </div>
    <EventModal id={id} mode={mode} logs={logs} open={open} close={() => setId(null)} />
  </div></AssistantLinkContext.Provider>
}

createRoot(document.getElementById('root')!).render(<MantineProvider><I18nProvider><HashRouter><App /></HashRouter></I18nProvider></MantineProvider>)





