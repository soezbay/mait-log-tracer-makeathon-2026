# Makeathon-Plan: KI-Log-Assistent für MAIT

> Arbeitstitel: **LogLens** · Challenge: *Automatisiertes Log File Management mit einem KI-Assistenten* (MAIT)
> Ablauf: Tag 1 Konzeption, User Stories & Ingest · Tag 2–3 Bauen · Tag 4 Pitch
> Englische Fassung: [plan.en.md](plan.en.md) · Architektur: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) · Datenbasis: `MAIT_Makeathon_Logpaket/` (nicht im Git)

---

## 1. Ziel in einem Satz

Ein Assistent, der die Logs aller Server **rekursiv einsammelt, ohne die Originale zu verändern**, sie vereinheitlicht, **Fehlergruppen und Anomalien erkennt**, sie **über Systeme hinweg korreliert** und per Chat **Ursachen als Hypothesen mit Belegen, Unsicherheit und Prüfschritten** erklärt.

## 2. Was MAIT erwartet (laut README des Logpakets)

Das Logpaket gibt einen Vier-Schritte-Rahmen vor. Darauf richten wir den Plan aus:

| MAIT-Schritt | Was wir bauen | Wann |
|---|---|---|
| 1. Rekursiv einsammeln, Quelle erhalten, Formate & Zeitstempel normalisieren, speichern | Ingest-Pipeline → DuckDB, Originale bleiben unverändert | Tag 1 nachmittags |
| 2. Fehlergruppen & Zusammenhänge erkennen, relevante KI-Kontexte auswählen, **Qualität und Kosten messen** | Templates, Anomalien, Korrelation, LLM-Tools, Evaluation mit Token-Kosten | Tag 2 |
| 3. Neue Einträge kontinuierlich verarbeiten, **Checkpoints und Deduplizierung** | Inkrementeller Ingest + Ordner-Watcher, Dedupe auf Datei- und Event-Ebene | Tag 3 vormittags |
| 4. Visualisieren; Ursachen als **Hypothesen mit Belegen, Unsicherheit und Prüfschritten** | UI mit Zeitleiste, Abhängigkeitsgraph, Chat | Tag 3 + Pitch |

Ausdrückliche Fallen, die die Jury prüfen wird:
- Ein **ERROR heißt nicht**, dass der Vorgang gescheitert ist (es gibt erfolgreiche Retries).
- **Mehrere ERRORs können eine Ursache haben**, also gruppieren statt zählen.
- **Gleiche Job-Anzeigenummer heißt nicht gleicher Job.**
- **Systeme widersprechen sich** (z. B. Konverter meldet `SUCCESS`, Publish findet kein Ergebnis).
- **Unvollständige Belege**: Dann muss der Assistent Unsicherheit zugeben.
- Technisch: unterschiedliche Formate, **Windows-1252/UTF-8, gzip, mehrzeilige Exceptions, doppelte Events, verspätete Einträge, eine abweichende Quelluhr**.

## 3. Was in den Daten steckt (Analyse vom 23.11.2026)

**Umfang**
- **14 Server**: 7 Linux, 7 Windows. Struktur: `<server>/logs/<anwendung>/<komponente>/<datei>`.
- **13.643 Logdateien**, aber nur **5.068 mit unterschiedlichem Inhalt** (ca. 460 MB entpackt). Viele `_runNN`-Dateien sind **byte-gleiche Kopien** → Dedupe per Datei-Hash spart ca. 60 % Arbeit.
- **ca. 1,67 Mio. Events** (eindeutige Dateien): INFO 92 %, DEBUG 79 Tsd., WARN 46 Tsd., **ERROR nur 3.345 (0,2 %)**.
- Metadaten (keine Logs): `server_info.json` (Hostname, OS, Rolle), `README.md` je Ordner.

**Server**

