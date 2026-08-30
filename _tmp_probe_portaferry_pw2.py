"""Click Portaferry newsletter and inspect viewer / real PDF bytes."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

PAGE = "https://churchmedia.tv/st-patricks-church-2"
LIVE = "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf?cb=1787226064"
OUT = Path("_tmp_probe_portaferry_pw2_out.txt")


async def main() -> None:
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()
        pdf_like: list[str] = []

        def on_response(resp) -> None:
            url = resp.url
            ct = (resp.headers.get("content-type") or "").lower()
            if "pdf" in ct or url.lower().endswith(".pdf") or "/newsletter/" in url.lower() or "application/octet" in ct:
                pdf_like.append(f"{resp.status} {ct} {len(url)} {url[:220]}")

        page.on("response", on_response)
        await page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)

        href = await page.locator("a:has-text('View Our Latest Newsletter')").first.get_attribute("href")
        log(f"href={href}")

        await page.locator("a:has-text('View Our Latest Newsletter')").first.click()
        await page.wait_for_timeout(4000)
        log(f"after_click url={page.url} pages={len(context.pages)}")
        for p in context.pages:
            log(f"  tab {p.url} title={await p.title()}")
            html = await p.content()
            log(f"  html_len={len(html)} iframe={html.lower().count('iframe')} embed={html.lower().count('embed')}")
            iframes = re.findall(r"<iframe[^>]+>", html, re.I)
            for fr in iframes[:10]:
                log(f"  IFRAME {fr[:300]}")

        log("PDF_LIKE after click")
        for hit in pdf_like:
            log(f"  {hit}")

        # Navigate directly to newsletter URL
        page2 = await context.new_page()
        page2.on("response", on_response)
        try:
            await page2.goto(LIVE, wait_until="domcontentloaded", timeout=30000)
        except Exception as exc:
            log(f"goto_live_err {type(exc).__name__} {exc}")
        await page2.wait_for_timeout(4000)
        log(f"live_tab url={page2.url} title={await page2.title()}")
        html = await page2.content()
        log(f"live html_len={len(html)}")
        # look for object/embed/canvas/pdfjs
        for pat in ("pdf", "iframe", "embed", "object", "canvas", "viewer", "s22osz"):
            log(f"  count {pat}={html.lower().count(pat)}")
        # evaluate computed newsletter srcs
        srcs = await page2.evaluate(
            """() => ({
              iframes: Array.from(document.querySelectorAll('iframe,embed,object,source')).map(el => ({
                tag: el.tagName, src: el.src || el.getAttribute('src') || el.getAttribute('data') || ''
              })),
              url: location.href
            })"""
        )
        log(f"EMBEDS {srcs}")

        log("PDF_LIKE all")
        for hit in pdf_like:
            log(f"  {hit}")

        await browser.close()
    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
