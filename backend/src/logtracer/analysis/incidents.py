"""Build candidate incidents from related error groups."""

from collections import defaultdict

import duckdb
import pyarrow as pa

from logtracer.analysis.problems import atomic

# Heuristic scores, not probabilities.
SINGLE, BY_TIME, RELATED, WITH_DEPENDENCY = 0.3, 0.5, 0.7, 0.9


def build_incidents(con: duckdb.DuckDBPyConnection, min_confidence: float = 0.6) -> dict:
    """Combine correlated error groups into candidate incidents.

    The trigger is the group whose server other groups name as `dependency=<server>`, otherwise
    the earliest group. It is a candidate, not a confirmed root cause. The incident ID is the ID
    of the trigger group. Successful retries alone are no incident; a chain that ends with a
    recovery has the status recovered.
    """
    groups = {row[0]: row for row in con.execute(
        "SELECT group_id, host, first_ts, last_ts, status FROM error_groups").fetchall()}
    links = con.execute(
        "SELECT group_a, group_b, kind FROM correlations WHERE confidence >= ?", [min_confidence]
    ).fetchall()
    linked_by_id = {g for a, b, kind in links if kind == "hard" for g in (a, b)}
    dependencies = _named_dependencies(con)
    titles = _titles(con)

    candidates = []
    for members in _connected(groups, [(a, b) for a, b, _ in links]):
        members.sort(key=lambda g: (groups[g][2] is None, groups[g][2], g))  # in time order
        statuses = {groups[g][4] for g in members}
        if statuses == {"recovered"}:
            continue
        named = defaultdict(int)  # how often the others name this group's server
        for candidate in members:
            for other in members:
                if other != candidate:
                    named[candidate] += dependencies.get((other, groups[candidate][1]), 0)
        root = max(members, key=lambda g: named[g]) if any(named.values()) else members[0]
        if len(members) == 1:
            confidence = SINGLE
        elif named[root]:
            confidence = WITH_DEPENDENCY
        else:
            confidence = RELATED if linked_by_id.intersection(members) else BY_TIME
        if groups[members[-1]][4] == "recovered":
            status = "recovered"
        else:
            status = "failed" if "failed" in statuses else "unknown"
        candidates.append({
            "incident_id": root,
            "title": titles.get(root, "Unknown problem"),
            "first_ts": min((groups[g][2] for g in members if groups[g][2]), default=None),
            "last_ts": max((groups[g][3] for g in members if groups[g][3]), default=None),
            "status": status,
            "hosts": sorted({groups[g][1] for g in members if groups[g][1]}),
            "group_ids": members,
            "root_group_id": root,
            "confidence": confidence,
        })

    with atomic(con):
        con.execute("DELETE FROM incidents")
        if candidates:
            con.register("_incidents", pa.Table.from_pylist(candidates, schema=_SCHEMA))
            try:
                con.execute("INSERT INTO incidents SELECT * FROM _incidents")
            finally:
                con.unregister("_incidents")
    return {"incidents_created": len(candidates), "groups_processed": len(groups)}


_SCHEMA = pa.schema([
    ("incident_id", pa.int32()), ("title", pa.string()), ("first_ts", pa.timestamp("us")),
    ("last_ts", pa.timestamp("us")), ("status", pa.string()), ("hosts", pa.list_(pa.string())),
    ("group_ids", pa.list_(pa.int32())), ("root_group_id", pa.int32()),
    ("confidence", pa.float64()),
])


def _connected(groups: dict, links: list[tuple[int, int]]) -> list[list[int]]:
    """Connected components of the correlation graph."""
    parent = {g: g for g in groups}

    def find(g: int) -> int:
        while parent[g] != g:
            parent[g] = parent[parent[g]]
            g = parent[g]
        return g

    for a, b in links:
        if a in parent and b in parent:
            parent[find(b)] = find(a)
    components = defaultdict(list)
    for g in parent:
        components[find(g)].append(g)
    return list(components.values())


def _named_dependencies(con: duckdb.DuckDBPyConnection) -> dict[tuple[int, str], int]:
    """(group, server) -> number of its events that say `dependency=<server>`."""
    rows = con.execute(
        r"""
        SELECT gm.group_id, regexp_extract(e.message, 'dependency=([\w.-]+)', 1) AS server, count(*)
        FROM group_members gm JOIN events e ON e.id = gm.event_pk
        WHERE e.message LIKE '%dependency=%' GROUP BY ALL
        """
    ).fetchall()
    return {(group, server): count for group, server, count in rows}


def _titles(con: duckdb.DuckDBPyConnection) -> dict[int, str]:
    """First line of the first message of each group."""
    rows = con.execute(
        """
        SELECT g.group_id, e.message FROM error_groups g
        JOIN events e ON e.id = g.sample_event_ids[1]
        """
    ).fetchall()
    return {group: (message or "").strip().split("\n")[0].strip() for group, message in rows}
