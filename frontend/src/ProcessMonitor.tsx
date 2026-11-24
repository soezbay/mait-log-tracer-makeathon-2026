import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import type { Entry } from './demo'
import { buildProcesses } from './processes'
import type { Process } from './processes'

const date = (value?: string) => value ? value.replace('T', ' ').replace(/(?:\.000)?Z$/, '') : '—'
const count = (number: number) => number.toLocaleString('de-DE')
function duration(ms: number) {
  if (ms < 1000) return count(ms) + ' ms'
  if (ms < 60000) return (ms / 1000).toLocaleString('de-DE', { maximumFractionDigits: 2 }) + ' s'
  return Math.floor(ms / 60000) + ' min ' + Math.floor(ms / 1000 % 60) + ' s'
}

export function ProcessMonitor({ events, open }: { events: Entry[]; open: (id: number) => void }) {
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
    const lower = from ? Date.parse(from + 'Z') : -Infinity
    const upper = to ? Date.parse(to + 'Z') : Infinity
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
  }, [processes, search, host, workflow, status, kind, from, to, sort])
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

  return <>
    <div className="metrics process-metrics">
      {[
        ['Aufträge', count(filtered.length), count(filtered.filter(process => process.conversion).length) + ' als Konvertierung erkannt'],
        ['Durchschnittliche Dauer', mean === undefined ? '—' : duration(mean), count(withDuration.length) + ' mit belegter Dauer'],
        ['Fehlgeschlagen', count(filtered.filter(process => process.status === 'Fehlgeschlagen').length), count(filtered.filter(process => process.status === 'Erholt').length) + ' erholt'],
        ['Beteiligte Server', count(new Set(filtered.flatMap(process => process.hosts)).size), 'in den gefilterten Aufträgen'],
      ].map(([label, value, detail]) => <section className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>{detail}</small></section>)}
    </div>
    <section className="panel process-panel">
      <h2>Aufträge und Workflows</h2>
      <div className="filters process-filters">
        <label>Auftrag oder Trace<input value={search} onChange={e => filter(setSearch, e.target.value)} placeholder="Job-ID oder Workflow suchen" /></label>
        <label>Workflow-Vorlage<select value={workflow} onChange={e => filter(setWorkflow, e.target.value)}><option value="">Alle Vorlagen</option>{workflows.map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Server<select value={host} onChange={e => filter(setHost, e.target.value)}><option value="">Alle Server</option>{hosts.map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Status<select value={status} onChange={e => filter(setStatus, e.target.value)}><option value="">Alle Status</option>{['Läuft', 'Erfolgreich', 'Erholt', 'Fehlgeschlagen', 'Unklar'].map(value => <option key={value}>{value}</option>)}</select></label>
        <label>Auftragstyp<select value={kind} onChange={e => filter(setKind, e.target.value)}><option value="">Alle Aufträge</option><option value="conversion">Konvertierungen</option></select></label>
        <label>Von (UTC)<input type="datetime-local" value={from} onChange={e => filter(setFrom, e.target.value)} /></label>
        <label>Bis (UTC)<input type="datetime-local" value={to} onChange={e => filter(setTo, e.target.value)} /></label>
        <label>Sortieren nach<select value={sort} onChange={e => filter(setSort, e.target.value)}><option value="recent">Letztes Log · neueste zuerst</option><option value="oldest">Erstes Log · älteste zuerst</option><option value="duration">Dauer · längste zuerst</option><option value="errors">Fehleranzahl · höchste zuerst</option><option value="job">Auftrags-ID</option></select></label>
      </div>
      {!filtered.length ? <p className="notice">{processes.length ? 'Keine Aufträge für diese Filter.' : 'In diesen Logs wurden keine Job- oder Trace-IDs gefunden. Alle erkannten Ereignisse sind in der Zeitleiste sichtbar.'}</p> :
        <div className="table process-table-scroll" role="region" aria-label="Auftragsliste" tabIndex={0}><table><thead><tr><th>Auftrag / Vorlage</th><th>Status</th><th>Start / Ende (UTC)</th><th>Dauer</th><th>Server</th><th>Protokolle</th></tr></thead>
          <tbody>{filtered.slice((current - 1) * pageSize, current * pageSize).map(process => <Fragment key={process.key}>
            <tr>
              <td><strong>{process.job || process.trace}</strong><small>{process.workflow || (process.conversion ? 'Konvertierung' : 'Vorlage unbekannt')}</small></td>
              <td><span className={'badge ' + badge(process)}>{process.status}</span></td>
              <td>{date(process.start)}<small>{date(process.end)}</small></td>
              <td>{process.duration === undefined ? '—' : duration(process.duration)}{process.durationSource && <small>{process.durationSource}</small>}</td>
              <td>{process.hosts[0]}{process.hosts.length > 1 && <small>+{process.hosts.length - 1} weitere</small>}</td>
              <td><button className="link" aria-expanded={selected === process.key} aria-controls={'process-details-' + process.key} onClick={() => setSelected(previous => previous === process.key ? null : process.key)}>{count(process.logs.length)} Logs</button>{!!process.errors.length && <small>{count(process.errors.length)} Fehlerereignisse</small>}</td>
            </tr>
            {selected === process.key && <tr className="process-expanded-row"><td colSpan={6}><ProcessDetails id={'process-details-' + process.key} process={process} open={open} /></td></tr>}
          </Fragment>)}</tbody></table></div>}
      {maxPage > 1 && <div className="actions"><button className="secondary" disabled={current <= 1} onClick={() => setPage(current - 1)}>Zurück</button><span>Seite {current} von {maxPage}</span><button className="secondary" disabled={current >= maxPage} onClick={() => setPage(current + 1)}>Weiter</button></div>}
      {!!unidentified && <p className="process-note">{count(unidentified)} Logs ohne Job- oder Trace-ID sind über die Zeitleiste verfügbar.</p>}
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
  const [errorsOnly, setErrorsOnly] = useState(false)
  const [visible, setVisible] = useState(50)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (process) heading.current?.focus() }, [process])
  const list = errorsOnly ? process.errors : process.logs
  return <section id={id} className="panel process-details process-details-inline" aria-label="Auftragsprotokolle">
    <h2 ref={heading} tabIndex={-1}>Protokolle · {process.job || process.trace}</h2>
    <p>{process.hosts.join(', ')}{process.trace ? ' · Trace ' + process.trace : ''}</p>
    <p>Beobachteter Zeitraum (UTC) · {date(process.first)} bis {date(process.last)}</p>
    {process.errors.length > 0 && <div className="process-alert"><strong>Erstes Fehlerereignis</strong><br />
      <button className="link" onClick={() => open(process.errors[0].id)}>{process.errors[0].host} · {process.errors[0].component} · {process.errors[0].message}</button></div>}
    <button className="secondary" aria-pressed={errorsOnly} onClick={() => { setErrorsOnly(value => !value); setVisible(50) }}>{errorsOnly ? 'Alle Protokolle' : 'Nur Fehlerereignisse'}</button>
    {list.length === 0 && <p>Keine Fehlerereignisse in diesem Auftrag.</p>}
    <ul className="process-logs">{list.slice(0, visible).map(entry => <li key={entry.id}><small>{date(entry.ts_utc)} UTC · {entry.host} · {entry.component} · {entry.level}</small><button className="link" onClick={() => open(entry.id)}>{entry.message}</button></li>)}</ul>
    {visible < list.length && <button className="secondary" onClick={() => setVisible(value => value + 50)}>Weitere Protokolle anzeigen</button>}
  </section>
}



