import datetime

import pytest

from unitelabs.applied_biosystems_atc.io import format_duration


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (1, "00:00:01"),
        (59.9, "00:00:59"),
        (3725, "01:02:05"),
        (25 * 3600, "25:00:00"),
    ],
)
def test_formats_duration_as_hours_minutes_seconds(seconds, expected):
    assert format_duration(datetime.timedelta(seconds=seconds)) == expected
