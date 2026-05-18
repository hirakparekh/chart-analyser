# TradingView OHLC Scraper (Headed Mode)

A Python-based web scraper that extracts OHLC (Open, High, Low, Close) candlestick data from TradingView charts using Playwright. This version runs with a **visible browser window** (headed mode) for debugging and monitoring.

## 🎯 What It Does

This scraper:
- Opens a visible Chromium browser window
- Navigates to TradingView charts for any stock symbol
- Hooks into the HTML5 Canvas rendering to capture candle drawing operations
- Extracts OHLC data by analyzing canvas `fillRect` and `fillText` calls
- Automatically detects candle body widths and colors (adaptive to zoom levels)
- Scrolls through historical data to capture more candles
- Calibrates pixel coordinates to actual prices using axis labels
- Exports data to CSV with columns: `idx, x, type, high, open, close, low`

## 🔧 How It Works

### 1. **Canvas Hook Injection**
Before the page loads, the script injects JavaScript that intercepts all canvas drawing operations:
```javascript
CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {
    // Capture bull candles (green #089981)
    // Capture bear candles (red #f23645)
    // Capture wicks (white #ffffff)
}
```

### 2. **Adaptive Width Detection**
Instead of hardcoding candle body width (which changes with zoom), the script:
- Captures all colored rectangles with width 3-30px and height ≥2px
- Analyzes the most common width among captured bodies
- Uses that width as the candle body width for the session

### 3. **Chart Scrolling**
The script calculates how many scroll batches are needed based on:
- Timeframe (daily, weekly, monthly, etc.)
- Period (1y, 2y, 5y, etc.)
- Approximately 30 candles revealed per scroll batch
- Scrolls by simulating keyboard `ArrowLeft` presses (15 per batch)
- Adds random jitter (1.5s + 0-0.5s) between scrolls to appear human-like

### 4. **OHLC Extraction**
For each candle body:
- Finds matching wicks within ±3px of the body center
- Determines bull/bear type by color
- Calculates:
  - `highY` = minimum Y of all wicks
  - `lowY` = maximum Y of all wicks
  - `openY` = bottom of body (bull) or top of body (bear)
  - `closeY` = top of body (bull) or bottom of body (bear)

### 5. **Price Calibration**
Converts Y pixel coordinates to actual prices:
- Captures numeric text labels from the price axis (y > 0)
- Uses topmost and bottommost labels as calibration anchors
- Applies linear interpolation: `price = p1 + (y - y1) * (p2 - p1) / (y2 - y1)`

### 6. **Timestamp Extraction**
Interpolates dates for each candle using X-axis labels:
- Captures date labels at y ≈ 15 (month names and year numbers)
- Separates into year markers (e.g., "2024", "2025") and month markers (e.g., "Jan", "Feb")
- Builds a timeline by assigning years to months
- For each candle, finds nearest timeline anchors (left and right)
- Interpolates date using linear interpolation based on X-coordinate
- Outputs dates in YYYY-MM-DD format

### 7. **Deduplication**
Removes duplicate candles captured during scrolling by keeping the last occurrence of each unique x-coordinate.

## 📦 Installation

### Prerequisites
- Python 3.8+
- pip (Python package manager)

### Install Dependencies
```bash
pip install playwright
playwright install chromium
```

## 🚀 Usage

### Basic Usage
```python
from tradingview_scraper_headed import get_ohlc

# Get 2 years of weekly NIFTY data
csv_path = get_ohlc("NIFTY", "W", "2y")
print(f"Data saved to: {csv_path}")
```

### Function Signature
```python
def get_ohlc(symbol: str, timeframe: str, period: str = "1y") -> str
```

**Parameters:**
- `symbol` (str): Stock symbol
  - Indian stocks: `"NIFTY"`, `"RELIANCE"`, `"TATAMOTORS"`, `"INFY"`, etc.
  - US stocks: `"AAPL"`, `"GOOGL"`, `"MSFT"`, `"TSLA"`, `"AMZN"`, etc.
  
- `timeframe` (str): TradingView interval code
  - `"D"` - Daily
  - `"W"` - Weekly
  - `"1M"` - Monthly
  - `"15"` - 15 minutes
  - `"60"` - 1 hour
  
- `period` (str, optional): How far back to fetch (default: `"1y"`)
  - `"1y"` - 1 year
  - `"2y"` - 2 years
  - `"5y"` - 5 years

**Returns:**
- `str`: Path to the saved CSV file

### Examples

```python
from tradingview_scraper_headed import get_ohlc

# Indian stocks (NSE)
get_ohlc("NIFTY", "W", "2y")           # 2 years weekly NIFTY
get_ohlc("RELIANCE", "D", "1y")        # 1 year daily Reliance
get_ohlc("TATAMOTORS", "D", "5y")      # 5 years daily Tata Motors

# US stocks (NASDAQ)
get_ohlc("AAPL", "D", "1y")            # 1 year daily Apple
get_ohlc("TSLA", "W", "2y")            # 2 years weekly Tesla
get_ohlc("GOOGL", "1M", "5y")          # 5 years monthly Google
```

### Command Line Usage
```bash
# Run the example in the script
python tradingview_scraper_headed.py

# Or use Python's -c flag
python -c "from tradingview_scraper_headed import get_ohlc; get_ohlc('AAPL', 'D', '1y')"
```

## 📊 Output Format

### CSV Structure
```csv
date,idx,x,type,high,open,close,low
2025-07-08,0,5,bull,23500.50,23450.25,23500.50,23450.25
2025-07-15,1,10,bear,23480.75,23480.75,23420.00,23420.00
2025-07-22,2,15,bull,23550.00,23430.50,23550.00,23430.50
...
```

