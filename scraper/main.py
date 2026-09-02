"""Entry point: scrape once, record the result, and email the report.

Scheduling note: GitHub cron is UTC-only, so the workflow fires every hour across
a window wide enough to cover both US Central offsets, and this module decides in
campus local time whether the run belongs to the 8am-4pm reporting window.
Daylight saving then needs no cron edit.

The workflow fires redundantly (three times an hour) because GitHub drops
scheduled runs outright, and arrives late by anything from minutes to hours.
Which hour a run reports on is therefore its slot (nearest hour), not its clock
hour, and the first arrival for a slot claims it — see scraper/schedule.py and
scraper/precheck.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from collections.abc import Sequence

from . import chart, config, mailer, report, schedule, storage
from .fetch import FetchError, fetch_html
from .models import LotRecord
from .parse import ParseError, parse_lots


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scrape and record, but do not send any email",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="run even outside the window, and even if this slot was already reported",
    )
    parser.add_argument(
        "--force-chart",
        action="store_true",
        help="treat this run as the last of the day, so the chart is included",
    )
    return parser.parse_args(argv)


def summarize(records: Sequence[LotRecord]) -> str:
    lines = [f"{len(records)} lot(s):"]
    for rec in records:
        value = "unknown" if rec.available is None else str(rec.available)
        if rec.raw_status:
            value += f" (site said {rec.raw_status!r})"
        marker = " <- focus" if rec.lot_id == config.FOCUS_LOT else ""
        lines.append(f"  [{rec.lot_id:>4}] {rec.name}: {value}{marker}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    now = dt.datetime.now(config.TIMEZONE)
    slot = schedule.slot_for(now)
    print(f"local time: {now:%Y-%m-%d %H:%M:%S %Z} (weekday {now.weekday()})")
    print(f"reporting slot: {slot:%Y-%m-%d %H:00} (scheduler drift {now - slot})")

    if not args.force and not schedule.in_window(now):
        print(
            f"outside the reporting window "
            f"(Mon-Fri {config.FIRST_HOUR}:00-{config.LAST_HOUR}:00 local); nothing to do"
        )
        return 0

    # The schedule fires redundantly because GitHub drops scheduled runs; the
    # later arrivals for a slot must not scrape the site again or send a second
    # email. Checked before fetching, so a redundant run costs the source site
    # nothing.
    if not args.force and storage.slot_already_recorded(slot):
        print(f"slot {slot:%H:00} already reported today; nothing to do")
        return 0

    try:
        html = fetch_html()
        records = parse_lots(html)
    except (FetchError, ParseError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        if not args.dry_run:
            _report_failure(str(exc), now)
        return 1

    print(summarize(records))

    path = storage.append(records, now, slot=slot)
    print(f"recorded -> {path}")

    is_final = args.force_chart or schedule.is_final(now)
    chart_png: bytes | None = None
    chart_cid: str | None = None
    series: list[tuple[dt.datetime, int]] = []

    covered: list[int] = []
    if is_final:
        covered = [s.hour for s in storage.recorded_slots(slot.date())]
        series = storage.series_for_lot(slot.date(), config.FOCUS_LOT)
        focus = report.find_focus(records)
        if series:
            chart_png = chart.render_trend(
                series,
                lot_name=focus.name if focus else f"Lot {config.FOCUS_LOT}",
                day=slot.date(),
                first_hour=config.FIRST_HOUR,
                last_hour=config.LAST_HOUR,
            )
            chart_cid = mailer.new_cid()
            print(f"chart: {len(series)} hourly point(s), {len(chart_png)} bytes")
        else:
            print(f"no recorded points for lot {config.FOCUS_LOT} today; sending without chart")

    subject = report.subject(records, slot, is_final)
    body = report.build_html(
        records,
        now,
        is_final=is_final,
        chart_cid=chart_cid,
        series=series,
        covered_hours=covered,
    )

    if args.dry_run:
        print(f"dry run: would send {subject!r} ({len(body)} chars of HTML)")
        return 0

    mailer.send(subject, body, chart_png=chart_png, chart_cid=chart_cid)
    print(f"sent: {subject}")
    return 0


def _report_failure(error: str, now: dt.datetime) -> None:
    """Tell the recipient the run failed. Never silently skip a report."""
    if mailer.missing_settings():
        print("mail not configured; failure not emailed", file=sys.stderr)
        return
    try:
        mailer.send(
            f"[UW 停车] 抓取失败 · {now:%-m/%-d %H:%M}",
            report.build_failure_html(error, now),
        )
    except mailer.MailError as exc:
        print(f"could not send failure notice: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
