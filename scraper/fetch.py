"""Fetch the occupancy page through a real browser engine.

transportation.wisc.edu sits behind an AWS WAF in "challenge" mode: a plain HTTP
request from a datacenter IP gets HTTP 202 and a JavaScript proof-of-work page
(``window.gokuProps``) instead of the content, no matter what headers it sends.
The challenge is the silent kind — no CAPTCHA, no human step — so rendering the
page in headless Chromium runs the challenge script, gets the ``aws-waf-token``
cookie, and lands on the real page. Hence Playwright rather than ``requests``.
"""

from __future__ import annotations

import time

from . import config

# Markers of the WAF interstitial rather than the page we want.
CHALLENGE_MARKERS = ("gokuProps", "awsWafCookieDomainList", "challenge.compact.js")


class FetchError(RuntimeError):
    """The page could not be retrieved; the caller must report, not invent data."""


def looks_like_challenge(html: str) -> bool:
    return any(marker in html for marker in CHALLENGE_MARKERS)


def fetch_html(
    url: str | None = None,
    *,
    attempts: int = 3,
    timeout_ms: int = 60_000,
) -> str:
    """Return the rendered HTML of ``url``, or raise FetchError.

    Each attempt loads the page and waits for the WAF interstitial to replace
    itself with real content. Attempts are spaced out so a transient block has
    time to clear.
    """
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    target = url or config.SOURCE_URL
    problems: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=config.USER_AGENT,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        try:
            for attempt in range(1, attempts + 1):
                try:
                    page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
                    # The challenge script solves itself and reloads the page.
                    page.wait_for_function(
                        "() => !document.documentElement.innerHTML.includes('gokuProps')",
                        timeout=timeout_ms,
                    )
                    page.wait_for_load_state("networkidle", timeout=timeout_ms)
                    html = page.content()
                    if html and not looks_like_challenge(html):
                        return html
                    problems.append(f"attempt {attempt}: still the WAF challenge page")
                except PlaywrightError as exc:
                    problems.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt < attempts:
                    time.sleep(5 * attempt)
        finally:
            context.close()
            browser.close()

    raise FetchError(f"could not load {target}: " + "; ".join(problems))
