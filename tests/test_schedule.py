"""Slot rounding decides which hour a late-firing run reports on."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from scraper.schedule import in_window, is_final, slot_for

TZ = ZoneInfo("America/Chicago")


def at(hour: int, minute: int = 0, day: int = 19) -> dt.datetime:
    """2026-08-19 is a Wednesday; 2026-08-22 a Saturday."""
    return dt.datetime(2026, 8, day, hour, minute, tzinfo=TZ)


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (7, 41, 8),   # cron fired on time
        (7, 52, 8),   # typical: 11 minutes of scheduler drift
        (8, 17, 8),   # worst observed: 36 minutes of drift
        (8, 29, 8),   # last minute that still rounds down
        (8, 30, 9),   # :30 rounds up
        (8, 31, 9),
        (16, 17, 16),
    ],
)
def test_slot_rounds_to_the_nearest_hour(hour, minute, expected):
    assert slot_for(at(hour, minute)).hour == expected


def test_whole_firing_window_lands_in_one_slot():
    """:41 plus the measured 11-36 min drift must never straddle two slots."""
    slots = {slot_for(at(7, 41) + dt.timedelta(minutes=d)).hour for d in range(0, 37)}
    assert slots == {8}


def test_early_run_is_inside_the_window():
    """A 7:52 run is the 8am report and must not be dropped as "too early"."""
    assert in_window(at(7, 52))
    assert in_window(at(7, 41))


def test_run_before_the_first_slot_is_dropped():
    assert not in_window(at(6, 41))  # slot 7, CST-season firing
    assert not in_window(at(7, 20))  # slot 7


def test_run_past_the_last_slot_is_dropped():
    assert not in_window(at(16, 41))  # slot 17
    assert in_window(at(16, 17))      # slot 16, the final report


def test_weekend_is_judged_by_the_slot():
    assert not in_window(at(9, 0, day=22))   # Saturday
    assert not in_window(at(23, 41, day=21))  # Friday 23:41 -> Saturday slot


def test_final_slot_carries_the_chart():
    assert is_final(at(15, 52))  # slot 16
    assert is_final(at(16, 17))  # slot 16
    assert not is_final(at(15, 17))  # slot 15
