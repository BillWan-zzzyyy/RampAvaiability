"""Round-trip the daily CSV and render the chart from it."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from scraper import chart, storage
from scraper.models import LotRecord

TZ = ZoneInfo("America/Chicago")
DAY = dt.date(2026, 8, 17)


def at(hour: int) -> dt.datetime:
    return dt.datetime(2026, 8, 17, hour, 3, tzinfo=TZ)


def test_append_and_read_back(tmp_path):
    records = [
        LotRecord(lot_id="17", name="017 Engineering Drive Ramp", available=546, region="South"),
        LotRecord(
            lot_id="6L",
            name="006L H.C. White Garage lower",
            available=None,
            region="East",
            raw_status="CLOSED",
        ),
    ]
    storage.append(records, at(8), data_dir=tmp_path)
    storage.append(records, at(9), data_dir=tmp_path)

    samples = storage.load_day(DAY, data_dir=tmp_path)
    assert len(samples) == 4
    assert samples[0].record.name == "017 Engineering Drive Ramp"
    assert samples[1].record.available is None  # unknown survives the round trip
    assert samples[1].record.raw_status == "CLOSED"  # and so does what the site said
    assert samples[0].record.region == "South"


def test_series_skips_unknowns_and_other_lots(tmp_path):
    storage.append(
        [
            LotRecord(lot_id="17", name="Ramp 17", available=500),
            LotRecord(lot_id="20", name="Ramp 20", available=10),
        ],
        at(8),
        data_dir=tmp_path,
    )
    storage.append([LotRecord(lot_id="17", name="Ramp 17", available=None)], at(9), tmp_path)
    storage.append([LotRecord(lot_id="17", name="Ramp 17", available=120)], at(10), tmp_path)

    series = storage.series_for_lot(DAY, "17", data_dir=tmp_path)
    assert [(t.hour, v) for t, v in series] == [(8, 500), (10, 120)]


def test_retried_slot_keeps_the_latest_sample(tmp_path):
    """A run retried 17 minutes later is still the same report, so it overwrites.

    (8:41 would NOT belong here — that rounds to the 9am slot, which is exactly
    the 9am cron firing on time.)
    """
    storage.append([LotRecord(lot_id="17", name="Ramp 17", available=500)], at(8), tmp_path)
    storage.append(
        [LotRecord(lot_id="17", name="Ramp 17", available=480)],
        dt.datetime(2026, 8, 17, 8, 20, tzinfo=TZ),
        data_dir=tmp_path,
    )
    assert storage.series_for_lot(DAY, "17", data_dir=tmp_path) == [
        (dt.datetime(2026, 8, 17, 8, 0, tzinfo=TZ), 480)
    ]


def test_slot_keeps_an_early_run_in_the_hour_it_reports_on(tmp_path):
    """7:52 and 8:17 runs both belong to the 8am slot, not 7am and 8am."""
    early = dt.datetime(2026, 8, 17, 7, 52, tzinfo=TZ)
    late = dt.datetime(2026, 8, 17, 8, 17, tzinfo=TZ)
    storage.append([LotRecord(lot_id="17", name="Ramp 17", available=600)], early, tmp_path)
    storage.append([LotRecord(lot_id="17", name="Ramp 17", available=410)], late, tmp_path)

    series = storage.series_for_lot(DAY, "17", data_dir=tmp_path)
    assert [(t.hour, v) for t, v in series] == [(8, 410)]  # same slot, later wins


def test_old_csv_without_a_slot_column_still_loads(tmp_path):
    """Three days of history predate slots; deriving the slot keeps them readable."""
    legacy = tmp_path / "2026-08-17.csv"
    legacy.write_text(
        "timestamp_local,lot_id,name,available,total,region,raw_status\n"
        "2026-08-17T08:03:00-05:00,17,017 Engineering Drive Ramp,546,,South,\n"
        "2026-08-17T09:02:00-05:00,17,017 Engineering Drive Ramp,410,,South,\n",
        encoding="utf-8",
    )
    samples = storage.load_day(DAY, data_dir=tmp_path)
    assert [s.slot.hour for s in samples] == [8, 9]
    assert [(t.hour, v) for t, v in storage.series_for_lot(DAY, "17", tmp_path)] == [
        (8, 546),
        (9, 410),
    ]


def test_missing_day_file_is_empty_not_an_error(tmp_path):
    assert storage.load_day(dt.date(2000, 1, 1), data_dir=tmp_path) == []
    assert storage.series_for_lot(dt.date(2000, 1, 1), "17", data_dir=tmp_path) == []


def test_chart_renders_png_with_gaps(tmp_path):
    series = [(at(h), v) for h, v in [(8, 620), (9, 410), (10, 180), (13, 96), (16, 505)]]
    png = chart.render_trend(
        series,
        lot_name="017 Engineering Drive Ramp",
        day=DAY,
        first_hour=8,
        last_hour=16,
    )
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000
    (tmp_path / "chart.png").write_bytes(png)


def test_chart_handles_a_single_point():
    png = chart.render_trend(
        [(at(8), 42)], lot_name="Ramp 17", day=DAY, first_hour=8, last_hour=16
    )
    assert png.startswith(b"\x89PNG\r\n\x1a\n")


def test_hour_labels():
    assert [chart.hour_label(h) for h in (8, 11, 12, 13, 16)] == [
        "8am",
        "11am",
        "12pm",
        "1pm",
        "4pm",
    ]
