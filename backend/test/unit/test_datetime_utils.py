from datetime import datetime

from yuxi.utils.datetime_utils import UTC, SHANGHAI_TZ, format_utc_datetime


def test_format_utc_datetime_treats_naive_clock_as_utc():
    naive_utc = datetime(2026, 9, 21, 7, 26, 12)

    assert format_utc_datetime(naive_utc) == "2026-09-21T07:26:12Z"


def test_format_utc_datetime_converts_shanghai_aware_to_utc_z():
    shanghai = datetime(2026, 9, 21, 15, 26, 12, tzinfo=SHANGHAI_TZ)

    assert format_utc_datetime(shanghai) == "2026-09-21T07:26:12Z"


def test_format_utc_datetime_keeps_aware_utc():
    aware_utc = datetime(2026, 9, 21, 7, 26, 12, tzinfo=UTC)

    assert format_utc_datetime(aware_utc) == "2026-09-21T07:26:12Z"


def test_format_utc_datetime_returns_none_for_missing_value():
    assert format_utc_datetime(None) is None
