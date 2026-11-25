"""Question suggestions for the assistant, derived from the ingested logs (no LLM call).

Two scopes:
- logs:  what stands out in the whole database (jobs, incidents, days, servers, noise)
- event: questions about one event that the user has open (its job, server and time)

The wording lives here in English and German, so a new kind of suggestion needs no frontend
change. Server names, job numbers and messages are taken over unchanged from the logs.
"""

from datetime import datetime, timedelta
from itertools import zip_longest
from statistics import median
from typing import Literal

import duckdb

from logtracer.storage.repositories import events as events_repo
from logtracer.storage.repositories import suggestions as repo

Language = Literal["en", "de"]

RECENT = timedelta(hours=24)  # "recent" is measured from the newest real error in the logs
FIRST_JOBS = 3
MIN_SPIKE_ERRORS = 10
SPIKE_FACTOR = 2
MESSAGE_CHARS = 100

# kind -> language -> (question, reason)
TEXTS: dict[str, dict[str, tuple[str, str]]] = {
    "job": {
        "en": ("What caused the errors in {job_id}?", "{errors}, {runs}, {servers}"),
        "de": ("Was hat die Fehler in {job_id} verursacht?", "{errors}, {runs}, {servers}"),
    },
    "incident": {
        "en": ("What caused {incident} and which systems were affected?", "{errors}, {day}"),
        "de": ("Was hat {incident} verursacht und welche Systeme waren betroffen?",
               "{errors}, {day}"),
    },
    "day": {
        "en": ("Why were there so many errors on {day}?",
               "{errors}, {usual} on a typical day"),
        "de": ("Warum gab es am {day} so viele Fehler?",
               "{errors}, {usual} an einem typischen Tag"),
    },
    "server": {
        "en": ("Which problems did {host} have on {day}?", "{errors}"),
        "de": ("Welche Probleme hatte {host} am {day}?", "{errors}"),
    },
    "message": {
        "en": ('What is behind the error "{message}"?', "{errors}, last on {day}"),
        "de": ("Was steckt hinter dem Fehler „{message}“?", "{errors}, zuletzt am {day}"),
    },
    "noise": {
        "en": ('Are the ERROR entries "{message}" harmless?',
               "{errors}, otherwise logged as normal"),
        "de": ("Sind die ERROR-Einträge „{message}“ harmlos?",
               "{errors}, sonst als normal protokolliert"),
    },
    "event_error": {
        "en": ('What caused "{message}" on {host} at {time}?', "opened error"),
        "de": ("Was hat „{message}“ auf {host} um {time} verursacht?", "geöffneter Fehler"),
    },
    "event_info": {
        "en": ('What does "{message}" on {host} at {time} mean?', "opened entry"),
        "de": ("Was bedeutet „{message}“ auf {host} um {time}?", "geöffneter Eintrag"),
    },
    "event_noise": {
        "en": ('Is the ERROR "{message}" on {host} at {time} harmless?',
               "this message is normal most of the time"),
        "de": ("Ist der ERROR „{message}“ auf {host} um {time} harmlos?",
               "die Meldung ist meist normal"),
    },
    "job_errors": {
        "en": ("What caused the errors in {job_id}?", "{errors}, {servers}"),
        "de": ("Was hat die Fehler in {job_id} verursacht?", "{errors}, {servers}"),
    },
    "job_flow": {
        "en": ("Which servers and steps did {job_id} pass through?", "{servers}"),
        "de": ("Über welche Server und Schritte lief {job_id}?", "{servers}"),
    },
    "job_runs": {
        "en": ("Do the other runs of {family} show the same problem?", "{runs}"),
        "de": ("Zeigen die anderen Läufe von {family} dasselbe Problem?", "{runs}"),
    },
    "around": {
        "en": ("What else happened on {host} around {time}?", "same server, same time"),
        "de": ("Was passierte sonst noch auf {host} gegen {time}?", "gleicher Server, gleiche Zeit"),
    },
}

_UNITS = {
    "errors": {"en": ("error", "errors"), "de": ("Fehler", "Fehler")},
    "runs": {"en": ("run", "runs"), "de": ("Lauf", "Läufe")},
    "servers": {"en": ("server", "servers"), "de": ("Server", "Server")},
}


