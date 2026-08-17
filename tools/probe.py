"""One-off diagnostic: fetch the UW lot-occupancy page and describe its structure.

Run on a GitHub Actions runner (the dev sandbox cannot reach the host). It tries a
few request styles, reports status/headers/body size for each, saves the best HTML as
a test fixture, and prints enough structure to the job log to decide how the occupancy
numbers should be parsed: inline HTML, an iframe, or a JSON endpoint the page calls.
"""

from __future__ import annotations

import gzip
import pathlib
import re
import ssl
import sys
import urllib.error
import urllib.request
import zlib

URL = "https://transportation.wisc.edu/parking-lots/lot-occupancy-count/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
    "image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}
FIXTURE = pathlib.Path("tests/fixtures/lot_occupancy.html")
KEYWORDS = ("occupancy", "stall", "available", "space", "vacan", "lot", "ramp", "count")


def section(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def decode(raw: bytes, encoding: str) -> str:
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        raw = zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw.decode("utf-8", errors="replace")


def attempt(label: str, url: str, headers: dict[str, str]) -> str:
    """Fetch one way, report everything about the response, return the body."""
    section(f"ATTEMPT: {label}")
    print(f"GET {url}")
    print(f"headers: {sorted(headers)}")
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            raw = resp.read()
            body = decode(raw, (resp.headers.get("Content-Encoding") or "").lower())
            print(f"status: {resp.status}")
            print(f"final url: {resp.geturl()}")
            print(f"raw bytes: {len(raw)}  decoded chars: {len(body)}")
            print("--- response headers ---")
            for k, v in resp.headers.items():
                print(f"{k}: {v}")
            if body:
                print("--- first 500 chars ---")
                print(body[:500])
            return body
    except urllib.error.HTTPError as exc:  # noqa: PERF203 - diagnostics
        raw = exc.read()
        print(f"HTTPError {exc.code}: {exc.reason}, {len(raw)} bytes")
        print("--- response headers ---")
        for k, v in (exc.headers or {}).items():
            print(f"{k}: {v}")
        print(raw[:1000].decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001 - diagnostics
        print(f"{type(exc).__name__}: {exc}")
    return ""


def describe(html: str) -> None:
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
    for line in html.splitlines():
        stripped = line.strip()
        if re.search(r"ramp|stall|available|occupanc", stripped, re.I):
            print(stripped[:400])


def main() -> int:
    bodies: list[tuple[str, str]] = []

    bodies.append(("bare UA", attempt("bare User-Agent only", URL, {"User-Agent": UA})))
    bodies.append(("browser headers", attempt("full browser headers", URL, BROWSER_HEADERS)))
    bodies.append(("site root", attempt("site root (reachability check)",
                                        "https://transportation.wisc.edu/", BROWSER_HEADERS)))

    label, html = max(bodies, key=lambda pair: len(pair[1]))
    section(f"BEST RESPONSE: {label} ({len(html)} chars)")

    # Only keep a fixture for the target page, never the site root.
    target = next((b for lbl, b in bodies if lbl != "site root" and b), "")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(target, encoding="utf-8")
    print(f"wrote {len(target)} chars to {FIXTURE}")

    if target:
        describe(target)
    else:
        print("\nTarget page returned an empty body in every attempt.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
