import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { Entry } from './demo'
import { buildProcesses } from './processes'
import type { Process } from './processes'
import { useI18n } from './i18n'
import type { MessageKey } from './i18n'
import { currentUtcDateTimeLocal, isValidDateTimeLocal } from './time'

const date = (value: string | undefined, locale: string) => value
  ? new Intl.DateTimeFormat(locale, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(value))
  : '—'
const count = (number: number, locale: string) => number.toLocaleString(locale)
function duration(ms: number, locale: string) {
  if (ms < 1000) return count(ms, locale) + ' ms'
  if (ms < 60000) return (ms / 1000).toLocaleString(locale, { maximumFractionDigits: 2 }) + ' s'
  return Math.floor(ms / 60000) + ' min ' + Math.floor(ms / 1000 % 60) + ' s'
}

const statusKeys: Record<Process['status'], MessageKey> = {
  Läuft: 'status.running', Erfolgreich: 'status.successful', Erholt: 'status.recovered',
  Fehlgeschlagen: 'status.failed', Unklar: 'status.unknown',
}

function workflowLabel(value: string, language: 'en' | 'de') {
  const english: Record<string, string> = { 'NX → JT · Baugruppe': 'NX → JT · Assembly', 'PLM-Synchronisation': 'PLM Synchronization' }
  const german: Record<string, string> = { 'NX → JT · Assembly': 'NX → JT · Baugruppe', 'PLM Synchronization': 'PLM-Synchronisation' }
  return (language === 'en' ? english : german)[value] ?? value
}

