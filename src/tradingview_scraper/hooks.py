"""JavaScript hook generation for capturing TradingView canvas activity."""

from tradingview_scraper.config import (
    BEAR_COLOR,
    BULL_COLOR,
    CANDLE_WIDTH,
    CHART_BOTTOM_Y,
    CHART_TOP_Y,
)


def build_hook_script() -> str:
    """Build the JavaScript hook injected before TradingView loads."""
    return (
        "(function() {\n"
        "  window.__BODIES = [];\n"
        "  window.__TOOLTIP = [];\n"
        "  window.__RAW_LEN = 0;\n"
        "\n"
        "  const _origFillRect = CanvasRenderingContext2D.prototype.fillRect;\n"
        "  CanvasRenderingContext2D.prototype.fillRect = function(x, y, w, h) {\n"
        "    const c = this.fillStyle;\n"
        "    if (\n"
        f"      (c === '{BULL_COLOR}' || c === '{BEAR_COLOR}') &&\n"
        f"      w === {CANDLE_WIDTH} &&\n"
        f"      y > {CHART_TOP_Y} &&\n"
        f"      y < {CHART_BOTTOM_Y} &&\n"
        "      h >= 1\n"
        "    ) {\n"
        "      window.__BODIES.push({ x, y, w, h, c });\n"
        "      window.__RAW_LEN++;\n"
        "    }\n"
        "    return _origFillRect.call(this, x, y, w, h);\n"
        "  };\n"
        "\n"
        "  const _origFillText = CanvasRenderingContext2D.prototype.fillText;\n"
        "  CanvasRenderingContext2D.prototype.fillText = function(text, x, y) {\n"
        "    if (Math.abs(x) < 1 && Math.abs(y) < 1) {\n"
        "      if (/\\d{1,2}\\s[A-Z][a-z]{2}/.test(text)) {\n"
        "        window.__TOOLTIP.push({ text: text, ts: Date.now() });\n"
        "      }\n"
        "    }\n"
        "    return _origFillText.call(this, text, x, y);\n"
        "  };\n"
        "\n"
        "  window.__clearBatch = function() {\n"
        "    window.__BODIES = [];\n"
        "    window.__RAW_LEN = 0;\n"
        "  };\n"
        "\n"
        "  window.__clearTooltip = function() {\n"
        "    window.__TOOLTIP = [];\n"
        "  };\n"
        "})();\n"
    )
