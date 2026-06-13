"""
html_capture.py — Archive-aware HTML bulletin capture as PDF.

Strategy for endless archive/listing pages:
  1. Try to click the best dated link for the harvest target week.
  2. Print only the main content region (article / entry-content) when possible.
  3. Fall back to full-page print.
  4. Reject PDFs over MAX_BULLETIN_PAGES (caller verifies).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable
from urllib.parse import unquote

from .utils import extract_date_from_string

if TYPE_CHECKING:
    from playwright.async_api import Page

CONTENT_SELECTORS: tuple[str, ...] = (
    "article",
    ".entry-content",
    ".post-content",
    ".content-area",
    ".inside-article",
    ".site-content",
    '[role="main"]',
    "main",
)

_LISTING_HINTS = re.compile(
    r"archive|newsletter|bulletin|weekly|past|previous|all.?posts|category",
    re.IGNORECASE,
)

_HIDE_CHROME_JS = """
(selector) => {
  const root = document.querySelector(selector);
  if (!root) return false;
  const mark = (node) => {
    if (!node || node === document.documentElement) return;
    for (const child of Array.from(node.children)) {
      if (child === root || root.contains(child)) {
        mark(child);
      } else {
        child.style.setProperty('display', 'none', 'important');
      }
    }
  };
  mark(document.body);
  root.style.setProperty('display', 'block', 'important');
  root.style.setProperty('max-width', '100%', 'important');
  window.scrollTo(0, 0);
  return true;
}
"""

_COLLECT_LINKS_JS = """
() => Array.from(document.querySelectorAll('a[href]')).map((a, index) => ({
  href: a.href,
  text: (a.innerText || a.textContent || '').trim().slice(0, 240),
  index,
}))
"""


def _target_date_tokens(target: date) -> list[str]:
    month = target.strftime("%B")
    mon_abbr = target.strftime("%b")
    dd = f"{target.day:02d}"
    mm = f"{target.month:02d}"
    yy = f"{target.year % 100:02d}"
    yyyy = f"{target.year}"
    return [
        f"{dd}{mm}{yy}",
        f"{dd}{mm}{yyyy}",
        f"{yyyy}-{mm}-{dd}",
        f"{yyyy}{mm}{dd}",
        f"{target.day}-{target.month}-{yy}",
        f"{target.day}-{month.lower()}-{yyyy}",
        f"{target.day}{month.lower()}{yyyy}",
        f"{target.day}{mon_abbr.lower()}{yyyy}",
        month.lower(),
        mon_abbr.lower(),
    ]


def score_link_for_target(target: date, href: str, label: str, index: int) -> tuple[int, int, int, int]:
    raw = f"{unquote(href)} {label}".lower()
    tokens = _target_date_tokens(target)
    has_target_token = any(tok in raw for tok in tokens if len(tok) >= 3)
    candidate_date = extract_date_from_string(raw)
    week_start = target - timedelta(days=6)
    in_week = candidate_date is not None and week_start <= candidate_date <= target
    not_stale = 1 if (candidate_date is None or in_week) else 0
    return (
        1 if has_target_token else 0,
        1 if in_week else 0,
        not_stale,
        -index,
    )


def pick_best_link(links: list[dict], target: date) -> str | None:
    ranked: list[tuple[tuple[int, int, int, int], str]] = []
    for item in links:
        href = str(item.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        label = str(item.get("text") or "")
        idx = int(item.get("index") or 0)
        ranked.append((score_link_for_target(target, href, label, idx), href))
    if not ranked:
        return None
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best_href = ranked[0]
    if best_score[0] or best_score[1] or best_score[2]:
        return best_href
    return None


def page_looks_like_listing(page_url: str, link_count: int) -> bool:
    if link_count < 8:
        return False
    return bool(_LISTING_HINTS.search(page_url or ""))


async def try_navigate_to_current_bulletin(page: Page, target: date) -> bool:
    current = page.url
    try:
        links = await page.evaluate(_COLLECT_LINKS_JS)
    except Exception:
        return False
    if not isinstance(links, list) or not page_looks_like_listing(current, len(links)):
        return False
    best = pick_best_link(links, target)
    if not best or best == current:
        return False
    try:
        await page.goto(best, wait_until="domcontentloaded")
        return True
    except Exception:
        return False


async def hide_non_content_chrome(page: Page) -> str | None:
    for selector in CONTENT_SELECTORS:
        try:
            used = await page.evaluate(_HIDE_CHROME_JS, selector)
        except Exception:
            continue
        if used:
            return selector
    return None


async def capture_html_page_as_pdf(
    page: Page,
    dest: Path,
    target: date,
    *,
    print_pdf: Callable[[Page, Path], Awaitable[None]],
    verify_pdf: Callable[[Path], None] | None = None,
    wait_ms: int = 1500,
) -> tuple[bool, str]:
    """Returns (success, capture_mode)."""
    await try_navigate_to_current_bulletin(page, target)
    if wait_ms > 0:
        wait_for_timeout = getattr(page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            await wait_for_timeout(wait_ms)
        else:
            import asyncio
            await asyncio.sleep(wait_ms / 1000)

    navigated = page.url
    selector = await hide_non_content_chrome(page)
    mode = "archive_nav_print" if navigated else "content_print"
    if selector:
        try:
            await print_pdf(page, dest)
            if verify_pdf:
                verify_pdf(dest)
            return True, mode
        except Exception:
            if dest.exists():
                dest.unlink(missing_ok=True)
            try:
                await page.reload(wait_until="domcontentloaded")
            except Exception:
                pass

    try:
        await print_pdf(page, dest)
        if verify_pdf:
            verify_pdf(dest)
        return True, "full_print"
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return False, "failed"