export function ProcessMonitor({ events, open }: { events: Entry[]; open: (id: number) => void }) {
  const { language, t } = useI18n()
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const latestDateTime = currentUtcDateTimeLocal()
  const processes = useMemo(() => buildProcesses(events), [events])
  const hosts = useMemo(() => [...new Set(processes.flatMap(process => process.hosts))].sort(), [processes])
  const workflows = useMemo(() => [...new Set(processes.map(process => process.workflow).filter(Boolean))].sort(), [processes])
  const [search, setSearch] = useState('')
  const [host, setHost] = useState('')
  const [workflow, setWorkflow] = useState('')
  const [status, setStatus] = useState('')
  const [kind, setKind] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [sort, setSort] = useState('recent')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<string | null>(null)
  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    const lower = isValidDateTimeLocal(from, latestDateTime) ? Date.parse(`${from}Z`) : -Infinity
    const upper = isValidDateTimeLocal(to, latestDateTime) ? Date.parse(`${to}Z`) : Infinity
    const list = processes.filter(process =>
      (!term || [process.job, process.trace, process.workflow].some(value => value.toLowerCase().includes(term)))
      && (!host || process.hosts.includes(host))
      && (!workflow || process.workflow === workflow)
      && (!status || process.status === status)
      && (!kind || process.conversion)
      && Date.parse(process.last) >= lower && Date.parse(process.first) <= upper,
    )
    return list.sort((a, b) => {
      if (sort === 'duration') return (b.duration ?? -1) - (a.duration ?? -1)
      if (sort === 'errors') return b.errors.length - a.errors.length
      if (sort === 'job') return (a.job || a.trace).localeCompare(b.job || b.trace, 'de', { numeric: true })
      if (sort === 'oldest') return a.first.localeCompare(b.first)
      return b.last.localeCompare(a.last)
    })
  }, [processes, search, host, workflow, status, kind, from, to, sort, latestDateTime])
  const pageSize = 25
  const maxPage = Math.max(1, Math.ceil(filtered.length / pageSize))
  const current = Math.min(page, maxPage)
  const withDuration = filtered.filter(process => process.duration !== undefined)
  const mean = withDuration.length ? withDuration.reduce((sum, process) => sum + process.duration!, 0) / withDuration.length : undefined
  const unidentified = events.filter(entry => !entry.job_id.trim() && !entry.trace_id.trim()).length

  function filter(setter: (value: string) => void, value: string) {
    setter(value)
    setPage(1)
  }
  function filterDate(setter: (value: string) => void, value: string) {
    filter(setter, value && !isValidDateTimeLocal(value, latestDateTime) ? '' : value)
  }

  return <>
    <div className="metrics process-metrics">
      {[
        [t('process.jobs'), count(filtered.length, locale), count(filtered.filter(process => process.conversion).length, locale) + ' ' + t('process.conversionsDetected')],
        [t('process.averageDuration'), mean === undefined ? '—' : duration(mean, locale), count(withDuration.length, locale) + ' ' + t('process.measuredDuration')],
        [t('process.failed'), count(filtered.filter(process => process.status === 'Fehlgeschlagen').length, locale), count(filtered.filter(process => process.status === 'Erholt').length, locale) + ' ' + t('process.recovered')],
        [t('process.serversInvolved'), count(new Set(filtered.flatMap(process => process.hosts)).size, locale), t('process.inFilteredJobs')],
      ].map(([label, value, detail]) => <section className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>{detail}</small></section>)}
    </div>
    <section className="panel process-panel">
      <h2>{t('process.title')}</h2>
      <div className="filters process-filters">
        <label>{t('process.jobOrTrace')}<input value={search} onChange={e => filter(setSearch, e.target.value)} placeholder={t('process.searchPlaceholder')} /></label>
        <label>{t('process.workflowTemplate')}<select value={workflow} onChange={e => filter(setWorkflow, e.target.value)}><option value="">{t('process.allTemplates')}</option>{workflows.map(value => <option key={value} value={value}>{workflowLabel(value, language)}</option>)}</select></label>
        <label>{t('filter.server')}<select value={host} onChange={e => filter(setHost, e.target.value)}><option value="">{t('process.allServers')}</option>{hosts.map(value => <option key={value}>{value}</option>)}</select></label>
        <label>{t('process.status')}<select value={status} onChange={e => filter(setStatus, e.target.value)}><option value="">{t('process.allStatuses')}</option>{(['Läuft', 'Erfolgreich', 'Erholt', 'Fehlgeschlagen', 'Unklar'] as const).map(value => <option key={value} value={value}>{t(statusKeys[value])}</option>)}</select></label>
        <label>{t('process.jobType')}<select value={kind} onChange={e => filter(setKind, e.target.value)}><option value="">{t('process.allJobs')}</option><option value="conversion">{t('process.conversions')}</option></select></label>
        <label>{t('filter.from')}<input type="datetime-local" max={latestDateTime} value={isValidDateTimeLocal(from, latestDateTime) ? from : ''} onChange={e => filterDate(setFrom, e.target.value)} onBlur={e => filterDate(setFrom, e.currentTarget.value)} /></label>
        <label>{t('filter.to')}<input type="datetime-local" max={latestDateTime} value={isValidDateTimeLocal(to, latestDateTime) ? to : ''} onChange={e => filterDate(setTo, e.target.value)} onBlur={e => filterDate(setTo, e.currentTarget.value)} /></label>
        <label>{t('process.sortBy')}<select value={sort} onChange={e => filter(setSort, e.target.value)}><option value="recent">{t('process.latest')}</option><option value="oldest">{t('process.oldest')}</option><option value="duration">{t('process.longest')}</option><option value="errors">{t('process.mostErrors')}</option><option value="job">{t('process.jobIdSort')}</option></select></label>
      </div>
      {!filtered.length ? <p className="notice">{processes.length ? t('process.noMatches') : t('process.noIds')}</p> :
        <div className="table process-table-scroll" role="region" aria-label={t('process.jobs')} tabIndex={0}><table><thead><tr><th>{t('process.jobTemplate')}</th><th>{t('process.status')}</th><th>{t('process.startEnd')}</th><th>{t('process.duration')}</th><th>{t('filter.server')}</th><th>{t('process.logs')}</th></tr></thead>
          <tbody>{filtered.slice((current - 1) * pageSize, current * pageSize).map(process => <Fragment key={process.key}>
            <tr>
              <td><strong>{process.job || process.trace}</strong><small>{process.workflow ? workflowLabel(process.workflow, language) : process.conversion ? t('process.conversion') : t('process.unknownTemplate')}</small></td>
              <td><span className={'badge ' + badge(process)}>{t(statusKeys[process.status])}</span></td>
              <td>{date(process.start, locale)}<small>{date(process.end, locale)}</small></td>
              <td>{process.duration === undefined ? '—' : duration(process.duration, locale)}{process.durationSource && <small>{t(process.durationSource === 'Auftrag' ? 'process.durationJob' : 'process.durationRange')}</small>}</td>
              <td>{process.hosts[0]}{process.hosts.length > 1 && <small>{t('process.moreServers', { count: process.hosts.length - 1 })}</small>}</td>
              <td><button className="link" aria-expanded={selected === process.key} aria-controls={'process-details-' + process.key} onClick={() => setSelected(previous => previous === process.key ? null : process.key)}>{count(process.logs.length, locale)} {t('process.logs')}</button>{!!process.errors.length && <small>{count(process.errors.length, locale)} {t('process.errorEvents')}</small>}</td>
            </tr>
            {selected === process.key && <tr className="process-expanded-row"><td colSpan={6}><ProcessDetails id={'process-details-' + process.key} process={process} open={open} /></td></tr>}
          </Fragment>)}</tbody></table></div>}
      {maxPage > 1 && <div className="actions"><button className="secondary" disabled={current <= 1} onClick={() => setPage(current - 1)}>{t('page.previous')}</button><span>{t('page.number', { page: current, total: maxPage })}</span><button className="secondary" disabled={current >= maxPage} onClick={() => setPage(current + 1)}>{t('page.next')}</button></div>}
      {!!unidentified && <p className="process-note">{t('process.unidentified', { count: count(unidentified, locale) })}</p>}
    </section>
  </>
}

