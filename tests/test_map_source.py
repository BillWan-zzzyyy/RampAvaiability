import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scraper.fetch import FetchError
from scraper.map_source import parse_map_lots, fetch_map_lots
from scraper.parse import ParseError

FIXTURE = Path(__file__).parent / 'fixtures' / 'map_parking.json'


def test_current_official_map_snapshot():
    records = parse_map_lots(FIXTURE.read_text())
    assert len(records) == 16
    assert next(r for r in records if r.lot_id == '17').available == 58
    assert next(r for r in records if r.lot_id == '29').available == 0
    assert next(r for r in records if r.lot_id == '75').available is None
    assert '6' in {r.lot_id for r in records}
    assert all(r.region == '' for r in records)


@pytest.mark.parametrize('payload', ['<html>WAF challenge</html>', '{}', '{"type":"FeatureCollection","features":[]}'])
def test_invalid_responses_fail_closed(payload):
    with pytest.raises(ParseError):
        parse_map_lots(payload)


@pytest.mark.parametrize('value', [-1, True, '58', 1.5, {}, []])
def test_invalid_counts_rejected(value):
    data = json.loads(FIXTURE.read_text())
    data['features'][2]['properties']['availability'] = value
    with pytest.raises(ParseError):
        parse_map_lots(json.dumps(data))


@pytest.mark.parametrize('mutation', ['duplicate', 'missing_count', 'missing_focus', 'all_null'])
def test_schema_and_coverage_errors(mutation):
    data = json.loads(FIXTURE.read_text())
    if mutation == 'duplicate':
        data['features'].append(data['features'][2])
    elif mutation == 'missing_count':
        del data['features'][2]['properties']['availability']
    elif mutation == 'missing_focus':
        del data['features'][2]
    else:
        for f in data['features']:
            f['properties']['availability'] = None
    with pytest.raises(ParseError):
        parse_map_lots(json.dumps(data))


def response(body, status=200):
    obj = MagicMock()
    obj.__enter__.return_value = obj
    obj.status = status
    obj.read.return_value = body.encode()
    return obj


@patch('scraper.map_source.time.sleep')
@patch('scraper.map_source.urlopen')
def test_retries_unexpected_html_then_succeeds(open_url, sleep):
    open_url.side_effect = [response('<html>maintenance</html>'), response(FIXTURE.read_text())]
    assert len(fetch_map_lots()) == 16
    assert open_url.call_count == 2


@patch('scraper.map_source.time.sleep')
@patch('scraper.map_source.urlopen')
def test_http_failure_is_not_a_successful_empty_report(open_url, sleep):
    open_url.return_value = response('', 202)
    with pytest.raises(FetchError, match='HTTP 202'):
        fetch_map_lots()
    assert open_url.call_count == 3
