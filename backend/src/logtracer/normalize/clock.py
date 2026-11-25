
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
