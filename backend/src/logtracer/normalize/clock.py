
"""Clock correction utilities for log timestamps."""

from datetime import timedelta


def correct_timestamp(timestamp, offset_seconds):
    """
    Correct a timestamp using a known clock offset.

    Positive offset:
        Server clock is ahead of actual time.

    Negative offset:
        Server clock is behind actual time.
    """

    if timestamp is None:
        return None

    return timestamp - timedelta(seconds=offset_seconds)


def calculate_offset(server_time, reference_time):
    """
    Calculate how far the server clock differs
    from a trusted reference clock.
    """

    return (server_time - reference_time).total_seconds()


def apply_clock_correction(con, host, offset_seconds):
    """
    Apply a known correction to events from one host.

    Only use offsets derived from reliable evidence.
    Do not repeatedly apply the same correction.
    """

    rows = con.execute(
        """
        SELECT id, ts_utc, clock_offset_s
        FROM events
        WHERE host = ?
          AND ts_utc IS NOT NULL
        """,
        [host],
    ).fetchall()

    updated = 0

    con.execute("BEGIN TRANSACTION")

    try:
        for event_id, timestamp, previous_offset in rows:
            previous_offset = previous_offset or 0.0

            # Undo previous correction before applying
            # the newly estimated total offset.
            original_timestamp = timestamp + timedelta(
                seconds=previous_offset
            )

            corrected = correct_timestamp(
                original_timestamp, offset_seconds
            )

            con.execute(
                """
                UPDATE events
                SET ts_utc = ?,
                    clock_offset_s = ?
                WHERE id = ?
                """,
                [corrected, offset_seconds, event_id],
            )

            updated += 1

        con.execute("COMMIT")

    except Exception:
        con.execute("ROLLBACK")
        raise

    return {"events_updated": updated}


def apply_declared_offsets(con):
    """
    Correct events that state their own clock error (attrs.clock_offset_seconds).

    Only these events are moved, not everything from the same server: the offset is known
    for them alone. Events that are already corrected stay as they are.
    """

    updated = con.execute(
        """
        UPDATE events
        SET ts_utc = ts_utc - to_microseconds(CAST(o.offset_s * 1000000 AS BIGINT)),
            clock_offset_s = o.offset_s
        FROM (
            SELECT id, TRY_CAST(attrs ->> 'clock_offset_seconds' AS DOUBLE) AS offset_s
            FROM events
            WHERE CAST(attrs AS VARCHAR) LIKE '%clock_offset_seconds%'
        ) o
        WHERE events.id = o.id AND o.offset_s <> 0 AND events.clock_offset_s = 0
          AND events.ts_utc IS NOT NULL
        """
    ).fetchone()[0]

    return {"clock_corrected": updated}
