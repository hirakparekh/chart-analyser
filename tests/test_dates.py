from datetime import date

from tradingview_scraper.dates import is_current_period, parse_date


def test_parse_date_from_tradingview_tooltip() -> None:
    cases = [
        ("Mon 12 May '25", "2025-05-12"),
        ("12 May '25", "2025-05-12"),
        ("Thu 1 Jan '24", "2024-01-01"),
        ("Fri 31 Dec '23", "2023-12-31"),
        ("no date here", None),
        ("", None),
    ]

    for text, expected in cases:
        assert parse_date(text) == expected


def test_is_current_period_rejects_old_dates() -> None:
    assert not is_current_period("2020-01-01", "W")
    assert not is_current_period("2020-01-01", "D")
    assert not is_current_period("2020-01-01", "1M")


def test_is_current_period_accepts_current_month() -> None:
    today = date.today()
    assert is_current_period(f"{today.year}-{today.month:02d}-01", "1M")
