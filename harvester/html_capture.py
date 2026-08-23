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
    "[data-ph-bulletin-root]",
    # Prefer the tightest "just the post body" theme class first — many WP
    # themes append a "related posts" / "you might also like" widget with
    # full sibling <article> content *inside* the same outer <article>
    # wrapper (below .entry-content, but still a descendant of it), so
    # picking the generic "article" tag first can sweep up extra full
    # newsletter posts and wrongly balloon the page count (see ardara.ie —
    # real bulletin is ~2 short paragraphs, but selecting "article" printed
    # 8 pages because a prior week's full newsletter was bundled in too).
    ".entry-content",
    ".post-content",
    '[data-hook="post"]',  # Wix blog post body (Ballinascreen HTML weeks)
    ".inside-article",
    "article",
    ".content-area",
    ".site-content",
    '[role="main"]',
    "main",
    "div.col-sm-9",
    "section.information_section",
    ".information_section .container",
)

_PARISH_MESSENGER_SCRIPT = 'script[src*="theparishmessenger.com"]'

_WAIT_DYNAMIC_BULLETIN_JS = """
() => {
  const script = document.querySelector('script[src*="theparishmessenger.com"]');
  if (!script) return true;
  const boxes = [];
  const seen = new Set();
  for (const sel of ['.col-sm-9', 'section.information_section', '.information_section .container', '.container']) {
    const el = script.closest(sel);
    if (el && !seen.has(el)) {
      seen.add(el);
      boxes.push(el);
    }
  }
  if (script.parentElement && !seen.has(script.parentElement)) {
    boxes.push(script.parentElement);
  }
  return boxes.some((box) => {
    const text = (box.innerText || '').replace(/\\s+/g, ' ').trim();
    return text.length >= 300;
  });
}
"""

_MARK_MESSENGER_ROOT_JS = """
() => {
  const script = document.querySelector('script[src*="theparishmessenger.com"]');
  if (!script) return null;
  const candidates = [];
  const seen = new Set();
  for (const sel of ['.col-sm-9', 'section.information_section', '.information_section .container', '.container']) {
    const el = script.closest(sel);
    if (el && !seen.has(el)) {
      seen.add(el);
      candidates.push(el);
    }
  }
  if (script.parentElement && !seen.has(script.parentElement)) {
    candidates.push(script.parentElement);
  }
  let best = null;
  let bestLen = 0;
  for (const el of candidates) {
    const text = (el.innerText || '').replace(/\\s+/g, ' ').trim();
    if (text.length > bestLen) {
      bestLen = text.length;
      best = el;
    }
  }
  if (!best || bestLen < 200) return null;
  best.setAttribute('data-ph-bulletin-root', '1');
  return '[data-ph-bulletin-root]';
}
"""

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
    // Stop at the bulletin root — keep all of its descendants visible.
    if (node === root) return;
    for (const child of Array.from(node.children)) {
      // Keep walking ancestors of root (child.contains(root)), not descendants
      // (root.contains(child)) — the old check hid the parent wrapper and
      // printed a blank ~1KB PDF.
      if (child === root || child.contains(root)) {
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


async def wait_for_dynamic_bulletin(page: Page, timeout_ms: int = 20_000) -> bool:
    """Wait for Parish Messenger (and similar) embeds to inject bulletin HTML."""
    try:
        await page.wait_for_function(_WAIT_DYNAMIC_BULLETIN_JS, timeout=timeout_ms)
        return True
    except Exception:
        return False


_CONTENT_TEXT_LEN_JS = """
(selector) => {
  const els = Array.from(document.querySelectorAll(selector));
  let best = 0;
  for (const el of els) {
    const n = (el.innerText || '').replace(/\\s+/g, ' ').trim().length;
    if (n > best) best = n;
  }
  return best;
}
"""

_HIDE_BEST_MATCH_JS = """
(selector) => {
  const els = Array.from(document.querySelectorAll(selector));
  let best = null;
  let bestLen = 0;
  for (const el of els) {
    const n = (el.innerText || '').replace(/\\s+/g, ' ').trim().length;
    if (n > bestLen) {
      bestLen = n;
      best = el;
    }
  }
  if (!best || bestLen < 200) return false;
  best.setAttribute('data-ph-bulletin-root', '1');
  const root = best;
  const mark = (node) => {
    if (!node || node === document.documentElement) return;
    if (node === root) return;
    for (const child of Array.from(node.children)) {
      if (child === root || child.contains(root)) {
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


async def hide_non_content_chrome(page: Page) -> str | None:
    try:
        messenger_sel = await page.evaluate(_MARK_MESSENGER_ROOT_JS)
    except Exception:
        messenger_sel = None
    if messenger_sel:
        try:
            used = await page.evaluate(_HIDE_CHROME_JS, messenger_sel)
        except Exception:
            used = False
        if used:
            return messenger_sel

    for selector in CONTENT_SELECTORS:
        # Skip [data-ph-bulletin-root] here — only set by messenger / best-match below.
        if selector == "[data-ph-bulletin-root]":
            continue
        try:
            text_len = await page.evaluate(_CONTENT_TEXT_LEN_JS, selector)
        except Exception:
            text_len = 0
        if not isinstance(text_len, int) or text_len < 200:
            continue
        try:
            used = await page.evaluate(_HIDE_BEST_MATCH_JS, selector)
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
    skip_listing_nav: bool = False,
) -> tuple[bool, str]:
    """Returns (success, capture_mode)."""
    await wait_for_dynamic_bulletin(page, timeout_ms=max(wait_ms, 15_000))
    if not skip_listing_nav:
        navigated_to_article = await try_navigate_to_current_bulletin(page, target)
        if navigated_to_article:
            # The dynamic-bulletin wait above ran on the listing page; a
            # Parish-Messenger-style embed on the article page itself needs
            # its own wait or a slow embed can still be empty when we print.
            await wait_for_dynamic_bulletin(page, timeout_ms=max(wait_ms, 15_000))
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
