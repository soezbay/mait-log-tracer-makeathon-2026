# Makeathon-Plan: KI-Log-Assistent für MAIT

> Arbeitstitel: **Log Tracer** · Challenge: *Automatisiertes Log File Management mit einem KI-Assistenten* (MAIT)
> Ablauf: Tag 1 Konzeption, User Stories & Ingest · Tag 2–3 Bauen · Tag 4 Pitch
> Englische Fassung: [plan.en.md](plan.en.md) · Architektur: [docs/ARCHITEKTUR.md](ARCHITEKTUR.md) · Datenbasis: `MAIT_Makeathon_Logpaket/` (nicht im Git)

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
- **23.11.2026**: überwiegend Normalbetrieb (`NORMAL-…`-Jobs), dient als Baseline. Enthält aber auch einige fehlschlagende Jobs (`JOB-1xxx`, z. B. `JOB-1003` „No output JT produced" auf `mait_windows2`), die aus der Baseline herausgenommen werden müssen.
- **24.11.2026** (`creative_*`): gezielte Fehlerszenarien in allen Formaten.

**Korrelations-Schlüssel**: `job_id`, `trace_id`, `session_id`, `event_id`, `INC-xx`, `dependency=<host>`, Objekt-IDs (`DEMO-…`, `DEMO-Seal-17/C`), Request-IDs (`REQ-…`).

**Gefundene Fehlerbilder (Kandidaten für Demo & Evaluation)**
- Downstream-Timeouts mit Abhängigkeit zur Teamcenter-DB bzw. zum Dispatcher Master (`INC-01…10`)
- „Worker failed … **local clock is behind**" → abweichende Quelluhr (`mait_win02_dispatcher_worker`, `dispatcher/module`, `JOB-2001`). Der Eintrag selbst enthält `clock_offset_seconds: -94` und eine `observed_at`-Zeit, der Versatz lässt sich also messen statt schätzen.
- **Konverter meldet SUCCESS, Publish findet kein Ergebnis** (`JOB-2003`) → widersprüchliche Systeme; die eigentliche Ursache ist ein abgelehnter FMS-Upload (fehlendes Schreibrecht auf dem Ziel-Volume), siehe §7
- **Fehlende Baugruppen-Referenz** `DEMO-Seal-17/C` (`JOB-2010`) → „Reference target absent" (Teamcenter SOA) → „Export aborted" (NX/JT-Konverter), dazu eine mehrzeilige Java-Exception
- „No output JT produced" (`JOB-1003`, Solid-Edge-→-JT-Translator auf `mait_windows2`, 23.11.): ein eigener Fall, nicht mit `DEMO-Seal-17/C` verknüpft
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

1. **„Publish schlägt fehl, obwohl der Konverter SUCCESS meldet"** (24.11., `JOB-2003`, in den Daten geprüft):
   - 08:30:00 `mait_win03_cad_converter` `converter/nx_jt`: „Conversion succeeded; JT output=DEMO-301.jt"
   - 08:30:08 `mait_linux1_teamcenter_app` `fms/fsc`: „Upload rejected; access policy lacks target volume write permission"
   - 08:30:12 `mait_linux1_teamcenter_app` `teamcenter/workflow`: „Publish task failed: no registered result; converter status=SUCCESS"

   Ursache: fehlendes Schreibrecht auf dem FMS-Volume, nicht der Konverter. Zeigt **widersprüchliche Systeme** über 2 Server und 3 Formate (CSV, TXT, JSONL).
2. **Fehlende Baugruppen-Referenz** (24.11., `JOB-2010`): `nx/batch` „Required child DEMO-Seal-17/C not resolved" → `teamcenter/soa` „Reference target absent from exported input package" → `converter/nx_jt` „Export aborted because required reference is missing". Um 11:01 folgt eine **mehrzeilige Java-Exception** mit derselben Job-Nummer; prüfen, ob sie zum selben Job gehört (das README warnt, dass gleiche Anzeigenummern nicht immer derselbe Job sind).
3. **`INC-01` im Oktober**: Teamcenter-App meldet wiederholt Downstream-Timeouts zur `teamcenter_db`. Viele ERRORs, **eine Ursache**, teils erfolgreiche Retries. Zeigt **Gruppierung + Retry ≠ Fehler**.
4. **„Worker failed, local clock is behind"** (`mait_win02_dispatcher_worker`, `JOB-2001`): Zeigt **Quelluhr-Korrektur** (`clock_offset_seconds: -94`). Ohne Korrektur stimmt die Reihenfolge der Kette nicht.

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
                           │ logtracer.duckdb│               │ LLM + Tool-Use   │
                           └──────────────┘               └────────┬─────────┘
                                                                   ▼
                       UI: Zeitleiste · Fehlergruppen · Abhängigkeitsgraph · Chat mit Belegen
```

### Grundsatz: Originale bleiben unverändert

Die Logdateien werden **nur gelesen**. Alles Abgeleitete liegt in **einer DuckDB-Datei** (`data/logtracer.duckdb`), die per Skript jederzeit neu gebaut werden kann. Jedes Event zeigt auf seine Originaldatei und -zeile zurück.

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
| Backend / API | FastAPI + Uvicorn, Pydantic, eingebautes SSE von FastAPI (`fastapi.sse`) | klare Schnittstelle, OpenAPI-Doku, Live-Streaming |
| Frontend | React 19 + TypeScript (Vite), Mantine, ECharts, Cytoscape.js; Node.js 22 oder 24 LTS; Fallback Streamlit | getrennt vom Backend, nur über die API |

Details zu allen Frameworks und Komponenten: [docs/ARCHITEKTUR.md](ARCHITEKTUR.md).

## 9. Repo-Struktur (Ziel)

```
makeathon/
├── AGENTS.md · CLAUDE.md     # rules for agents and humans
├── docs/                      # plan.md, plan.en.md, ARCHITEKTUR.md, ARCHITECTURE.md, AI_LOG.md, WORKLOG.md
├── MAIT_Makeathon_Logpaket/   # Originaldaten, nur lesen, in .gitignore
├── data/logtracer.duckdb        # abgeleitet, in .gitignore
├── eval/questions.yaml        # Testfragen + Ground Truth
├── backend/                   # Python + FastAPI
│   └── src/logtracer/
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
2. **Lösung** (30 s): Log Tracer: alle Logs, eine Antwort mit Belegen, Unsicherheit und Prüfschritten.
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
| Drain3 wird nicht mehr gepflegt (letzte Version 0.9.11 von 2022) | an Tag 1 mit unserer Python-Version installieren und testen; Fallback: eigene Regex-Maskierung + Gruppierung nach maskierter Meldung |
| Zeitzonen unter Windows | Pythons `zoneinfo` hat unter Windows keine Zeitzonendaten: Paket `tzdata` als Backend-Abhängigkeit aufnehmen |

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

## 16. TODO nach Phasen

Rollen-Kürzel: **[ING]** Ingest · **[ANA]** Analytics · **[AI]** AI & Evaluation · **[FE]** Frontend & Pitch · **[ALLE]** ganzes Team.
Jede Phase endet mit einem **Abschluss-Kriterium**. Erst wenn es erfüllt ist, gilt die Phase als fertig.

### Phase 0: Setup (Tag 1, früh)
- [ ] [ALLE] Repo klonen, Logpaket lokal nach `MAIT_Makeathon_Logpaket/` kopieren
- [ ] [ING] `backend/` anlegen: `pyproject.toml` (uv), FastAPI-Grundgerüst, `/api/health`, `.env.example`
- [ ] [FE] `frontend/` anlegen: Vite + React 19 + TypeScript, Mantine, Router, Proxy `/api` → `:8000` (Node.js 22 oder 24 LTS; Node 20 hat sein Lebensende erreicht)
- [ ] [AI] Claude-API-Schlüssel besorgen, in `backend/.env` eintragen (nie committen)
- [ ] [ALLE] Branch-Regeln festlegen (z. B. Feature-Branches, kurzer Review vor Merge)

**Abschluss:** Backend und Frontend starten lokal, Frontend zeigt die Antwort von `/api/health`.

### Phase 1: Konzeption & User Stories (Tag 1, vormittags)
- [ ] [ALLE] Briefing, Fragen an den Mentor stellen (§13), fehlende Doku anfragen
- [ ] [ALLE] Personas und User Stories bestätigen, MVP-Schnitt festlegen
- [ ] [ALLE] Demo-Szenario aus §7 wählen und in den Logs nachvollziehen
- [ ] [ALLE] Rollen verteilen, Teamgröße bestätigen
- [ ] [ALLE] API-Vertrag aus `docs/ARCHITEKTUR.md` §5 kurz durchgehen und einfrieren (Änderungen nur nach Absprache)

**Abschluss:** priorisiertes Backlog, gewähltes Demo-Szenario, eingefrorener API-Vertrag.

### Phase 2: Ingest & Normalisierung (Tag 1, nachmittags/abends)
- [ ] [ING] `scanner.py`: rekursiv scannen, Metadaten (`server_info.json`, `README.md`) trennen, Server/Anwendung/Komponente aus dem Pfad
- [ ] [ING] `fingerprint.py`: SHA-256 je Datei, byte-gleiche Kopien nur verknüpfen
- [ ] [ING] `reader.py`: `.gz` im Speicher, UTF-8 mit Windows-1252-Fallback, CRLF
- [ ] [ING] Parser `kv_log`, `bracket_json`, `csv_semicolon` (mehrzeilig), `jsonl`, `xml_events`, `freetext`
- [ ] [ING] Parser-Tests mit echten Beispielzeilen je Format
- [ ] [ING] `storage/schema.sql` + `db.py`: Tabellen `sources`, `events`; Arrow-Batch-Insert
- [ ] [ANA] `timestamps.py` (UTC) und `levels.py` (Level-Mapping)
- [ ] [ANA] `dedupe.py`: Event-Fingerprint, Duplikate markieren
- [ ] [AI] `eval/questions.yaml` v1: 10–15 Testfragen mit richtiger Ursache, Servern und Belegen
- [ ] [FE] Seitengerüst mit Navigation; Übersicht mit Mock-Daten

**Abschluss:** Voller Ingest läuft durch, alle Events sind in DuckDB. Plausibilitäts-Check: Events pro Server, Level-Verteilung, Anzahl Duplikate stimmen ungefähr mit der Analyse in §3 überein.

### Phase 3: Analyse (Tag 2, vormittags)
- [ ] [ANA] `templates.py`: Drain3 mit Maskierung, `template_id` je Event
- [ ] [ANA] `error_groups.py`: Gruppen bilden, Status „erholt" / „fehlgeschlagen"
- [ ] [ANA] `anomalies.py`: Fehlerrate vs. Baseline, neue/seltene Templates, Dauer-Ausreißer
- [ ] [ANA] `clock.py`: Uhrabweichung erkennen (`mait_win02_dispatcher_worker`), `clock_offset_s` setzen
- [ ] [ING] API: `/stats`, `/sources`, `/events`, `/events/{id}`, `/events/{id}/context`
- [ ] [FE] Zeitleiste (ECharts) und Event-Tabelle an echte API anbinden
- [ ] [FE] `SourceViewer`: Originalzeilen um ein Event anzeigen

**Abschluss:** Fehlergruppen für das Demo-Szenario sind korrekt; harmlose ERRORs landen in „erholt"; Zeitleiste zeigt echte Daten.

### Phase 4: Korrelation & KI-Assistent (Tag 2, nachmittags/abends)
- [ ] [ANA] `correlation.py`: harte (Trace, Job im Zeitfenster, Objekt-ID, `INC-xx`) und weiche Verknüpfungen
- [ ] [ANA] `graph.py` + API `/analysis/graph`, `/analysis/groups`, `/analysis/anomalies`, `/analysis/timeseries`, `/trace/{key}`
- [ ] [AI] `providers/`: `ClaudeProvider` (und Schnittstelle für Ollama)
- [ ] [AI] `tools.py`: `search_events`, `get_error_groups`, `get_anomalies`, `trace`, `correlate`, `get_context`
- [ ] [AI] `prompt.py` + `answer.py`: Antwortformat mit Belegen, Unsicherheit, Prüfschritten; Event-IDs prüfen
- [ ] [AI] `agent.py`: Tool-Use-Schleife mit Rundenlimit; `costs.py` schreibt `llm_calls`
- [ ] [AI] API `/chat` mit SSE (`step`, `token`, `answer`, `done`)
- [ ] [FE] Chat-Seite mit Zwischenschritten, `AnswerCard`, `EvidenceChip` → `SourceViewer`
- [ ] [AI] `scripts/evaluate.py`: erster Evaluationslauf

**Abschluss (Meilenstein):** Die Demo-Frage funktioniert einmal komplett End-to-End im Frontend. Erste Zahlen zu Trefferquote und Kosten liegen vor.

### Phase 5: Kontinuierlich & Vervollständigung (Tag 3, vormittags)
- [ ] [ING] `checkpoint.py`: Byte-Offset/Zeile je Datei, inkrementeller Ingest
- [ ] [ING] `watcher.py`: watchdog im Backend-Prozess, neue Dateien automatisch einlesen
- [ ] [ING] API `/ingest` und `/ingest/progress` (SSE)
- [ ] [ANA] Verspätete Einträge markieren; Uhr-Korrektur in der Zeitleiste sichtbar machen
- [ ] [FE] Fehlergruppen-Seite, Abhängigkeitsgraph (Cytoscape.js), `IngestProgress`
- [ ] [AI] Prompt anhand der Evaluation verbessern (falsche Ursachen, fehlende Belege)

**Abschluss:** Eine neu in den Ordner kopierte Logdatei erscheint ohne Neustart und ohne Duplikate in der UI.

### Phase 6: Evaluation & Feinschliff (Tag 3, mittags)
- [ ] [AI] Finaler Evaluationslauf; Vergleich „ganze Logs" vs. „Tools" für die Kosten
- [ ] [FE] Seite „Qualität & Kosten" mit den Zahlen aus `/eval/results`
- [ ] [ALLE] Kann-Stories nur, wenn alle Muss-Stories fertig sind (Ticket-Entwurf, „schon mal passiert?", Masking)
- [ ] [ALLE] Bugfixing, Demo-Pfad mehrfach durchklicken
- [ ] [ALLE] **Feature-Freeze 16:00**

**Abschluss:** Alle Punkte der Definition of Done (§15) sind abgehakt.

### Phase 7: Pitch-Vorbereitung (Tag 3, nachmittags/abends)
- [ ] [FE] Demo-Skript Schritt für Schritt (welche Klicks, welche Frage, welche Belege)
- [ ] [FE] Folien nach §12, mit echten Zahlen aus der Evaluation
- [ ] [ALLE] Backup-Video der Demo aufnehmen
- [ ] [ING] DuckDB vorab bauen und sichern; Start ohne Internet testen (außer LLM)
- [ ] [ALLE] README im Repo: Projekt, Start, Architektur-Links
- [ ] [ALLE] Generalprobe mit Zeitnahme, Jury-Fragen üben

**Abschluss:** Pitch passt in 5 Minuten, Demo läuft zweimal hintereinander fehlerfrei.

### Phase 8: Pitch Day (Tag 4)
- [ ] [ALLE] Letzter Durchlauf am Morgen
- [ ] [ING] Demo-Rechner prüfen: Backend, Frontend, DuckDB, API-Schlüssel, Internet
- [ ] [FE] Backup-Video und Folien offline verfügbar
- [ ] [ALLE] Pitch halten, Fragen beantworten

## 17. Aufgeschobene Entscheidungen

Bewusst vertagte Entscheidungen (Details und Stand in [plan.en.md](plan.en.md) §17).

### D1: Wo das Logpaket liegt (Sichtbarkeit des Repos)

- **Stand:** offen, entscheiden wir später im Team. Commit `87bfd44` (ZIP per Git LFS) wird bis dahin **nicht gepusht**.
- **Problem:** Eine LFS-Datei hat bei GitHub immer dieselbe Sichtbarkeit wie das Repo; man kann sie nicht einzeln privat stellen. In einem öffentlichen Repo kann jeder die ZIP herunterladen, und einmal hochgeladen bekommt man sie nur durch Löschen des Repos oder über den GitHub-Support wieder weg.
- **Möglichkeiten:**

| Variante | Code | Logdaten | Aufwand |
|---|---|---|---|
| A. Ganzes Repo privat | privat | privat (LFS) | keiner, fertig gebaut |
| B. Zweites, privates Repo nur für die Daten | öffentlich | privat | klein: Download holt die ZIP aus dem Daten-Repo statt per `git lfs pull` |
| C. ZIP als Release-Anhang in einem privaten Repo | öffentlich | privat | klein, braucht aber ein GitHub-Token |
| D. Cloud-Speicher (OneDrive, S3 …) | öffentlich | privat | mittel, Freigabelinks lassen sich leicht weitergeben |

- **Empfehlung:** A, wenn der Code nicht öffentlich sein muss; B, wenn er öffentlich bleiben soll.
- **Beim Veranstalter nachfragen:** Dürfen die MAIT-Logs überhaupt weitergegeben werden? Falls nein, müssen die Daten in jeder Variante privat bleiben.
