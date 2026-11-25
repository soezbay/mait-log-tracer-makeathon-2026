import { useContext, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Feedback, firstLine, formatTime, useAnalysis } from './data'
import { useI18n } from './i18n'
import { InfoTip, LevelBadge, PageTitle, StatusBadge } from './ui'
import { AssistantLinkContext, EventQuestions } from './suggestions'

// Incidents: connected problems across servers, calculated by the backend (GET /api/analysis/…).

type Page<T> = { items: T[]; total: number; limit: number; offset: number }
export type Incident = {
  incident_id: number; title: string | null; first_ts: string | null; last_ts: string | null; status: string | null
  hosts: string[]; confidence: number | null; group_count: number; event_count: number
  root_host: string | null; root_component: string | null; root_level: string | null; root_event_id: number | null
  jobs: { job_id: string; runs: number }[]
}
type Step = {
  group_id: number; is_root: boolean; host: string | null; component: string | null; level: string | null; status: string | null
  count: number; first_ts: string | null; last_ts: string | null; event_id: number | null; message: string | null
  job_id: string | null; clock_offset_s: number | null; source_path: string | null; line_start: number | null
}
type StepLink = { group_a: number; group_b: number; kind: string; link_key: string; lag_s: number }
type Anomaly = { anomaly_id: number; host: string | null; component: string | null; window_start: string | null; window_end: string | null; score: number | null; details: { observed_errors?: number; threshold?: number } }
type IncidentDetail = Incident & { steps: Step[]; links: StepLink[]; anomalies: Anomaly[] }

const shortHost = (host: string | null) => (host ?? '').replace(/^mait_/, '')
const clock = (timestamp: string | null) => timestamp ? timestamp.slice(11).replace(/(\.\d+)?Z$/, '') : '—'
const day = (timestamp: string | null) => timestamp ? timestamp.slice(0, 10) : '—'

function seconds(value: number, locale: string) {
  const rounded = Math.abs(value) < 10 ? Math.round(value * 10) / 10 : Math.round(value)
  if (Math.abs(rounded) < 120) return rounded.toLocaleString(locale) + ' s'
  return Math.round(value / 60).toLocaleString(locale) + ' min'
}

function useLocale() {
  const { language } = useI18n()
  return language === 'en' ? 'en-GB' : 'de-DE'
}

/** How the problems of an incident are connected, from the heuristic score of the backend. */
function relationKey(incident: Incident) {
  const score = incident.confidence ?? 0
  if (incident.group_count === 1) return 'incidents.relationSingle' as const
  if (score >= 0.9) return 'incidents.relationDependency' as const
  return score >= 0.7 ? 'incidents.relationId' as const : 'incidents.relationTime' as const
}

function IncidentMeta({ incident }: { incident: Incident }) {
  const { t } = useI18n()
  const locale = useLocale()
  const job = incident.jobs[0]
  return <span className="incident-meta">
    <span>{shortHost(incident.root_host)} · {incident.root_component}</span>
    {incident.hosts.length > 1 && <span>{t('incidents.servers', { count: incident.hosts.length })}</span>}
    <span>{t(incident.group_count === 1 ? 'incidents.step' : 'incidents.steps', { count: incident.group_count })}</span>
    {incident.event_count > incident.group_count && <span>{t('incidents.entries', { count: incident.event_count.toLocaleString(locale) })}</span>}
    {job && <span>{job.job_id}{job.runs > 1 ? ' · ' + t('incidents.runs', { count: job.runs }) : ''}{incident.jobs.length > 1 ? ' +' + (incident.jobs.length - 1) : ''}</span>}
  </span>
}

function IncidentRow({ incident }: { incident: Incident }) {
  return <li><Link className="incident-row" to={'/incidents/' + incident.incident_id}>
    <span className="incident-time">{clock(incident.first_ts)}</span>
    <StatusBadge status={incident.status} />
    <span className="incident-title"><strong>{incident.title}</strong><IncidentMeta incident={incident} /></span>
  </Link></li>
}

