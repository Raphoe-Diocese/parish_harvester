"""Probe Portaferry churchmedia.tv newsletter button and PDF date."""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
PAGE = "https://churchmedia.tv/st-patricks-church-2"
PINNED = "https://churchmedia.tv/newsletter/ovt7qm.st-patricks-church-2.pdf?cb=1786005944"
OUT = Path("_tmp_probe_portaferry_out.txt")


def fetch(url: str) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Referer": PAGE, "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, dict(resp.headers), resp.read()


def main() -> None:
    lines: list[str] = []

    def log(msg: str) -> None:
        print(msg)
        lines.append(msg)

    log(f"now={datetime.now(timezone.utc).isoformat()}")
    log(f"pinned_cb_ts={datetime.fromtimestamp(1786005944, timezone.utc).isoformat()}")

    for label, url in [("PAGE", PAGE), ("PINNED", PINNED)]:
        log("=" * 80)
        log(f"{label} {url}")
        try:
            status, headers, body = fetch(url)
        except Exception as exc:
            log(f"ERR {type(exc).__name__} {exc}")
            continue
        ct = headers.get("Content-Type", "")
        log(f"status={status} ct={ct} len={len(body)} lm={headers.get('Last-Modified')} cd={headers.get('Content-Disposition')}")
        if body[:8] == b"%PDF-1.":
            log(f"PDF_MAGIC {body[:8]!r}")
            text = body.decode("latin-1", "replace")
            dates = re.findall(r"D:(\d{8,14})", text)
            log(f"PDF_DATES {dates[:20]}")
            strings = re.findall(r"\(([^)]{4,80})\)", text)
            interesting = [
                s for s in strings
                if re.search(r"20\d\d|June|July|August|Aug|Sunday|Mass|Portaferry|newsletter", s, re.I)
            ]
            log(f"PDF_STRINGS {interesting[:40]}")
            Path("_tmp_probe_portaferry.pdf").write_bytes(body)
            log("wrote _tmp_probe_portaferry.pdf")
            continue
        text = body.decode("utf-8", "replace")
        log(f"title={re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)}")
        for pat in ("newsletter", "View Our Latest", "pdf", "st-patricks-church-2", "ovt7qm", "churchmedia"):
            log(f"count {pat!r}={text.lower().count(pat.lower())}")
        pdfs = re.findall(r"https?://[^\s\"']+\.pdf[^\s\"']*", text, re.I)
        log(f"PDF_URLS {pdfs[:30]}")
        hrefs = re.findall(r'href=["\']([^"\']+)["\']', text, re.I)
        news = [h for h in hrefs if "newsletter" in h.lower() or h.lower().endswith(".pdf")]
        log(f"NEWS_HREFS {news[:30]}")
        scripts = re.findall(r'src=["\']([^"\']+)["\']', text, re.I)
        log(f"SCRIPTS {scripts[:30]}")
        apis = re.findall(r"https?://[^\s\"']*(api|graphql|newsletter)[^\s\"']*", text, re.I)
        log(f"APIISH {apis[:40]}")
        # dump a small html sample around newsletter
        idx = text.lower().find("newsletter")
        if idx >= 0:
            log(f"AROUND_NEWSLETTER {text[max(0, idx-200):idx+400]!r}")

    OUT.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
