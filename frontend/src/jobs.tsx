import { Fragment, useContext, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Feedback, firstLine, formatTime, useAnalysis } from './data'
import type { Entry } from './demo'
import { useI18n } from './i18n'
import type { MessageKey } from './i18n'
import { AssistantLinkContext, EventQuestions } from './suggestions'
import { browserTimeZone, currentLocalDateTime, isValidDateTimeLocal, localDateTimeToUtcIso } from './time'
import { InfoTip, LevelBadge } from './ui'

// All jobs of the logs, combined by the backend (GET /api/jobs). Live mode only.

type Status = 'failed' | 'warning' | 'recovered' | 'ok'
type Job = {
  job_pk: number; job_id: string; trace_id: string | null; runs: number; status: Status; first_ts: string | null; last_ts: string | null
  hosts: string[]; events: number; errors: number; warnings: number; problem_event_id: number | null; problem: string | null; conversion: boolean; incident_id: number | null
}
type JobPage = { items: Job[]; total: number; limit: number; offset: number; by_status: Partial<Record<Status, number>>; servers: string[] }
type EventPage = { items: Entry[]; total: number }

const PAGE_SIZE = 25
const STATUSES: Status[] = ['failed', 'warning', 'recovered', 'ok']
const tileKeys: Record<Status, MessageKey> = { failed: 'jobs.failed', warning: 'jobs.warning', recovered: 'jobs.recovered', ok: 'jobs.ok' }
const statusKeys: Record<Status, MessageKey> = { failed: 'jobs.statusFailed', warning: 'jobs.statusWarning', recovered: 'jobs.statusRecovered', ok: 'jobs.statusOk' }
const badge: Record<Status, string> = { failed: 'error', warning: 'warn', recovered: 'ok', ok: 'ok' }
const shortHost = (host: string) => host.replace(/^mait_/, '')
const shortTime = (timestamp: string | null) => timestamp ? timestamp.replace('T', ' ').replace(/(\.\d+)?Z$/, '') : '—'

function useLocale() {
  const { language } = useI18n()
  return language === 'en' ? 'en-GB' : 'de-DE'
}

function duration(job: Job, locale: string) {
  const seconds = (Date.parse(job.last_ts ?? '') - Date.parse(job.first_ts ?? '')) / 1000
  if (!Number.isFinite(seconds) || seconds <= 0) return '—'
  if (seconds < 120) return seconds.toLocaleString(locale, { maximumFractionDigits: 1 }) + ' s'
  if (seconds < 7200) return Math.round(seconds / 60) + ' min'
  return (seconds / 3600).toLocaleString(locale, { maximumFractionDigits: 1 }) + ' h'
}

