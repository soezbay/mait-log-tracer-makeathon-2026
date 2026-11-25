
"""Group similar log messages using Drain3."""

from collections import defaultdict

from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig


def build_templates(con):
    """
    Read events using Safak's existing DuckDB connection.
    Group log messages and store the results.
    """

    config = TemplateMinerConfig()
    miner = TemplateMiner(config=config)

    rows = con.execute(
        """
        SELECT id, message, ts_utc
        FROM events
        WHERE message IS NOT NULL
          AND TRIM(message) <> ''
          AND duplicate_of IS NULL
        ORDER BY id
        """
    ).fetchall()

    grouped = defaultdict(
        lambda: {"count": 0, "timestamps": []}
    )

    assignments = []

    for event_id, message, timestamp in rows:
        result = miner.add_log_message(message)

        cluster_id = result["cluster_id"]

        grouped[cluster_id]["count"] += 1

        if timestamp is not None:
            grouped[cluster_id]["timestamps"].append(timestamp)

        assignments.append((cluster_id, event_id))

    # Replace earlier template analysis.
    # Run only when ingestion is stopped.
    con.execute("BEGIN TRANSACTION")

    try:
        con.execute("UPDATE events SET template_id = NULL")
        con.execute("DELETE FROM templates")

        clusters = {
            cluster.cluster_id: cluster
            for cluster in miner.drain.clusters
        }

        for cluster_id, info in grouped.items():
            cluster = clusters[cluster_id]
            timestamps = info["timestamps"]

            con.execute(
                """
                INSERT INTO templates (
                    template_id,
                    template,
                    count,
                    first_seen,
                    last_seen,
                    in_baseline
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    cluster_id,
                    cluster.get_template(),
                    info["count"],
                    min(timestamps) if timestamps else None,
                    max(timestamps) if timestamps else None,
                    False,
                ],
            )

        con.executemany(
            """
            UPDATE events
            SET template_id = ?
            WHERE id = ?
            """,
            assignments,
        )

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    return {
        "events_processed": len(rows),
        "templates_created": len(grouped),
    }
