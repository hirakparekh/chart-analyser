"""
TradingView OHLC Data Scraper — DOM Reading Approach

HOW THIS WORKS (big picture):
  1. We open a real Chromium browser and go to the TradingView chart page
  2. BEFORE the page loads, we inject a tiny JavaScript "spy" that watches
     every rectangle the chart draws on its canvas
  3. When the chart draws a green or red rectangle of the right size,
     we know that's a candle — we save its X position on screen
  4. We then move the mouse to each candle's X position, one at a time
  5. When the mouse hovers a candle, TradingView shows:
       - The OHLC values in a legend at the top-left of the chart (DOM)
       - The date in a tooltip drawn on the canvas
  6. We read the OHLC from the DOM and the date from the tooltip
  7. We scroll left to load older candles, and repeat
  8. Everything gets saved to a CSV file

WHY DOM instead of pixel math?
  The old approach tried to convert pixel Y-coordinates back into prices
  using axis labels. That was fragile and error-prone. This approach
  just reads the actual price numbers that TradingView already displays
  in the chart legend — much simpler and always accurate.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    from tradingview_scraper_dom import get_ohlc
    csv_path = get_ohlc("NIFTY", "W", "2y")
"""

import time
import random
import re
import csv
from datetime import date, timedelta
from playwright.sync_api import sync_playwright, Page


# ═══════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════
# These control how the scraper identifies candles and paces itself.
# If TradingView changes its colors or layout, update these.

# Colors TradingView uses to draw candle bodies on the canvas
BULL_COLOR = '#089981'    # green — price went UP (close > open)
BEAR_COLOR = '#f23645'    # red   — price went DOWN (close < open)

# The pixel width of candle body rectangles at default zoom level
CANDLE_WIDTH = 3

# Vertical pixel boundaries of the price chart area
# Anything drawn above CHART_TOP_Y is UI chrome (toolbar, legend, etc.)
# Anything drawn below CHART_BOTTOM_Y is the volume bar section
CHART_TOP_Y = 50
CHART_BOTTOM_Y = 650

# How many ArrowLeft key presses per scroll batch
# Each press shifts the chart a little to the right, revealing older candles
SCROLL_PRESSES = 15

# Timing controls (milliseconds unless noted)
HOVER_WAIT_MS = 200       # pause after moving mouse, so DOM legend updates
TOOLTIP_WAIT_MS = 200     # pause for the date tooltip to appear on canvas
RENDER_POLL_MS = 300      # how often we check if the chart is done drawing
RENDER_SETTLE_MS = 500    # chart must be idle this long to count as "settled"
RENDER_MAX_WAIT_S = 5     # give up waiting for render after this many seconds

# How many candles we expect for each timeframe + period combination
# Used as the target — we keep scrolling until we collect this many
CANDLES_PER_PERIOD = {
    'W':  {'1y': 52,  '2y': 104, '5y': 260},    # ~52 trading weeks/year
    'D':  {'1y': 252, '2y': 504, '5y': 1260},   # ~252 trading days/year
    '1M': {'1y': 12,  '2y': 24,  '5y': 60},     # 12 months/year
}

# Month abbreviation → number, used when parsing tooltip dates
MONTHS = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12,
}


# ═══════════════════════════════════════
# HOOK SCRIPT
# ═══════════════════════════════════════

