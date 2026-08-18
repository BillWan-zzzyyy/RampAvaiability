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

HEADER = ["timestamp_local", "lot_id", "name", "available", "total", "region", "raw_status"]


def csv_path(day: dt.date, data_dir: pathlib.Path | None = None) -> pathlib.Path:
    return (data_dir or config.DATA_DIR) / f"{day:%Y-%m-%d}.csv"


def append(
    records: Iterable[LotRecord],
    observed_at: dt.datetime,
    data_dir: pathlib.Path | None = None,
) -> pathlib.Path:
    """Append one observation round; creates the file with a header if needed."""
    path = csv_path(observed_at.date(), data_dir)
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
            samples.append(
                Sample(
                    observed_at=observed_at,
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
    """Chronological (time, available) points for one lot, skipping unknowns.

    When a lot was sampled more than once in the same clock hour (a retried or
    delayed run), the last sample of that hour wins.
    """
    by_hour: dict[dt.datetime, tuple[dt.datetime, int]] = {}
    for sample in load_day(day, data_dir):
        rec = sample.record
        if rec.lot_id != lot_id or rec.available is None:
            continue
        hour = sample.observed_at.replace(minute=0, second=0, microsecond=0)
        previous = by_hour.get(hour)
        if previous is None or sample.observed_at >= previous[0]:
            by_hour[hour] = (sample.observed_at, rec.available)
    return [(hour, value) for hour, (_, value) in sorted(by_hour.items())]


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
