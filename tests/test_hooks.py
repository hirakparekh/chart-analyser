from tradingview_scraper.config import BEAR_COLOR, BULL_COLOR, CANDLES_PER_PERIOD
from tradingview_scraper.hooks import build_hook_script


def test_hook_script_contains_required_globals() -> None:
    hook = build_hook_script()

    assert "__BODIES" in hook
    assert "__TOOLTIP" in hook
    assert "__clearBatch" in hook
    assert "__clearTooltip" in hook
    assert BULL_COLOR in hook
    assert BEAR_COLOR in hook


def test_candle_targets() -> None:
    assert CANDLES_PER_PERIOD["W"]["1y"] == 52
    assert CANDLES_PER_PERIOD["W"]["2y"] == 104
    assert CANDLES_PER_PERIOD["D"]["1y"] == 252
    assert CANDLES_PER_PERIOD["1M"]["5y"] == 60