def build_hook_script() -> str:
    """
    Build the JavaScript "spy" that we inject into the page BEFORE it loads.

    TradingView draws its chart on an HTML5 <canvas> element using
    CanvasRenderingContext2D.fillRect() for rectangles and fillText() for text.

    We monkey-patch (replace) these two functions with our own versions that:
      1. Check if the thing being drawn looks like a candle body or tooltip
      2. If yes, save it to a global array we can read from Python later
      3. Then call the original function so the chart still draws normally

    We capture TWO things:
      - __BODIES: candle body rectangles (used to find X positions)
      - __TOOLTIP: date strings drawn at position (0,0) when hovering

    We do NOT capture wicks, axis labels, or prices here.
    OHLC prices are read from the DOM instead (see read_ohlc_from_dom).

    The Python constants (colors, dimensions) are substituted as literal
    JavaScript values in the string, since JS can't access Python variables.
    """
    return (
        # Wrap in IIFE (Immediately Invoked Function Expression) to avoid
        # polluting the global scope with our temporary variables
        "(function() {\n"

        # --- Global arrays that Python will read via page.evaluate() ---
        "  window.__BODIES = [];\n"     # stores {x, y, w, h, c} for each candle body
        "  window.__TOOLTIP = [];\n"    # stores {text, ts} for each tooltip date
        "  window.__RAW_LEN = 0;\n"     # counter used to detect when drawing stops
        "\n"

        # --- Monkey-patch fillRect (draws rectangles) ---
        # Save the original so we can still call it after our spy logic
        "  const _origFillRect = CanvasRenderingContext2D.prototype.fillRect;\n"
        "  CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {\n"
        "    const c = this.fillStyle;\n"  # c = the fill color (e.g. '#089981')
        # Check: is this rectangle a candle body?
        #   - Color must be bull green OR bear red
        #   - Width must exactly match CANDLE_WIDTH (3px at default zoom)
        #   - Y position must be inside the chart area (not toolbar or volume)
        #   - Height must be at least 1px (skip invisible zero-height rects)
        "    if (\n"
        f"      (c === '{BULL_COLOR}' || c === '{BEAR_COLOR}') &&\n"
        f"      w === {CANDLE_WIDTH} &&\n"
        f"      y > {CHART_TOP_Y} &&\n"
        f"      y < {CHART_BOTTOM_Y} &&\n"
        "      h >= 1\n"
        "    ) {\n"
        # Yes — save this candle body's position and color
        "      window.__BODIES.push({ x, y, w, h, c });\n"
        "      window.__RAW_LEN++;\n"  # bump counter so render-settle can detect activity
        "    }\n"
        # Always call the original fillRect so the candle actually appears on screen
        "    return _origFillRect.call(this, x, y, w, h);\n"
        "  };\n"
        "\n"

        # --- Monkey-patch fillText (draws text) ---
        # We only care about tooltip date strings, which TradingView draws
        # at canvas position (0, 0) when the mouse hovers over a candle
        "  const _origFillText = CanvasRenderingContext2D.prototype.fillText;\n"
        "  CanvasRenderingContext2D.prototype.fillText = function(text, x, y) {\n"
        # Check: is this text drawn at position (0, 0)?  (within ±1px tolerance)
        "    if (Math.abs(x) < 1 && Math.abs(y) < 1) {\n"
        # Check: does the text look like a date? (e.g. "12 May" pattern)
        "      if (/\\d{1,2}\\s[A-Z][a-z]{2}/.test(text)) {\n"
        # Yes — save the text and a millisecond timestamp for freshness checking
        "        window.__TOOLTIP.push({ text: text, ts: Date.now() });\n"
        "      }\n"
        "    }\n"
        # Always call the original fillText so the text still appears on screen
        "    return _origFillText.call(this, text, x, y);\n"
        "  };\n"
        "\n"

        # --- Helper functions callable from Python via page.evaluate() ---

        # Clear captured candle bodies between scroll batches
        # so we only process the newly-visible candles each time
        "  window.__clearBatch = function() {\n"
        "    window.__BODIES = [];\n"
        "    window.__RAW_LEN = 0;\n"
        "  };\n"
        "\n"
        # Clear captured tooltip dates before each mouse hover
        # so we don't accidentally read a stale date from a previous hover
        "  window.__clearTooltip = function() {\n"
        "    window.__TOOLTIP = [];\n"
        "  };\n"
        "})();\n"
    )


# ═══════════════════════════════════════
# RENDER SETTLING
# ═══════════════════════════════════════

