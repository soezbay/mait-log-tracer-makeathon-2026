"""Group similar log messages using Drain3."""

from datetime import date

import duckdb
import pyarrow as pa
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from logtracer.analysis.problems import MESSAGE_KEY, atomic

BASELINE_DAY = date(2026, 11, 23)  # mostly normal day of the log package (schema.sql: in_baseline)
SIMILARITY = 0.7  # Drain3's default 0.4 merges different messages (all INC numbers in one)


def build_templates(con: duckdb.DuckDBPyConnection, baseline_day: date = BASELINE_DAY) -> dict:
    """Find message templates, store them and set events.template_id.

    Each distinct message (numbers masked) is mined once, in order of its first event.
    Everything is written in bulk: one UPDATE per event takes more than half an hour on the
    full data.
    """
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE message_keys AS
        SELECT message, {MESSAGE_KEY} AS message_key, min(id) AS first_id FROM events
        WHERE message IS NOT NULL AND trim(message) <> '' AND duplicate_of IS NULL
        GROUP BY message
        """
    )
    keys = [row[0] for row in con.execute(
        "SELECT message_key FROM message_keys GROUP BY message_key ORDER BY min(first_id)"
    ).fetchall()]

    config = TemplateMinerConfig()
    config.drain_sim_th = SIMILARITY
    miner = TemplateMiner(config=config)
    cluster_ids = [miner.add_log_message(k)["cluster_id"] for k in keys]
    clusters = {c.cluster_id: c.get_template() for c in miner.drain.clusters}

    con.register("_key_templates", pa.table({
        "message_key": pa.array(keys, pa.string()),
        "template_id": pa.array(cluster_ids, pa.int32()),
    }))
    con.register("_templates", pa.table({
        "template_id": pa.array(list(clusters), pa.int32()),
        "template": pa.array(list(clusters.values()), pa.string()),
    }))
    try:
        with atomic(con):
            con.execute(
                """
                UPDATE events SET template_id = t.template_id
                FROM message_keys m JOIN _key_templates t USING (message_key)
                WHERE events.message = m.message AND events.duplicate_of IS NULL
                  AND events.template_id IS DISTINCT FROM t.template_id
                """
            )
            con.execute("DELETE FROM templates")
            con.execute(
                """
                INSERT INTO templates
                SELECT t.template_id, t.template, count(*), min(e.ts_utc), max(e.ts_utc),
                       coalesce(bool_or(CAST(e.ts_utc AS DATE) = ?), FALSE)
                FROM _templates t JOIN events e USING (template_id)
                WHERE e.duplicate_of IS NULL
                GROUP BY t.template_id, t.template
                """,
                [baseline_day],
            )
    finally:
        con.unregister("_key_templates")
        con.unregister("_templates")

    processed = con.execute("SELECT coalesce(sum(count), 0) FROM templates").fetchone()[0]
    return {"events_processed": int(processed), "templates_created": len(clusters)}
