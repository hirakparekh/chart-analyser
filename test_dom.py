from tradingview_scraper_dom import (
    build_hook_script, parse_date, is_current_period,
    CANDLES_PER_PERIOD, MONTHS
)

# Test hook script builds without error
hook = build_hook_script()
print(f"Hook script: {len(hook)} chars")
assert '__BODIES' in hook
assert '__TOOLTIP' in hook
assert '__clearBatch' in hook
assert '__clearTooltip' in hook
assert '#089981' in hook
assert '#f23645' in hook
print("  Hook OK")

# Test date parsing
tests = [
    ("Mon 12 May '25", "2025-05-12"),
    ("12 May '25",     "2025-05-12"),
    ("Thu 1 Jan '24",  "2024-01-01"),
    ("Fri 31 Dec '23", "2023-12-31"),
    ("no date here",   None),
    ("",               None),
]
for text, expected in tests:
    result = parse_date(text)
    assert result == expected, f"parse_date({text!r}) = {result!r}, expected {expected!r}"
print("  Date parsing OK")

# Test is_current_period
assert not is_current_period("2020-01-01", "W")
assert not is_current_period("2020-01-01", "D")
assert not is_current_period("2020-01-01", "1M")
assert is_current_period("2099-06-01", "W")
assert is_current_period("2099-06-01", "D")
from datetime import date as _d
_today = _d.today()
assert is_current_period(f"{_today.year}-{_today.month:02d}-01", "1M")
print("  Current period check OK")

# Test candle targets
assert CANDLES_PER_PERIOD['W']['1y'] == 52
assert CANDLES_PER_PERIOD['W']['2y'] == 104
assert CANDLES_PER_PERIOD['D']['1y'] == 252
assert CANDLES_PER_PERIOD['1M']['5y'] == 60
print("  Candle targets OK")

print("\nAll tests passed!")
