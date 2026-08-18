"""Render the end-of-day availability trend for the focus ramp as a PNG.

Change over time for a single series, so: a line chart, zero baseline included
(zero means "full", which is the number that matters), no legend because the title
names the only series, and direct labels only on the two points worth calling out.
Every label is English — the runner has no CJK font installed, so Chinese text in
the image would render as tofu boxes. The email body carries the Chinese.
"""

from __future__ import annotations

import datetime as dt
import io
from collections.abc import Sequence

import matplotlib

matplotlib.use("Agg")  # headless: no display on a CI runner

import matplotlib.pyplot as plt  # noqa: E402

# Reference palette, light surface (the PNG always renders light: an email client
# cannot restyle a bitmap, so it must carry its own background).
SURFACE = "#fcfcfb"
SERIES = "#2a78d6"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

# DejaVu Sans ships with matplotlib, so it is always present; naming absent
# families here only produces a findfont warning per glyph.
FONT_STACK = ["DejaVu Sans", "sans-serif"]


def hour_label(hour: int) -> str:
    """8 -> '8am', 12 -> '12pm', 16 -> '4pm'."""
    suffix = "am" if hour < 12 else "pm"
    display = hour if 1 <= hour <= 12 else abs(hour - 12) or 12
    return f"{display}{suffix}"


def render_trend(
    points: Sequence[tuple[dt.datetime, int]],
    *,
    lot_name: str,
    day: dt.date,
    first_hour: int,
    last_hour: int,
) -> bytes:
    """Return PNG bytes for the day's hourly availability.

    ``points`` is (observed_at, available) in chronological order. Hours with no
    observation are left as gaps rather than interpolated — a missing run is not
    the same as a measurement.
    """
    hours = list(range(first_hour, last_hour + 1))
    by_hour = {p[0].hour: p[1] for p in points}
    values = [by_hour.get(h) for h in hours]

    plt.rcParams["font.family"] = FONT_STACK
    fig, ax = plt.subplots(figsize=(8.4, 4.2), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    ax.plot(
        hours,
        values,
        color=SERIES,
        linewidth=2,
        marker="o",
        markersize=8,
        markerfacecolor=SERIES,
        markeredgecolor=SURFACE,
        markeredgewidth=2,  # 2px surface ring so overlapping marks stay separate
        zorder=3,
    )

    observed = [(h, v) for h, v in zip(hours, values, strict=True) if v is not None]
    peak = max((v for _, v in observed), default=0)
    ax.set_ylim(0, max(peak * 1.18, 5))
    ax.set_xlim(first_hour - 0.4, last_hour + 0.4)
    ax.set_xticks(hours)
    ax.set_xticklabels([hour_label(h) for h in hours])

    ax.grid(axis="y", color=GRIDLINE, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(colors=INK_MUTED, length=0, labelsize=10)

    # Selective direct labels: the low point (when it was hardest to park) and the
    # final reading. Never one on every point.
    if observed:
        low_hour, low_value = min(observed, key=lambda hv: hv[1])
        last_hour_seen, last_value = observed[-1]
        annotated = {(low_hour, low_value), (last_hour_seen, last_value)}
        for h, v in annotated:
            ax.annotate(
                str(v),
                xy=(h, v),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                fontsize=11,
                fontweight="bold",
                color=INK_PRIMARY,
            )

    ax.set_title(
        f"{lot_name} — available stalls",
        loc="left",
        fontsize=14,
        fontweight="bold",
        color=INK_PRIMARY,
        pad=34,
    )
    ax.text(
        0,
        1.025,
        f"{day:%A, %B %-d, %Y} · hourly, {hour_label(first_hour)}–{hour_label(last_hour)}",
        transform=ax.transAxes,
        fontsize=10,
        color=INK_SECONDARY,
    )
    if len(observed) < len(hours):
        missing = len(hours) - len(observed)
        ax.text(
            1,
            -0.16,
            f"{missing} hour(s) not recorded",
            transform=ax.transAxes,
            ha="right",
            fontsize=9,
            color=INK_MUTED,
        )

    fig.tight_layout()
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=SURFACE)
    plt.close(fig)
    return buffer.getvalue()
