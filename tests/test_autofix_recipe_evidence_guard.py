"""Regressions for unverified /news/ guesses overwriting trained recipes."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import autofix_recipes as autofix


def _sample_recipe() -> dict:
    return {
        "parish_key": "test_parish",
        "display_name": "Test parish",
        "start_url": "https://real-parish.example.com/bulletins/",
        "steps": [
            {
                "action": "download",
                "url": "https://files.example.net/wp-content/uploads/2026/10/11-October-2026.pdf",
            }
        ],
    }


def test_dated_pdf_autofixer_does_not_invent_a_news_url(tmp_path, monkeypatch):
    path = tmp_path / "test_parish.json"
    recipe = _sample_recipe()
    before = json.dumps(recipe)
    path.write_text(before, encoding="utf-8")
    monkeypatch.setattr(
        autofix, "_probe_pdf_links",
        lambda *_: (_ for _ in ()).throw(AssertionError("No web probe without a verified listing")),
    )

    assert autofix._fix_hardcoded_pdf_recipe(path, recipe) is False
    assert json.dumps(recipe) == before
    assert path.read_text(encoding="utf-8") == before


def test_invalid_verified_listing_cannot_replace_recipe(tmp_path, monkeypatch):
    path = tmp_path / "test_parish.json"
    recipe = _sample_recipe()
    recipe["verified_news_listing"] = "https://files.example.net/2026-11-15.pdf"
    monkeypatch.setattr(
        autofix, "_probe_pdf_links",
        lambda *_: (_ for _ in ()).throw(AssertionError("PDF itself is not a listing")),
    )
    assert autofix._fix_hardcoded_pdf_recipe(path, recipe) is False
    assert recipe["start_url"] == "https://real-parish.example.com/bulletins/"


def test_verified_listing_without_links_must_not_be_promoted(tmp_path, monkeypatch):
    path = tmp_path / "test_parish.json"
    recipe = _sample_recipe()
    recipe["verified_news_listing"] = "https://real-parish.example.com/newsletters/"
    monkeypatch.setattr(autofix, "_probe_pdf_links", lambda _: [])
    assert autofix._fix_hardcoded_pdf_recipe(path, recipe) is False
    assert "auto_fixed" not in recipe
    assert recipe["steps"][0]["url"].endswith("11-October-2026.pdf")


def test_operator_verified_listing_with_pdf_links_can_be_promoted(tmp_path, monkeypatch):
    path = tmp_path / "test_parish.json"
    recipe = _sample_recipe()
    verified = "https://real-parish.example.com/newsletters/"
    recipe["verified_news_listing"] = verified
    monkeypatch.setattr(
        autofix,
        "_probe_pdf_links",
        lambda url: ["https://real-parish.example.com/uploads/2026/11/newsletter.pdf"]
        if url == verified else [],
    )

    assert autofix._fix_hardcoded_pdf_recipe(path, recipe) is True
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["start_url"] == verified
    assert saved["steps"][0] == {"action": "goto", "url": verified}
    assert saved["steps"][1]["pick_strategy"] == "newest_dated"
    assert saved["steps"][2] == {"action": "download", "use_captured_url": True}
    assert saved["auto_fixed"] is True
