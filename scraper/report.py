"""Compose the email: subject line and HTML body.

Body text is Chinese; lot names stay in English so they match campus signage.
"""

from __future__ import annotations

import datetime as dt
import html
from collections.abc import Sequence

from . import config
from .models import LotRecord

SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
ACCENT = "#2a78d6"
CRITICAL = "#d03b3b"
WARNING = "#b3760a"

# Availability bands used for the status word next to each lot.
LOW = 20
TIGHT = 60


def subject(records: Sequence[LotRecord], slot: dt.datetime, is_final: bool) -> str:
    """Subject line, labelled with the reporting slot rather than the scrape time.

    A run that fires at 7:52 is the 8am report, and the subject must say 8am.
    """
    focus = find_focus(records)
    when = f"{slot:%-m/%-d %-I%p}".replace("AM", "am").replace("PM", "pm")
    if focus is None or focus.available is None:
        head = "车位播报"
    else:
        head = f"Ramp {config.FOCUS_LOT} 剩 {focus.available} 个车位"
    return f"[UW 停车] {head} · {when}" + ("（今日收官 + 曲线图）" if is_final else "")


def find_focus(records: Sequence[LotRecord]) -> LotRecord | None:
    for rec in records:
        if rec.lot_id == config.FOCUS_LOT:
            return rec
    return None


def status_of(available: int | None, raw_status: str = "") -> tuple[str, str]:
    """(label, color) for a stall count."""
    if available is None:
        # Show whatever the site published ("CLOSED", ...) rather than a bare dash.
        return (raw_status or "未知"), INK_MUTED
    if available == 0:
        return "已满", CRITICAL
    if available < LOW:
        return "紧张", CRITICAL
    if available < TIGHT:
        return "偏紧", WARNING
    return "充足", INK_SECONDARY


def coverage_note(covered_hours: Sequence[int]) -> str | None:
    """Say how many of the day's slots actually got a reading, if any are missing.

    GitHub drops scheduled runs, sometimes for a whole day. A silently short
    chart would look like the ramp had no data; naming the gap makes it obvious
    that the scheduler, not the parking lot, was the thing that went quiet.
    """
    expected = list(range(config.FIRST_HOUR, config.LAST_HOUR + 1))
    missing = [h for h in expected if h not in set(covered_hours)]
    if not missing:
        return f"今日 {len(expected)} 个档位全部记录成功。"
    names = "、".join(f"{h if h <= 12 else h - 12}{'am' if h < 12 else 'pm'}" for h in missing)
    return (
        f"今日只记录到 {len(expected) - len(missing)}/{len(expected)} 档，"
        f"缺 {names}（GitHub 定时任务未触发，不是车位数据有问题）。"
    )


def build_html(
    records: Sequence[LotRecord],
    observed_at: dt.datetime,
    *,
    is_final: bool,
    chart_cid: str | None = None,
    series: Sequence[tuple[dt.datetime, int]] = (),
    covered_hours: Sequence[int] = (),
) -> str:
    focus = find_focus(records)
    parts: list[str] = [
        f'<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        f'background:{SURFACE};color:{INK_PRIMARY};padding:20px;max-width:720px">'
    ]

    parts.append(
        f'<div style="font-size:13px;color:{INK_SECONDARY}">'
        f'{html.escape(observed_at.strftime("%Y-%m-%d %H:%M"))} '
        f"（校园本地时间 America/Chicago）</div>"
    )

    if focus is not None:
        label, color = status_of(focus.available, focus.raw_status)
        value = (focus.raw_status or "未知") if focus.available is None else str(focus.available)
        parts.append(
            f'<div style="margin:14px 0 22px">'
            f'<div style="font-size:13px;color:{INK_SECONDARY}">'
            f"{html.escape(focus.name)}</div>"
            f'<div style="font-size:38px;font-weight:700;line-height:1.15">{value}'
            f'<span style="font-size:15px;font-weight:400;color:{INK_SECONDARY}">'
            f" 个空位</span></div>"
            f'<div style="font-size:14px;color:{color};font-weight:600">{label}</div>'
            f"</div>"
        )
    else:
        parts.append(
            f'<div style="margin:14px 0;color:{CRITICAL};font-size:14px">'
            f"本次抓取里没有找到 Lot {html.escape(config.FOCUS_LOT)}，"
            f"下面是页面上实际列出的所有车库。</div>"
        )

    parts.append(_records_table(records))

    if chart_cid:
        parts.append(
            f'<div style="margin-top:26px">'
            f'<div style="font-size:15px;font-weight:600;margin-bottom:8px">'
            f"今日 Ramp {html.escape(config.FOCUS_LOT)} 逐小时变化</div>"
            f'<img src="cid:{chart_cid}" alt="Ramp {html.escape(config.FOCUS_LOT)} '
            f'hourly availability" style="width:100%;max-width:672px;height:auto"/>'
            f"</div>"
        )
        if series:
            parts.append(_series_table(series))
        note = coverage_note(covered_hours) if covered_hours else None
        if note:
            parts.append(
                f'<div style="margin-top:10px;font-size:12px;color:{INK_MUTED}">{note}</div>'
            )

    parts.append(
        f'<div style="margin-top:26px;font-size:12px;color:{INK_MUTED};'
        f"border-top:1px solid {GRIDLINE};padding-top:12px\">"
        f"数据来源："
        f'<a href="{html.escape(config.SOURCE_URL)}" style="color:{ACCENT}">'
        f"UW–Madison Transportation Services</a><br>"
        f"网站说明：空位数为近似值，可能快速变化。"
        f"</div></div>"
    )
    return "".join(parts)