export function IncidentsPage() {
  const { t } = useI18n()
  const result = useAnalysis<Page<Incident>>('/analysis/incidents?limit=500')
  const [text, setText] = useState('')
  const [server, setServer] = useState('')
  const [status, setStatus] = useState('')
  const all = result.data?.items ?? []
  const servers = useMemo(() => [...new Set(all.flatMap(incident => incident.hosts))].sort(), [all])
  const term = text.trim().toLowerCase()
  const shown = all.filter(incident =>
    (!server || incident.hosts.includes(server))
    && (!status || (incident.status ?? 'unknown') === status)
    && (!term || [incident.title ?? '', incident.root_component ?? '', ...incident.hosts, ...incident.jobs.map(job => job.job_id)].some(value => value.toLowerCase().includes(term))))
  const days = [...new Set(shown.map(incident => day(incident.first_ts)))]
  return <>
    <PageTitle title={t('incidents.title')} info={t('incidents.info')}>{result.data && <small>{t('incidents.shown', { shown: shown.length, total: result.data.total })}</small>}</PageTitle>
    <div className="panel filters incident-filters">
      <label>{t('filter.text')}<input value={text} onChange={event => setText(event.target.value)} placeholder={t('incidents.searchPlaceholder')} /></label>
      <label>{t('filter.server')}<select value={server} onChange={event => setServer(event.target.value)}><option value="">{t('process.allServers')}</option>{servers.map(value => <option key={value}>{value}</option>)}</select></label>
      <label>{t('process.status')}<select value={status} onChange={event => setStatus(event.target.value)}><option value="">{t('process.allStatuses')}</option><option value="failed">{t('incidents.failed')}</option><option value="recovered">{t('incidents.recovered')}</option><option value="unknown">{t('incidents.unknown')}</option></select></label>
    </div>
    <Feedback {...result} />
    {result.data && !shown.length && <p className="notice">{t(all.length ? 'incidents.noMatch' : 'incidents.none')}</p>}
    {days.map(date => <section className="panel incident-day" key={date}><h2>{date}</h2>
      <ul className="incident-list">{shown.filter(incident => day(incident.first_ts) === date).map(incident => <IncidentRow key={incident.incident_id} incident={incident} />)}</ul></section>)}
  </>
}

/** The newest incidents for the start page. */
export function LatestIncidents() {
  const { t } = useI18n()
  const { data } = useAnalysis<Page<Incident>>('/analysis/incidents?limit=5')
  if (!data?.items?.length) return null
  return <section className="panel"><div className="section-title"><h2>{t('incidents.latest')} <InfoTip text={t('incidents.info')} /></h2><Link to="/incidents">{t('incidents.showAll', { count: data.total })}</Link></div>
    <ul className="incident-list">{data.items.map(incident => <li key={incident.incident_id}><Link className="incident-row" to={'/incidents/' + incident.incident_id}>
      <span className="incident-time">{day(incident.first_ts)}<br />{clock(incident.first_ts)}</span>
      <StatusBadge status={incident.status} />
      <span className="incident-title"><strong>{incident.title}</strong><IncidentMeta incident={incident} /></span>
    </Link></li>)}</ul></section>
}

/** Shown with an event: the incident it belongs to. */
export function EventIncident({ eventId, close }: { eventId: number; close: () => void }) {
  const { t } = useI18n()
  const { data } = useAnalysis<Page<Incident>>('/analysis/incidents?event_id=' + eventId)
  const incident = data?.items?.[0]
  if (!incident) return null
  return <section className="event-card"><h3>{t('incidents.partOf')}</h3>
    <Link to={'/incidents/' + incident.incident_id} onClick={close}><strong>{incident.title}</strong></Link>
    <p><StatusBadge status={incident.status} /> <IncidentMeta incident={incident} /></p></section>
}

/** Unusual error rates as shortcuts into the timeline. */
export function AnomalyStrip({ server, from, to, select }: { server: string; from: string | null; to: string | null; select: (server: string, from: string, to: string) => void }) {
  const { t } = useI18n()
  const locale = useLocale()
  const query = new URLSearchParams({ limit: '12' })
  if (server) query.set('server', server)
  if (from) query.set('from', from)
  if (to) query.set('to', to)
  const { data } = useAnalysis<Page<Anomaly>>('/analysis/anomalies?' + query)
  if (!data?.items?.length) return null
  return <section className="panel anomaly-strip"><h2>{t('anomalies.title')} <InfoTip text={t('anomalies.info')} /></h2>
    <div className="anomaly-list">{data.items.map(anomaly => <button type="button" className="secondary" key={anomaly.anomaly_id}
      onClick={() => select(anomaly.host ?? '', anomaly.window_start ?? '', anomaly.window_end ?? '')}>
      {shortHost(anomaly.host)} · {anomaly.component}<small>{day(anomaly.window_start)} {clock(anomaly.window_start).slice(0, 5)}–{clock(anomaly.window_end).slice(0, 5)} UTC · {t('anomalies.errors', { count: (anomaly.details.observed_errors ?? 0).toLocaleString(locale) })}</small>
    </button>)}</div></section>
}