| Server | OS | Rolle |
|---|---|---|
| `mait_linux1` | Linux | Teamcenter Backend |
| `mait_linux1_teamcenter_app` | Linux | Teamcenter Applikation |
| `mait_linux2` | Linux | Web und Suche (Active Workspace) |
| `mait_linux2_teamcenter_db` | Linux | Teamcenter Datenbank |
| `mait_linux3` | Linux | Gateway & Infrastruktur (Lizenz, T4S/T4EA, DB) |
| `mait_linux3_cad_service` | Linux | CAD-Service (NX, TLS, DNS) |
| `mait_linux4_dispatcher_service` | Linux | Dispatcher-Service |
| `mait_win01_dispatcher_master` | Windows | Dispatcher Master |
| `mait_win02_dispatcher_worker` | Windows | Dispatcher Worker (inkl. `clock`-Logs) |
| `mait_win03_cad_converter` | Windows | CAD-Konverter (NX/JT, PDF, ME10, Solid Edge) |
| `mait_win04_plm_sync` | Windows | PLM-Sync (inkl. `imported_mixed_hosts`) |
| `mait_windows1` | Windows | Dispatcher und NX |
| `mait_windows2` | Windows | CAD und weitere Konverter |
| `mait_windows3` | Windows | Integrationsclients (Rich Client, CAD-Integration) |

**Formate** (alle mit Zeitstempel, Level, Host, Komponente, Event-ID, Job-ID, Text)

| Format | Beispiel |
|---|---|
| `.log` key=value | `2026-11-23T08:00:14Z WARN host=… component=… event_id=… job_id=… \| Text` |
| `.txt` mit JSON-Nutzlast | `2026-11-24T08:00:37Z [WARN] host=… \| {"message": …, "duration_ms": …}` |
| `.csv` (Semikolon, CRLF) | `timestamp;level;host;component;event_id;job_id;message[;duration_ms;session_id]`, **mehrzeilige Stacktraces in Anführungszeichen** |
| `.jsonl` / `.jsonl.gz` | ein JSON-Objekt pro Zeile; `ki-integriert`-Variante zusätzlich mit `trace_id` |
| `.xml` | `<Events><Event><timestamp>…</timestamp>…</Event></Events>` (Demo-Format, kein EVTX) |
| `import_*.log` | `2026-10-06 14:02:15.234 [INFO] …` bzw. **nur Uhrzeit** `[14:02:15] TC.RAC - …` (Datum aus Kontext ableiten) |

Besonderheiten: 1 Datei in Windows-1252, CRLF bei Windows-Dateien, Zeitstempel fast überall ISO-8601 UTC (`…Z`).