def _records_table(records: Sequence[LotRecord]) -> str:
    rows: list[str] = [
        f'<table style="border-collapse:collapse;width:100%;font-size:14px">'
        f'<thead><tr style="text-align:left;color:{INK_SECONDARY};font-size:12px">'
        f'<th style="padding:6px 8px;border-bottom:1px solid {GRIDLINE}">车库 / Ramp</th>'
        f'<th style="padding:6px 8px;border-bottom:1px solid {GRIDLINE}">区域</th>'
        f'<th style="padding:6px 8px;border-bottom:1px solid {GRIDLINE};'
        f'text-align:right">空位</th>'
        f'<th style="padding:6px 8px;border-bottom:1px solid {GRIDLINE}">状态</th>'
        f"</tr></thead><tbody>"
    ]
    ordered = sorted(
        records,
        key=lambda r: (r.lot_id != config.FOCUS_LOT, -(r.available or 0)),
    )
    for rec in ordered:
        label, color = status_of(rec.available, rec.raw_status)
        is_focus = rec.lot_id == config.FOCUS_LOT
        weight = "700" if is_focus else "400"
        background = "#eef4fd" if is_focus else "transparent"
        value = (rec.raw_status or "—") if rec.available is None else str(rec.available)
        rows.append(
            f'<tr style="background:{background}">'
            f'<td style="padding:6px 8px;border-bottom:1px solid {GRIDLINE};'
            f'font-weight:{weight}">{html.escape(rec.name)}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid {GRIDLINE};'
            f'color:{INK_SECONDARY}">{html.escape(rec.region)}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid {GRIDLINE};'
            f'text-align:right;font-weight:{weight};font-variant-numeric:tabular-nums">'
            f"{value}</td>"
            f'<td style="padding:6px 8px;border-bottom:1px solid {GRIDLINE};'
            f'color:{color}">{label}</td>'
            f"</tr>"
        )
    rows.append("</tbody></table>")
    return "".join(rows)


def _series_table(series: Sequence[tuple[dt.datetime, int]]) -> str:
    cells = "".join(
        f'<td style="padding:4px 10px;border-bottom:1px solid {GRIDLINE};'
        f'text-align:right;font-variant-numeric:tabular-nums">{value}</td>'
        for _, value in series
    )
    heads = "".join(
        f'<td style="padding:4px 10px;border-bottom:1px solid {GRIDLINE};'
        f'text-align:right;color:{INK_SECONDARY};font-size:12px">{when:%-I%p}</td>'.replace(
            "AM", "am"
        ).replace("PM", "pm")
        for when, _ in series
    )
    return (
        f'<table style="border-collapse:collapse;margin-top:10px;font-size:14px">'
        f"<tbody><tr>{heads}</tr><tr>{cells}</tr></tbody></table>"
    )


def build_failure_html(error: str, observed_at: dt.datetime) -> str:
    """Body for a run that could not get data — say so, never fake numbers."""
    return (
        f'<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;'
        f'background:{SURFACE};color:{INK_PRIMARY};padding:20px;max-width:720px">'
        f'<div style="font-size:13px;color:{INK_SECONDARY}">'
        f'{html.escape(observed_at.strftime("%Y-%m-%d %H:%M"))} '
        f"（校园本地时间 America/Chicago）</div>"
        f'<div style="margin:14px 0;font-size:18px;font-weight:600;color:{CRITICAL}">'
        f"本次抓取失败，没有拿到车位数据</div>"
        f'<pre style="white-space:pre-wrap;font-size:13px;color:{INK_SECONDARY};'
        f'background:#f3f2ef;padding:12px;border-radius:6px">{html.escape(error)}</pre>'
        f'<div style="font-size:13px;color:{INK_SECONDARY}">'
        f'可以直接打开 <a href="{html.escape(config.SOURCE_URL)}" '
        f'style="color:{ACCENT}">官网页面</a> 手动查看。</div></div>'
    )
