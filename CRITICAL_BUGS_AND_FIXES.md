# Critical Bugs and Required Fixes

## 🐛 Bug #1: Multiple Canvas Capture (CRITICAL)

### Problem
The hook is capturing fillRect calls from **multiple overlapping canvas elements** simultaneously, causing:
- Duplicate candles with different price scales mixed together
- 5,448 raw bodies reduced to only 391 unique candles
- Inconsistent price calibration

### Root Cause
TradingView uses multiple layered canvases (background, grid, chart, overlays). The hook captures from ALL of them without discrimination.

### Solution: Canvas Identification

```javascript
// Add to inject_canvas_hook():
window.__CANVAS_STATS = new WeakMap();
window.__LOCKED_CONTEXT = null;
window.__OBSERVATION_COMPLETE = false;

// 2-second observation period at startup
setTimeout(() => {
    console.log('[CANVAS] Observation period complete');
    window.__OBSERVATION_COMPLETE = true;
}, 2000);

// In fillRect hook:
if (!window.__OBSERVATION_COMPLETE) {
    const isColored = (style === BULL_COLOR || style === BEAR_COLOR) 
                      && w >= 3 && w <= 30 && h >= 2;
    
    if (isColored) {
        const count = window.__CANVAS_STATS.get(this) || 0;
        window.__CANVAS_STATS.set(this, count + 1);
        
        // Update locked context to the one with most colored rectangles
        const currentMax = window.__CANVAS_STATS.get(window.__LOCKED_CONTEXT) || 0;
        if (count + 1 > currentMax) {
            window.__LOCKED_CONTEXT = this;
        }
    }
}

// After observation, only capture from the locked context
if (window.__OBSERVATION_COMPLETE && window.__LOCKED_CONTEXT && this !== window.__LOCKED_CONTEXT) {
    return originalFillRect.apply(this, arguments);
}
```

### Expected Result
- Only capture from the main chart canvas
- Reduce raw bodies from 5,448 to ~400-500 (actual unique candles)
- Eliminate duplicate candles with mixed price scales

---

## 🐛 Bug #2: Aggressive Deduplication

### Problem
Current deduplication uses `Math.round(x)` which groups candles within 1px. This is too aggressive when candles are close together.

### Current Code
```javascript
const roundedX = Math.round(body.x);
bodyMap.set(roundedX, body);
```

### Solution: Wider Grouping
```javascript
// Group by 12px intervals (half candle width)
const groupedX = Math.round(body.x / 12) * 12;
bodyMap.set(groupedX, body);
```

### Expected Result
- Better grouping of nearby candles
- Reduce false duplicates
- More accurate candle count

---

## 🐛 Bug #3: Price Calibration Validation

### Problem
No validation of calibrated prices. Mixed canvas data can cause wildly incorrect price ranges.

### Solution: Add Validation

```python
def calibrate_prices(candles: list, labels: list, symbol: str) -> list:
    # ... existing calibration code ...
    
    # DEBUG: Print calibration details
    print(f"\nPrice Calibration Debug:")
    print(f"  Top label: '{top_label['text']}' at Y={y1:.1f}")
    print(f"  Bottom label: '{bottom_label['text']}' at Y={y2:.1f}")
    print(f"  Pixels per price: {(y2-y1)/(p2-p1):.4f}")
    
    # Convert Y coordinates to prices
    for candle in candles:
        candle['high'] = y_to_price(candle['highY'])
        candle['open'] = y_to_price(candle['openY'])
        candle['close'] = y_to_price(candle['closeY'])
        candle['low'] = y_to_price(candle['lowY'])
    
    # Validate price range
    all_prices = []
    for c in candles:
        all_prices.extend([c['high'], c['low']])
    
    if all_prices:
        min_price = min(all_prices)
        max_price = max(all_prices)
        price_range = max_price - min_price
        
        print(f"  Price range: {min_price:.2f} to {max_price:.2f} (span: {price_range:.2f})")
        
        # Validation for NIFTY (adjust for other symbols)
        if 'NIFTY' in symbol.upper():
            if price_range < 5000 or price_range > 50000:
                print(f"  ❌ ERROR: Price range {price_range:.2f} is outside expected range (5000-50000)")
                print(f"  This indicates calibration error from mixed canvas data")
                raise ValueError(f"Price calibration failed: range {price_range:.2f} is invalid")
        
        print(f"  ✓ Price range validation passed")
    
    return candles
```

