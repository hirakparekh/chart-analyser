"""Date parsing and current-period filtering."""

import re
import time
from datetime import date, timedelta

from playwright.sync_api import Page

from tradingview_scraper.config import MONTHS, TOOLTIP_WAIT_MS


def parse_date(text: str) -> str | None:
    """Parse TradingView tooltip dates into YYYY-MM-DD strings."""
    match = re.search(r"(\d{1,2})\s([A-Z][a-z]{2})\s'(\d{2})", text)
    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS.get(match.group(2))
    year = 2000 + int(match.group(3))

    if not month:
        return None

    return f"{year}-{month:02d}-{day:02d}"


def read_candle_date(page: Page, move_ts: float) -> str | None:
    """Read the current hovered candle date from captured tooltip text."""
    time.sleep(TOOLTIP_WAIT_MS / 1000)
    tooltips = page.evaluate("window.__TOOLTIP")

    move_ts_ms = move_ts * 1000
    fresh = [tooltip for tooltip in tooltips if tooltip["ts"] > move_ts_ms]

    if not fresh:
        last_x = page.evaluate("window.__lastX || 400")
        page.mouse.move(last_x + 2, 400)
        time.sleep(0.2)
        tooltips = page.evaluate("window.__TOOLTIP")
        fresh = [tooltip for tooltip in tooltips if tooltip["ts"] > move_ts_ms]

    if not fresh:
        return None

    return parse_date(fresh[-1]["text"])


def is_current_period(date_str: str, timeframe: str) -> bool:
    """Return True when a candle belongs to the unfinished current period."""
    today = date.today()
    candle_date = date.fromisoformat(date_str)

    if timeframe == "W":
        week_start = today - timedelta(days=today.weekday())
        return candle_date >= week_start
    if timeframe == "D":
        return candle_date >= today
    if timeframe == "1M":
        return candle_date.year == today.year and candle_date.month == today.month

    return False