**Zeiträume & Datensätze**
- **01.–30.10.2026** (`*.ki-integriert.jsonl`): Monatsbetrieb mit `trace_id` und **markierten Incidents `INC-01` … `INC-10`** (z. B. „Downstream timeout/retry during INC-01; dependency=mait_linux2_teamcenter_db").
- **06.10.2026** (`import_*.log`): importierte Fehlerszenarien in Freitext (Job 4710/4711, Konverter, Lizenz, Workflow).
- **23.11.2026**: Normalbetrieb (`NORMAL-…`-Jobs), Baseline.
- **24.11.2026** (`creative_*`): gezielte Fehlerszenarien in allen Formaten.

**Korrelations-Schlüssel**: `job_id`, `trace_id`, `session_id`, `event_id`, `INC-xx`, `dependency=<host>`, Objekt-IDs (`DEMO-…`, `DEMO-Seal-17/C`), Request-IDs (`REQ-…`).

**Gefundene Fehlerbilder (Kandidaten für Demo & Evaluation)**
- Downstream-Timeouts mit Abhängigkeit zur Teamcenter-DB bzw. zum Dispatcher Master (`INC-01…10`)
- „Worker failed … **local clock is behind**" → abweichende Quelluhr (`mait_win02_dispatcher_worker`)
- **Konverter meldet SUCCESS, Publish findet kein Ergebnis** → widersprüchliche Systeme
- **Fehlende Baugruppen-Referenz** `DEMO-Seal-17/C` → „No output JT produced" (mehrzeilige Java-Exception)
- `no space left on device` beim Schreiben des Ergebnisses
- Zugriff verweigert (Share lesen, PDF schreiben, `WRITE_DATASET`)
- Prozess wegen **Speicherdruck** beendet (große Baugruppe)
- **Gecachter Endpunkt** → Connection refused (DNS/Cache)
- Suche/Indexer nicht verfügbar
- ERP: zyklische Produktstruktur, Lieferantensperre → „upstream dependency failure"-Ketten
- Dispatcher-Queue-Sättigung
- **Fallen**: ERROR-Level bei harmlosen Meldungen („Transient retry recovered", „Cache lookup successful").

> Fehlende Doku: Das README verweist auf `_dokumentation/FORMATE.md` und `INTEGRATION.md`, die nicht im Paket liegen (Zeitzonen, Begrenzungen, T4S/T4EA-Begriffe). **Am Tag 1 beim Mentor anfragen.**

## 4. Bezug zu MAIT (für Konzept & Pitch)

- MAIT: IT-Dienstleister für den produzierenden Mittelstand. **PLM, CAD/CAM, ERP, Managed Services** (Partner u. a. Siemens, PTC, SAP-PLM, abas, Comarch).
- Die Daten bilden genau so eine Landschaft ab: **Teamcenter, Active Workspace, Dispatcher, NX/Solid Edge/ME10-Konverter, FMS, T4S/T4EA (ERP-Gateway), Lizenzdienst**.
- **Hebel = Managed Service**: Supporter suchen heute manuell in 14 Servern und mehreren Formaten. Jede Minute weniger Ursachenanalyse skaliert über tausende Kunden.
- **Abgrenzung**: hackaTUM 2023 (Rohde & Schwarz, z. B. „Logzilla") machte *eine* Datei hochladen und befragen. **Wir: 14 Server, Korrelation über Systeme, Hypothesen mit Belegen, Unsicherheit und Prüfschritten, gemessene Qualität und Kosten.**

## 5. Personas

1. **Sandra, Supporterin im MAIT Managed Service**: Ticket „JT-Konvertierung für Baugruppe X fehlgeschlagen". Will in < 5 Minuten wissen, *wo* die Ursache liegt und *was sie prüfen soll*.
2. **Tobias, System-Engineer beim Kunden**: Will wissen, ob ein Problem wiederkehrt und welche Systeme abhängig sind.
3. **Teamleitung Managed Service**: Überblick über auffällige Server und offene Incidents.

## 6. User Stories (MVP = Muss, Rest = Kann)

**Muss**
- US1: Als Supporterin möchte ich, dass **alle Logs eines Ordners rekursiv eingelesen** werden, egal welches Format oder welche Kodierung. Die Originale bleiben unverändert.
- US2: Als Supporterin möchte ich alle Events auf **einer gemeinsamen Zeitleiste** sehen, gefiltert nach Server, Komponente, Level und Job/Trace.
- US3: Als Supporterin möchte ich **Fehlergruppen statt einzelner ERRORs** sehen: Was hat dieselbe Ursache, was hat sich per Retry erholt?
- US4: Als Supporterin möchte ich im Chat fragen „**Warum ist die JT-Konvertierung am 24.11. fehlgeschlagen?**" und eine **Hypothese mit Kausalkette, betroffenen Systemen, Belegzeilen, Unsicherheit und Prüfschritten** bekommen.
- US5: Als Supporterin möchte ich auf einen Beleg klicken und die **Originalzeile in der Originaldatei** mit Kontext sehen.
- US6: Als Betreiber möchte ich, dass **neue Logdateien automatisch nachgeladen** werden (Checkpoint), **ohne Duplikate**.

**Kann**
- US7: Ticket-/Incident-Zusammenfassung als Entwurf exportieren.
- US8: „Ist das schon mal passiert?": ähnliche Fehlergruppen aus dem Oktober finden.
- US9: Abhängigkeitsgraph der Server (aus `dependency=…` und Korrelationen).
- US10: Neues Logformat per Beispielzeilen anlernen (LLM schlägt Parser-Profil vor).
- US11: Dashboard „Qualität & Kosten" (Trefferquote, Tokens, € pro Frage).

## 7. Demo-Szenario

**Am Tag 1 aus den echten Daten festlegen.** Favoriten, weil sie die Jury-Fallen zeigen:

1. **„JT fehlt, obwohl der Konverter SUCCESS meldet"** (24.11.): Konverter `SUCCESS` → Publish „no registered result" → Ursache fehlende Referenz `DEMO-Seal-17/C` (mehrzeilige Exception). Zeigt **widersprüchliche Systeme + Multiline**.
2. **`INC-01` im Oktober**: Teamcenter-App meldet wiederholt Downstream-Timeouts zur `teamcenter_db`. Viele ERRORs, **eine Ursache**, teils erfolgreiche Retries. Zeigt **Gruppierung + Retry ≠ Fehler**.
3. **„Worker failed, local clock is behind"** (`mait_win02_dispatcher_worker`): Zeigt **Quelluhr-Korrektur**. Ohne Korrektur stimmt die Reihenfolge der Kette nicht.

Zusätzlich als **falsche Fährte**: harmlose ERRORs („Transient retry recovered") werden *nicht* als Ursache genannt.

## 8. Architektur

```
 MAIT_Makeathon_Logpaket/  (nur lesen)
        │ rekursiv scannen · Hash · Kodierung · gzip im Speicher
        ▼
 ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
 │ Format-      │─▶│ Normalisierer│─▶│ Dedupe &    │─▶│ Templates    │─▶│ Fehlergruppen│
 │ Erkennung &  │  │ UTC, Level,  │  │ Checkpoint  │  │ (Drain3)     │  │ Anomalien,   │
 │ Parser (6)   │  │ Uhr-Korrektur│  │             │  │              │  │ Korrelation  │
 └──────────────┘  └──────────────┘  └─────────────┘  └──────────────┘  └──────┬───────┘
                                  ▼                                               │
                           ┌──────────────┐  Tools (SQL)   ┌──────────────────┐   │
                           │ DuckDB       │◀──────────────│ KI-Assistent     │◀──┘
                           │ loglens.duckdb│               │ LLM + Tool-Use   │
                           └──────────────┘               └────────┬─────────┘
                                                                   ▼
                       UI: Zeitleiste · Fehlergruppen · Abhängigkeitsgraph · Chat mit Belegen
```

### Grundsatz: Originale bleiben unverändert

Die Logdateien werden **nur gelesen**. Alles Abgeleitete liegt in **einer DuckDB-Datei** (`data/loglens.duckdb`), die per Skript jederzeit neu gebaut werden kann. Jedes Event zeigt auf seine Originaldatei und -zeile zurück.

### Datenmodell (DuckDB)

**`sources`**: eine Zeile pro Datei

| Feld | Beschreibung |
|---|---|
| `source_id`, `path` | relativer Pfad im Logpaket |
| `server`, `os`, `role` | aus Ordner + `server_info.json` |
| `application`, `component` | aus `logs/<anwendung>/<komponente>` |
| `format`, `encoding`, `compressed` | erkannt beim Einlesen |
| `sha256`, `size`, `mtime` | für Datei-Dedupe |
| `duplicate_of` | Verweis, falls byte-gleiche Kopie |
| `checkpoint_bytes`, `checkpoint_line`, `ingested_at` | für inkrementelles Nachladen |

**`events`**: ein Event pro (ggf. mehrzeiliger) Logeintrag

| Feld | Beschreibung |
|---|---|
| `id` | interne ID (Belegstelle) |
| `source_id`, `line_start`, `line_end` | Rückverweis aufs Original |
| `ts_raw`, `ts_utc`, `clock_offset_s` | Originalzeit, korrigierte UTC-Zeit, angewandte Korrektur |
| `ingest_seq` | Einlesereihenfolge, um verspätete Einträge zu erkennen |
| `host`, `component`, `level` | `level` normalisiert: `DEBUG/INFO/WARN/ERROR/FATAL` |
| `event_id`, `job_id`, `trace_id`, `session_id` | Korrelations-Schlüssel |
| `message`, `attrs` (JSON) | Text + Zusatzfelder (`duration_ms`, `dependency`, `object` …) |
| `template_id` | aus Drain3 |
| `fingerprint`, `duplicate_of` | Event-Dedupe |
| `raw` | Originaltext |

Weitere Tabellen: `templates`, `error_groups` (Gruppe gleicher Ursache, mit Retry-Status), `anomalies`, `hypotheses` (gespeicherte Antworten für die Evaluation), `llm_calls` (Tokens, Dauer, Kosten).

### Bausteine im Detail

1. **Einsammeln & Parsen**
   - Rekursiv über alle Server, Metadaten (`README.md`, `server_info.json`) getrennt behandeln.
   - Datei-Hash vor dem Parsen → byte-gleiche Kopien (`_runNN`) nur verknüpfen, nicht neu parsen.
   - Kodierung: UTF-8, Fallback Windows-1252; `.gz` im Speicher entpacken.
   - 6 Parser: `kv_log`, `bracket_json_txt`, `csv_semicolon` (mit `csv`-Modul wegen mehrzeiliger Felder), `jsonl`, `xml_events`, `import_freetext` (inkl. Zeilen nur mit Uhrzeit).
   - Folgezeilen ohne Zeitstempel (Stacktraces) an das vorherige Event hängen.
2. **Normalisieren**: Zeit → UTC; Level-Mapping (`Critical/CRITICAL/SEVERE` → `FATAL`, `WARNING` → `WARN` …); **Uhr-Korrektur** pro Host, wenn erkannt (`clock_offset` in Meldungen oder systematischer Versatz zu Partnern über gemeinsame `job_id`/`trace_id`).
3. **Deduplizieren**
   - Datei-Ebene: gleicher Hash.
   - Event-Ebene: gleicher Fingerprint aus `host + event_id + ts_utc + message`. Duplikat wird markiert, nicht gelöscht.
   - Verspätete Einträge: `ts_utc` deutlich vor dem letzten Event derselben Quelle → markieren.
4. **Templates & Fehlergruppen**: Drain3 auf `message`. Gruppe = gleiches Template + gleiche Komponente + zeitliche Nähe. Pro Gruppe der Status **„erholt"** (Retry erfolgreich) oder **„endgültig fehlgeschlagen"**.
5. **Anomalien**: Fehlerrate pro Server und Minute gegen die Baseline vom 23.11. bzw. Oktober (z-Score), neue/seltene Templates, Level-Sprünge, Dauer-Ausreißer (`duration_ms`).
6. **Korrelation**
   - Harte Verknüpfung: gleiche `trace_id`, `job_id` (+ Host/Zeitfenster, weil gleiche Nummer ≠ gleicher Job), `session_id`, Objekt-ID, `INC-xx`.
   - Weiche Verknüpfung: zeitliche Nähe von Fehlergruppen über Server, Reihenfolge, `dependency=<host>`.
   - Ergebnis: **Hypothese** = Kausalkette + Konfidenz + Gegenbelege.
7. **KI-Assistent**: LLM mit Tool-Use. Er liest nie alle Logs, sondern wählt gezielt Kontext aus (Schritt 2 im MAIT-Rahmen):
   - `search_events(server, component, level, zeitraum, text)`
   - `get_error_groups(zeitraum)` · `get_anomalies(zeitraum)`
   - `trace(job_id | trace_id | object_id)`: alle Events einer Kette über Server
   - `correlate(group_id)` · `get_context(event_id, ±n)`
   - **Antwortformat (Pflicht)**: Zusammenfassung · Kausalkette · betroffene Server/Komponenten · Belege `[server | datei:zeile | zeit]` · **Unsicherheit & Gegenbelege** · **Prüfschritte** · Empfehlung.
8. **Kontinuierlich (Tag 3)**: Watcher auf den Logordner. Neue Datei oder angehängte Zeilen werden ab dem Checkpoint eingelesen, dedupliziert und in der UI sichtbar. Demo: Datei während des Pitches in den Ordner kopieren.
9. **UI**: Zeitleiste pro Server, Fehlergruppen-Liste, Abhängigkeitsgraph, Chat mit klickbaren Belegen, Kachel „Qualität & Kosten".

### Qualität & Kosten messen

- **Testfragen** (ca. 10–15) aus bekannten Szenarien: `INC-01…10`, `creative_*`-Szenarien vom 24.11., `import_*`-Szenarien vom 06.10.
- **Ground Truth** pro Frage: erwartete Ursache, erwartete Server, erwartete Belege.
- **Metriken**: Ursache richtig (ja/teilweise/nein), Trefferquote der Belege, falsche Ursachen (z. B. harmlose ERRORs), Antwortzeit, **Tokens und € pro Frage**.
- Vergleich „ganze Logs ins LLM" vs. „Tool-basierte Kontextauswahl", das stärkste Kostenargument im Pitch.

### Tech-Stack

| Bereich | Wahl | Warum |
|---|---|---|
| Sprache | Python 3.11+ | Parsing, ML, LLM-SDKs in einem |
| Speicher | DuckDB | eine Datei, schnell, SQL für Tools |
| Template-Mining | Drain3 | Standard für Log-Parsing |
| Analyse | pandas, scikit-learn | einfach & erklärbar |
| Graph | networkx (+ pyvis/Plotly) | Abhängigkeitsgraph |
| Watcher | watchdog | Ordner überwachen |
| LLM | Claude API (Tool-Use); Ollama als „lokal"-Option | Qualität für Demo; Datenschutz-Argument |
| Backend / API | FastAPI + Uvicorn, Pydantic, SSE | klare Schnittstelle, OpenAPI-Doku, Live-Streaming |
| Frontend | React + TypeScript (Vite), Mantine, ECharts, Cytoscape.js; Fallback Streamlit | getrennt vom Backend, nur über die API |

Details zu allen Frameworks und Komponenten: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## 9. Repo-Struktur (Ziel)

```
makeathon/
├── plan.md / plan.en.md
├── docs/ARCHITEKTUR.md · ARCHITECTURE.md
├── MAIT_Makeathon_Logpaket/   # Originaldaten, nur lesen, in .gitignore
├── data/loglens.duckdb        # abgeleitet, in .gitignore
├── eval/questions.yaml        # Testfragen + Ground Truth
├── backend/                   # Python + FastAPI
│   └── src/loglens/
│       ├── api/               # REST + SSE-Endpunkte
│       ├── services/          # Anwendungslogik (von API und LLM-Tools genutzt)
│       ├── ingest/            # Scan, Formaterkennung, Parser, Checkpoints, Watcher
│       ├── normalize/         # Zeit, Level, Uhr-Korrektur, Dedupe
│       ├── analysis/          # Templates, Fehlergruppen, Anomalien, Korrelation, Graph
│       ├── assistant/         # LLM-Provider, Tools, Prompt, Antwortformat, Kosten
│       └── storage/           # DuckDB, Schema, Repositories
└── frontend/                  # React + TypeScript (Vite)
    └── src/                   # api/, pages/, components/, hooks/
```

## 10. Zeitplan

### Tag 1: Konzeption, User Stories & Ingest
| Zeit | Was | Ergebnis |
|---|---|---|
| Vormittag | Briefing, Fragen an Mentor (§13), fehlende Doku anfragen | Klarheit über Daten & Bewertung |
| | Personas, User Stories, MVP-Schnitt; **Demo-Szenario aus §7 wählen** | priorisiertes Backlog, Demo-Fall |
| Mittag | Datenmodell + Parser-Liste festzurren, Rollen verteilen | Schema, Aufgaben |
| Nachmittag | Scanner + Datei-Dedupe + 6 Parser + DuckDB-Schreiben | **Meilenstein: alles in DuckDB** |
| Abend | Plausibilitäts-Check (Events pro Server, Level-Verteilung); Testfragen + Ground Truth entwerfen | `eval/questions.yaml` v1 |

### Tag 2: Analyse & Assistent (MAIT-Schritt 2)
| Zeit | Was |
|---|---|
| Vormittag | Drain3-Templates, Fehlergruppen mit Retry-Status, Anomalien, Uhr-Korrektur |
| Nachmittag | Korrelation (`trace`/`job`/Zeitfenster), LLM-Tools, Antwortformat, Kosten-Logging |
| Abend | **Meilenstein: Demo-Frage End-to-End + erster Evaluationslauf mit Zahlen** |

### Tag 3: Kontinuierlich, UI, Pitch (MAIT-Schritte 3 + 4)
| Zeit | Was |
|---|---|
| Vormittag | Inkrementeller Ingest mit Checkpoints, Event-Dedupe, Watcher; UI: Zeitleiste, Fehlergruppen, Chat mit Belegen |
| Mittag | Abhängigkeitsgraph, Qualität-&-Kosten-Kachel, Prompt nach Evaluation verbessern |
| Nachmittag | **Feature-Freeze 16:00**; finaler Evaluationslauf, Demo-Skript, Folien, Backup-Video |
| Abend | Generalprobe, Fragen-Training |

### Tag 4: Pitch Day
- Morgens: letzter Durchlauf, DuckDB vorab gebaut, Backup-Video bereit
- Pitch halten, Fragen beantworten

## 11. Rollen (Annahme: 4 Personen)

| Rolle | Verantwortung |
|---|---|
| **Ingest** | Scanner, Parser, Kodierung, DuckDB, Checkpoints, Dedupe |
| **Analytics** | Templates, Fehlergruppen, Anomalien, Uhr-Korrektur, Korrelation |
| **AI & Evaluation** | LLM-Tools, Prompt, Antwortformat, Testfragen, Qualität & Kosten |
| **Frontend & Pitch** | React-Frontend, Graph, Demo-Skript, Folien, Story |

## 12. Pitch-Struktur (5 Min.)

1. **Problem** (45 s): Sandra, Ticket „JT fehlt", 14 Server, 6 Formate, 1,7 Mio. Zeilen, 3.345 ERRORs, und die meisten davon sind nicht die Ursache.
2. **Lösung** (30 s): LogLens: alle Logs, eine Antwort mit Belegen, Unsicherheit und Prüfschritten.
3. **Live-Demo** (2 min): Zeitleiste → Fehlergruppe → Chat-Frage → Kausalkette über Server mit Belegen → Klick auf Originalzeile → neue Logdatei wird live nachgeladen.
4. **Wie es funktioniert** (45 s): Originale unverändert · 6 Parser · Dedupe (60 % Kopien) · Uhr-Korrektur · Gruppen statt ERRORs · LLM nur mit Tools.
5. **Gemessen** (30 s): x von y Testfragen richtig, 0 harmlose ERRORs als Ursache, z Cent pro Frage.
6. **Nutzen für MAIT & Ausblick** (30 s): schnellere Ursachenanalyse im Managed Service, Datenschutz durch lokales LLM möglich, Wissensbasis aus gelösten Tickets.

**Erwartete Jury-Fragen**: Unterschied zu Splunk/Elastic? (→ Ursachen-Erklärung mit Belegen statt Suche, leichtgewichtig) · Wie verlässlich ist die Kausalität? (→ Hypothese mit Konfidenz, Gegenbelegen und Prüfschritten; gemessen an Testfragen) · Kosten? (→ Kontextauswahl statt alles ins LLM, Zahlen aus `llm_calls`) · Skalierung? (→ DuckDB → ClickHouse/Elastic, Schema bleibt).

## 13. Offene Fragen an den Mentor (Tag 1)

- Wo sind `_dokumentation/FORMATE.md` und `INTEGRATION.md`? (Zeitzonen, Begrenzungen, T4S/T4EA-Begriffe)
- Welche Quelle hat die abweichende Uhr, und um wie viel? Selbst herausfinden oder bekannt?
- Gibt es eine Ground Truth für `INC-01…10` und die `creative`-Szenarien?
- Sind die `_runNN`-Kopien absichtlich (Dedupe-Test) oder Mehrfachläufe?
- Welche Rolle spielen `imported_mixed_hosts` und `import_*`-Dateien?
- Vorgaben zum LLM (Cloud erlaubt? lokal gewünscht?) und Bewertungskriterien der Jury?

## 14. Risiken & Gegenmaßnahmen

| Risiko | Gegenmaßnahme |
|---|---|
| 13.643 Dateien, Ingest zu langsam | Datei-Hash-Dedupe vor dem Parsen; DuckDB-Bulk-Insert; DB vor dem Pitch vorbauen |
| Mehrzeilige / unvollständige Einträge zerbrechen Parser | Parser-Tests je Format mit echten Beispielzeilen; Fallback „unparsed" statt Abbruch |
| Falsche Reihenfolge durch Quelluhr | Uhr-Korrektur mit `clock_offset_s` sichtbar machen |
| LLM nennt harmlose ERRORs als Ursache | Fehlergruppen mit Retry-Status als Tool-Ergebnis; Testfrage dafür |
| LLM halluziniert | Nur Tool-basierte Antworten, Pflicht-Belege, Unsicherheit ausweisen |
| Zu viel Scope | Feature-Freeze Tag 3, 16:00; Kann-Stories nur nach MVP |
| Demo-Ausfall | Backup-Video + lokal vorgebaute DuckDB |

## 15. Definition of Done (MVP)

- [ ] Alle 6 Formate inkl. gzip, Windows-1252 und mehrzeiliger Exceptions werden eingelesen; Originale unverändert
- [ ] Jedes Event verweist auf Datei + Zeile; Klick zeigt Original mit Kontext
- [ ] Datei- und Event-Duplikate erkannt; inkrementeller Ingest per Checkpoint
- [ ] Quelluhr-Abweichung erkannt und korrigiert
- [ ] Fehlergruppen mit Status „erholt" / „fehlgeschlagen"
- [ ] Demo-Frage liefert Hypothese über ≥ 3 Server mit Belegen, Unsicherheit und Prüfschritten
- [ ] Harmlose ERRORs werden nicht als Ursache genannt
- [ ] Evaluationslauf mit Trefferquote und Kosten pro Frage
- [ ] Pitch + Backup-Video fertig