/** Small picture of one incident: one row per server, the steps from left to right. */
function IncidentGraph({ incident, open }: { incident: IncidentDetail; open: (id: number) => void }) {
  const { t } = useI18n()
  const locale = useLocale()
  const hosts = [...new Set(incident.steps.map(step => step.host ?? ''))]
  if (incident.steps.length < 2 || hosts.length < 2) return null
  const label = 200, gap = Math.max(85, Math.min(170, 500 / incident.steps.length)), row = 54
  const width = label + incident.steps.length * gap + 20, height = hosts.length * row + 16
  const position = new Map(incident.steps.map((step, index) => [step.group_id, { x: label + 30 + index * gap, y: 8 + hosts.indexOf(step.host ?? '') * row + row / 2, index }]))
  // All links of a small incident, only neighbouring steps of a large one.
  const links = incident.links.filter(link => {
    const a = position.get(link.group_a), b = position.get(link.group_b)
    return a && b && (incident.steps.length <= 5 || Math.abs(a.index - b.index) === 1)
  })
  return <div className="incident-graph" tabIndex={0} role="region" aria-label={t('incidents.graph')}><svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
    <defs><marker id="incident-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 8 4 0 8z" className="graph-arrow" /></marker></defs>
    {hosts.map((host, index) => <g key={host}><line x1="0" x2={width} y1={8 + index * row + row / 2} y2={8 + index * row + row / 2} className="graph-lane" />
      <rect x="0" y={8 + index * row + row / 2 - 12} width={label - 20} height="24" className="graph-label-back" /><text x="4" y={8 + index * row + row / 2 + 5} className="graph-label">{shortHost(host)}</text></g>)}
    {links.map(link => {
      const a = position.get(link.group_a)!, b = position.get(link.group_b)!
      const bend = Math.abs(a.index - b.index) > 1 && a.y === b.y ? -26 : 0
      const dx = Math.sign(b.x - a.x) * 13
      return <path key={link.group_a + '-' + link.group_b} className={'graph-link ' + link.kind} markerEnd="url(#incident-arrow)"
        d={`M${a.x + dx} ${a.y} Q${(a.x + b.x) / 2} ${(a.y + b.y) / 2 + bend} ${b.x - dx} ${b.y}`}><title>{link.link_key + ' · ' + seconds(link.lag_s, locale)}</title></path>
    })}
    {incident.steps.map(step => {
      const { x, y } = position.get(step.group_id)!
      const text = clock(step.first_ts) + ' ' + step.host + ' ' + step.component + ': ' + firstLine(step.message ?? '')
      return <g key={step.group_id} className={'graph-node ' + (step.level ?? '').toLowerCase() + (step.is_root ? ' root' : '')} role="button" tabIndex={0} aria-label={text}
        onClick={() => step.event_id !== null && open(step.event_id)} onKeyDown={event => { if ((event.key === 'Enter' || event.key === ' ') && step.event_id !== null) { event.preventDefault(); open(step.event_id) } }}>
        <circle cx={x} cy={y} r="11" /><text x={x} y={y + 26} textAnchor="middle">{clock(step.first_ts)}</text><title>{text}</title></g>
    })}
  </svg></div>
}

