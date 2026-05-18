"""
TradingView OHLC Data Scraper v2.0 — Clean Rewrite

Extracts accurate OHLC candlestick data from TradingView charts
by hooking into canvas rendering calls.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    from tradingview_scraper_headed import get_ohlc
    csv_path = get_ohlc("NIFTY", "W", "1y")
"""

import time
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from playwright.sync_api import sync_playwright, Page


# ═══════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════

BULL_COLOR = '#089981'
BEAR_COLOR = '#f23645'
CANDLE_WIDTH = 3        # px width of candle bodies at default zoom
CHART_TOP_Y = 50        # ignore anything above this (UI chrome)
CHART_BOTTOM_Y = 650    # ignore anything below this (volume bars)
SCROLL_WAIT_MS = 1500   # base wait after each scroll
RENDER_SETTLE_MS = 500  # how long RAW must be stable to confirm render done
RENDER_POLL_MS = 300    # how often to check if render has settled


# ═══════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════

class CalibrationError(Exception):
    """Raised when Y-to-price calibration fails."""
    pass


# ═══════════════════════════════════════
# MONTH MAP
# ═══════════════════════════════════════

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}


# ═══════════════════════════════════════
# HOOK SCRIPT
# ═══════════════════════════════════════

def build_hook_script() -> str:
    """Build the JavaScript canvas hook script with Python constants substituted."""
    return (
        "(function() {\n"
        "  window.__BODIES = [];\n"
        "  window.__WICKS = [];\n"
        "  window.__AXIS = [];\n"
        "  window.__TOOLTIP = [];\n"
        "  window.__RAW_LEN = 0;\n"
        "\n"
        "  const _origFillRect = CanvasRenderingContext2D.prototype.fillRect;\n"
        "  CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {\n"
        "    const c = this.fillStyle;\n"
        "\n"
        "    if (\n"
        f"      (c === '{BULL_COLOR}' || c === '{BEAR_COLOR}') &&\n"
        f"      w === {CANDLE_WIDTH} &&\n"
        f"      y > {CHART_TOP_Y} &&\n"
        f"      y < {CHART_BOTTOM_Y} &&\n"
        "      h >= 1\n"
        "    ) {\n"
        "      window.__BODIES.push({ x, y, w, h, c });\n"
        "      window.__RAW_LEN++;\n"
        "    }\n"
        "\n"
        "    if (\n"
        "      w === 1 &&\n"
        f"      y > {CHART_TOP_Y} &&\n"
        f"      y < {CHART_BOTTOM_Y} &&\n"
        "      h >= 1 &&\n"
        "      (c === '#ffffff' || c === '#FFFFFF')\n"
        "    ) {\n"
        "      window.__WICKS.push({ x, y, h });\n"
        "      window.__RAW_LEN++;\n"
        "    }\n"
        "\n"
        "    return _origFillRect.call(this, x, y, w, h);\n"
        "  };\n"
        "\n"
        "  const _origFillText = CanvasRenderingContext2D.prototype.fillText;\n"
        "  CanvasRenderingContext2D.prototype.fillText = function(text, x, y) {\n"
        "\n"
        "    if (Math.abs(x - 8.8) < 1 && y > 0) {\n"
        "      const num = parseFloat(text.replace(/,/g, ''));\n"
        "      if (!isNaN(num) && num > 100) {\n"
        "        window.__AXIS.push({ price: num, y });\n"
        "      }\n"
        "    }\n"
        "\n"
        "    if (Math.abs(x) < 1 && Math.abs(y) < 1) {\n"
        "      if (/\\d{1,2}\\s[A-Z][a-z]{2}/.test(text)) {\n"
        "        window.__TOOLTIP.push({ text: text, t: Date.now() });\n"
        "      }\n"
        "    }\n"
        "\n"
        "    return _origFillText.call(this, text, x, y);\n"
        "  };\n"
        "\n"
        "  window.__clearBatch = function() {\n"
        "    window.__BODIES = [];\n"
        "    window.__WICKS = [];\n"
        "    window.__AXIS = [];\n"
        "    window.__TOOLTIP = [];\n"
        "    window.__RAW_LEN = 0;\n"
        "  };\n"
        "})();\n"
    )


# ═══════════════════════════════════════
# RENDER SETTLING
# ═══════════════════════════════════════