**Columns:**
- `date`: Interpolated date in YYYY-MM-DD format (most recent period only)
- `idx`: Sequential index (0, 1, 2, ...)
- `x`: X-coordinate on canvas (for reference)
- `type`: `"bull"` (green/up) or `"bear"` (red/down)
- `high`: Highest price of the candle
- `open`: Opening price
- `close`: Closing price
- `low`: Lowest price of the candle

### Important Notes
- **Period Filtering**: The scraper captures all visible candles on the chart, then filters to keep only the requested period (most recent N years/months)
- **Date Accuracy**: Dates are interpolated from X-axis labels and may not be exact for every candle
- **Expected Candle Counts**:
  - Weekly 1y: ~52-106 candles
  - Daily 1y: ~252 candles
  - Monthly 1y: ~12 candles

### File Naming
Files are saved in the same directory as the script with the format:
```
{SYMBOL}_{TIMEFRAME}_{PERIOD}.csv
```

Examples:
- `NIFTY_W_2y.csv`
- `AAPL_D_1y.csv`
- `TATAMOTORS_D_5y.csv`

## 🎨 Features

### ✅ Adaptive Detection
- Automatically detects candle body width (works at any zoom level)
- Auto-detects bull and bear colors from actual canvas data
- No manual configuration needed

### ✅ Multi-Exchange Support
- **NSE** (National Stock Exchange, India): NIFTY, RELIANCE, INFY, etc.
- **NASDAQ** (US): AAPL, GOOGL, MSFT, TSLA, AMZN, META, NVDA

### ✅ Human-Like Behavior
- Random jitter between scrolls (1.5s + 0-0.5s)
- Keyboard-based scrolling (ArrowLeft key)
- Gradual data collection

### ✅ Robust Extraction
- Handles overlapping candles
- Deduplicates data across scroll batches
- Matches wicks to bodies with tolerance
- Linear price calibration from axis labels

## ⚙️ Configuration

### Color Constants
Located at the top of the script:
```python
BULL_COLOR = '#089981'  # Green for bull candles
BEAR_COLOR = '#f23645'  # Red for bear candles
WICK_COLOR = '#ffffff'  # White for wicks
```

Change these if TradingView uses different colors in your region/theme.

### Browser Settings
The script launches with:
```python
browser = p.chromium.launch(headless=False)  # Visible browser
context = browser.new_context(viewport={'width': 1920, 'height': 1080})
```

To run headless (invisible), change `headless=False` to `headless=True`.

## 🐛 Troubleshooting

### No Candles Captured
**Problem:** `Captured 0 raw candles`

**Solutions:**
1. Check if the symbol exists on the exchange
2. Verify color constants match TradingView's theme
3. Increase wait time after page load (currently 4 seconds)
4. Check browser console for JavaScript errors

### Wrong Exchange
**Problem:** Symbol not found (e.g., AAPL on NSE)

**Solution:** Add the symbol to the exchange detection list:
```python
if symbol in ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'AMZN', 'META', 'NVDA']:
    exchange = 'NASDAQ'
```

### Price Calibration Issues
**Problem:** Prices look incorrect

**Solutions:**
1. Check if price labels are being captured (`Captured X price labels`)
2. Verify the calibration output shows reasonable price ranges
3. Ensure the chart has visible price axis labels

### Too Few Candles
**Problem:** Expected more candles for the period

**Solutions:**
1. Increase scroll count calculation multiplier
2. Add more wait time between scrolls
3. Check if the chart loaded completely before scrolling

## 📝 Technical Details

### Dependencies
- **Playwright**: Browser automation framework
- **Python 3.8+**: Core language

### Canvas Hook Mechanism
The script uses `page.add_init_script()` to inject JavaScript **before** the page loads. This ensures the canvas hook is active when TradingView starts drawing candles.

### Scroll Calculation
```python
candles_per_year = {
    'W': 52,      # Weekly
    'D': 252,     # Daily (trading days)
    '1M': 12,     # Monthly
    '15': 252 * 26,  # 15-min
    '60': 252 * 6.5, # 1-hour
}
total_candles = years * candles_per_year[timeframe]
scroll_count = int(total_candles / 30) + 1
```

### Deduplication Strategy
Uses a Map/dictionary with x-coordinate as key, keeping the last occurrence:
```javascript
const bodyMap = new Map();
bodies.forEach(body => {
    bodyMap.set(body.x, body);  // Overwrites previous
});
```

## 🔒 Limitations

1. **Approximate Timestamps**: Dates are interpolated from X-axis labels and may not be exact
2. **Approximate Data**: Scroll-based collection may miss some candles
3. **TradingView Dependent**: Breaks if TradingView changes canvas rendering
4. **Rate Limiting**: No built-in rate limiting (use responsibly)
5. **Single Session**: Each run is independent (no incremental updates)

## 🚧 Future Enhancements

- [x] Add timestamp extraction from chart
- [ ] Improve timestamp accuracy for intraday timeframes
- [ ] Support for more exchanges (BSE, NYSE, etc.)
- [ ] Headless mode option via command-line flag
- [ ] Progress bar for long scraping sessions
- [ ] Retry logic for failed extractions
- [ ] Volume data extraction
- [ ] Support for indicators (RSI, MACD, etc.)

## 📄 License

This project is provided as-is for educational purposes. Use responsibly and respect TradingView's Terms of Service.

## ⚠️ Disclaimer

This tool is for educational and research purposes only. Web scraping may violate TradingView's Terms of Service. Use at your own risk. The authors are not responsible for any misuse or consequences of using this tool.

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📧 Support

For issues or questions:
1. Check the Troubleshooting section
2. Review the code comments
3. Open an issue with detailed error logs

---

**Happy Scraping! 📈**
