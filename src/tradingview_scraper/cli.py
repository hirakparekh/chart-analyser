"""Command-line entry point for the TradingView DOM scraper."""

import logging

from tradingview_scraper.scraper import get_ohlc


def main() -> None:
    """Prompt for scrape inputs and run the DOM scraper."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    symbol = input("Symbol [NIFTY]: ").strip().upper() or "NIFTY"
    timeframe = input("Timeframe (W/D/1M) [W]: ").strip() or "W"
    period = input("Period (1y/2y/5y) [1y]: ").strip() or "1y"
    get_ohlc(symbol, timeframe, period)


if __name__ == "__main__":
    main()
