"""Candle position extraction from the injected canvas hook."""

from typing import Any

from playwright.sync_api import Page


def extract_candle_positions(page: Page) -> list[dict[str, Any]]:
    """Return deduplicated candle body positions sorted left to right."""
    bodies = page.evaluate("window.__BODIES")

    body_map = {}
    for body in bodies:
        body_map[round(body["x"])] = body

    return sorted(body_map.values(), key=lambda body: body["x"])
