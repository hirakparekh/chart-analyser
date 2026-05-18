"""Helpers for waiting until the TradingView chart has finished rendering."""

import time

from playwright.sync_api import Page

from tradingview_scraper.config import (
    RENDER_MAX_WAIT_S,
    RENDER_POLL_MS,
    RENDER_SETTLE_MS,
)


def wait_for_render_settle(page: Page) -> None:
    """Wait until captured candle rendering has been idle long enough."""
    previous_count = -1
    stable_since: float | None = None
    start = time.time()

    while time.time() - start < RENDER_MAX_WAIT_S:
        current_count = page.evaluate("window.__RAW_LEN")
        now = time.time()

        if current_count == previous_count:
            if stable_since and (now - stable_since) > RENDER_SETTLE_MS / 1000:
                return
        else:
            stable_since = now

        previous_count = current_count
        time.sleep(RENDER_POLL_MS / 1000)