def wait_for_render_settle(page: Page):
    """
    Wait until the chart has finished drawing (render has "settled").

    How it works:
      - Every time a candle body is drawn, __RAW_LEN increments
      - We poll __RAW_LEN every RENDER_POLL_MS milliseconds
      - If the value hasn't changed for RENDER_SETTLE_MS, drawing is done
      - Safety: give up after RENDER_MAX_WAIT_S seconds no matter what

    Why we need this:
      After navigating to the page or scrolling, TradingView takes a moment
      to redraw all the candles. If we try to read data too early, we'll
      get an incomplete set of candles.
    """
    prev_len = -1          # previous __RAW_LEN value (-1 = haven't checked yet)
    stable_since = None    # timestamp when __RAW_LEN last changed
    start = time.time()

    while time.time() - start < RENDER_MAX_WAIT_S:
        # Ask the page: how many candle bodies have been drawn so far?
        current_len = page.evaluate("window.__RAW_LEN")
        now = time.time()

        if current_len == prev_len:
            # Same as last time — drawing might be done
            if stable_since and (now - stable_since) > RENDER_SETTLE_MS / 1000:
                return  # stable long enough, render is settled!
        else:
            # Value changed — drawing is still happening, reset the timer
            stable_since = now

        prev_len = current_len
        time.sleep(RENDER_POLL_MS / 1000)  # wait before checking again


# ═══════════════════════════════════════
# CANDLE X EXTRACTION
# ═══════════════════════════════════════

def extract_candle_positions(page: Page) -> list:
    """
    Read the captured candle bodies from the JavaScript spy and return
    a deduplicated, left-to-right sorted list.

    Why deduplicate?
      TradingView redraws the same candle multiple times per animation
      frame (e.g. during hover highlighting or crosshair movement).
      We only need one entry per unique X position.

    We round X to the nearest integer and keep the LAST occurrence,
    since later draws have the most up-to-date position data.
    """
    # Pull the __BODIES array from the browser into Python
    bodies = page.evaluate("window.__BODIES")

    # Deduplicate by rounded x — keep last occurrence per x value
    # Example: if x=100.3 and x=100.7 both appear, they map to x=100,
    #          and we keep whichever was drawn last
    body_map = {}
    for b in bodies:
        body_map[round(b['x'])] = b

    # Sort left to right (oldest candle on left, newest on right)
    return sorted(body_map.values(), key=lambda b: b['x'])


# ═══════════════════════════════════════
# OHLC DOM READING
# ═══════════════════════════════════════

def read_ohlc_from_dom(page: Page):
    """
    Read OHLC values from TradingView's chart legend in the DOM.

    When you hover over a candle on TradingView, the top-left corner
    of the chart shows something like:
        O 24150.30  H 24325.25  L 24050.10  C 24200.45

    These values are stored in DOM elements whose CSS class names
    contain "valueValue-" (TradingView uses hashed class names that
    change between deployments, but always contain this substring).

    The elements are in order:
      els[0] = volume or symbol name (we skip this)
      els[1] = Open
      els[2] = High
      els[3] = Low
      els[4] = Close

    Returns:
      dict with 'open', 'high', 'low', 'close' as floats
      or None if the values couldn't be read or are invalid
    """
    # Run JavaScript in the browser to query the DOM and extract text
    script = """
        () => {
            const els = document.querySelectorAll('[class*="valueValue-"]');
            if (els.length < 5) return null;
            return {
                open:  els[1].innerText,
                high:  els[2].innerText,
                low:   els[3].innerText,
                close: els[4].innerText,
            };
        }
    """
    result = page.evaluate(script)

    # If the DOM query returned nothing, the legend isn't visible
    if not result:
        return None

    def parse_price(s):
        """Convert price string like '24,325.25' to float 24325.25."""
        try:
            return float(s.replace(',', '').strip())
        except (ValueError, AttributeError):
            return None

    # Parse each value from string to float
    o = parse_price(result['open'])
    h = parse_price(result['high'])
    l = parse_price(result['low'])
    c = parse_price(result['close'])

    # Make sure all four values parsed successfully
    if None in [o, h, l, c]:
        return None

    # Sanity check: High must be the highest, Low must be the lowest
    # The chain h >= max(o,c) >= min(o,c) >= l must hold for valid OHLC
    if not (h >= max(o, c) >= min(o, c) >= l):
        return None

    return {'open': o, 'high': h, 'low': l, 'close': c}


# ═══════════════════════════════════════
# DATE READING VIA TOOLTIP
# ═══════════════════════════════════════

