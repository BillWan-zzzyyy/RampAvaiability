"""One-off diagnostic: fetch the UW lot-occupancy page and describe its structure.

Run on a GitHub Actions runner (the dev sandbox cannot reach the host). It renders
the page with the real fetcher (headless Chromium, because the site is behind an AWS
WAF challenge), saves the HTML as a test fixture, and prints enough structure to the
job log to decide how the occupancy numbers should be parsed.
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scraper import config  # noqa: E402
from scraper.fetch import fetch_html  # noqa: E402

FIXTURE = pathlib.Path("tests/fixtures/lot_occupancy.html")
KEYWORDS = ("occupancy", "stall", "available", "space", "vacan", "lot", "ramp", "count")


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def describe(html: str) -> None:
    section("TITLE")
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    print(m.group(1).strip() if m else "(no title)")

    section("TABLES")
    tables = re.findall(r"<table\b.*?</table>", html, re.S | re.I)
    print(f"{len(tables)} table(s) found")
    for i, table in enumerate(tables):
        print(f"\n--- table[{i}] ({len(table)} chars, first 4000) ---")
        print(table[:4000])

    section("IFRAMES")
    for m in re.finditer(r"<iframe\b[^>]*>", html, re.I):
        print(m.group(0))

    section("CANDIDATE DATA URLS (json / api / rest / ajax)")
    for u in sorted(set(re.findall(r"""https?://[^\s"'<>()]+""", html))):
        if re.search(r"\.json|/api|/rest|ajax|wp-json|feed|occupancy|parking", u, re.I):
            print(u)

    section("SCRIPT BLOCKS MENTIONING KEYWORDS")
    for i, m in enumerate(re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I)):
        body = m.group(1)
        if any(k in body.lower() for k in KEYWORDS):
            print(f"\n--- script[{i}] ({len(body)} chars, first 2000) ---")
            print(body[:2000])

    section("LINES MENTIONING ramp / stall / available / occupanc")
    seen = 0
    for line in html.splitlines():
        stripped = line.strip()
        if re.search(r"ramp|stall|available|occupanc", stripped, re.I):
            print(stripped[:400])
            seen += 1
            if seen > 200:
                print("... (truncated)")
                break


def main() -> int:
    section(f"RENDERING {config.SOURCE_URL}")
    html = fetch_html()
    print(f"got {len(html)} chars")

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(html, encoding="utf-8")
    print(f"wrote fixture -> {FIXTURE}")

    describe(html)

    section("robots.txt")
    try:
        print(fetch_html("https://transportation.wisc.edu/robots.txt")[:2000])
    except Exception as exc:  # noqa: BLE001 - diagnostics only
        print(f"could not read robots.txt: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