def _short(message: str | None) -> str:
    """First line of a message, shortened; double quotes would break the quoted question."""
    lines = (message or "").strip().splitlines() or [""]
    text = " ".join(lines[0].split()).replace('"', "'")
    return text if len(text) <= MESSAGE_CHARS else text[: MESSAGE_CHARS - 1].rstrip() + "…"


def _suggestion(kind: str, lang: Language, row: dict) -> dict:
    values = {**row, "message": _short(row.get("message"))}
    ts: datetime | None = row.get("last_ts")
    if ts is not None:
        values.setdefault("day", f"{ts:%Y-%m-%d}")
        values.setdefault("time", f"{ts:%Y-%m-%d %H:%M:%S} UTC")
    for unit, names in _UNITS.items():
        if unit in row:
            values[unit] = f"{row[unit]} {names[lang][row[unit] != 1]}"
    question, reason = TEXTS[kind][lang]
    return {
        "kind": kind,
        "question": question.format(**values),
        "reason": reason.format(**values),
        "job_id": row.get("job_id"),
        "event_id": row.get("event_id"),
        "last_ts": ts,
    }


def _unusual_days(days: list[dict]) -> list[dict]:
    """Days with clearly more errors than a typical day, newest first."""
    if len(days) < 3:
        return []
    usual = median(d["errors"] for d in days)
    found = [
        {**d, "day": d["day"].isoformat(), "usual": f"{usual:.0f}"}
        for d in days
        if d["errors"] >= max(MIN_SPIKE_ERRORS, SPIKE_FACTOR * usual)
    ]
    return found[::-1]


def suggest_from_logs(con: duckdb.DuckDBPyConnection, limit: int = 8,
                      lang: Language = "en") -> list[dict]:
    """What stands out in the logs, mixed over the kinds. Empty if there are no errors."""
    repo.prepare(con)
    jobs: list[dict] = []
    others: list[tuple[str, list[dict]]] = []
    newest = repo.newest_error(con)
    if newest is not None:
        since = newest - RECENT
        jobs = repo.job_families(con, since, limit)
        others = [
            ("incident", repo.incidents(con, limit)),
            ("day", _unusual_days(repo.errors_per_day(con))),
            ("server", repo.servers(con, since, limit)),
            ("message", repo.messages(con, since, limit)),
        ]
    others.append(("noise", repo.noise(con, 1)))
    others.append(("job", jobs[FIRST_JOBS:]))

    # Some jobs first, then one of each kind in turn, so the list is never one-sided.
    ordered = [("job", row) for row in jobs[:FIRST_JOBS]]
    for group in zip_longest(*([(kind, row) for row in rows] for kind, rows in others)):
        ordered.extend(item for item in group if item is not None)
    return [_suggestion(kind, lang, row) for kind, row in ordered[:limit]]


def suggest_for_event(con: duckdb.DuckDBPyConnection, event_pk: int, limit: int = 5,
                      lang: Language = "en") -> list[dict] | None:
    """Questions about one event, its job and its surroundings. None if the event is unknown."""
    event = events_repo.get_event(con, event_pk)
    if event is None:
        return None
    message = event["message"] or event["raw"]
    row = {"message": message, "host": event["host"], "event_id": event["id"],
           "job_id": event["job_id"], "last_ts": event["ts_utc"]}
    located = event["ts_utc"] is not None and event["host"]
    items = []
    if located:
        kind = "event_info"
        if event["level"] in ("ERROR", "FATAL"):
            kind = "event_noise" if repo.is_noise(con, message) else "event_error"
        items.append(_suggestion(kind, lang, row))
    if event["job_id"]:
        job = {**row, **repo.job_summary(con, event["job_id"])}
        if job["errors"]:
            items.append(_suggestion("job_errors", lang, job))
        items.append(_suggestion("job_flow", lang, job))
        if job["runs"] > 1:
            items.append(_suggestion("job_runs", lang, job))
    if located:
        items.append(_suggestion("around", lang, row))
    return items[:limit]
