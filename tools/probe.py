"""One-off diagnostic: fetch the UW lot-occupancy page and describe its structure.

Run on a GitHub Actions runner (the dev sandbox cannot reach the host). It saves the
raw HTML as a test fixture and prints enough structure to the job log to decide how the
occupancy numbers should be parsed: inline HTML, an iframe, or a JSON endpoint that the
page's JavaScript calls.
"""

from __future__ import annotations

import pathlib
import re
import sys
import urllib.request

URL = "https://transportation.wisc.edu/parking-lots/lot-occupancy-count/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
FIXTURE = pathlib.Path("tests/fixtures/lot_occupancy.html")
KEYWORDS = ("occupancy", "stall", "available", "space", "vacan", "lot", "ramp", "count")


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> int:
    html = fetch(URL)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(html, encoding="utf-8")

    section(f"FETCHED {len(html)} chars -> {FIXTURE}")

    section("TABLES")
    tables = re.findall(r"<table\b.*?</table>", html, re.S | re.I)
    print(f"{len(tables)} table(s) found")
    for i, table in enumerate(tables):
        print(f"\n--- table[{i}] ({len(table)} chars, first 3000) ---")
        print(table[:3000])

    section("IFRAMES")
    for m in re.finditer(r"<iframe\b[^>]*>", html, re.I):
        print(m.group(0))

    section("CANDIDATE DATA URLS (json / api / rest / ajax)")
    urls = set(re.findall(r"""https?://[^\s"'<>()]+""", html))
    for u in sorted(urls):
        if re.search(r"\.json|/api|/rest|ajax|wp-json|feed|occupancy|parking", u, re.I):
            print(u)

    section("SCRIPT BLOCKS MENTIONING KEYWORDS")
    for i, m in enumerate(re.finditer(r"<script\b[^>]*>(.*?)</script>", html, re.S | re.I)):
        body = m.group(1)
        if any(k in body.lower() for k in KEYWORDS):
            print(f"\n--- script[{i}] ({len(body)} chars, first 2000) ---")
            print(body[:2000])

    section("LINES MENTIONING 'ramp' OR 'stall' OR 'available'")
    for line in html.splitlines():
        stripped = line.strip()
        if re.search(r"ramp|stall|available|occupanc", stripped, re.I):
            print(stripped[:400])

    return 0


if __name__ == "__main__":
    sys.exit(main())
