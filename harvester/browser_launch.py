"""
browser_launch.py — Playwright launch settings for parish harvest.

Reduces obvious bot signals and supports a headful fallback for hosts that
block headless Chromium on CI.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Playwright

HARVESTER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

_STEALTH_INIT_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""

_LAUNCH_ARGS = (
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
)


def headful_fallback_enabled() -> bool:
    """Headful retry is on unless explicitly disabled (e.g. local quick tests)."""
    return os.getenv("HARVEST_DISABLE_HEADFUL_FALLBACK", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }


def looks_like_bot_block(error: str) -> bool:
    text = (error or "").lower()
    markers = (
        "403",
        "forbidden",
        "access denied",
        "captcha",
        "cloudflare",
        "bot detection",
        "err_aborted",
        "blocked",
        "challenge",
    )
    return any(marker in text for marker in markers)


async def launch_harvester_browser(
    playwright: Playwright,
    *,
    headless: bool = True,
) -> Browser:
    return await playwright.chromium.launch(
        headless=headless,
        args=list(_LAUNCH_ARGS),
    )


async def new_harvester_context(browser: Browser) -> BrowserContext:
    context = await browser.new_context(
        user_agent=HARVESTER_USER_AGENT,
        viewport={"width": 1366, "height": 900},
        locale="en-GB",
        timezone_id="Europe/Dublin",
    )
    await context.add_init_script(_STEALTH_INIT_SCRIPT)
    return context
