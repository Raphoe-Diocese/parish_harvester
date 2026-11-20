"""The newsletter is Killenaule's *featured* image, not its event posters.

The 15 November 2026 post's visible featured picture is
Newsletter-Sunday-15th-November-1140x641.jpg. Older weeks used
Newsletter-8th-November.jpg, so predicted filename patterns are insufficient.
"""
from __future__ import annotations

import asyncio
import io
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from PyPDF2 import PdfReader

from harvester.replay import _try_wp_json_newest_post_images, _extract_post_page_images

BASE = "https://killenaule.net"
CATEGORY = BASE + "/category/newsletter/"
POST15 = BASE + "/parish-newsletter-sunday-15th-november-2026/"
POST8 = BASE + "/parish-newsletter-sunday-8th-november-2026/"
ORIGINAL = BASE + "/wp-content/uploads/2026/11/Newsletter-Sunday-15th-November.jpg"
THUMB = BASE + "/wp-content/uploads/2026/11/Newsletter-Sunday-15th-November-1140x641.jpg"
SALE = BASE + "/wp-content/uploads/2026/10/Sale-of-Work-724x1024.jpg"
COFFEE = BASE + "/wp-content/uploads/2026/11/Coffee-Morning-Nov-26-722x1024.jpeg"


def jpeg_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (1140, 641), "white").save(output, format="JPEG")
    return output.getvalue()


def article(with_newsletter: bool) -> str:
    # Simulate the source's featured image, plus two unrelated event posters.
    featured = f'<img class="featured" src="{THUMB}">' if with_newsletter else ""
    return (f"<html><main><h1>Parish Newsletter Sunday 15th November 2026</h1>"
            f"{featured}<h2>Parish Newsletter</h2>"
            f'<img src="{SALE}"><img src="{COFFEE}"></main></html>')


def fetcher_factory(*, latest: str = POST15, include_newsletter: bool = True,
                    allow_original: bool = True, allow_thumbnail: bool = True):
    seen: list[str] = []
    post_record = {"link": latest, "slug": latest.rstrip("/").split("/")[-1],
                   "title": {"rendered": "Parish Newsletter Sunday 15th November 2026"}}
    def fake_fetch(url: str, **kwargs):
        seen.append(url)
        if "/wp-json/wp/v2/posts?" in url:
            return json.dumps([post_record]).encode(), {"content-type": "application/json"}
        if url == latest:
            return article(include_newsletter).encode(), {"content-type": "text/html"}
        if url == ORIGINAL and allow_original:
            return jpeg_bytes(), {"content-type": "image/jpeg"}
        if url == THUMB and allow_thumbnail:
            return jpeg_bytes(), {"content-type": "image/jpeg"}
        return None
    return fake_fetch, seen


def collect(tmp_path: Path, fake_fetch, *, target: date = date(2026,11,15)):
    dest = tmp_path / "killenaule.pdf"
    with patch("harvester.replay._fetch_bytes_with_retries", side_effect=fake_fetch):
        result = asyncio.run(_try_wp_json_newest_post_images(
            CATEGORY, dest,
            slug_patterns=["parish-newsletter-"],
            target_date=target,
            example_post_url=None,
            weeks_back=0, image_count=1, href_patterns=["Newsletter-"],
            featured_image_fallback=True, require_target_post_week=True,
        ))
    return result, dest


def test_featured_image_thumbnail_yields_full_size_original(tmp_path):
    fake, requests = fetcher_factory()
    found, dest = collect(tmp_path, fake)
    assert found == (POST15, "image_to_pdf")
    assert ORIGINAL in requests
    assert THUMB not in requests
    assert SALE not in requests and COFFEE not in requests
    assert len(PdfReader(str(dest)).pages) == 1


def test_uses_featured_image_thumbnail_if_original_missing(tmp_path):
    fake, requests = fetcher_factory(allow_original=False)
    found, dest = collect(tmp_path, fake)
    assert found == (POST15, "image_to_pdf")
    assert ORIGINAL in requests and THUMB in requests
    assert SALE not in requests and COFFEE not in requests
    assert len(PdfReader(str(dest)).pages) == 1


def test_event_posters_are_not_accepted_as_newsletter(tmp_path):
    fake, requests = fetcher_factory(include_newsletter=False)
    found, dest = collect(tmp_path, fake)
    assert found is None
    assert not dest.exists()
    assert SALE not in requests and COFFEE not in requests


def test_prior_sundays_are_not_substituted_for_this_sunday(tmp_path):
    fake, requests = fetcher_factory(latest=POST8)
    found, dest = collect(tmp_path, fake, target=date(2026,11,15))
    assert found is None
    assert not dest.exists()
    assert POST8 not in requests


def test_original_extractor_correctly_skips_featured_resized_image():
    images = _extract_post_page_images(article(True), POST15)
    assert THUMB not in images
    assert ORIGINAL not in images
