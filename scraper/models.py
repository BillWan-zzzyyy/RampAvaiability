"""Shared data types."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class LotRecord:
    """Availability for one parking lot at one point in time.

    ``available`` is None when the source publishes the lot but not a usable
    number (closed, "FULL" without a count, unparsable cell). Callers must show
    that as unknown rather than guessing a value.
    """

    lot_id: str
    name: str
    available: int | None
    total: int | None = None
    region: str = ""

    @property
    def is_full(self) -> bool:
        return self.available == 0


@dataclass(frozen=True)
class Sample:
    """A LotRecord stamped with the campus-local time it was observed."""

    observed_at: dt.datetime
    record: LotRecord
