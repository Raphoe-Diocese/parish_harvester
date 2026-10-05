import json
from datetime import date
from pathlib import Path

from harvester.recipe_brain import (
    candidate_probe_urls,
    hint_for_url,
    remember_win,
    scan_skipped,
)


def test_mcn_camera_url_is_mcn_live() -> None:
    hint = hint_for_url(
        "https://mcn.live/Camera/our-lady-of-perpetual-succour-glenfinn"
    )
    assert hint is not None
    assert hint.site_type == "mcn_live_parish_page"
    assert hint.confidence == "high"


def test_mayo_listing_is_scrape_not_guid_pin() -> None:
    hint = hint_for_url(
        "https://www.mayo.ie/en-ie/parish-newsletters/belmullet-parish-newsletters"
    )
    assert hint is not None
    assert hint.site_type == "http_scrape_newest_pdf"
    assert any("GUID" in line for line in hint.do_not)


def test_churchmedia_is_api_newsletter() -> None:
    hint = hint_for_url("https://churchmedia.tv/st-patricks-church-2")
    assert hint is not None
    assert hint.site_type == "churchmedia_newsletter"


def test_churchservices_is_pointer_only() -> None:
    hint = hint_for_url("https://www.churchservices.tv/letterkenny")
    assert hint is not None
    assert hint.site_type == "link_only"
    assert hint.confidence == "low"


def test_current_newsletter_is_permanent_redirect() -> None:
    hint = hint_for_url("https://www.naasparish.ie/current-newsletter/")
    assert hint is not None
    assert hint.site_type == "permanent_redirect_document"


def test_unknown_host_has_no_invented_hint() -> None:
    assert hint_for_url("https://example.invalid/parish") is None


def test_facebook_is_not_probed() -> None:
    assert candidate_probe_urls("https://www.facebook.com/someparish/") == []


def test_parish_site_gets_current_newsletter_and_wp_json_probes() -> None:
    urls = candidate_probe_urls("https://exampleparish.ie/")
    joined = " ".join(u for u, _site, _key in urls)
    assert "/current-newsletter/" in joined
    assert "wp-json" in joined


def test_remember_win_writes_parish_into_site_patterns(tmp_path: Path) -> None:
    path = tmp_path / "site_patterns.json"
    remember_win(
        "current-newsletter+direct_download",
        "naas",
        "Proved /current-newsletter/ GET 200.",
        patterns_path=path,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    row = data["patterns"]["current-newsletter+direct_download"]
    assert row["success_count"] == 1
    assert "naas" in row["example_parishes"]


def test_scan_skips_aliases_and_does_not_unskip_without_proof(tmp_path: Path) -> None:
    recipes = tmp_path / "recipes" / "derry"
    recipes.mkdir(parents=True)
    (recipes / "alias.json").write_text(
        json.dumps(
            {
                "parish_key": "alias",
                "skip": True,
                "alias_of": "realparish",
                "start_url": "https://exampleparish.ie/",
            }
        ),
        encoding="utf-8",
    )
    (recipes / "facebook.json").write_text(
        json.dumps(
            {
                "parish_key": "facebook",
                "skip": True,
                "start_url": "https://www.facebook.com/parish/",
            }
        ),
        encoding="utf-8",
    )
    wins = scan_skipped(
        recipes_dir=tmp_path / "recipes",
        patterns_path=tmp_path / "site_patterns.json",
        cursor_path=tmp_path / "cursor.json",
        limit=10,
        apply=True,
        today=date(2026, 10, 5),
    )
    assert wins == []
    leftover = json.loads((recipes / "facebook.json").read_text(encoding="utf-8"))
    assert leftover["skip"] is True
