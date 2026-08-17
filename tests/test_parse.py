"""Parser tests against the page as actually served (captured from a runner)."""

from __future__ import annotations

import pathlib

import pytest

from scraper.parse import ParseError, normalize_lot_id, parse_lots

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "lot_occupancy.html"


@pytest.fixture(scope="module")
def records():
    return parse_lots(FIXTURE.read_text(encoding="utf-8"))


def test_finds_every_lot_on_the_page(records):
    assert len(records) == 14


def test_focus_ramp_is_present_and_numeric(records):
    focus = next(r for r in records if r.lot_id == "17")
    assert focus.name == "017 Engineering Drive Ramp"
    assert focus.available == 546
    assert focus.region == "South"


def test_lot_ids_are_normalized_including_deck_suffixes(records):
    ids = {r.lot_id for r in records}
    assert {"17", "20", "27", "36", "67", "6L", "6U", "80", "83"} <= ids


def test_every_lot_has_a_usable_count(records):
    assert all(r.available is not None and r.available >= 0 for r in records)
    assert all(r.name for r in records)


def test_names_keep_the_site_numbering(records):
    assert any(r.name.startswith("006L ") for r in records)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("017", "17"), ("006L", "6L"), ("006u", "6U"), ("80", "80"), ("", "")],
)
def test_normalize_lot_id(raw, expected):
    assert normalize_lot_id(raw) == expected


def test_missing_table_raises_rather_than_returning_nothing():
    with pytest.raises(ParseError):
        parse_lots("<html><body><p>maintenance</p></body></html>")


def test_waf_challenge_page_is_not_mistaken_for_data():
    challenge = "<html><head><script>window.gokuProps = {}</script></head><body></body></html>"
    with pytest.raises(ParseError):
        parse_lots(challenge)


def test_column_order_is_read_from_headers_not_positions():
    html = """
    <table>
      <thead><tr>
        <th class="column-garageramp">Garage/Ramp</th>
        <th class="column-region">Region</th>
        <th class="column-availability">Availability</th>
      </tr></thead>
      <tbody><tr>
        <td>017 Engineering Drive Ramp</td><td>South</td><td>42</td>
      </tr></tbody>
    </table>
    """
    (record,) = parse_lots(html)
    assert (record.lot_id, record.available, record.region) == ("17", 42, "South")


def test_unreadable_count_becomes_unknown_not_zero():
    html = """
    <table>
      <thead><tr>
        <th class="column-availability">Availability</th>
        <th class="column-garageramp">Garage/Ramp</th>
      </tr></thead>
      <tbody>
        <tr><td>FULL</td><td>017 Engineering Drive Ramp</td></tr>
        <tr><td>0</td><td>080 Union South Garage</td></tr>
      </tbody>
    </table>
    """
    full, zero = parse_lots(html)
    assert full.available is None
    assert zero.available == 0