def parse_date(text: str):
    """
    Parse a TradingView tooltip date string into YYYY-MM-DD format.

    TradingView draws the date on the canvas when hovering. It looks like:
      "Mon 12 May '25"  or just  "12 May '25"

    We use regex to extract: day (12), month name (May), year suffix (25)
    Then convert: month name → number, year suffix → full year (2000 + 25)

    Returns "2025-05-12" or None if parsing fails.
    """
    # Regex breakdown:
    #   (\d{1,2})      → capture 1-2 digit day (e.g. "12" or "1")
    #   \s             → whitespace
    #   ([A-Z][a-z]{2}) → capture 3-letter month (e.g. "May")
    #   \s'            → whitespace then apostrophe
    #   (\d{2})        → capture 2-digit year (e.g. "25")
    m = re.search(r"(\d{1,2})\s([A-Z][a-z]{2})\s'(\d{2})", text)
    if not m:
        return None

    day = int(m.group(1))             # e.g. 12
    month = MONTHS.get(m.group(2))    # e.g. "May" → 5
    year = 2000 + int(m.group(3))     # e.g. "25" → 2025

    if not month:
        return None

    # Format as YYYY-MM-DD with zero-padded month and day
    return f"{year}-{month:02d}-{day:02d}"


def read_candle_date(page: Page, move_ts: float):
    """
    Read the date for the candle the mouse is currently hovering over.

    The date comes from the tooltip text that TradingView draws on the
    canvas at position (0,0). Our JavaScript spy captures these into
    __TOOLTIP with a millisecond timestamp.

    We only accept tooltip entries captured AFTER move_ts to make sure
    we're reading the date for the candle we just moved to, not a
    leftover date from a previous hover.

    If no fresh tooltip appears within TOOLTIP_WAIT_MS, we nudge the
    mouse by +2px and try once more (sometimes the hover target is
    slightly off).

    Args:
        page:    the Playwright page object
        move_ts: Python time.time() value recorded just before mouse.move()

    Returns:
        "YYYY-MM-DD" string or None if no date could be read
    """
    # Give TradingView time to draw the tooltip after our mouse move
    time.sleep(TOOLTIP_WAIT_MS / 1000)

    # Read all captured tooltip entries from the browser
    tooltips = page.evaluate("window.__TOOLTIP")

    # Filter: only keep entries with timestamp AFTER our mouse move
    # Note: Python time.time() is in seconds, JS Date.now() is in milliseconds
    move_ts_ms = move_ts * 1000
    fresh = [t for t in tooltips if t['ts'] > move_ts_ms]

    if not fresh:
        # No fresh tooltip — maybe our mouse was slightly off-target
        # Nudge the mouse +2 pixels to the right and try again
        last_x = page.evaluate("window.__lastX || 400")
        page.mouse.move(last_x + 2, 400)
        time.sleep(200 / 1000)
        tooltips = page.evaluate("window.__TOOLTIP")
        fresh = [t for t in tooltips if t['ts'] > move_ts_ms]

    if not fresh:
        return None  # still nothing — this candle has no readable date

    # Take the most recent fresh entry and parse it
    return parse_date(fresh[-1]['text'])


def is_current_period(date_str: str, timeframe: str) -> bool:
    """
    Check if a candle date represents the CURRENT (unfinished) period.

    We skip unfinished candles because their OHLC values are still
    changing as new trades come in. Including them would give
    inaccurate/incomplete data.

    For weekly: skip if the date falls in the current week (Mon–Sun)
    For daily:  skip if the date is today
    For monthly: skip if the date is in the current month
    """
    today = date.today()
    d = date.fromisoformat(date_str)

    if timeframe == 'W':
        # Find this week's Monday (weekday 0 = Monday in Python)
        week_start = today - timedelta(days=today.weekday())
        return d >= week_start
    elif timeframe == 'D':
        return d >= today
    elif timeframe == '1M':
        return d.year == today.year and d.month == today.month

    return False


# ═══════════════════════════════════════
# MAIN FUNCTION
# ═══════════════════════════════════════

