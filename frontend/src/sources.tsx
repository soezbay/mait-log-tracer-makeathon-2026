import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Feedback, useAnalysis } from './data'
import { useI18n } from './i18n'
import { InfoTip, PageTitle } from './ui'

// Where the data comes from: servers, formats and every log file (GET /api/sources…). Live mode only.

type Server = {
  server: string; os: string | null; role: string | null; files: number; copies: number; events: number; duplicate_events: number
  unparsed_events: number; errors: number; bytes: number; formats: string[]; first_ts: string | null; last_ts: string | null
}
type Format = { format: string; files: number; copies: number; events: number }
type Summary = { servers: Server[]; formats: Format[] }
type Source = { source_id: number; path: string; server: string; format: string | null; encoding: string | null; compressed: boolean; size: number | null; duplicate_of: number | null; event_count: number; original_path: string | null; copies: number }
type SourcePage = { items: Source[]; total: number }

const PAGE_SIZE = 25
const FORMAT_NAMES: Record<string, string> = { kv_log: 'key=value (.log)', bracket_json: 'Text + JSON (.txt)', csv_semicolon: 'CSV (.csv)', jsonl: 'JSON Lines (.jsonl, .gz)', xml_events: 'XML (.xml)', freetext: 'Text (import_*.log)' }
const formatName = (format: string | null) => format ? FORMAT_NAMES[format] ?? format : '—'
const day = (timestamp: string | null) => timestamp ? timestamp.slice(0, 10) : '—'
const sum = <T,>(items: T[], value: (item: T) => number) => items.reduce((total, item) => total + value(item), 0)

function size(bytes: number, locale: string) {
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes, unit = 0
  while (value >= 1000 && unit < units.length - 1) { value /= 1000; unit++ }
  return value.toLocaleString(locale, { maximumFractionDigits: unit ? 1 : 0 }) + ' ' + units[unit]
}

