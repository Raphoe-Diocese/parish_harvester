"""Roslea bulletin uses the official dated weekly PDF pattern rather than pinning 8 Nov."""
from datetime import date
import json
from pathlib import Path

from harvester.utils import predicted_dated_upload_urls


def test_roslea_predicted_weekly_finds_verified_15_november_pdf():
    recipe = json.loads((Path(__file__).resolve().parents[1] / "parishes/recipes/clogher/roslea.json").read_text(encoding="utf-8"))
    assert recipe["site_type"] == "predicted_dated_pdf"
    assert recipe["playbook_type"] == "dated_pdf_bulletin"
    assert recipe["steps"][0]["action"] == "download"
    assert recipe["weeks_back"] == 1
    urls = predicted_dated_upload_urls(recipe["example_url"], date(2026, 11, 15), weeks_back=0)
    assert "https://parishofroslea.com/wp-content/uploads/2026/11/Bulletin-Sunday-15th-November-2026.pdf" in urls
    assert urls[0].endswith("Bulletin-Sunday-15th-November-2026.pdf")


def test_roslea_rolls_forward_to_next_sunday_without_manual_repin():
    recipe = json.loads((Path(__file__).resolve().parents[1] / "parishes/recipes/clogher/roslea.json").read_text(encoding="utf-8"))
    urls = predicted_dated_upload_urls(recipe["example_url"], date(2026, 11, 22), weeks_back=0)
    assert urls[0].endswith("Bulletin-Sunday-22nd-November-2026.pdf")
