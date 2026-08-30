"""Download live Portaferry churchmedia PDF via browser navigation and date it."""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright
from PyPDF2 import PdfReader

LIVE = "https://churchmedia.tv/newsletter/s22osz.st-patricks-church-2.pdf?cb=1787226064"
OUT = Path("_tmp_probe_portaferry.pdf")
TXT = Path("_tmp_probe_portaferry_pdf_out.txt")


async def main() -> None:
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        lines.append(msg)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chrome")
        page = await browser.new_page()
        response = await page.goto(LIVE, wait_until="domcontentloaded", timeout=60000)
        log(f"status={response.status if response else None} ct={response.headers.get('content-type') if response else None}")
        body = await response.body() if response else b""
        log(f"len={len(body)} magic={body[:8]!r}")
        if body[:4] == b"%PDF":
            OUT.write_bytes(body)
            log(f"wrote {OUT}")
        await browser.close()

    if OUT.exists() and OUT.read_bytes()[:4] == b"%PDF":
        reader = PdfReader(str(OUT))
        log(f"pages={len(reader.pages)}")
        meta = reader.metadata
        log(f"meta={meta}")
        text = ""
        for i, page in enumerate(reader.pages[:3]):
            chunk = page.extract_text() or ""
            text += chunk + "\n"
            log(f"--- page {i+1} ---")
            log(chunk[:1500])
        dates = re.findall(
            r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{1,2}\s+\w+\s+20\d{2}|20\d{2}-\d{2}-\d{2}|(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s+\d{1,2}\s+\w+)",
            text,
            re.I,
        )
        log(f"DATES {dates[:30]}")
        for word in ("June", "July", "August", "Aug", "16th", "17th", "20th", "23rd", "Portaferry", "Ballyphilip"):
            log(f"has {word}={word.lower() in text.lower()}")

    TXT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
