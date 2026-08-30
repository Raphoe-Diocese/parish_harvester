"""Find a URL/method that actually returns Portaferry PDF bytes."""
from __future__ import annotations

import asyncio
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

PAGE = "https://churchmedia.tv/st-patricks-church-2"
LIVE = "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf?cb=1787226064"
GUESSES = [
    LIVE,
    "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf",
    "https://cache.churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf",
    "https://cache.churchmedia.tv/s22osz.st-patricks-church-2.pdf",
    "https://cache.churchmedia.tv/131/s22osz.st-patricks-church-2.pdf",
    "https://cache.churchmedia.tv/131/newsletter/s22osz.st-patricks-church-2.pdf",
    "https://cache.churchmedia.tv/cache/131/s22osz.st-patricks-church-2.pdf",
    "https://churchmedia.tv/api/newsletter?slug=st-patricks-church-2",
    "https://churchmedia.tv/api/getNewsletter?slug=st-patricks-church-2",
]


def http_probe(url: str, accept: str = "*/*") -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": accept,
            "Referer": PAGE,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(64)
            return f"{resp.status} ct={resp.headers.get('content-type')} len={resp.headers.get('content-length')} magic={body[:12]!r}"
    except Exception as exc:
        return f"ERR {type(exc).__name__} {exc}"


async def main() -> None:
    print("HTTP guesses")
    for url in GUESSES:
        print(url, "->", http_probe(url, "application/pdf,application/octet-stream,*/*"))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        await page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        href = await page.locator("a:has-text('View Our Latest Newsletter')").first.get_attribute("href")
        print("href", href)

        # In-page fetch from the church page (same origin)
        result = await page.evaluate(
            """async (url) => {
              const r = await fetch(url, { credentials: 'include' });
              const buf = await r.arrayBuffer();
              const u8 = new Uint8Array(buf.slice(0, 16));
              return {
                status: r.status,
                ct: r.headers.get('content-type'),
                len: buf.byteLength,
                magic: Array.from(u8)
              };
            }""",
            href,
        )
        print("INPAGE_FETCH", result)
        if result and result.get("len", 0) > 1000 and result.get("magic", [0])[0] == 37:
            raw = await page.evaluate(
                """async (url) => {
                  const r = await fetch(url, { credentials: 'include' });
                  const buf = await r.arrayBuffer();
                  const u8 = new Uint8Array(buf);
                  let s = '';
                  const chunk = 0x8000;
                  for (let i = 0; i < u8.length; i += chunk) {
                    s += String.fromCharCode.apply(null, u8.subarray(i, i + chunk));
                  }
                  return btoa(s);
                }""",
                href,
            )
            data = __import__("base64").b64decode(raw)
            Path("_tmp_probe_portaferry.pdf").write_bytes(data)
            print("saved inpage pdf", len(data))

        # Try clicking with Ctrl to see download attribute
        handle = await page.locator("a:has-text('View Our Latest Newsletter')").first.element_handle()
        attrs = await page.evaluate(
            """el => ({download: el.getAttribute('download'), target: el.getAttribute('target'), rel: el.getAttribute('rel'), href: el.href})""",
            handle,
        )
        print("BTN_ATTRS", attrs)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
