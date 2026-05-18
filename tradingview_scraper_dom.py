"""Compatibility wrapper for the modular TradingView DOM scraper."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tradingview_scraper import get_ohlc  # noqa: E402
from tradingview_scraper.cli import main  # noqa: E402

__all__ = ["get_ohlc"]


if __name__ == "__main__":
    main()
