"""Which events are real problems? Shared input of error groups and anomalies.

Many messages in the log package are logged as WARN or ERROR now and then although they are
normal ("Job heartbeat" is INFO more than 99 % of the time). They would connect unrelated
problems, so a message counts as a problem only if at least NOISE_SHARE of all its lines are
WARN or worse.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

import duckdb

NOISE_SHARE = 0.10
PROBLEM_LEVELS = "('WARN', 'ERROR', 'FATAL')"

# The message without free-standing numbers: "Queue depth increased to 125" and "... to 130" are
# the same message. Numbers inside identifiers (INC-03, DEMO-033.pdf) stay, because they tell
# different problems apart.
MESSAGE_KEY = r"regexp_replace(message, '(^|[\s=:(,/])\d+([.,]\d+)*', '\1<n>', 'g')"


# Connections with an open `atomic` block in this thread (DuckDB has no nested transactions).
_open: ContextVar[frozenset[int]] = ContextVar("open_transactions", default=frozenset())


@contextmanager
def atomic(con: duckdb.DuckDBPyConnection) -> Iterator[None]:
    """Run a block in one transaction; inside an outer `atomic` it joins that transaction."""
    if id(con) in _open.get():
        yield
        return
    con.execute("BEGIN TRANSACTION")
    token = _open.set(_open.get() | {id(con)})
    try:
        yield
    except BaseException:
        con.execute("ROLLBACK")
        raise
    else:
        con.execute("COMMIT")
    finally:
        _open.reset(token)


def collect_problems(con: duckdb.DuckDBPyConnection) -> int:
    """(Re)build the temp table `problem_events`. Temp tables are private to the cursor."""
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE problem_events AS
        WITH problem_keys AS (
            SELECT {MESSAGE_KEY} AS message_key FROM events
            WHERE message IS NOT NULL AND duplicate_of IS NULL
            GROUP BY message_key
            HAVING avg(CASE WHEN level IN {PROBLEM_LEVELS} THEN 1.0 ELSE 0.0 END) >= ?
        )
        SELECT id, ts_utc, host, component, level, job_id, trace_id, template_id, message,
               {MESSAGE_KEY} AS message_key
        FROM events
        WHERE level IN {PROBLEM_LEVELS} AND duplicate_of IS NULL AND ts_utc IS NOT NULL
          AND message IS NOT NULL
          AND {MESSAGE_KEY} IN (SELECT message_key FROM problem_keys)
        """,
        [NOISE_SHARE],
    )
    return con.execute("SELECT count(*) FROM problem_events").fetchone()[0]
