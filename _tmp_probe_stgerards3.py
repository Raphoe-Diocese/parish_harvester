"""Dump image markup and date-parse the St Gerard 16 Aug post."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from harvester.replay import (
    _extract_matching_hrefs,
    _extract_wp_upload_images,
    _fetch_bytes_with_retries,
)
from harvester.utils import extract_date_from_slug, extract_date_from_string, rewrite_date_url

POST = "https://stgerardsparish.org/sunday-bulletin-16th-august-2026/"
LISTING = "https://stgerardsparish.org/parish-news-events/"


def main() -> None:
    lines: list[str] = []

    def p(*a: object) -> None:
        s = " ".join(str(x) for x in a)
        lines.append(s)
        print(s)

    hit = _fetch_bytes_with_retries(
        POST, max_attempts=20, per_attempt_timeout_s=5.0, total_budget_s=40.0
    )
    assert hit, "no post"
    body, _ = hit
    html = body.decode("utf-8", "ignore")
    Path("_tmp_stgerards_16aug.html").write_text(html, encoding="utf-8")

    p("slug date", extract_date_from_slug("sunday-bulletin-16th-august-2026"))
    p("string date", extract_date_from_string("sunday-bulletin-16th-august-2026"))
    p(
        "rewrite 23rd",
        rewrite_date_url(
            "https://stgerardsparish.org/sunday-bulletin-16th-august-2026/",
            date(2026, 8, 23),
        ),
    )
    p(
        "rewrite parish 23rd",
        rewrite_date_url(
            "https://stgerardsparish.org/parish-bulletin-9th-august-2026/",
            date(2026, 8, 23),
        ),
    )

    imgs = _extract_wp_upload_images(html, 2026, 8, POST)
    p("extract_wp_upload_images", imgs)

    for m in re.finditer(r"<img\b[^>]{0,1200}>", html, re.I):
        tag = m.group(0)
        if "wp-content/uploads" in tag.lower():
            p("IMG", re.sub(r"\s+", " ", tag)[:500])

    srcsets = re.findall(r"""srcset=["']([^"']+)["']""", html, re.I)
    p("srcsets", len(srcsets))
    for s in srcsets[:8]:
        p(" SRCSET", s[:400])

    hrefs = _extract_matching_hrefs(
        html,
        POST,
        ["parish-bulletin-", "sunday-bulletin-", "bulletin"],
    )
    p("post matching hrefs", hrefs)

    listing = _fetch_bytes_with_retries(
        LISTING, max_attempts=20, per_attempt_timeout_s=5.0, total_budget_s=40.0
    )
    assert listing, "no listing"
    listing_html = listing[0].decode("utf-8", "ignore")
    cands = _extract_matching_hrefs(
        listing_html,
        LISTING,
        ["parish-bulletin-", "sunday-bulletin-", "bulletin"],
    )
    p("listing cands", cands)
    messages = _extract_matching_hrefs(listing_html, LISTING, ["sunday-message-"])
    p("sunday-message cands", messages[:8])

    Path("_tmp_probe_stgerards3_out.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
