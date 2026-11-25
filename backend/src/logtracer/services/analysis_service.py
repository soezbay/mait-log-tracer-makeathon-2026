"""Read access to the analysis results for the API."""

import duckdb

from logtracer.storage.repositories import analysis as repo


def list_incidents(con: duckdb.DuckDBPyConnection, **filters) -> tuple[list[dict], int]:
    items, total = repo.list_incidents(con, **filters)
    jobs = repo.incident_jobs(con, [i["incident_id"] for i in items]) if items else {}
    for item in items:
        item["jobs"] = jobs.get(item["incident_id"], [])
    return items, total


def get_incident(con: duckdb.DuckDBPyConnection, incident_id: int) -> dict | None:
    """One incident with its steps in time order, the links between them and anomalies."""
    items, _ = list_incidents(con, incident_id=incident_id)
    found = repo.incident_group_ids(con, incident_id)
    if not items or found is None:
        return None
    incident, (group_ids, root_group_id) = items[0], found
    steps, _ = repo.groups(con, group_ids=group_ids)
    for step in steps:
        step["is_root"] = step["group_id"] == root_group_id
    anomalies, _ = repo.list_anomalies(
        con, hosts=incident["hosts"], ts_from=incident["first_ts"], ts_to=incident["last_ts"],
        limit=20)
    return {**incident, "steps": steps, "links": repo.links(con, group_ids),
            "anomalies": anomalies}


def list_groups(con: duckdb.DuckDBPyConnection, limit: int, offset: int
                ) -> tuple[list[dict], int]:
    """Error groups in the shape of the API contract (id, label, status, event_ids)."""
    items, total = repo.groups(con, limit=limit, offset=offset)
    for item in items:
        item["id"] = item["group_id"]
        item["label"] = f"{item['host']} · {item['component']} · {item['message']}"
    return items, total
