"""
TradingView OHLC Scraper Launcher

Adds the local 'src' directory to python path and launches the interactive CLI.
"""

import sys
from pathlib import Path

# Ensure Python can find modules inside 'src' without pre-installation.
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from tradingview_scraper.cli import main

if __name__ == "__main__":
    main()