function badge(process: Process) {
  if (process.status === 'Fehlgeschlagen') return 'error'
  if (process.status === 'Erfolgreich' || process.status === 'Erholt') return 'info'
  if (process.status === 'Läuft') return 'warn'
  return ''
}

function ProcessDetails({ id, process, open }: { id: string; process: Process; open: (id: number) => void }) {
  const { language, t } = useI18n()
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const [errorsOnly, setErrorsOnly] = useState(false)
  const [visible, setVisible] = useState(50)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (process) heading.current?.focus() }, [process])
  const list = errorsOnly ? process.errors : process.logs
  return <section id={id} className="panel process-details process-details-inline" aria-label={t('process.logs')}>
    <h2 ref={heading} tabIndex={-1}>{t('process.logsHeading', { job: process.job || process.trace })}</h2>
    <p>{process.hosts.join(', ')}{process.trace ? ' · ' + t('incident.trace', { trace: process.trace }) : ''}</p>
    <p>{t('process.observedPeriod')} · {date(process.first, locale)} – {date(process.last, locale)}</p>
    {process.errors.length > 0 && <div className="process-alert"><strong>{t('process.firstError')}</strong><br />
      <button className="link" onClick={() => open(process.errors[0].id)}>{process.errors[0].host} · {process.errors[0].component} · {process.errors[0].message}</button></div>}
    <button className="secondary" aria-pressed={errorsOnly} onClick={() => { setErrorsOnly(value => !value); setVisible(50) }}>{errorsOnly ? t('process.allLogs') : t('process.onlyErrors')}</button>
    {list.length === 0 && <p>{t('process.noErrors')}</p>}
    <ul className="process-logs">{list.slice(0, visible).map(entry => <li key={entry.id}><small>{date(entry.ts_utc, locale)} UTC · {entry.host} · {entry.component} · {entry.level}</small><button className="link" onClick={() => open(entry.id)}>{entry.message}</button></li>)}</ul>
    {visible < list.length && <button className="secondary" onClick={() => setVisible(value => value + 50)}>{t('process.moreLogs')}</button>}
  </section>
}



