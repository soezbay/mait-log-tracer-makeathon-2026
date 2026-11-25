"""Prepare error-group graph data for the frontend."""

import duckdb


def build_graph(con: duckdb.DuckDBPyConnection, group_ids: list[int] | None = None) -> dict:
    """Return nodes and relationships; with `group_ids` only those groups (one incident)."""
    where, params = "", []
    if group_ids is not None:
        where, params = "WHERE list_contains(?, group_id)", [group_ids]
    groups = con.execute(
        f"""
        SELECT group_id, host, component, level, count, status
        FROM error_groups {where} ORDER BY group_id
        """,
        params,
    ).fetchall()
    links = con.execute(
        """
        SELECT group_a, group_b, kind, link_key, lag_s, confidence
        FROM correlations ORDER BY correlation_id
        """
    ).fetchall()

    nodes = [
        {
            "id": str(group_id),
            "label": f"{component or 'unknown'} ({host or 'unknown'})",
            "host": host,
            "component": component,
            "level": level,
            "count": count,
            "status": status,
        }
        for group_id, host, component, level, count, status in groups
    ]
    valid_ids = {node["id"] for node in nodes}
    edges = [
        {
            "source": str(source),
            "target": str(target),
            "kind": kind,
            "link_key": link_key,
            "lag_s": lag,
            "confidence": confidence,
        }
        for source, target, kind, link_key, lag, confidence in links
        if str(source) in valid_ids and str(target) in valid_ids
    ]
    return {"nodes": nodes, "edges": edges}