def wait_for_render_settle(page: Page):
    """
    Wait for canvas render to settle by polling window.__RAW_LEN.
    When it hasn't changed for RENDER_SETTLE_MS, render is done.
    Maximum wait of 5 seconds before giving up.
    """
    prev_len = -1
    stable_since = None
    start = time.time()

    while time.time() - start < 5:
        current_len = page.evaluate("window.__RAW_LEN")
        now = time.time()

        if current_len == prev_len:
            if stable_since and (now - stable_since) > RENDER_SETTLE_MS / 1000:
                return  # settled
        else:
            stable_since = now

        prev_len = current_len
        time.sleep(RENDER_POLL_MS / 1000)


# ═══════════════════════════════════════
# Y → PRICE CALIBRATION
# ═══════════════════════════════════════

def calibrate(page: Page):
    """
    Build a y_to_price function from current axis labels.
    Returns a callable: y_to_price(y) -> float
    Raises CalibrationError if calibration fails.
    """
    axis_labels = page.evaluate("window.__AXIS")

    if not axis_labels or len(axis_labels) < 2:
        raise CalibrationError(
            f"Not enough axis labels for calibration (got {len(axis_labels or [])})"
        )

    # Deduplicate axis labels by rounding y to nearest integer
    deduped = {}
    for label in axis_labels:
        y_key = round(label['y'])
        deduped[y_key] = label

    labels = sorted(deduped.values(), key=lambda l: l['y'])

    if len(labels) < 2:
        raise CalibrationError(
            f"Not enough unique axis labels after dedup (got {len(labels)})"
        )

    # Top of chart = smallest y = highest price
    top = labels[0]
    bottom = labels[-1]

    y1, p1 = top['y'], top['price']
    y2, p2 = bottom['y'], bottom['price']

    print(f"  Calibration: y={y1:.0f} -> {p1:,.2f}  |  y={y2:.0f} -> {p2:,.2f}")

    if y2 == y1:
        raise CalibrationError("Calibration anchors have same Y coordinate")

    price_range = abs(p1 - p2)
    if price_range < 100 or price_range > 10_000_000:
        raise CalibrationError(f"Price range {price_range:.2f} is unreasonable")

    def y_to_price(y: float) -> float:
        return p1 + (y - y1) * (p2 - p1) / (y2 - y1)

    return y_to_price


# ═══════════════════════════════════════
# CANDLE EXTRACTION (per batch)
# ═══════════════════════════════════════

def extract_candles(page: Page, y_to_price) -> list:
    """
    Extract candles from current __BODIES and __WICKS arrays.
    Deduplicates bodies by x (keeps last occurrence).
    Matches wicks at wick.x == body.x + 1 (exact).
    """
    bodies = page.evaluate("window.__BODIES")
    wicks = page.evaluate("window.__WICKS")

    if not bodies:
        print("  Warning: No candle bodies captured in this batch")
        return []

    # Deduplicate bodies by x — keep last occurrence per x value
    body_map = {}
    for body in bodies:
        body_map[body['x']] = body

    unique_bodies = sorted(body_map.values(), key=lambda b: b['x'])

    # Build wick lookup: wick.x -> list of wicks
    wick_map = {}
    for wick in (wicks or []):
        wx = wick['x']
        if wx not in wick_map:
            wick_map[wx] = []
        wick_map[wx].append(wick)

    candles = []
    for body in unique_bodies:
        # === BODY: determines Open and Close ONLY ===
        body_top_y = body['y']
        body_bottom_y = body['y'] + body['h']
        is_bull = body['c'] == BULL_COLOR

        # Bull candle (close > open, price went up):
        #   openY  = bodyBottomY (lower position = lower price)
        #   closeY = bodyTopY    (higher position = higher price)
        # Bear candle (open > close, price went down):
        #   openY  = bodyTopY    (higher position = higher price)
        #   closeY = bodyBottomY (lower position = lower price)
        open_y = body_bottom_y if is_bull else body_top_y
        close_y = body_top_y if is_bull else body_bottom_y

        # === WICKS: determines High and Low ONLY ===
        # Wicks: wick.x === body.x + 1 (exact match)
        matching_wicks = wick_map.get(body['x'] + 1, [])

        if matching_wicks:
            # High = topmost wick pixel (min y = highest price)
            high_y = min(w['y'] for w in matching_wicks)
            # Low = bottommost wick pixel (max y+h = lowest price)
            low_y = max(w['y'] + w['h'] for w in matching_wicks)
        else:
            # No wicks found — use body extremes as fallback
            # but ensure high/low extend at least to body edges
            high_y = body_top_y
            low_y = body_bottom_y

        # === Convert to prices (strictly separated) ===
        # Open and Close from BODY only
        open_price = y_to_price(open_y)
        close_price = y_to_price(close_y)
        # High and Low from WICKS only
        high = y_to_price(high_y)
        low = y_to_price(low_y)

        # Determine type from price (not color)
        candle_type = 'bull' if close_price > open_price else 'bear'

        candles.append({
            'x': body['x'],
            'high': round(high, 2),
            'open': round(open_price, 2),
            'close': round(close_price, 2),
            'low': round(low, 2),
            'type': candle_type,
        })

    print(f"  Extracted {len(candles)} candles from {len(bodies)} raw bodies")
    return candles


