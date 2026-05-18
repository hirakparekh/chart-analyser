# Quick Start Guide

## Installation (One-Time Setup)

```bash
pip install playwright
playwright install chromium
```

## Basic Usage

### Python Script
```python
from tradingview_scraper_headed import get_ohlc

# Indian stocks (NSE)
get_ohlc("NIFTY", "W", "2y")           # NIFTY weekly, 2 years
get_ohlc("RELIANCE", "D", "1y")        # Reliance daily, 1 year
get_ohlc("TATAMOTORS", "D", "5y")      # Tata Motors daily, 5 years

# US stocks (NASDAQ)
get_ohlc("AAPL", "D", "1y")            # Apple daily, 1 year
get_ohlc("TSLA", "W", "2y")            # Tesla weekly, 2 years
get_ohlc("GOOGL", "1M", "5y")          # Google monthly, 5 years
```

### Command Line
```bash
# Run the built-in example
python tradingview_scraper_headed.py

# Custom symbol
python -c "from tradingview_scraper_headed import get_ohlc; get_ohlc('AAPL', 'D', '1y')"
```

## Parameters

### Symbol (Required)
- **Indian**: `NIFTY`, `RELIANCE`, `TATAMOTORS`, `INFY`, `TCS`, etc.
- **US**: `AAPL`, `GOOGL`, `MSFT`, `TSLA`, `AMZN`, `META`, `NVDA`

### Timeframe (Required)
- `"D"` - Daily
- `"W"` - Weekly  
- `"1M"` - Monthly
- `"15"` - 15 minutes
- `"60"` - 1 hour

### Period (Optional, default: "1y")
- `"1y"` - 1 year
- `"2y"` - 2 years
- `"5y"` - 5 years

## Output

CSV file saved as: `{SYMBOL}_{TIMEFRAME}_{PERIOD}.csv`

Example: `AAPL_D_1y.csv`

```csv
date,idx,x,type,high,open,close,low
2024-01-08,0,5,bull,175.50,170.25,175.50,170.25
2024-01-15,1,10,bear,174.80,174.80,172.00,172.00
2024-01-22,2,15,bull,178.00,172.50,178.00,172.50
```

**Note**: Dates are interpolated from X-axis labels and may not be exact for every candle.

## What You'll See

1. **Browser opens** (Chromium window)
2. **Navigates to TradingView**
3. **Chart loads** (4 second wait)
4. **Scrolls left** (multiple batches)
5. **Extracts data** (auto-detection)
6. **Saves CSV** (same directory)
7. **Browser closes**

Total time: ~30-60 seconds per symbol

## Troubleshooting

### "No candles captured"
- Check if symbol exists on the exchange
- Wait for chart to fully load
- Verify internet connection

### "Wrong exchange"
Add your symbol to the exchange list in the code:
```python
if symbol in ['AAPL', 'GOOGL', 'YOUR_SYMBOL']:
    exchange = 'NASDAQ'
```

### "Prices look wrong"
- Ensure price axis is visible
- Check calibration output in console
- Verify chart loaded completely

## Tips

- **Watch the browser** - You can see what's happening in real-time
- **Check console output** - Shows progress and debug info
- **One symbol at a time** - Don't run multiple instances
- **Be patient** - Scrolling takes time for accuracy

## Need More Help?

Read the full documentation: `README_headed.md`
