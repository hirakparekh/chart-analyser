"""Main TradingView DOM scraper orchestration."""

import logging
import random
import time
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from tradingview_scraper.candles import extract_candle_positions
from tradingview_scraper.config import (
    CANDLES_PER_PERIOD,
    HOVER_WAIT_MS,
    SCROLL_PRESSES,
)
from tradingview_scraper.csv_writer import write_candles_csv
from tradingview_scraper.dates import is_current_period, read_candle_date
from tradingview_scraper.dom_reader import read_ohlc_from_dom
from tradingview_scraper.hooks import build_hook_script
from tradingview_scraper.render import wait_for_render_settle

logger = logging.getLogger(__name__)


def get_ohlc(symbol: str, timeframe: str, period: str = "1y") -> str:
    """Scrape OHLC data from TradingView and save it to a CSV file."""
    target = CANDLES_PER_PERIOD.get(timeframe, {}).get(period)
    if not target:
        raise ValueError(f"Unsupported timeframe={timeframe} period={period}")

    seen_dates: dict[str, dict[str, Any]] = {}
    hook = build_hook_script()

    logger.info("TradingView OHLC Scraper - DOM Approach")
    logger.info("Symbol: %s  Timeframe: %s  Period: %s", symbol, timeframe, period)
    logger.info("Target candles: %s", target)

    browser = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context(viewport={"width": 1920, "height": 1080})
            page = context.new_page()
            page.add_init_script(hook)

            url = (
                "https://in.tradingview.com/chart/"
                f"?symbol=NSE:{symbol}&interval={timeframe}"
            )
            logger.info("Navigating to: %s", url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("canvas", timeout=30000)

            logger.info("Waiting for initial render...")
            time.sleep(3)
            wait_for_render_settle(page)

            scroll_count = 0
            max_scrolls = (target // 20) + 15

            while len(seen_dates) < target and scroll_count < max_scrolls:
                candles = extract_candle_positions(page)

                if not candles:
                    logger.warning("No candles in batch %s", scroll_count)
                else:
                    _collect_visible_candles(page, candles, seen_dates, timeframe)
                    logger.info(
                        "Scroll %s: %s/%s candles",
                        scroll_count,
                        len(seen_dates),
                        target,
                    )

                if len(seen_dates) >= target:
                    break

                _scroll_to_older_candles(page)
                wait_for_render_settle(page)
                scroll_count += 1

            time.sleep(1)
            browser.close()
            browser = None

    except (PlaywrightTimeoutError, PlaywrightError):
        logger.exception("TradingView scraping failed")
        raise
    finally:
        if browser:
            try:
                browser.close()
            except PlaywrightError:
                logger.debug("Browser close failed during cleanup", exc_info=True)

    output_path = write_candles_csv(
        symbol,
        timeframe,
        period,
        list(seen_dates.values()),
    )
    logger.info("Complete: collected %s/%s candles", len(seen_dates), target)
    logger.info("File: %s", output_path)
    return output_path


def _collect_visible_candles(
    page,
    candles: list[dict[str, Any]],
    seen_dates: dict[str, dict[str, Any]],
    timeframe: str,
) -> None:
    """Hover visible candles and collect their DOM legend values."""
    for candle in candles:
        hover_x = candle["x"] + 1
        hover_y = 400

        page.evaluate("window.__clearTooltip()")
        move_ts = time.time()
        page.evaluate(f"window.__lastX = {hover_x}")
        page.mouse.move(hover_x, hover_y)
        time.sleep(HOVER_WAIT_MS / 1000)

        ohlc = read_ohlc_from_dom(page)
        if not ohlc:
            continue

        date_str = read_candle_date(page, move_ts)
        if not date_str or is_current_period(date_str, timeframe):
            continue

        ohlc["type"] = "bull" if ohlc["close"] > ohlc["open"] else "bear"
        ohlc["date"] = date_str
        seen_dates[date_str] = ohlc


def _scroll_to_older_candles(page) -> None:
    """Reveal older candles by shifting the chart left."""
    page.evaluate("window.__clearBatch()")

    for _ in range(SCROLL_PRESSES):
        page.keyboard.press("ArrowLeft")
        time.sleep(random.uniform(0.05, 0.1))

    time.sleep(random.uniform(0.3, 0.6))
