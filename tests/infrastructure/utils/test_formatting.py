import pytest

from src.infrastructure.utils.formatting import format_duration


def test_format_duration_zero() -> None:
    assert format_duration(0) == "0s"


def test_format_duration_seconds_only() -> None:
    assert format_duration(45) == "45s"


def test_format_duration_minutes_only() -> None:
    assert format_duration(120) == "2m"


def test_format_duration_hours_only() -> None:
    assert format_duration(7200) == "2h"


def test_format_duration_minutes_and_seconds() -> None:
    assert format_duration(125) == "2m 5s"


def test_format_duration_hours_and_minutes() -> None:
    assert format_duration(5400) == "1h 30m"


def test_format_duration_hours_minutes_seconds() -> None:
    assert format_duration(9015) == "2h 30m 15s"


def test_format_duration_negative_raises() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        format_duration(-1)
