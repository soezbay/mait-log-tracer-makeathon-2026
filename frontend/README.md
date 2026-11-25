# Log Tracer – Frontend

React, TypeScript, Vite, Mantine und React Router für das MAIT-Makeathon-Projekt.

## Start

Node.js 22 oder 24 verwenden. Beim Start über HTTP/HTTPS öffnet die Anwendung direkt den Live-Modus und ruft das Backend ab. Über `Demo` bleiben die vorbereiteten Fälle verfügbar; beim Öffnen der HTML-Datei startet die Anwendung automatisch offline in der Demo.

English is the default language. Use **Settings** at the bottom of the sidebar to switch between English and German. The selection is saved in this browser.

```powershell
cd frontend
npm install
npm run dev
```

Die von Vite angezeigte Adresse öffnen. In der Demo sind drei getrennte Fälle vorbereitet: JOB-2003 (FMS-Schreibrecht trotz erfolgreicher Konvertierung), JOB-2010 (fehlende Baugruppenreferenz) und SYNC-312 (erfolgreicher Retry). Im Assistenten eine Frage auswählen und auf einen Beleg klicken, um die zugehörigen Quellzeilen zu sehen.

`npm run build` prüft TypeScript und erstellt `dist/`. `npm run preview` startet eine lokale Vorschau des Builds.

## Backend anbinden

FastAPI auf Port 8000 starten. Vite leitet Browser-Aufrufe unter `/api` an `http://localhost:8000` weiter; dadurch ist für die lokale Entwicklung kein CORS-Zugriff vom Browser auf einen zweiten Ursprung nötig. Für einen anderen Backend-Host die Datei `.env.example` nach `.env.local` kopieren und `VITE_API_TARGET` setzen. Vite nach Änderungen an `.env.local` neu starten. Bei produktivem Hosting `/api` am selben Ursprung an FastAPI weiterleiten.

Die Repo-Architektur beschreibt die Endpunkte und den strukturierten Chat-Output. Die folgenden REST-Felder sind Integrationsannahmen und lassen sich in `src/main.tsx` und `src/api.ts` an die FastAPI-Modelle anpassen.

| Pfad | Erwartete Form |
| --- | --- |
| GET /api/health | `status`, `version`, `log_root_found`, `db_found` |
| GET /api/stats | `servers`, `sources`, `unique_sources`, `duplicate_sources`, `events`, `levels`, `time_range`, `last_ingest_at` |
| GET /api/events | `{ items, total, limit, offset }`; Filter `server, component, level, from, to, q, job_id, trace_id` |
| GET /api/analysis/groups | Liste oder `{ items }`; je Gruppe `id, label, status, event_ids` |
| GET /api/events/{id} | Einzelereignis mit `source_path`, `line_start`, `line_end`, UTC-Zeit, Host, Level und Meldung |
| GET /api/events/{id}/context?n=10 | `{ id, source_path, line_start, line_end, lines: [{ no, is_event, text }] }` |
| GET /api/trace/{key} | Ereignisse einer Trace-ID als Liste oder `{ items, total, limit, offset }` |
| GET /api/suggestions | `{ scope, event_id, items: [{ kind, question, reason, job_id, event_id, last_ts }] }`; `lang=en\|de`, optional `event_id` |
| POST /api/chat | JSON `{ question }`; SSE mit `step`, `token`, `answer`, `done` oder `error`. Die UI zeigt Zwischenschritte und anschließend die strukturierte Antwort. |

Die verbindlichen Beispiele für die P1-Routen liegen in `../contracts/examples/`. Das Frontend normalisiert deren `source_path`, `line_start`, `line_end`, `no` und `limit/offset`-Felder für die Ansichten.

Alle oben genannten Routen sind auf `main` vorhanden; dazu kommen `GET /api/analysis/incidents`, `/api/analysis/incidents/{id}`, `/api/analysis/anomalies` und `/api/analysis/status`. Für Live-Daten müssen außerdem das Logpaket verfügbar sein, die Fixture-Datenbank gebaut und das Backend auf Port 8000 gestartet werden. Die Demo-Ansicht funktioniert unabhängig davon mit lokalen Beispieldaten.

Details zu den UI-Datentypen stehen in `src/demo.ts`; die Backend-Beispiele sind maßgeblich für die Antwortform. Die Zeitleiste zeigt eine chronologisch sortierte Ereignistabelle mit teilbaren Filtern, einschließlich UTC-Zeitraum. Der Live-Modus lädt Übersicht, Aufträge, Zeitleiste, Fehlergruppen, Quellkontext und Chat über die API. Die Auftragsübersicht gruppiert die erste vom Backend gelieferte Ereignisseite; die vollständige Suche mit serverseitiger `limit/offset`-Paginierung ist in der Zeitleiste verfügbar. Fehlende API-Routen erscheinen als Backend-Fehler. Abhängigkeitsgraph, grafische Zeitreihe und Evaluationsdashboard sind spätere Ausbauschritte.


