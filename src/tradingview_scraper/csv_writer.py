"""CSV output helpers."""

import csv
from pathlib import Path
from typing import Any


def build_output_path(symbol: str, timeframe: str, period: str) -> Path:
    """Build the historical output filename used by the DOM scraper."""
    return Path(f"{symbol}_{timeframe}_{period}_dom.csv")


def write_candles_csv(
    symbol: str,
    timeframe: str,
    period: str,
    candles: list[dict[str, Any]],
) -> str:
    """Write candles to CSV and return the generated path."""
    output_path = build_output_path(symbol, timeframe, period)
    sorted_candles = sorted(candles, key=lambda candle: candle["date"])

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["date", "open", "high", "low", "close", "type"],
        )
        writer.writeheader()
        writer.writerows(sorted_candles)

    return str(output_path)
