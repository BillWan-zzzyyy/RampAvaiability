"""Turn the rendered occupancy page into LotRecords.

The page publishes a single wpDataTable whose columns carry stable
``column-<name>`` classes:

    Availability | Garage/Ramp                | Region  | Directions
    546          | 017 Engineering Drive Ramp | South   | Map It

Lot names are prefixed with a zero-padded number, sometimes with a deck suffix
("006L H.C. White Garage lower"). Columns are located by class first and by
header text second, so a reordered or renamed column degrades instead of
silently reading the wrong cell.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from .models import LotRecord

# "017 Engineering Drive Ramp" -> ("017", "Engineering Drive Ramp")
LOT_PREFIX = re.compile(r"^(\d{1,4}[A-Za-z]?)\s+(.*)$")

AVAILABILITY_HINTS = ("availability", "available", "open", "stalls", "spaces")
NAME_HINTS = ("garage", "ramp", "lot", "location")
REGION_HINTS = ("region", "area", "campus")


class ParseError(RuntimeError):
    """The page did not look like the occupancy table we know how to read."""


def normalize_lot_id(raw: str) -> str:
    """'017' -> '17', '006L' -> '6L', so config can say FOCUS_LOT=17."""
    match = re.match(r"^(\d+)([A-Za-z]?)$", raw.strip())
    if not match:
        return raw.strip()
    digits, suffix = match.groups()
    return f"{int(digits)}{suffix.upper()}"


def parse_lots(html: str) -> list[LotRecord]:
    """Extract every lot row from the page.

    Raises ParseError when no occupancy table can be found at all — a structural
    change must surface loudly rather than yield an empty, plausible-looking report.
    """
    soup = BeautifulSoup(html, "html.parser")

    for table in soup.find_all("table"):
        columns = _column_indices(table)
        if columns is None:
            continue
        records = _rows_to_records(table, columns)
        if records:
            return records

    raise ParseError(
        "no occupancy table found; the page structure likely changed "
        "(expected a table with availability and garage/ramp columns)"
    )


def _column_indices(table: Tag) -> dict[str, int] | None:
    """Map 'availability'/'name'/'region' to column positions, or None."""
    header_cells = table.select("thead th") or table.select("thead td")
    if not header_cells:
        return None

    found: dict[str, int] = {}
    for index, cell in enumerate(header_cells):
        classes = " ".join(cell.get("class", []))
        text = cell.get_text(" ", strip=True).lower()
        if "column-availability" in classes or _matches(text, AVAILABILITY_HINTS):
            found.setdefault("availability", index)
        elif "column-garageramp" in classes or _matches(text, NAME_HINTS):
            found.setdefault("name", index)
        elif "column-region" in classes or _matches(text, REGION_HINTS):
            found.setdefault("region", index)

    if "availability" not in found or "name" not in found:
        return None
    return found


def _rows_to_records(table: Tag, columns: dict[str, int]) -> list[LotRecord]:
    records: list[LotRecord] = []
    body_rows = table.select("tbody tr") or table.find_all("tr")
    needed = max(columns.values())

    for row in body_rows:
        cells = row.find_all(["td", "th"])
        if len(cells) <= needed:
            continue  # header remnants, spacer rows, "no data" placeholders

        raw_name = cells[columns["name"]].get_text(" ", strip=True)
        if not raw_name:
            continue

        lot_id, name = _split_lot_name(raw_name)
        region_index = columns.get("region")
        region = (
            cells[region_index].get_text(" ", strip=True)
            if region_index is not None and region_index < len(cells)
            else ""
        )

        raw_availability = cells[columns["availability"]].get_text(" ", strip=True)
        available = _to_available(raw_availability)
        records.append(
            LotRecord(
                lot_id=lot_id,
                name=name,
                available=available,
                region=region,
                raw_status="" if _is_plain_count(raw_availability) else raw_availability,
            )
        )
    return records


def _split_lot_name(raw: str) -> tuple[str, str]:
    """('017 Engineering Drive Ramp') -> ('17', '017 Engineering Drive Ramp').

    The displayed name keeps the site's own numbering so the email matches the
    signage; only the id is normalized, for matching.
    """
    match = LOT_PREFIX.match(raw)
    if not match:
        return "", raw
    return normalize_lot_id(match.group(1)), raw


def _is_plain_count(text: str) -> bool:
    return bool(re.fullmatch(r"\d[\d,]*", text.strip()))


def _to_available(text: str) -> int | None:
    """Stall count, or None when the site published no usable number.

    "FULL" is a count, not an unknown — it means zero, and reporting it as
    unknown would hide exactly the situation worth knowing about. "CLOSED" and
    anything unrecognized stay None, which keeps them out of the chart and makes
    the email say what the source said instead of inventing a number.
    """
    cleaned = text.strip()
    if _is_plain_count(cleaned):
        return int(cleaned.replace(",", ""))
    if re.search(r"\bfull\b", cleaned, re.I):
        return 0
    if re.search(r"closed|unavailable|n/?a", cleaned, re.I):
        return None
    match = re.search(r"\d[\d,]*", cleaned)
    return int(match.group().replace(",", "")) if match else None


def _matches(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)
