"""Settings shared by the scraper, all overridable through the environment."""

from __future__ import annotations

import os
import pathlib
from zoneinfo import ZoneInfo

# Where the occupancy numbers come from.
SOURCE_URL = os.environ.get(
    "SOURCE_URL",
    "https://transportation.wisc.edu/parking-lots/lot-occupancy-count/",
)

# Campus local time. Every hour decision is made in this zone so the schedule
# survives daylight saving transitions without touching the cron expression.
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "America/Chicago"))

# Reporting window, inclusive, in campus local time.
FIRST_HOUR = int(os.environ.get("FIRST_HOUR", "8"))
LAST_HOUR = int(os.environ.get("LAST_HOUR", "16"))

# The lot that gets the end-of-day trend chart.
FOCUS_LOT = os.environ.get("FOCUS_LOT", "17")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = pathlib.Path(os.environ.get("DATA_DIR", REPO_ROOT / "data"))

USER_AGENT = os.environ.get(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
)

# SMTP delivery (Gmail by default). Credentials come from GitHub Actions secrets.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("GMAIL_USER", "")
SMTP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
# Recipient lives in a secret: this repository is public.
MAIL_TO = os.environ.get("MAIL_TO", "")
