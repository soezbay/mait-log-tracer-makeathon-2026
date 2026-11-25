
"""Build candidate incidents from related error groups."""


def build_incidents(con, min_confidence=0.6):
    """
    Combine correlated error groups into candidate incidents.

    Full rebuild for isolated testing only.
    The earliest group is a candidate origin, not
    a confirmed root cause.
    """

    groups = con.execute("""
        SELECT group_id, host, first_ts, last_ts, status
        FROM error_groups
        ORDER BY group_id
    """).fetchall()

    if not groups:
        return {"incidents_created": 0}

    group_data = {
        row[0]: {
            "host": row[1],
            "first": row[2],
            "last": row[3],
            "status": row[4],
        }
        for row in groups
    }

    # Initially, each group is independent.
    parent = {group_id: group_id for group_id in group_data}

    def find(group_id):
        while parent[group_id] != group_id:
            group_id = parent[group_id]
        return group_id

    def union(a, b):
        root_a = find(a)
        root_b = find(b)

        if root_a != root_b:
            parent[root_b] = root_a

    # Connect groups with sufficiently strong links.
    links = con.execute("""
        SELECT group_a, group_b, confidence
        FROM correlations
        WHERE confidence >= ?
    """, [min_confidence]).fetchall()

    for a, b, confidence in links:
        if a in parent and b in parent:
            union(a, b)

    # Collect connected groups into incidents.
    components = {}

    for group_id in parent:
        root = find(group_id)
        components.setdefault(root, []).append(group_id)

    candidates = []

    for member_ids in components.values():
        member_ids = sorted(member_ids)

        starts = [
            group_data[g]["first"]
            for g in member_ids
            if group_data[g]["first"] is not None
        ]

        ends = [
            group_data[g]["last"]
            for g in member_ids
            if group_data[g]["last"] is not None
        ]

        hosts = sorted({
            group_data[g]["host"]
            for g in member_ids
            if group_data[g]["host"]
        })

        # Fallback: choose the earliest group.
        root_group_id = min(
            member_ids,
            key=lambda g: (
                group_data[g]["first"] is None,
                group_data[g]["first"] or "",
                g,
            ),
        )

        # Prefer a group explicitly referenced as a dependency
        # by another group in the same incident.
        dependency_scores = {g: 0 for g in member_ids}

        for dependent_group in member_ids:
            dependent_host = group_data[dependent_group]["host"]

            # Some unit tests use a minimal database schema.
            tables = {
                row[0]
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main'"
                ).fetchall()
            }

            if {"group_members", "events"}.issubset(tables):
                messages = con.execute(
                    """
                    SELECT e.message
                    FROM group_members gm
                    JOIN events e ON e.id = gm.event_pk
                    WHERE gm.group_id = ?
                    """,
                    [dependent_group],
                ).fetchall()
            else:
                messages = []

            for (message,) in messages:
                if not message:
                    continue

                for candidate_group in member_ids:
                    if candidate_group == dependent_group:
                        continue

                    candidate_host = group_data[candidate_group]["host"]

                    if candidate_host and (
                            f"dependency={candidate_host}" in message
                    ):
                        dependency_scores[candidate_group] += 1

        # Use explicit dependency evidence when available.
        if any(dependency_scores.values()):
            root_group_id = max(
                member_ids,
                key=lambda g: (
                    dependency_scores[g],
                    -g,
                ),
            )

        statuses = {
            group_data[g]["status"]
            for g in member_ids
        }

        if statuses == {"recovered"}:
            status = "recovered"
        elif statuses == {"failed"}:
            status = "failed"
        else:
            status = "unknown"

        # This is a heuristic score, not a probability.
        confidence = (
            0.7 if len(member_ids) > 1 else 0.3
        )

        title = (
            f"Related errors across {len(hosts)} host(s)"
            if len(member_ids) > 1
            else f"Error group {member_ids[0]}"
        )

        candidates.append((
            title,
            min(starts) if starts else None,
            max(ends) if ends else None,
            status,
            hosts,
            member_ids,
            root_group_id,
            confidence,
        ))

    # Only run on a test DB or coordinated rebuild.
    con.execute("BEGIN TRANSACTION")

    try:
        con.execute("DELETE FROM incidents")

        for incident_id, candidate in enumerate(
            candidates, start=1
        ):
            con.execute("""
                INSERT INTO incidents (
                    incident_id,
                    title,
                    first_ts,
                    last_ts,
                    status,
                    hosts,
                    group_ids,
                    root_group_id,
                    confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [incident_id, *candidate])

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "incidents_created": len(candidates),
        "groups_processed": len(groups),
    }
