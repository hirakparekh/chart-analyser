# TradingView OHLC DOM Scraper

This project scrapes OHLC candlestick data from TradingView using Playwright.
The current production path is the DOM-based scraper exposed by:

```python
from tradingview_scraper import get_ohlc

csv_path = get_ohlc("NIFTY", "W", "2y")
```

The scraper opens a Chromium browser, injects a small canvas hook to discover
visible candle X positions, hovers each candle, reads OHLC values from the
TradingView DOM legend, reads dates from the tooltip, and writes a CSV file.

Unlike the older headed scraper, this implementation does not calculate prices
from canvas pixels or calibrate against the Y-axis. TradingView already renders
the hovered candle's OHLC values in the page, so the scraper reads those values
directly.

## Install

```bash
pip install playwright
playwright install chromium
```

## Usage

```bash
python tradingview_scraper_dom.py
```

or:

```python
from tradingview_scraper import get_ohlc

get_ohlc("NIFTY", "W", "1y")
get_ohlc("AAPL", "D", "1y")
```

The output file keeps the existing naming convention:

```text
{SYMBOL}_{TIMEFRAME}_{PERIOD}_dom.csv
```

## Project Layout

```text
src/tradingview_scraper/
  config.py        constants and scraper settings
  hooks.py         JavaScript hook builder
  render.py        render-settle wait logic
  candles.py       candle X-position extraction
  dom_reader.py    OHLC legend reader
  dates.py         tooltip date parsing and current-period filtering
  csv_writer.py    CSV output
  scraper.py       get_ohlc orchestration
  cli.py           command-line prompt
```

Older documentation for the previous canvas-calibration scraper lives in
`docs/legacy/`.
