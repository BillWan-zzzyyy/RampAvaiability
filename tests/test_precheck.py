"""The gate that lets redundant firings exit before installing or scraping."""

from __future__ import annotations

import datetime as dt
import pathlib
from zoneinfo import ZoneInfo

from scraper import precheck, storage
from scraper.models import LotRecord

TZ = ZoneInfo("America/Chicago")
DAY = dt.date(2026, 8, 19)  # a Wednesday


def at(hour: int, minute: int = 5, day: int = 19) -> dt.datetime:
    return dt.datetime(2026, 8, day, hour, minute, tzinfo=TZ)


def record(hour: int, tmp_path, minute: int = 2) -> None:
    storage.append(
        [LotRecord(lot_id="17", name="Ramp 17", available=100)],
        at(hour, minute),
        data_dir=tmp_path,
    )


def decide(moment, tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    return precheck.decide(moment)


def test_empty_day_proceeds(tmp_path, monkeypatch):
    proceed, reason = decide(at(9), tmp_path, monkeypatch)
    assert proceed
    assert "not yet reported" in reason


def test_recorded_slot_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    record(9, tmp_path)
    proceed, reason = precheck.decide(at(9, 25))
    assert not proceed
    assert "already reported" in reason


def test_a_different_slot_still_proceeds(tmp_path, monkeypatch):
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    record(9, tmp_path)
    proceed, _ = precheck.decide(at(10, 5))
    assert proceed


def test_outside_the_window_is_skipped(tmp_path, monkeypatch):
    proceed, reason = decide(at(6), tmp_path, monkeypatch)
    assert not proceed
    assert "outside the reporting window" in reason


def test_weekend_is_skipped(tmp_path, monkeypatch):
    proceed, reason = decide(at(9, 5, day=22), tmp_path, monkeypatch)  # Saturday
    assert not proceed
    assert "outside the reporting window" in reason


def test_early_firing_counts_for_the_upcoming_slot(tmp_path, monkeypatch):
    """A 7:45 firing is the 8am attempt and must be allowed through."""
    proceed, reason = decide(at(7, 45), tmp_path, monkeypatch)
    assert proceed
    assert "08:00" in reason


def test_precheck_uses_only_the_standard_library():
    """It runs before pip install, so any third-party import would break the gate.

    Imported in a fresh interpreter so the check is about what precheck itself
    pulls in, not what the rest of the test session already loaded.
    """
    import subprocess
    import sys

    probe = (
        "import sys, scraper.precheck; "
        "banned = {'playwright', 'bs4', 'matplotlib', 'numpy', 'requests', 'PIL'}; "
        "print(sorted(banned & {m.split('.')[0] for m in sys.modules}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=pathlib.Path(__file__).parent.parent,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", f"precheck pulled in {result.stdout.strip()}"


def test_precheck_writes_github_output(tmp_path, monkeypatch):
    """The workflow gates every heavy step on this value."""
    monkeypatch.setattr(storage.config, "DATA_DIR", tmp_path)
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    assert precheck.main() == 0
    assert "proceed=" in out.read_text()
