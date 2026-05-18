"""Configuration constants for the TradingView DOM scraper."""

BULL_COLOR = "#089981"
BEAR_COLOR = "#f23645"

CANDLE_WIDTH = 3
CHART_TOP_Y = 50
CHART_BOTTOM_Y = 650

SCROLL_PRESSES = 15

HOVER_WAIT_MS = 200
TOOLTIP_WAIT_MS = 200
RENDER_POLL_MS = 300
RENDER_SETTLE_MS = 500
RENDER_MAX_WAIT_S = 5

CANDLES_PER_PERIOD = {
    "W": {"1y": 52, "2y": 104, "5y": 260},
    "D": {"1y": 252, "2y": 504, "5y": 1260},
    "1M": {"1y": 12, "2y": 24, "5y": 60},
}

MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}
