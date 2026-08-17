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
        LotRecord(lot_id="6L", name="006L H.C. White Garage lower", available=None, region="East"),
    ]
    storage.append(records, at(8), data_dir=tmp_path)
    storage.append(records, at(9), data_dir=tmp_path)

    samples = storage.load_day(DAY, data_dir=tmp_path)
    assert len(samples) == 4
    assert samples[0].record.name == "017 Engineering Drive Ramp"
    assert samples[1].record.available is None  # unknown survives the round trip
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


def test_retried_hour_keeps_the_latest_sample(tmp_path):
    storage.append([LotRecord(lot_id="17", name="Ramp 17", available=500)], at(8), tmp_path)
    storage.append(
        [LotRecord(lot_id="17", name="Ramp 17", available=480)],
        dt.datetime(2026, 8, 17, 8, 41, tzinfo=TZ),
        data_dir=tmp_path,
    )
    assert storage.series_for_lot(DAY, "17", data_dir=tmp_path) == [
        (dt.datetime(2026, 8, 17, 8, 0, tzinfo=TZ), 480)
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
