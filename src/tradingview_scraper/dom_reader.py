"""Read OHLC values from TradingView's DOM legend."""

from playwright.sync_api import Page


def parse_price(value: str | None) -> float | None:
    """Convert a formatted TradingView price string to a float."""
    try:
        if value is None:
            return None
        return float(value.replace(",", "").strip())
    except (AttributeError, ValueError):
        return None


def read_ohlc_from_dom(page: Page) -> dict[str, float] | None:
    """Read open, high, low, and close values from the chart legend."""
    result = page.evaluate(
        """
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
    )

    if not result:
        return None

    open_price = parse_price(result["open"])
    high_price = parse_price(result["high"])
    low_price = parse_price(result["low"])
    close_price = parse_price(result["close"])

    if None in [open_price, high_price, low_price, close_price]:
        return None

    if not (
        high_price >= max(open_price, close_price)
        >= min(open_price, close_price)
        >= low_price
    ):
        return None

    return {
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
    }
