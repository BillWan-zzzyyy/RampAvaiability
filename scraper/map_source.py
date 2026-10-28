"""Official campus-map feed, linked by the retired occupancy page.

The map's parking layer fetches /api/v1/parking (GeoJSON). Null counts
mean no published availability, not zero. No source timestamp is supplied.
"""
from __future__ import annotations

import json
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from . import config
from .fetch import FetchError
from .models import LotRecord
from .parse import ParseError, normalize_lot_id


def parse_map_lots(payload: str) -> list[LotRecord]:
    try:
        data = json.loads(payload)
    except (ValueError, TypeError) as exc:
        raise ParseError("campus map returned invalid JSON") from exc
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ParseError("campus map: expected a GeoJSON FeatureCollection")
    records = []
    seen = set()
    for feature in data["features"]:
        props = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(props, dict):
            raise ParseError("campus map: missing feature properties")
        lot, name = props.get("lot"), props.get("name")
        if not isinstance(lot, str) or not lot.strip() or not isinstance(name, str) or not name.strip() or "availability" not in props:
            raise ParseError("campus map: missing lot, name or availability")
        lot_id = normalize_lot_id(lot)
        if lot_id in seen:
            raise ParseError(f"campus map: duplicate lot {lot_id}")
        seen.add(lot_id)
        count = props["availability"]
        if count is not None and (type(count) is not int or count < 0):
            raise ParseError(f"campus map: invalid availability for lot {lot_id}")
        records.append(LotRecord(lot_id=lot_id, name=name, available=count,
                                 region="", raw_status="unavailable" if count is None else ""))
    if not records or not any(r.available is not None for r in records):
        raise ParseError("campus map: no usable availability counts")
    if not any(r.lot_id == config.FOCUS_LOT for r in records):
        raise ParseError(f"campus map: focus lot {config.FOCUS_LOT} missing")
    return records


def fetch_map_lots(*, attempts: int = 3, timeout: float = 30) -> list[LotRecord]:
    problems = []
    for attempt in range(1, attempts + 1):
        try:
            request = Request(config.MAP_API_URL, headers={"Accept": "application/json", "User-Agent": config.USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise FetchError(f"campus map HTTP {response.status}")
                payload = response.read().decode("utf-8")
            return parse_map_lots(payload)
        except (URLError, TimeoutError, UnicodeError, ParseError, FetchError) as exc:
            problems.append(f"attempt {attempt}: {exc}")
            if attempt < attempts:
                time.sleep(2 * attempt)
    raise FetchError("could not retrieve campus map availability: " + "; ".join(problems))
