
from logtracer.analysis.anomalies import detect_spikes


def test_normal_error_counts():
    counts = [2, 3, 2, 4, 3, 2, 3]

    result = detect_spikes(counts)

    assert result == []


def test_detect_error_spike():
    baseline = [2, 3, 2, 4, 3, 2, 3]

    # Compare a new interval against a normal baseline.
    new_count = 35

    result = detect_spikes(baseline + [new_count], sensitivity=2.0)

    assert len(result) == 1
    assert result[0]["count"] == 35


def test_empty_counts():
    assert detect_spikes([]) == []
