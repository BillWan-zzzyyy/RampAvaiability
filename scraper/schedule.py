"""Which reporting slot a run belongs to.

GitHub's cron scheduler is unreliable on the free tier: measured on this repo it
arrives 12 to 201 minutes late and drops most firings outright. The workflow
therefore fires three times an hour and the first arrival for a slot claims it.

That makes "which hour is this run reporting on?" a separate question from
"what time is it right now": a run that starts at 7:52 is the 8am report. The
slot is the observation time rounded to the nearest hour, and everything that
needs an hour — the window check, the end-of-day decision, the CSV bucket, the
chart's x-axis, the subject line — uses it. Only the email body shows the real
observation time, so the reader is never told a reading is fresher than it is.
"""

from __future__ import annotations

import datetime as dt

from . import config

HALF_HOUR = dt.timedelta(minutes=30)


def slot_for(moment: dt.datetime) -> dt.datetime:
    """The reporting hour this moment belongs to (nearest hour, :30 rounds up)."""
    return (moment + HALF_HOUR).replace(minute=0, second=0, microsecond=0)


def in_window(moment: dt.datetime) -> bool:
    """True when this run's slot is a weekday hour inside the reporting window."""
    slot = slot_for(moment)
    return (
        slot.weekday() < 5  # Monday=0 .. Friday=4
        and config.FIRST_HOUR <= slot.hour <= config.LAST_HOUR
    )


def is_final(moment: dt.datetime) -> bool:
    """True for the last slot of the day, the one that carries the chart."""
    return slot_for(moment).hour >= config.LAST_HOUR