function Chain({ incident, open }: { incident: IncidentDetail; open: (id: number) => void }) {
  const { t } = useI18n()
  const locale = useLocale()
  const start = Date.parse(incident.steps[0]?.first_ts ?? '')
  return <ol className="chain">{incident.steps.map((step, index) => {
    const offset = (Date.parse(step.first_ts ?? '') - start) / 1000
    return <li key={step.group_id} className={(step.is_root ? 'root ' : '') + (step.level ?? '').toLowerCase()}>
      <p className="chain-head"><strong>{clock(step.first_ts)}</strong>{index > 0 && Number.isFinite(offset) && <small>+{seconds(offset, locale)}</small>}
        <span>{step.host} · {step.component}</span><LevelBadge level={step.level ?? '—'} />
        {step.count > 1 && <span className="badge">× {step.count.toLocaleString(locale)}</span>}
        {step.is_root && <span className="badge root-badge">{t('incidents.trigger')}</span>}</p>
      <p>{step.event_id === null ? step.message : <button type="button" className="link" onClick={() => open(step.event_id!)}>{firstLine(step.message ?? '')}</button>}</p>
      <small>{step.source_path}{step.line_start !== null && ':' + step.line_start}{!!step.clock_offset_s && ' · ' + t('incidents.clockCorrected', { seconds: step.clock_offset_s.toLocaleString(locale) })}</small>
    </li>
  })}</ol>
}

export function IncidentPage({ open }: { open: (id: number) => void }) {
  const { t } = useI18n()
  const locale = useLocale()
  const { id } = useParams()
  const { ask, setContext } = useContext(AssistantLinkContext)
  const result = useAnalysis<IncidentDetail>('/analysis/incidents/' + encodeURIComponent(id ?? ''))
  const incident = result.data
  const rootEvent = incident?.root_event_id ?? null
  useEffect(() => { if (rootEvent !== null) setContext(rootEvent) }, [rootEvent, setContext])
  return <>
    <p className="back-link"><Link to="/incidents">← {t('incidents.title')}</Link></p>
    <Feedback {...result} />
    {incident && <>
      <PageTitle title={incident.title}><StatusBadge status={incident.status} /></PageTitle>
      <div className="incident-page">
        <div>
          <section className="panel"><h2>{t('incidents.chain')} <InfoTip text={t('incidents.chainInfo')} /></h2>
            <IncidentGraph incident={incident} open={open} />
            <Chain incident={incident} open={open} />
          </section>
        </div>
        <aside>
          <section className="panel"><h2>{t('incidents.overview')}</h2>
            <dl className="facts">
              <dt>{t('incidents.period')}</dt><dd>{formatTime(incident.first_ts ?? '')}{incident.last_ts !== incident.first_ts && <><br />– {formatTime(incident.last_ts ?? '')}</>}</dd>
              <dt>{t('incidents.triggerServer')}</dt><dd>{incident.root_host}<br />{incident.root_component}</dd>
              <dt>{t('process.serversInvolved')}</dt><dd>{incident.hosts.map(host => <span key={host}>{host}<br /></span>)}</dd>
              {incident.jobs.length > 0 && <><dt>{t('incidents.jobs')}</dt><dd>{incident.jobs.slice(0, 6).map(job => <span key={job.job_id}><Link to={'/timeline?job_id=' + encodeURIComponent(job.job_id)}>{job.job_id}</Link>{job.runs > 1 && ' · ' + t('incidents.runs', { count: job.runs })}<br /></span>)}{incident.jobs.length > 6 && '+' + (incident.jobs.length - 6)}</dd></>}
              <dt>{t('process.logs')}</dt><dd>{incident.event_count.toLocaleString(locale)}</dd>
              <dt>{t('incidents.relation')}</dt><dd>{t(relationKey(incident))}</dd>
            </dl>
            <p className="incident-note">{t('incidents.hypothesis')}</p>
          </section>
          <section className="panel"><button type="button" onClick={() => ask(t('incidents.question', { title: incident.title ?? '', host: incident.root_host ?? '', time: formatTime(incident.first_ts ?? '') }))}>{t('incidents.explain')}</button>
            {rootEvent !== null && <EventQuestions id={rootEvent} />}</section>
          {incident.anomalies.length > 0 && <section className="panel"><h2>{t('anomalies.title')} <InfoTip text={t('anomalies.info')} /></h2>
            <ul className="plain-list">{incident.anomalies.map(anomaly => <li key={anomaly.anomaly_id}>{shortHost(anomaly.host)} · {anomaly.component}<small>{clock(anomaly.window_start).slice(0, 5)}–{clock(anomaly.window_end).slice(0, 5)} UTC · {t('anomalies.errors', { count: (anomaly.details.observed_errors ?? 0).toLocaleString(locale) })}</small></li>)}</ul></section>}
        </aside>
      </div>
    </>}
  </>
}