export function SourcesPage() {
  const { language, t } = useI18n()
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const number = (value: number) => value.toLocaleString(locale)
  const summary = useAnalysis<Summary>('/sources/summary')
  const [filters, setFilters] = useState({ server: '', format: '', kind: '', q: '' })
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  function set(field: keyof typeof filters, value: string) {
    setFilters(previous => previous[field] === value ? previous : { ...previous, [field]: value })
    setPage(0)
  }
  useEffect(() => {
    const timer = setTimeout(() => set('q', search.trim()), 300)
    return () => clearTimeout(timer)
  }, [search])
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(page * PAGE_SIZE) })
  for (const field of ['server', 'format', 'q'] as const) if (filters[field]) query.set(field, filters[field])
  if (filters.kind) query.set('duplicates', filters.kind)
  const files = useAnalysis<SourcePage>('/sources?' + query, true)
  const servers = summary.data?.servers ?? [], formats = summary.data?.formats ?? []
  const most = Math.max(1, ...formats.map(format => format.files))
  return <>
    <PageTitle title={t('sources.title')} info={t('sources.info')} />
    <Feedback {...summary} />
    {summary.data && <>
      <div className="metrics source-metrics">{[
        [t('sources.servers'), servers.length], [t('sources.files'), sum(servers, s => s.files)], [t('sources.originals'), sum(servers, s => s.files - s.copies)], [t('sources.copies'), sum(servers, s => s.copies)],
        [t('metric.events'), sum(servers, s => s.events)], [t('sources.duplicateLines'), sum(servers, s => s.duplicate_events)], [t('sources.unparsed'), sum(servers, s => s.unparsed_events)],
      ].map(([label, value]) => <section className="metric" key={label}><span>{label}</span><strong>{number(Number(value))}</strong></section>)}</div>
      <section className="panel"><h2>{t('sources.formats')} <InfoTip text={t('sources.formatsInfo')} /></h2>
        <ul className="format-list">{formats.map(format => <li key={format.format}><button type="button" className="secondary" aria-pressed={filters.format === format.format} onClick={() => set('format', filters.format === format.format ? '' : format.format)}>
          <span className="format-name">{formatName(format.format)}</span>
          <span className="format-bar" aria-hidden="true"><span style={{ width: (format.files - format.copies) / most * 100 + '%' }} /><span className="copy" style={{ width: format.copies / most * 100 + '%' }} /></span>
          <small>{t('sources.formatLine', { originals: number(format.files - format.copies), copies: number(format.copies), events: number(format.events) })}</small></button></li>)}</ul>
        <p className="format-legend"><span className="dot" /> {t('sources.originals')} <span className="dot copy" /> {t('sources.copies')}</p></section>
      <section className="panel"><h2>{t('sources.servers')} <InfoTip text={t('sources.serversInfo')} /></h2>
        <div className="table"><table className="source-table"><thead><tr><th>{t('filter.server')}</th><th>{t('sources.os')}</th><th>{t('sources.role')}</th><th>{t('sources.files')}</th><th>{t('sources.copies')}</th><th>{t('metric.events')}</th><th>{t('sources.duplicateLines')}</th><th>{t('sources.errors')}</th><th>{t('sources.size')}</th><th>{t('incidents.period')}</th></tr></thead>
          <tbody>{servers.map(server => <tr key={server.server} className={filters.server === server.server ? 'is-selected' : ''}><td><button type="button" className="link" aria-pressed={filters.server === server.server} onClick={() => set('server', filters.server === server.server ? '' : server.server)}>{server.server}</button></td>
            <td>{server.os ?? '—'}</td><td>{server.role ?? '—'}</td><td>{number(server.files)}</td><td>{number(server.copies)}</td><td><Link to={'/timeline?server=' + encodeURIComponent(server.server)}>{number(server.events)}</Link></td><td>{number(server.duplicate_events)}</td><td>{number(server.errors)}</td><td>{size(server.bytes, locale)}</td><td>{day(server.first_ts)}<small>{day(server.last_ts)}</small></td></tr>)}</tbody></table></div></section>
    </>}
    <section className="panel"><h2>{t('sources.fileList')} {files.data && <small>{number(files.data.total)}</small>}</h2>
      <div className="filters">
        <label>{t('sources.path')}<input value={search} onChange={event => setSearch(event.target.value)} placeholder={t('sources.searchPlaceholder')} /></label>
        <label>{t('filter.server')}<select value={filters.server} onChange={event => set('server', event.target.value)}><option value="">{t('process.allServers')}</option>{servers.map(server => <option key={server.server}>{server.server}</option>)}</select></label>
        <label>{t('sources.format')}<select value={filters.format} onChange={event => set('format', event.target.value)}><option value="">{t('sources.allFormats')}</option>{formats.map(format => <option key={format.format} value={format.format}>{formatName(format.format)}</option>)}</select></label>
        <label>{t('sources.kind')}<select value={filters.kind} onChange={event => set('kind', event.target.value)}><option value="">{t('sources.allFiles')}</option><option value="false">{t('sources.onlyOriginals')}</option><option value="true">{t('sources.onlyCopies')}</option></select></label>
      </div>
      <Feedback pending={files.pending && !files.data} error={files.error} />
      {files.data && !files.data.items.length && <p className="notice">{t('sources.none')}</p>}
      {!!files.data?.items.length && <div className="table"><table className="file-table" aria-busy={files.pending}><thead><tr><th>{t('sources.path')}</th><th>{t('sources.format')}</th><th>{t('sources.size')}</th><th>{t('metric.events')}</th><th>{t('sources.kind')}</th></tr></thead>
        <tbody>{files.data.items.map(file => <tr key={file.source_id}>
          <td>{file.path}{file.original_path && <small>{t('sources.identicalTo', { path: file.original_path.split('/').at(-1) ?? '' })}</small>}</td>
          <td>{formatName(file.format)}<small>{[file.encoding, file.compressed && 'gzip'].filter(Boolean).join(' · ')}</small></td>
          <td>{file.size === null ? '—' : size(file.size, locale)}</td>
          <td>{file.duplicate_of === null ? <Link to={'/timeline?' + new URLSearchParams({ source_id: String(file.source_id), source: file.path })}>{number(file.event_count)}</Link> : '—'}</td>
          <td>{file.duplicate_of !== null ? <span className="badge">{t('sources.copy')}</span> : <><span className="badge ok">{t('sources.original')}</span>{file.copies > 0 && <small>{t('sources.copyCount', { count: number(file.copies) })}</small>}</>}</td>
        </tr>)}</tbody></table></div>}
      {files.data && files.data.total > PAGE_SIZE && <div className="actions job-pager"><button type="button" className="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>{t('page.previous')}</button>
        <span>{t('jobs.range', { from: number(page * PAGE_SIZE + 1), to: number(Math.min(files.data.total, (page + 1) * PAGE_SIZE)), total: number(files.data.total) })}</span>
        <button type="button" className="secondary" disabled={(page + 1) * PAGE_SIZE >= files.data.total} onClick={() => setPage(page + 1)}>{t('page.next')}</button></div>}
    </section>
  </>
}
