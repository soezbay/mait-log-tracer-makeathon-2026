import { useMemo, useState } from 'react'
import type { Entry } from './demo'
import type { Process } from './processes'

import { describeError, incidentEvidence } from './incident'

const time = (entry: Entry) => (entry.ts_utc.split('T')[1] ?? entry.ts_utc).replace(/(?:\.000)?Z$/, '') + ' UTC'

export function IncidentDetail({ selected, process, onSelect, children }: {
  selected: Entry; process?: Process; onSelect: (id: number) => void; children: React.ReactNode
}) {
  const events = process?.logs ?? [selected]
  const { errors, error, preceding, previousLog, following } = useMemo(() => incidentEvidence(selected, events), [selected, events])
  const interpretation = error && describeError(error, preceding)
  const [extra, setExtra] = useState(0)
  const selectedIndex = events.findIndex(entry => entry.id === selected.id)
  const important = new Set([selected.id, error?.id, preceding?.id, previousLog?.id, following?.id])
  const visible = events.length <= 35
    ? events
    : events.filter((entry, index) => Math.abs(index - selectedIndex) <= 7 + extra || important.has(entry.id))
  const indices = new Map(events.map((entry, index) => [entry.id, index]))
  const source = process?.trace ? 'Trace ' + process.trace : process?.job ? 'Auftrag ' + process.job + ' · je Server' : 'Einzelereignis'
  return <div className="incident-detail">
    <aside className="incident-rail" aria-label="Zeitstrahl der zusammenhängenden Logs">
      <h3>Zeitstrahl</h3>
      <p>{source} · {events.length.toLocaleString('de-DE')} Logs</p>
      <ol className="incident-timeline">
        {visible.map((entry, index) => <li key={entry.id} className={[
          entry.id === selected.id ? 'is-selected' : '',
          entry.id === error?.id ? 'is-incident' : '',
          entry.id === preceding?.id || entry.id === previousLog?.id ? 'is-prior' : '',
          entry.id === following?.id ? 'is-following' : '',
        ].join(' ')}>
          {index > 0 && indices.get(entry.id)! - indices.get(visible[index - 1].id)! > 1 && <small className="incident-gap">Weitere Logs dazwischen</small>}
          <button type="button" aria-current={entry.id === selected.id ? 'true' : undefined} onClick={() => onSelect(entry.id)}>
            <small>{time(entry)} · {entry.host}</small>
            <span>{entry.message}</span>
            <small className="incident-tag">{[
              entry.id === selected.id && 'Ausgewählt',
              entry.id === error?.id && 'Bezugsfehler',
              entry.id === preceding?.id && 'Vorheriger Fehler',
              entry.id === previousLog?.id && 'Direkt davor',
              entry.id === following?.id && 'Folgeereignis',
            ].filter(Boolean).join(' · ') || entry.level}</small>
          </button>
        </li>)}
      </ol>
      {visible.length < events.length && <button type="button" className="secondary" onClick={() => setExtra(value => value + 25)}>Weitere Logs anzeigen</button>}
    </aside>
    <div className="incident-explanation">
      <h3>Fehleranalyse</h3>
      {error ? <>
        <p className="incident-summary"><strong>{error.id === selected.id ? 'Ausgewählter Fehler' : 'Zugehöriger Fehler'}</strong><br />{error.message}</p>
        <p>Der Fehler wurde um {time(error)} von <strong>{error.host}</strong>{error.component ? ' (' + error.component + ')' : ''} gemeldet.</p>
        {interpretation && <p><strong>Was der Fehler bedeutet.</strong> {interpretation}</p>}
        {preceding && <p><strong>Möglicher Auslöser.</strong> Zuvor meldete {preceding.host}{preceding.component ? ' (' + preceding.component + ')' : ''} einen Fehler: <button type="button" className="link" onClick={() => onSelect(preceding.id)}>{preceding.message}</button>. Die Reihenfolge und der gemeinsame {process?.trace ? 'Trace' : 'Auftrag'} geben einen Hinweis auf einen Zusammenhang.</p>}
        {previousLog && previousLog.id !== preceding?.id && <p><strong>Direkt davor.</strong> {previousLog.host} protokollierte <button type="button" className="link" onClick={() => onSelect(previousLog.id)}>{previousLog.message}</button>.</p>}
        {following && <p><strong>Danach.</strong> {following.host} protokollierte <button type="button" className="link" onClick={() => onSelect(following.id)}>{following.message}</button>.</p>}
        <p className="incident-note">{preceding ? 'Die Ursache bleibt eine Hypothese und lässt sich anhand der Originalzeilen prüfen.' : 'Aus den verfügbaren Einträgen lässt sich kein früherer Fehler als Auslöser ableiten.'}{errors.length > 1 ? ' Der Zeitstrahl enthält mehrere Fehlerereignisse.' : ''}</p>
      </> : <p>Für diese Meldung ist im zugeordneten Verlauf kein Fehlerereignis belegt.</p>}
      <h3>Originalprotokoll der Auswahl</h3>
      {children}
    </div>
  </div>
}