# ═══════════════════════════════════════
# DATE EXTRACTION VIA TOOLTIP
# ═══════════════════════════════════════

def parse_tooltip_date(text: str):
    """
    Parse a TradingView tooltip date string.
    Formats: "Mon 12 May '25" or "12 May '25"
    Returns: "2025-05-12" or None if parsing fails.
    """
    match = re.search(r"(\d{1,2})\s+([A-Z][a-z]{2})\s+'(\d{2})", text)
    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)
    year_short = int(match.group(3))

    month = MONTH_MAP.get(month_name)
    if month is None:
        return None

    year = 2000 + year_short

    try:
        dt = datetime(year, month, day)
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        return None


def is_unfinished_candle(date_str: str, timeframe: str) -> bool:
    """Check if a candle date represents an unfinished (current) candle."""
    candle_date = datetime.strptime(date_str, '%Y-%m-%d')
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    if timeframe == 'W':
        this_monday = today - timedelta(days=today.weekday())
        return candle_date >= this_monday
    elif timeframe == 'D':
        return candle_date >= today
    elif timeframe == '1M':
        first_of_month = today.replace(day=1)
        return candle_date >= first_of_month

    return False


def get_candle_dates(page: Page, candles: list, timeframe: str) -> list:
    """
    Get exact dates for each candle by hovering and reading tooltip.
    Uses timestamp-based freshness to avoid stale tooltip data.
    Returns only candles with valid, finished dates.
    """
    dated_candles = []

    for candle in candles:
        # Clear tooltip BEFORE moving mouse
        page.evaluate("window.__TOOLTIP = []")

        # Record timestamp just before mouse move
        move_time = page.evaluate("Date.now()")

        # Move mouse to candle center
        cx = candle['x'] + CANDLE_WIDTH / 2
        cy = 400  # middle of chart, any y works
        page.mouse.move(cx, cy)

        # Wait 300ms for tooltip to render
        time.sleep(0.3)

        # Read tooltip — only entries captured AFTER the mouse move
        tooltips = page.evaluate(
            f"window.__TOOLTIP.filter(function(t) {{ return t.t > {move_time}; }})"
        )

        # If empty, nudge mouse +2px and wait 200ms more
        if not tooltips:
            page.mouse.move(cx + 2, cy)
            time.sleep(0.2)
            tooltips = page.evaluate(
                f"window.__TOOLTIP.filter(function(t) {{ return t.t > {move_time}; }})"
            )

        # If still empty, nudge mouse -2px and wait 200ms more
        if not tooltips:
            page.mouse.move(cx - 2, cy)
            time.sleep(0.2)
            tooltips = page.evaluate(
                f"window.__TOOLTIP.filter(function(t) {{ return t.t > {move_time}; }})"
            )

        if not tooltips:
            continue  # no fresh date captured, skip this candle

        # Take the most recent fresh entry
        date_str = parse_tooltip_date(tooltips[-1]['text'])
        if date_str is None:
            continue

        # Skip unfinished candles
        if is_unfinished_candle(date_str, timeframe):
            continue

        candle['date'] = date_str
        dated_candles.append(candle)

    print(f"  Dated {len(dated_candles)}/{len(candles)} candles")
    return dated_candles


# ═══════════════════════════════════════
# TARGET CANDLE COUNT
# ═══════════════════════════════════════

def calculate_target_candles(timeframe: str, period: str) -> int:
    """
    Calculate expected candle count for a timeframe and period.
    Weekly: 1y=52, 2y=104, 5y=260
    Daily:  1y=252, 2y=504, 5y=1260
    Monthly: 1y=12, 2y=24, 5y=60
    """
    if period.endswith('y'):
        years = int(period[:-1])
    elif period.endswith('m'):
        years = int(period[:-1]) / 12
    else:
        years = 1

    candles_per_year = {
        'W': 52,
        'D': 252,
        '1M': 12,
    }

    return int(years * candles_per_year.get(timeframe, 252))


# ═══════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════

