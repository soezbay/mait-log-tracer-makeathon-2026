import { useMemo, useState } from 'react'
import type { Entry } from './demo'
import type { Process } from './processes'

import { describeError, incidentEvidence } from './incident'
import { useI18n } from './i18n'

const time = (entry: Entry, locale: string) => new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date(entry.ts_utc)) + ' UTC'

export function IncidentDetail({ selected, process, onSelect, children }: {
  selected: Entry; process?: Process; onSelect: (id: number) => void; children: React.ReactNode
}) {
  const { language, t } = useI18n()
  const locale = language === 'en' ? 'en-GB' : 'de-DE'
  const events = process?.logs ?? [selected]
  const { errors, error, preceding, previousLog, following } = useMemo(() => incidentEvidence(selected, events), [selected, events])
  const interpretation = error && describeError(error, preceding, language)
  const [extra, setExtra] = useState(0)
  const selectedIndex = events.findIndex(entry => entry.id === selected.id)
  const important = new Set([selected.id, error?.id, preceding?.id, previousLog?.id, following?.id])
  const visible = events.length <= 35
    ? events
    : events.filter((entry, index) => Math.abs(index - selectedIndex) <= 7 + extra || important.has(entry.id))
  const indices = new Map(events.map((entry, index) => [entry.id, index]))
  const source = process?.trace ? t('incident.trace', { trace: process.trace }) : process?.job ? t('incident.jobPerServer', { job: process.job }) : t('incident.singleEvent')
  return <div className="incident-detail">
    <aside className="incident-rail" aria-label={t('incident.timeline')}>
      <h3>{t('timeline.title')}</h3>
      <p>{source} · {events.length.toLocaleString(locale)} {t('process.logs')}</p>
      <ol className="incident-timeline">
        {visible.map((entry, index) => <li key={entry.id} className={[
          entry.id === selected.id ? 'is-selected' : '',
          entry.id === error?.id ? 'is-incident' : '',
          entry.id === preceding?.id || entry.id === previousLog?.id ? 'is-prior' : '',
          entry.id === following?.id ? 'is-following' : '',
        ].join(' ')}>
          {index > 0 && indices.get(entry.id)! - indices.get(visible[index - 1].id)! > 1 && <small className="incident-gap">{t('incident.moreBetween')}</small>}
          <button type="button" aria-current={entry.id === selected.id ? 'true' : undefined} onClick={() => onSelect(entry.id)}>
            <small>{time(entry, locale)} · {entry.host}</small>
            <span>{entry.message}</span>
            <small className="incident-tag">{[
              entry.id === selected.id && t('incident.selected'),
              entry.id === error?.id && t('incident.relatedError'),
              entry.id === preceding?.id && t('incident.previousError'),
              entry.id === previousLog?.id && t('incident.directlyBefore'),
              entry.id === following?.id && t('incident.following'),
            ].filter(Boolean).join(' · ') || entry.level}</small>
          </button>
        </li>)}
      </ol>
      {visible.length < events.length && <button type="button" className="secondary" onClick={() => setExtra(value => value + 25)}>{t('incident.moreLogs')}</button>}
    </aside>
    <div className="incident-explanation">
      <h3>{t('incident.analysis')}</h3>
      {error ? <>
        <p className="incident-summary"><strong>{error.id === selected.id ? t('incident.selectedError') : t('incident.relatedError')}</strong><br />{error.message}</p>
        <p>{t('incident.reportedAt', { time: time(error, locale) })} <strong>{error.host}</strong>{error.component ? ' (' + error.component + ')' : ''}.</p>
        {interpretation && <p><strong>{t('incident.meaning')}</strong> {interpretation}</p>}
        {preceding && <p><strong>{t('incident.possibleCause')}</strong> {t('incident.before')} {preceding.host}{preceding.component ? ' (' + preceding.component + ')' : ''} {language === 'en' ? 'reported an error:' : 'einen Fehler:'} <button type="button" className="link" onClick={() => onSelect(preceding.id)}>{preceding.message}</button>. {t('incident.sequenceLink', { relation: t(process?.trace ? 'incident.relationTrace' : 'incident.relationJob') })}</p>}
        {previousLog && previousLog.id !== preceding?.id && <p><strong>{t('incident.directlyBeforeLabel')}</strong> {previousLog.host} {language === 'en' ? 'logged' : 'protokollierte'} <button type="button" className="link" onClick={() => onSelect(previousLog.id)}>{previousLog.message}</button>.</p>}
        {following && <p><strong>{t('incident.after')}</strong> {following.host} {language === 'en' ? 'logged' : 'protokollierte'} <button type="button" className="link" onClick={() => onSelect(following.id)}>{following.message}</button>.</p>}
        <p className="incident-note">{preceding ? t('incident.hypothesisNote') : t('incident.noCauseNote')}{errors.length > 1 ? ' ' + t('incident.multipleErrors') : ''}</p>
      </> : <p>{t('incident.noError')}</p>}
      <h3>{t('incident.originalLog')}</h3>
      {children}
    </div>
  </div>
}