## Chat mit Rückfragen

`conversation.tsx` hält den Verlauf über den Seiten: Er bleibt beim Wechsel der Ansicht erhalten, eine laufende Frage läuft weiter. Die Oberfläche schickt die `conversation_id` aus dem `done`-Ereignis mit der nächsten Frage; das Backend gibt dem Modell die letzten drei beantworteten Fragen. Ältere Analysen sind eingeklappt. „Neuer Chat“ beginnt von vorn, „Stopp“ bricht ab. Nach einem Neuladen der Seite beginnt ein neuer Chat.

## Schritte des Assistenten

Während der Assistent arbeitet, zeigt `assistant-run.tsx` seine Schritte als Zeitleiste (Werkzeug, Suchbegriff, Ergebnis, Dauer). Mit der Antwort klappt sie zu einer Zeile zusammen und lässt sich wieder öffnen; nach einem Fehler bleibt sie offen.

## Fragevorschläge im Assistenten

Im Live-Modus zeigt der Assistent Fragen aus vier Quellen (`src/suggestions.tsx`): aus den aktuellen Logs (`GET /api/suggestions`), zum zuletzt geöffneten Ereignis oder Auftrag (`?event_id=`), Favoriten (☆) und die letzten 8 Fragen. Favoriten und letzte Fragen liegen im `localStorage` dieses Browsers. Dieselben Fragen zum Ereignis stehen auch in den Meldungsdetails und im aufgeklappten Auftrag. Der Demo-Modus behält seine drei vorbereiteten Fragen.

## ZIP-Datei im Browser importieren

In der Übersicht unter **Log-ZIP hochladen** ein Archiv auswählen. Der Browser verarbeitet die Dateien lokal. Danach öffnet **Importierte Logs ansehen** die Zeitleiste, in der ein Klick auf eine Meldung ihre Quellzeilen zeigt. Die Datei bleibt bis zum Schließen oder Neuladen der Seite im Browser-Speicher.

Der Browser-Import unterstützt CSV, JSONL, Log-/Textdateien mit datiertem Zeitstempel und XML-Event-Dateien sowie Gzip-Varianten. Zeitstempel ohne Zeitzone werden als UTC gelesen. Das Limit beträgt 128 MiB für das ZIP und die entpackten Logdaten. Größere Archive aufteilen oder über den Backend-Ingest verarbeiten. Die lokale ZIP-Ansicht berechnet keine Fehlergruppen und ruft kein KI-Modell auf.

## Prozessüberwachung

Die Startseite listet erkannte Aufträge und Konvertierungen. Sortierung, Filter, Server, Status, Start, Ende, Dauer und anklickbare Protokolle orientieren sich an Seite 12 der MAIT-Challenge. ZIPs werden über dieselbe Seite ausgewählt.

Die Zuordnung erfolgt über die Trace-ID oder über die Kombination aus Server und lokaler Job-ID. Bei mehr als 30 Minuten zwischen zwei Einträgen beginnt eine neue Gruppe. Workflow-Vorlagen werden angezeigt, wenn sie als Feld vorliegen. Die Verarbeitungsdauer wird aus einem expliziten Auftragsdauerfeld oder aus erkanntem Start und Ende gebildet. Die Detailansicht zeigt zusätzlich den beobachteten Zeitraum. Status und Konvertierungstyp werden aus Logfeldern und Meldungen abgeleitet.

## Aufbau der Oberfläche

- **Titel:** eine Zeile mit Info-Symbol (`ui.tsx`, `PageTitle`); die Erklärung erscheint beim Überfahren, Fokus oder Antippen.
- **Seitenleiste:** enthält Navigation, Datenquelle (Live, Demo, ZIP), Backend-Status und Einstellungen; es gibt keine obere Leiste.
- **Incidents** (`incidents.tsx`): Liste, Detail mit Ursachenkette und Graph, Hinweis in den Meldungsdetails, neueste Incidents auf der Startseite, auffällige Fehlerraten in der Zeitleiste. Im Demo-Modus zeigt die Seite die vorbereiteten Fälle.
- **Meldungsdetails** (`event-details.tsx`): Dialog fast in Fenstergröße mit Kette, Analyse, Originalzeilen, Feldern und Fragen; Pfeile wechseln zum vorherigen oder nächsten Eintrag.
- Neue Stile liegen in `layout.css` und werden nach `style.css` geladen.

## Meldungsdetails

Ein Klick auf eine Meldung öffnet den Zeitstrahl des zugeordneten Auftrags. Der Zeitstrahl markiert die Auswahl, den Bezugsfehler sowie relevante Logs davor und danach. Die Textansicht erklärt zeitliche Zusammenhänge und zeigt die Originalzeilen. Ein früheres Fehlerereignis erscheint als möglicher Auslöser. Im Live-Modus benötigt der Zeitstrahl mit mehreren Servern eine Trace-ID und die Antwort von `GET /api/trace/{key}` als Liste oder `{ items }`.
