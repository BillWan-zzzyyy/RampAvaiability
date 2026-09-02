"""Decide, using only the standard library, whether this run has work to do.

The schedule fires 36 times a weekday because GitHub drops scheduled runs, and
most of those firings are redundant. Installing Chromium before finding that out
would waste about 70 seconds per firing, so the workflow runs this first — it
imports nothing outside the standard library and finishes in a second.

Writes ``proceed=true|false`` to $GITHUB_OUTPUT and always exits 0: "nothing to
do" is a normal outcome, not a failure.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys

from . import config, schedule, storage


def decide(now: dt.datetime) -> tuple[bool, str]:
    """(proceed, human-readable reason)."""
    slot = schedule.slot_for(now)
    if not schedule.in_window(now):
        return False, (
            f"slot {slot:%a %H:00} is outside the reporting window "
            f"(Mon-Fri {config.FIRST_HOUR}:00-{config.LAST_HOUR}:00)"
        )
    if storage.slot_already_recorded(slot):
        return False, f"slot {slot:%H:00} already reported today"
    return True, f"slot {slot:%H:00} not yet reported"


def main() -> int:
    now = dt.datetime.now(config.TIMEZONE)
    proceed, reason = decide(now)
    print(f"local time {now:%Y-%m-%d %H:%M:%S %Z} -> {reason}")
    print(f"proceed={str(proceed).lower()}")

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with pathlib.Path(output).open("a", encoding="utf-8") as fh:
            fh.write(f"proceed={str(proceed).lower()}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