export function JobList({ open }: { open: (id: number) => void }) {
  const { t } = useI18n()
  const locale = useLocale()
  const [filters, setFilters] = useState({ q: '', server: '', status: '', conversion: '', from: '', to: '', sort: 'problems' })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const latest = currentLocalDateTime()
  const zone = browserTimeZone()
  function set(field: keyof typeof filters, value: string) {
    setFilters(previous => previous[field] === value ? previous : { ...previous, [field]: value })
    setPage(0)
    setSelected(null)
  }
  // The search waits until the user pauses typing.
  useEffect(() => {
    const timer = setTimeout(() => set('q', search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])
  const query = new URLSearchParams({ sort: filters.sort, limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  for (const field of ['q', 'server', 'status', 'conversion'] as const) if (filters[field]) query.set(field, filters[field])
  for (const field of ['from', 'to'] as const) if (isValidDateTimeLocal(filters[field], latest)) query.set(field, localDateTimeToUtcIso(filters[field]))
  const result = useAnalysis<JobPage>('/jobs?' + query, true)
  const data = result.data
  const counts = data?.by_status ?? {}
  const all = STATUSES.reduce((sum, status) => sum + (counts[status] ?? 0), 0)
  const number = (value: number) => value.toLocaleString(locale)
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  return <section className="panel jobs">
    <h2>{t('jobs.title')} <InfoTip text={t('jobs.info')} /></h2>
    <div className="job-tiles" role="group" aria-label={t('process.status')}>
      <button type="button" className="secondary job-tile" aria-pressed={!filters.status} onClick={() => set('status', '')}>{t('jobs.total')}<strong>{data ? number(all) : '—'}</strong></button>
      {STATUSES.map(status => <button type="button" key={status} className={'secondary job-tile ' + status} aria-pressed={filters.status === status} onClick={() => set('status', filters.status === status ? '' : status)}>{t(tileKeys[status])}<strong>{data ? number(counts[status] ?? 0) : '—'}</strong></button>)}
    </div>
    <div className="filters process-filters">
      <label>{t('process.jobOrTrace')}<input value={search} onChange={event => setSearch(event.target.value)} placeholder={t('jobs.search')} /></label>
      <label>{t('filter.server')}<select value={filters.server} onChange={event => set('server', event.target.value)}><option value="">{t('process.allServers')}</option>{data?.servers.map(server => <option key={server}>{server}</option>)}</select></label>
      <label>{t('process.jobType')}<select value={filters.conversion} onChange={event => set('conversion', event.target.value)}><option value="">{t('process.allJobs')}</option><option value="true">{t('process.conversions')}</option></select></label>
      <label>{t('filter.from', { zone })}<input type="datetime-local" max={latest} value={filters.from} onChange={event => set('from', event.target.value)} /></label>
      <label>{t('filter.to', { zone })}<input type="datetime-local" max={latest} value={filters.to} onChange={event => set('to', event.target.value)} /></label>
      <label>{t('process.sortBy')}<select value={filters.sort} onChange={event => set('sort', event.target.value)}><option value="problems">{t('jobs.sortProblems')}</option><option value="recent">{t('process.latest')}</option><option value="oldest">{t('process.oldest')}</option><option value="errors">{t('process.mostErrors')}</option><option value="duration">{t('process.longest')}</option><option value="job">{t('process.jobIdSort')}</option></select></label>
    </div>
    <Feedback pending={result.pending && !data} error={result.error} />
    {data && !data.items.length && <p className="notice">{t('jobs.none')}</p>}
    {!!data?.items.length && <div className="table"><table className="job-table" aria-busy={result.pending}><thead><tr><th>{t('events.job')}</th><th>{t('process.status')}</th><th>{t('jobs.period')}</th><th>{t('process.duration')}</th><th>{t('filter.server')}</th><th>{t('jobs.problem')}</th><th>{t('process.logs')}</th></tr></thead>
      <tbody>{data.items.map(job => <Fragment key={job.job_pk}><tr>
        <td><strong>{job.job_id}</strong>{(job.runs > 1 || job.conversion) && <small>{[job.runs > 1 && t('jobs.runs', { count: number(job.runs) }), job.conversion && t('process.conversion')].filter(Boolean).join(' · ')}</small>}</td>
        <td><span className={'badge ' + badge[job.status]}>{t(statusKeys[job.status])}</span></td>
        <td>{shortTime(job.first_ts)}{job.last_ts !== job.first_ts && <small>{shortTime(job.last_ts)}</small>}</td>
        <td>{duration(job, locale)}</td>
        <td title={job.hosts.join(', ')}>{job.hosts[0] ? shortHost(job.hosts[0]) : '—'}{job.hosts.length > 1 && <small>{t('jobs.moreServers', { count: job.hosts.length - 1 })}</small>}</td>
        <td>{job.problem && job.problem_event_id !== null ? <button type="button" className="link" onClick={() => open(job.problem_event_id!)}>{firstLine(job.problem)}</button> : '—'}
          {(job.errors > 0 || job.warnings > 0) && <small>{[job.errors > 0 && t(job.errors === 1 ? 'jobs.oneError' : 'jobs.errors', { count: number(job.errors) }), job.warnings > 0 && t(job.warnings === 1 ? 'jobs.oneWarning' : 'jobs.warnings', { count: number(job.warnings) })].filter(Boolean).join(' · ')}</small>}</td>
        <td><button type="button" className="link" aria-expanded={selected === job.job_pk} onClick={() => setSelected(selected === job.job_pk ? null : job.job_pk)}>{number(job.events)} {t('process.logs')}</button></td>
      </tr>
      {selected === job.job_pk && <tr className="process-expanded-row"><td colSpan={7}><JobDetails job={job} open={open} /></td></tr>}
      </Fragment>)}</tbody></table></div>}
    {data && data.total > PAGE_SIZE && <div className="actions job-pager"><button type="button" className="secondary" disabled={page === 0} onClick={() => { setPage(page - 1); setSelected(null) }}>{t('page.previous')}</button>
      <span>{t('jobs.range', { from: number(page * PAGE_SIZE + 1), to: number(Math.min(data.total, (page + 1) * PAGE_SIZE)), total: number(data.total) })}</span>
      <button type="button" className="secondary" disabled={page + 1 >= pages} onClick={() => { setPage(page + 1); setSelected(null) }}>{t('page.next')}</button></div>}
  </section>
}

function JobDetails({ job, open }: { job: Job; open: (id: number) => void }) {
  const { t } = useI18n()
  const problems = job.errors + job.warnings > 0
  const [onlyProblems, setOnlyProblems] = useState(problems)
  const [limit, setLimit] = useState(50)
  const result = useAnalysis<EventPage>(`/jobs/${job.job_pk}/events?limit=${limit}${onlyProblems ? '&problems=true' : ''}`, true)
  // An opened job is the assistant's context: its first problem, else its first entry.
  const { setContext } = useContext(AssistantLinkContext)
  const contextId = job.problem_event_id ?? job.job_pk
  useEffect(() => setContext(contextId), [contextId, setContext])
  return <section className="process-details-inline panel" aria-label={t('jobs.entries', { job: job.job_id })}>
    <div className="section-title"><h3>{t('jobs.entries', { job: job.job_id })}</h3>{job.incident_id !== null && <Link to={'/incidents/' + job.incident_id}>{t('jobs.incident')}</Link>}</div>
    <p>{job.hosts.join(', ')}{job.trace_id && <> · {t('incident.trace', { trace: job.trace_id })}</>}</p>
    <EventQuestions id={contextId} />
    {problems ? <button type="button" className="secondary" aria-pressed={onlyProblems} onClick={() => { setOnlyProblems(!onlyProblems); setLimit(50) }}>{t(onlyProblems ? 'jobs.showAll' : 'jobs.showProblems')}</button> : <p>{t('jobs.noProblems')}</p>}
    <Feedback pending={result.pending && !result.data} error={result.error} />
    {result.data && <><ul className="job-entries">{result.data.items.map(entry => <li key={entry.id}><small><LevelBadge level={entry.level} /> {formatTime(entry.ts_utc)} · {entry.host} · {entry.component}{entry.job_id !== job.job_id && ' · ' + entry.job_id}</small><button type="button" className="link" onClick={() => open(entry.id)}>{firstLine(entry.message)}</button></li>)}</ul>
      {result.data.items.length < result.data.total && limit < 500 && <button type="button" className="secondary" onClick={() => setLimit(Math.min(500, limit + 100))}>{t('jobs.more')} ({result.data.items.length} / {result.data.total})</button>}</>}
  </section>
}