def get_ohlc(symbol: str, timeframe: str, period: str = "1y") -> str:
    """
    Extract OHLC data from TradingView for a given symbol, timeframe, and period.

    Args:
        symbol:    NSE stock symbol e.g. "NIFTY", "RELIANCE", "INFY"
        timeframe: "W" (weekly), "D" (daily), "1M" (monthly)
        period:    "1y", "2y", "5y" etc. Default "1y"

    Returns:
        Path to the saved CSV file.
    """
    target = calculate_target_candles(timeframe, period)
    seen_dates = {}  # date string -> candle dict (deduplicates automatically)

    print(f"\n{'=' * 60}")
    print(f"TradingView OHLC Scraper v2.0")
    print(f"Symbol: {symbol}  Timeframe: {timeframe}  Period: {period}")
    print(f"Target candles: {target}")
    print(f"{'=' * 60}\n")

    browser = None

    try:
        with sync_playwright() as p:
            # Launch browser (headed)
            print("Launching browser...")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()

            # Inject hook before navigation
            print("Injecting canvas hook...")
            page.add_init_script(build_hook_script())

            # Navigate
            url = (
                f"https://in.tradingview.com/chart/"
                f"?symbol=NSE:{symbol}&interval={timeframe}"
            )
            print(f"Navigating to: {url}")
            page.goto(url, wait_until='domcontentloaded')

            # Wait for canvas to appear
            page.wait_for_selector('canvas', timeout=30000)

            # Initial render settle
            print("Waiting for initial render...")
            time.sleep(3)
            wait_for_render_settle(page)

            scroll_count = 0
            max_scrolls = target // 20 + 10  # safety limit

            while len(seen_dates) < target and scroll_count < max_scrolls:
                print(f"\n--- Batch {scroll_count} ---")

                # Calibrate Y -> price from current axis
                try:
                    y_to_price = calibrate(page)
                except CalibrationError as e:
                    print(f"  Calibration failed: {e}")
                    print("  Retrying calibration in 2 seconds...")
                    time.sleep(2)
                    try:
                        y_to_price = calibrate(page)
                    except CalibrationError as e2:
                        print(f"  Calibration retry failed: {e2}")
                        print("  Skipping this batch.")
                        # Still try to scroll to get fresh data
                        y_to_price = None

                if y_to_price is not None:
                    # Extract candle geometry
                    candles = extract_candles(page, y_to_price)

                    if candles:
                        # Get exact dates via tooltip hover
                        candles = get_candle_dates(page, candles, timeframe)

                        # Add to seen_dates (deduplication is automatic)
                        new_count = 0
                        for c in candles:
                            if c.get('date') and c['date'] not in seen_dates:
                                new_count += 1
                            if c.get('date'):
                                seen_dates[c['date']] = c

                        print(f"  New candles this batch: {new_count}")
                    else:
                        print("  Warning: Zero candles extracted in this batch")

                print(
                    f"  Progress: {len(seen_dates)}/{target} candles collected"
                )

                # Check if we have enough
                if len(seen_dates) >= target:
                    break

                # Scroll left for more history
                page.keyboard.press('ArrowLeft')
                for _ in range(14):  # 15 presses total per scroll batch
                    time.sleep(random.uniform(0.05, 0.1))
                    page.keyboard.press('ArrowLeft')

                # Clear batch arrays
                page.evaluate("window.__clearBatch()")

                # Wait for new render
                time.sleep(random.uniform(0.3, 0.6))
                wait_for_render_settle(page)

                scroll_count += 1

            # Keep browser open briefly to see final state
            time.sleep(1)
            browser.close()
            browser = None

    except Exception as e:
        print(f"\nError occurred: {e}")
        raise
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    # Sort by date ascending
    sorted_candles = sorted(seen_dates.values(), key=lambda c: c['date'])

    # Write CSV
    filename = f"{symbol}_{timeframe}_{period}.csv"
    filepath = Path(__file__).parent / filename

    with open(filepath, 'w') as f:
        f.write("date,open,high,low,close,type\n")
        for c in sorted_candles:
            f.write(
                f"{c['date']},{c['open']},{c['high']},"
                f"{c['low']},{c['close']},{c['type']}\n"
            )

    print(f"\n{'=' * 60}")
    print(f"COMPLETE")
    print(f"{'=' * 60}")
    print(f"Symbol:     {symbol}")
    print(f"Timeframe:  {timeframe}")
    print(f"Period:     {period}")
    print(f"Target:     {target}")
    print(f"Collected:  {len(sorted_candles)}")
    print(f"File:       {filepath}")
    print(f"{'=' * 60}\n")

    return str(filepath)


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

if __name__ == "__main__":
    get_ohlc("NIFTY", "W", "1y")
