from tradingview_scraper import get_ohlc as package_get_ohlc
from tradingview_scraper_dom import get_ohlc as wrapper_get_ohlc


def test_root_wrapper_exports_package_get_ohlc() -> None:
    assert wrapper_get_ohlc is package_get_ohlc