def get_ohlc(symbol: str, timeframe: str, period: str = "1y") -> str:
    """
    Main entry point. Scrapes OHLC data from TradingView and saves to CSV.

    The overall flow:
      1. Launch a visible Chromium browser
      2. Inject the canvas spy script
      3. Navigate to the TradingView chart URL
      4. Wait for the chart to finish drawing
      5. LOOP (until we have enough candles or run out of scrolls):
         a. Read candle X positions from the canvas spy
         b. For each candle, hover mouse → read OHLC from DOM + date from tooltip
         c. Store in a dict keyed by date (automatic deduplication)
         d. Scroll left to reveal older candles
         e. Clear the spy's buffers and wait for the new candles to render
      6. Sort collected candles by date and write to CSV

    Args:
        symbol:    NSE stock symbol e.g. "NIFTY", "RELIANCE", "INFY"
        timeframe: "W" (weekly), "D" (daily), "1M" (monthly)
        period:    "1y", "2y", "5y"

    Returns:
        Path to the saved CSV file.
    """
    # Look up how many candles we need for this timeframe + period combo
    target = CANDLES_PER_PERIOD.get(timeframe, {}).get(period)
    if not target:
        raise ValueError(f"Unsupported timeframe={timeframe} period={period}")

    # This dict stores our collected candles, keyed by date string.
    # Using a dict means if we see the same date twice (e.g. from
    # overlapping scroll batches), it automatically keeps only one copy.
    seen_dates = {}

    # Print a header so the user knows what's happening
    print(f"\n{'=' * 60}")
    print(f"TradingView OHLC Scraper — DOM Approach")
    print(f"Symbol: {symbol}  Timeframe: {timeframe}  Period: {period}")
    print(f"Target candles: {target}")
    print(f"{'=' * 60}\n")

    # Build the JavaScript spy script (with our Python constants baked in)
    hook = build_hook_script()

    browser = None

    try:
        with sync_playwright() as p:

            # --- STEP 1: Launch browser ---
            # headless=False means we can see the browser window
            # (useful for debugging; change to True for background operation)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080}  # full HD viewport
            )
            page = context.new_page()

            # --- STEP 2: Inject the canvas spy ---
            # add_init_script runs our JavaScript BEFORE any page scripts load,
            # so our monkey-patches are in place when TradingView starts drawing
            page.add_init_script(hook)

            # --- STEP 3: Navigate to TradingView ---
            # URL format: /chart/?symbol=NSE:NIFTY&interval=W
            url = (
                f"https://in.tradingview.com/chart/"
                f"?symbol=NSE:{symbol}&interval={timeframe}"
            )
            print(f"Navigating to: {url}")
            page.goto(url, wait_until='domcontentloaded', timeout=60000)

            # Wait for at least one <canvas> element to exist in the DOM
            # (TradingView creates these dynamically after JS loads)
            page.wait_for_selector('canvas', timeout=30000)

            # --- STEP 4: Wait for initial chart render ---
            # First give it a flat 3 seconds (TradingView has heavy JS),
            # then use our render-settle detector for precision
            print("Waiting for initial render...")
            time.sleep(3)
            wait_for_render_settle(page)

            scroll_count = 0
            # Safety limit: don't scroll forever if something goes wrong
            # Formula: (target candles / ~20 candles per scroll) + 15 buffer
            max_scrolls = (target // 20) + 15

            # --- STEP 5: Main collection loop ---
            while len(seen_dates) < target and scroll_count < max_scrolls:

                # 5a. Get all candle X positions currently visible on screen
                candles = extract_candle_positions(page)

                if not candles:
                    print(f"  Warning: no candles in batch {scroll_count}")
                else:
                    # 5b. For each candle, hover and read OHLC + date
                    for candle in candles:
                        # Position to hover: just right of candle's left edge
                        hover_x = candle['x'] + 1
                        hover_y = 400  # vertical middle of chart (doesn't matter which y)

                        # Clear any stale tooltip data from previous hover
                        page.evaluate("window.__clearTooltip()")

                        # Record the current time so we can filter stale tooltips
                        move_ts = time.time()

                        # Save hover_x in the browser for the retry-nudge logic
                        page.evaluate(f"window.__lastX = {hover_x}")

                        # Move the mouse to this candle's position
                        # This triggers TradingView to:
                        #   - Update the legend at top-left with this candle's OHLC
                        #   - Draw a tooltip with this candle's date
                        page.mouse.move(hover_x, hover_y)

                        # Give TradingView time to update the DOM legend
                        time.sleep(HOVER_WAIT_MS / 1000)

                        # Read the O, H, L, C values from the DOM legend
                        ohlc = read_ohlc_from_dom(page)
                        if not ohlc:
                            continue  # couldn't read — skip this candle

                        # Read the date from the tooltip on the canvas
                        date_str = read_candle_date(page, move_ts)
                        if not date_str:
                            continue  # no date — skip this candle

                        # Don't include the current (unfinished) candle
                        # Its OHLC is still changing as trading continues
                        if is_current_period(date_str, timeframe):
                            continue

                        # Determine if this candle is bullish or bearish
                        # based on the actual price values (not the color)
                        ohlc['type'] = 'bull' if ohlc['close'] > ohlc['open'] else 'bear'
                        ohlc['date'] = date_str

                        # 5c. Store in our results dict
                        # If this date already exists, it gets overwritten (dedup)
                        seen_dates[date_str] = ohlc

                    # Show progress after processing each batch
                    print(
                        f"  Scroll {scroll_count}: "
                        f"{len(seen_dates)}/{target} candles"
                    )

                # Check if we've collected enough candles
                if len(seen_dates) >= target:
                    break

                # 5d. Scroll left to reveal older candles
                # Clear the spy's body buffer so we only get fresh positions
                page.evaluate("window.__clearBatch()")

                # Press ArrowLeft SCROLL_PRESSES times to shift chart right
                # (revealing older candles on the left side)
                # Random delay between presses to look more human-like
                for _ in range(SCROLL_PRESSES):
                    page.keyboard.press('ArrowLeft')
                    time.sleep(random.uniform(0.05, 0.1))

                # 5e. Wait for the chart to redraw after scrolling
                time.sleep(random.uniform(0.3, 0.6))  # brief pause for render to start
                wait_for_render_settle(page)           # then wait for it to finish
                scroll_count += 1

            # Done collecting — show the browser briefly before closing
            time.sleep(1)
            browser.close()
            browser = None

    except Exception as e:
        print(f"\nError: {e}")
        raise
    finally:
        # Make sure the browser gets closed even if an error occurred
        if browser:
            try:
                browser.close()
            except Exception:
                pass

    # --- STEP 6: Sort and write CSV ---

    # Sort candles oldest-first by date string (YYYY-MM-DD sorts correctly)
    sorted_candles = sorted(seen_dates.values(), key=lambda c: c['date'])

    # Build filename like "NIFTY_W_2y_dom.csv"
    # The "_dom" suffix distinguishes from the old canvas-math approach
    filename = f"{symbol}_{timeframe}_{period}_dom.csv"
    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(
            f, fieldnames=['date', 'open', 'high', 'low', 'close', 'type']
        )
        writer.writeheader()
        writer.writerows(sorted_candles)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"COMPLETE")
    print(f"{'=' * 60}")
    print(f"Symbol:     {symbol}")
    print(f"Timeframe:  {timeframe}")
    print(f"Period:     {period}")
    print(f"Target:     {target}")
    print(f"Collected:  {len(sorted_candles)}")
    print(f"File:       {filename}")
    print(f"{'=' * 60}\n")

    return filename


# ═══════════════════════════════════════
# MAIN
# ═══════════════════════════════════════

if __name__ == "__main__":
    # When running directly (python tradingview_scraper_dom.py),
    # prompt the user for inputs. Press Enter to accept the default
    # shown in [brackets].
    symbol = input("Symbol [NIFTY]: ").strip().upper() or "NIFTY"
    timeframe = input("Timeframe (W/D/1M) [W]: ").strip() or "W"
    period = input("Period (1y/2y/5y) [1y]: ").strip() or "1y"
    get_ohlc(symbol, timeframe, period)
