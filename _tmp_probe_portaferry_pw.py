"""Playwright probe: Portaferry churchmedia newsletter button."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

PAGE = "https://churchmedia.tv/st-patricks-church-2"
PINNED = "https://churchmedia.tv/newsletter/ovt7qm.st-patricks-church-2.pdf?cb=1786005944"
OUT_PDF = Path("_tmp_probe_portaferry.pdf")
OUT_TXT = Path("_tmp_probe_portaferry_pw_out.txt")


def log(lines: list[str], msg: str) -> None:
    print(msg, flush=True)
    lines.append(msg)


async def main() -> None:
    lines: list[str] = []
    log(lines, f"now={datetime.now(timezone.utc).isoformat()}")
    api_hits: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 900},
        )
        page = await context.new_page()

        def on_response(resp) -> None:
            url = resp.url
            if any(x in url.lower() for x in ("newsletter", "api", "graphql", "church", "st-patrick")):
                api_hits.append(f"{resp.status} {resp.request.method} {url[:240]}")

        page.on("response", on_response)

        log(lines, f"goto {PAGE}")
        try:
            await page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
        except Exception as exc:
            log(lines, f"goto_err {type(exc).__name__} {exc}")
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception as exc:
            log(lines, f"networkidle_err {type(exc).__name__} {exc}")
        await page.wait_for_timeout(4000)
        log(lines, f"url={page.url} title={await page.title()}")

        html = await page.content()
        log(lines, f"html_len={len(html)} newsletter_count={html.lower().count('newsletter')}")
        log(lines, f"has_view_text={'view our latest newsletter' in html.lower()}")

        anchors = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a,button,[role="button"]')).map(el => ({
              tag: el.tagName,
              text: ((el.innerText || el.textContent || '') + '').replace(/\\s+/g, ' ').trim().slice(0, 120),
              href: el.getAttribute('href') || '',
              cls: (el.className || '').toString().slice(0, 80)
            })).filter(x => (x.text + x.href).toLowerCase().includes('news') || (x.text + x.href).toLowerCase().includes('pdf') || (x.text + x.href).toLowerCase().includes('bulletin'))"""
        )
        log(lines, f"NEWS_ELS {json.dumps(anchors, indent=2)}")

        all_a = await page.evaluate(
            """() => Array.from(document.querySelectorAll('a[href]')).map(a => ({
              text: ((a.innerText || '') + '').replace(/\\s+/g, ' ').trim().slice(0, 80),
              href: a.href
            }))"""
        )
        log(lines, f"ALL_A_COUNT {len(all_a)}")
        for item in all_a[:40]:
            log(lines, f"  A {item}")

        # Try Playwright request after cookies
        for label, url in [("PINNED_REQ", PINNED), ("BARE_NEWSLETTER", "https://churchmedia.tv/newsletter/ovt7qm.st-patricks-church-2.pdf")]:
            try:
                resp = await page.request.get(url, timeout=30000)
                body = await resp.body()
                log(lines, f"{label} status={resp.status} ct={resp.headers.get('content-type')} len={len(body)} magic={body[:8]!r}")
            except Exception as exc:
                log(lines, f"{label} ERR {type(exc).__name__} {exc}")

        loc = page.get_by_text("View Our Latest Newsletter", exact=False)
        count = await loc.count()
        log(lines, f"text_locator_count={count}")
        if count:
            try:
                async with page.expect_download(timeout=20000) as dl_info:
                    await loc.first.click(timeout=15000)
                download = await dl_info.value
                path = await download.path()
                suggested = download.suggested_filename
                src = download.url
                log(lines, f"DOWNLOAD suggested={suggested} url={src} path={path}")
                if path:
                    data = Path(path).read_bytes()
                    OUT_PDF.write_bytes(data)
                    log(lines, f"saved pdf len={len(data)} magic={data[:8]!r}")
                    text = data.decode("latin-1", "replace")
                    dates = re.findall(r"D:(\d{8,14})", text)
                    log(lines, f"PDF_DATES {dates[:20]}")
                    strings = [
                        s for s in re.findall(r"\(([^)]{4,80})\)", text)
                        if re.search(r"20\d\d|June|July|August|Aug|Sunday|Mass|Portaferry", s, re.I)
                    ]
                    log(lines, f"PDF_STRINGS {strings[:40]}")
            except Exception as exc:
                log(lines, f"CLICK_ERR {type(exc).__name__} {exc}")
                log(lines, f"after_click_url={page.url}")

        log(lines, "API_HITS")
        for hit in api_hits[:80]:
            log(lines, f"  {hit}")

        await browser.close()

    OUT_TXT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
