# Log Tracer – Frontend

React, TypeScript, Vite, Mantine und React Router für das MAIT-Makeathon-Projekt.

## Start

Node.js 22 oder 24 verwenden. Beim Start über HTTP/HTTPS öffnet die Anwendung direkt den Live-Modus und ruft das Backend ab. Über `Demo` bleiben die vorbereiteten Fälle verfügbar; beim Öffnen der HTML-Datei startet die Anwendung automatisch offline in der Demo.

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
| POST /api/chat | JSON `{ question }`; SSE mit `step`, `token`, `answer`, `done` oder `error`. Die UI zeigt Zwischenschritte und anschließend die strukturierte Antwort. |

Die verbindlichen Beispiele für die P1-Routen liegen in `../contracts/examples/`. Das Frontend normalisiert deren `source_path`, `line_start`, `line_end`, `no` und `limit/offset`-Felder für die Ansichten.

Im aktuellen Backend-Checkout ist bisher nur `GET /api/health` registriert. Die übrigen Live-Aufrufe entsprechen den eingefrorenen Schnittstellenbeispielen; sie liefern erst Daten, wenn die jeweiligen Backend-Router ergänzt und der Server unter `localhost:8000` gestartet ist.

Details zu den UI-Datentypen stehen in `src/demo.ts`; die Backend-Beispiele sind maßgeblich für die Antwortform. Die Zeitleiste zeigt eine chronologisch sortierte Ereignistabelle mit teilbaren Filtern, einschließlich UTC-Zeitraum. Der Live-Modus lädt Übersicht, Aufträge, Zeitleiste, Fehlergruppen, Quellkontext und Chat über die API. Die Auftragsübersicht gruppiert die erste vom Backend gelieferte Ereignisseite; die vollständige Suche mit serverseitiger `limit/offset`-Paginierung ist in der Zeitleiste verfügbar. Fehlende API-Routen erscheinen als Backend-Fehler. Abhängigkeitsgraph, grafische Zeitreihe und Evaluationsdashboard sind spätere Ausbauschritte.


## ZIP-Datei im Browser importieren

In der Übersicht unter **Log-ZIP hochladen** ein Archiv auswählen. Der Browser verarbeitet die Dateien lokal. Danach öffnet **Importierte Logs ansehen** die Zeitleiste, in der ein Klick auf eine Meldung ihre Quellzeilen zeigt. Die Datei bleibt bis zum Schließen oder Neuladen der Seite im Browser-Speicher.

Der Browser-Import unterstützt CSV, JSONL, Log-/Textdateien mit datiertem Zeitstempel und XML-Event-Dateien sowie Gzip-Varianten. Zeitstempel ohne Zeitzone werden als UTC gelesen. Das Limit beträgt 128 MiB für das ZIP und die entpackten Logdaten. Größere Archive aufteilen oder über den Backend-Ingest verarbeiten. Die lokale ZIP-Ansicht berechnet keine Fehlergruppen und ruft kein KI-Modell auf.

## Prozessüberwachung

Die Startseite listet erkannte Aufträge und Konvertierungen. Sortierung, Filter, Server, Status, Start, Ende, Dauer und anklickbare Protokolle orientieren sich an Seite 12 der MAIT-Challenge. ZIPs werden über dieselbe Seite ausgewählt.

Die Zuordnung erfolgt über die Trace-ID oder über die Kombination aus Server und lokaler Job-ID. Bei mehr als 30 Minuten zwischen zwei Einträgen beginnt eine neue Gruppe. Workflow-Vorlagen werden angezeigt, wenn sie als Feld vorliegen. Die Verarbeitungsdauer wird aus einem expliziten Auftragsdauerfeld oder aus erkanntem Start und Ende gebildet. Die Detailansicht zeigt zusätzlich den beobachteten Zeitraum. Status und Konvertierungstyp werden aus Logfeldern und Meldungen abgeleitet.

## Meldungsdetails

Ein Klick auf eine Meldung öffnet den Zeitstrahl des zugeordneten Auftrags. Der Zeitstrahl markiert die Auswahl, den Bezugsfehler sowie relevante Logs davor und danach. Die Textansicht erklärt zeitliche Zusammenhänge und zeigt die Originalzeilen. Ein früheres Fehlerereignis erscheint als möglicher Auslöser. Im Live-Modus benötigt der Zeitstrahl mit mehreren Servern eine Trace-ID und die Antwort von `GET /api/trace/{key}` als Liste oder `{ items }`.
