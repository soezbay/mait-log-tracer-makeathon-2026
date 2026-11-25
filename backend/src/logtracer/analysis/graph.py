
"""Prepare error-group graph data for the frontend."""


def build_graph(con):
    """Return nodes and relationships from DuckDB."""

    groups = con.execute("""
        SELECT
            group_id,
            host,
            component,
            level,
            count,
            status
        FROM error_groups
        ORDER BY group_id
    """).fetchall()

    links = con.execute("""
        SELECT
            group_a,
            group_b,
            kind,
            link_key,
            lag_s,
            confidence
        FROM correlations
        ORDER BY correlation_id
    """).fetchall()

    nodes = []

    for group_id, host, component, level, count, status in groups:
        nodes.append({
            "id": str(group_id),
            "label": f"{component or 'unknown'} ({host or 'unknown'})",
            "host": host,
            "component": component,
            "level": level,
            "count": count,
            "status": status,
        })

    edges = []

    valid_ids = {node["id"] for node in nodes}

    for source, target, kind, link_key, lag, confidence in links:
        if str(source) not in valid_ids or str(target) not in valid_ids:
            continue

        edges.append({
            "source": str(source),
            "target": str(target),
            "kind": kind,
            "link_key": link_key,
            "lag_s": lag,
            "confidence": confidence,
        })

    return {
        "nodes": nodes,
        "edges": edges,
    }