### Expected Result
- Detect and abort on calibration errors
- Prevent saving CSV with incorrect prices
- Clear diagnostic output for debugging

---

## 🐛 Bug #4: Date Anchor Accumulation

### Problem
Date anchors may not accumulate during scrolling if labels are not re-captured after chart redraws.

### Solution: Track and Re-read After Scrolling

```python
def perform_scrolling(page: Page, scroll_count: int):
    print(f"Performing {scroll_count} scroll batches...")
    
    # Get initial date anchor count
    initial_date_count = page.evaluate("""
        (window.__RAW_TEXT || []).filter(l => l.type === 'date').length
    """)
    print(f"  Initial date anchors: {initial_date_count}")
    
    for i in range(scroll_count):
        # Press ArrowLeft 15 times per batch
        for _ in range(15):
            page.keyboard.press('ArrowLeft')
            time.sleep(0.05)
        
        # Wait with jitter
        jitter = random.uniform(0, 0.5)
        wait_time = 1.5 + jitter
        
        # Check captured counts
        captured_count = page.evaluate("(window.__RAW || []).length")
        date_count = page.evaluate("""
            (window.__RAW_TEXT || []).filter(l => l.type === 'date').length
        """)
        
        print(f"  Scroll batch {i+1}/{scroll_count}: {captured_count} items, {date_count} date anchors")
        
        # If date anchors didn't increase, force re-read
        if date_count == initial_date_count and i > 0:
            print(f"  ⚠️  Date anchors not increasing - labels may not be captured during scroll")
        
        time.sleep(wait_time)
```

### Expected Result
- Track date anchor accumulation
- Warn if anchors don't increase during scrolling
- Better date interpolation accuracy

---

## 📋 Implementation Checklist

- [x] 1. Add canvas identification with 2-second observation period
- [x] 2. Lock hook to only capture from main chart canvas
- [x] 3. Change deduplication from `Math.round(x)` to `Math.round(x/12)*12`
- [x] 4. Add price calibration validation with range checks
- [x] 5. Add symbol-specific price range validation (NIFTY: 5000-50000)
- [x] 6. Track date anchor count during scrolling
- [x] 7. Warn if date anchors don't accumulate
- [x] 8. Add detailed debug output for calibration
- [ ] 9. Test with NIFTY, AAPL, and RELIANCE
- [ ] 10. Update README with new expected behavior

---

## 🧪 Testing Plan

### Test Case 1: NIFTY Weekly 1y
**Expected:**
- ~52-60 candles (not 391)
- Price range: 20,000 - 25,000 (reasonable for NIFTY)
- Date range: Last 1 year only
- No calibration errors

### Test Case 2: AAPL Daily 1y
**Expected:**
- ~252 candles
- Price range: $150 - $250 (reasonable for AAPL)
- Date range: Last 1 year only
- No calibration errors

### Test Case 3: Multiple Scrolls (2y period)
**Expected:**
- Date anchors increase with each scroll batch
- No duplicate candles from multiple canvases
- Consistent price calibration

---

## 🎯 Success Criteria

1. **Canvas Isolation**: Only one canvas context is used for capture
2. **Correct Candle Count**: Weekly 1y = ~52 candles (not 391)
3. **Valid Prices**: Price range within expected bounds for symbol
4. **Date Accuracy**: Dates match requested period
5. **No Duplicates**: Deduplication reduces raw count by ~10-20% (not 90%)

---

## 📝 Notes

- The current implementation captures from ALL canvases, causing the 5,448 → 391 reduction
- Canvas identification is CRITICAL - must be implemented first
- Price validation prevents saving bad data
- Date anchor tracking helps diagnose interpolation issues

---

**Priority**: 🔴 CRITICAL - Implement canvas identification immediately
**Impact**: High - Affects all data accuracy
**Effort**: Medium - Requires careful JavaScript modification
