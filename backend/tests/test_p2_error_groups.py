
from logtracer.analysis.error_groups import classify_event


def test_error_classification():
    assert classify_event(
        "ERROR", "Database unavailable"
    ) == "error"

    assert classify_event(
        "WARN", "Connection taking too long"
    ) == "warning"

    assert classify_event(
        "INFO", "Request accepted"
    ) == "normal"

    assert classify_event(
        "INFO", "Workflow transition complete"
    ) == "normal"

    assert classify_event(
        None, "Connection failed"
    ) == "possible_error"

    assert classify_event(
        None, "Unknown event"
    ) == "unknown"
