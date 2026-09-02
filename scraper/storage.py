"""Append observations to a per-day CSV and read them back for charting.

One file per campus-local day (``data/YYYY-MM-DD.csv``) keeps the end-of-day chart
a plain file read, and the committed history doubles as a record you can look at
later without re-scraping.
"""

from __future__ import annotations

import csv
import datetime as dt
import pathlib
from collections.abc import Iterable, Sequence

from . import config
from .models import LotRecord, Sample
from .schedule import slot_for

# ``slot_local`` is the reporting hour a row belongs to; ``timestamp_local`` is
# when the scrape actually happened. They differ because the scheduler is late
# by a variable amount — see scraper/schedule.py.
HEADER = [
    "timestamp_local",
    "slot_local",
    "lot_id",
    "name",
    "available",
    "total",
    "region",
    "raw_status",
]


def csv_path(day: dt.date, data_dir: pathlib.Path | None = None) -> pathlib.Path:
    return (data_dir or config.DATA_DIR) / f"{day:%Y-%m-%d}.csv"


def append(
    records: Iterable[LotRecord],
    observed_at: dt.datetime,
    data_dir: pathlib.Path | None = None,
    slot: dt.datetime | None = None,
) -> pathlib.Path:
    """Append one observation round; creates the file with a header if needed.

    The file is named for the slot's date, so a run that drifts across midnight
    still lands in the day it is reporting on.
    """
    slot = slot or slot_for(observed_at)
    path = csv_path(slot.date(), data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if is_new:
            writer.writerow(HEADER)
        for rec in records:
            writer.writerow(
                [
                    observed_at.isoformat(timespec="seconds"),
                    slot.isoformat(timespec="seconds"),
                    rec.lot_id,
                    rec.name,
                    "" if rec.available is None else rec.available,
                    "" if rec.total is None else rec.total,
                    rec.region,
                    rec.raw_status,
                ]
            )
    return path


def load_day(day: dt.date, data_dir: pathlib.Path | None = None) -> list[Sample]:
    """Read every sample recorded for a day; missing file means no samples yet."""
    path = csv_path(day, data_dir)
    if not path.exists():
        return []

    samples: list[Sample] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                observed_at = dt.datetime.fromisoformat(row["timestamp_local"])
            except (ValueError, KeyError, TypeError):
                continue  # a corrupt line must not sink the whole day
            # Rows written before slots existed carry no slot_local; derive it
            # so the three days of history already in the repo still load.
            try:
                slot = dt.datetime.fromisoformat(row["slot_local"])
            except (ValueError, KeyError, TypeError):
                slot = slot_for(observed_at)
            samples.append(
                Sample(
                    observed_at=observed_at,
                    slot=slot,
                    record=LotRecord(
                        lot_id=row.get("lot_id", ""),
                        name=row.get("name", ""),
                        available=_to_int(row.get("available")),
                        total=_to_int(row.get("total")),
                        region=row.get("region") or "",
                        raw_status=row.get("raw_status") or "",
                    ),
                )
            )
    return samples


def series_for_lot(
    day: dt.date,
    lot_id: str,
    data_dir: pathlib.Path | None = None,
) -> list[tuple[dt.datetime, int]]:
    """Chronological (slot, available) points for one lot, skipping unknowns.

    Points are keyed by reporting slot rather than by wall-clock hour, so a run
    that fired at 7:52 plots at 8am where it belongs. If two runs land in the
    same slot, the later observation wins.
    """
    by_slot: dict[dt.datetime, tuple[dt.datetime, int]] = {}
    for sample in load_day(day, data_dir):
        rec = sample.record
        if rec.lot_id != lot_id or rec.available is None:
            continue
        slot = sample.slot or slot_for(sample.observed_at)
        previous = by_slot.get(slot)
        if previous is None or sample.observed_at >= previous[0]:
            by_slot[slot] = (sample.observed_at, rec.available)
    return [(slot, value) for slot, (_, value) in sorted(by_slot.items())]


def slot_already_recorded(
    slot: dt.datetime,
    data_dir: pathlib.Path | None = None,
) -> bool:
    """True when this reporting slot already has readings on disk.

    The schedule fires several redundant times per hour because GitHub drops
    scheduled runs, so the second and later arrivals for one slot must do
    nothing: no scrape, no duplicate email.
    """
    return any(
        (sample.slot or slot_for(sample.observed_at)) == slot
        for sample in load_day(slot.date(), data_dir)
    )


def recorded_slots(day: dt.date, data_dir: pathlib.Path | None = None) -> list[dt.datetime]:
    """Every slot that has readings for a day, in order."""
    return sorted(
        {sample.slot or slot_for(sample.observed_at) for sample in load_day(day, data_dir)}
    )


def latest_round(samples: Sequence[Sample]) -> list[LotRecord]:
    """The records from the most recent observation in ``samples``."""
    if not samples:
        return []
    newest = max(s.observed_at for s in samples)
    return [s.record for s in samples if s.observed_at == newest]


def _to_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
