"""Unit tests for schedule calculation and timezone handling."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.main import calculate_next_scheduled_run, get_ha_timezone


def test_calculate_next_scheduled_run_future_today():
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 8, 14, 2, 0, 0, tzinfo=tz)
    next_run = calculate_next_scheduled_run("03:00", tz=tz, now=now)
    assert next_run == datetime(2026, 8, 14, 3, 0, 0, tzinfo=tz)


def test_calculate_next_scheduled_run_past_today():
    tz = ZoneInfo("America/New_York")
    now = datetime(2026, 8, 14, 4, 0, 0, tzinfo=tz)
    next_run = calculate_next_scheduled_run("03:00", tz=tz, now=now)
    assert next_run == datetime(2026, 8, 15, 3, 0, 0, tzinfo=tz)


def test_calculate_next_scheduled_run_invalid_format():
    tz = ZoneInfo("UTC")
    now = datetime(2026, 8, 14, 2, 0, 0, tzinfo=tz)
    next_run = calculate_next_scheduled_run("invalid_time", tz=tz, now=now)
    assert next_run == datetime(2026, 8, 14, 3, 0, 0, tzinfo=tz)


def test_get_ha_timezone_utc_fallback():
    tz_obj, tz_name = get_ha_timezone(client=None)
    assert tz_obj == UTC
    assert tz_name == "UTC"


def test_get_ha_timezone_invalid_tz_name(monkeypatch):
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.get_config_timezone.return_value = "Invalid/Timezone_Name"
    tz_obj, tz_name = get_ha_timezone(client=mock_client)
    assert tz_obj == UTC
    assert tz_name == "UTC"


def test_calculate_next_scheduled_run_invalid_hours():
    tz = ZoneInfo("UTC")
    now = datetime(2026, 8, 14, 2, 0, 0, tzinfo=tz)
    # Hour > 23 or minute > 59
    next_run = calculate_next_scheduled_run("25:99", tz=tz, now=now)
    assert next_run == datetime(2026, 8, 14, 3, 0, 0, tzinfo=tz)
