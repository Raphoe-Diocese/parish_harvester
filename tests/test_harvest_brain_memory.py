"""Harvest memory stores a strategy only for this Sunday's ok bulletin."""

import json
from datetime import date
from pathlib import Path

from harvester.recipe_brain import remember_harvest_results

TARGET = date(2026, 11, 8)
THIS_WEEK_FILE = (
    "https://www.memorywin.ie/wp-content/uploads/2026/11/"
    "newsletter-8th-November-2026.pdf"
)
STALE_FILE = (
    "https://www.memorywin.ie/wp-content/uploads/2026/11/"
    "newsletter-1st-November-2026.pdf"
)
LISTING = "https://www.memorywin.ie/current-newsletter/"
FILENAME = "newsletter-8th-November-2026.pdf"


class _Result:
    def __init__(
        self,
        key: str,
        url: str,
        *,
        status: str = "ok",
        is_stale: bool = False,
        bulletin_date: str | None = None,
    ):
        self.key = key
        self.status = status
        self.is_stale = is_stale
        self.url = url
        self.file_type = "pdf"
        self.file_path = None
        self.diagnosis = {}
        self.bulletin_date = bulletin_date


def _store(folder: Path, results, parishes: Path | None = None) -> list[str]:
    if parishes is None:
        parishes = folder / "empty-parishes"
        parishes.mkdir(parents=True, exist_ok=True)
    return remember_harvest_results(
        results,
        TARGET,
        memory_path=folder / "newsletter_brain.json",
        patterns_path=folder / "site_patterns.json",
        parishes_dir=parishes,
    )


def _write_recipe(parishes: Path) -> Path:
    folder = parishes / "recipes" / "kildare"
    folder.mkdir(parents=True)
    path = folder / "memorywin.json"
    path.write_text(
        json.dumps(
            {
                "parish_key": "memorywin",
                "site_type": "permanent_redirect_document",
                "start_url": LISTING,
                "skip": True,
                "reason": "Harvest memory must not edit this recipe.",
                "steps": [{"action": "download", "url": LISTING}],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_ok_target_sunday_is_remembered_once(tmp_path: Path) -> None:
    parishes = tmp_path / "parishes"
    recipe = _write_recipe(parishes)
    original = recipe.read_text(encoding="utf-8")
    result = _Result("memorywin", THIS_WEEK_FILE)
    folder = tmp_path / "memory"

    assert _store(folder, [result], parishes) == ["memorywin"]
    assert _store(folder, [result], parishes) == ["memorywin"]

    memory = json.loads((folder / "newsletter_brain.json").read_text(encoding="utf-8"))
    patterns = json.loads((folder / "site_patterns.json").read_text(encoding="utf-8"))
    assert len(memory["wins"]) == 1
    win = memory["wins"][0]
    assert win["parish_key"] == "memorywin"
    assert win["strategy_id"] == "permanent_redirect_document"
    assert win["url"] == LISTING
    assert win["bulletin_date"] == "2026-11-08"
    assert win["verdict"] == "fresh"
    row = patterns["patterns"]["permanent_redirect_document+/current-newsletter/"]
    assert row["page_type"] == "permanent_redirect_document"
    assert row["example_parishes"] == ["memorywin"]
    assert row["success_count"] == 1
    stored = (folder / "newsletter_brain.json").read_text(encoding="utf-8")
    stored += (folder / "site_patterns.json").read_text(encoding="utf-8")
    assert FILENAME not in stored
    assert "/2026/11/" not in stored
    assert recipe.read_text(encoding="utf-8") == original
    assert not (parishes / "parish_status.json").exists()


def test_dated_filename_stores_the_listing_pattern(tmp_path: Path) -> None:
    folder = tmp_path / "fileonly"
    remembered = _store(
        folder,
        [
            {
                "outcome": "ok",
                "parish_key": "fileonly",
                "site_type": "http_scrape_newest_pdf",
                "url": (
                    "https://fileonly.ie/wp-content/uploads/2026/11/"
                    "newsletter-8th-November-2026.pdf"
                ),
            }
        ],
    )
    assert remembered == ["fileonly"]
    memory = json.loads((folder / "newsletter_brain.json").read_text(encoding="utf-8"))
    patterns = json.loads((folder / "site_patterns.json").read_text(encoding="utf-8"))
    assert memory["wins"][0]["url"] == "https://fileonly.ie/wp-content/uploads/"
    assert memory["wins"][0]["strategy_id"] == "http_scrape_newest_pdf"
    row = patterns["patterns"]["http_scrape_newest_pdf+/wp-content/uploads/"]
    assert row["example_parishes"] == ["fileonly"]
    stored = (folder / "newsletter_brain.json").read_text(encoding="utf-8")
    stored += (folder / "site_patterns.json").read_text(encoding="utf-8")
    assert FILENAME not in stored
    assert "/2026/11/" not in stored


def test_same_parish_and_strategy_is_stored_once(tmp_path: Path) -> None:
    from harvester.newsletter_brain import Win, remember

    path = tmp_path / "newsletter_brain.json"
    remember(
        Win(
            strategy_id="http_scrape_newest_pdf",
            url="https://parish.ie/bulletins/",
            parish_key="memorywin",
            verdict="fresh",
            bulletin_date="2026-11-08",
            file_kind="pdf",
        ),
        path,
    )
    remember(
        Win(
            strategy_id="http_scrape_newest_pdf",
            url=THIS_WEEK_FILE,
            parish_key="memorywin",
            verdict="fresh",
            bulletin_date="2026-11-08",
            file_kind="pdf",
        ),
        path,
    )
    remember(
        Win(
            strategy_id="wp_json_newest_media",
            url="https://parish.ie/newsletters/",
            parish_key="memorywin",
            verdict="fresh",
            bulletin_date="2026-11-08",
            file_kind="pdf",
        ),
        path,
    )
    wins = json.loads(path.read_text(encoding="utf-8"))["wins"]
    assert [item["strategy_id"] for item in wins] == [
        "http_scrape_newest_pdf",
        "wp_json_newest_media",
    ]
    assert wins[0]["url"] == "https://parish.ie/bulletins/"
    assert FILENAME not in path.read_text(encoding="utf-8")


def _assert_not_stored(folder: Path, results) -> None:
    assert _store(folder, results) == []
    assert not (folder / "newsletter_brain.json").exists()
    assert not (folder / "site_patterns.json").exists()


def test_stale_date_is_not_remembered(tmp_path: Path) -> None:
    _assert_not_stored(
        tmp_path / "last-sunday",
        [
            {
                "outcome": "ok",
                "parish_key": "memorywin",
                "site_type": "permanent_redirect_document",
                "listing_url": LISTING,
                "url": STALE_FILE,
            }
        ],
    )
    _assert_not_stored(
        tmp_path / "saturday",
        [
            {
                "outcome": "ok",
                "parish_key": "memorywin",
                "site_type": "http_scrape_newest_pdf",
                "listing_url": "https://parish.ie/bulletins/",
                "url": "https://parish.ie/bulletins/",
                "bulletin_date": "2026-11-07",
            }
        ],
    )
    _assert_not_stored(
        tmp_path / "marked-stale",
        [
            {
                "outcome": "ok",
                "is_stale": True,
                "parish_key": "memorywin",
                "site_type": "http_scrape_newest_pdf",
                "listing_url": "https://parish.ie/bulletins/",
                "url": THIS_WEEK_FILE,
                "bulletin_date": "2026-11-08",
            }
        ],
    )


def test_miss_and_facebook_are_not_remembered(tmp_path: Path) -> None:
    _assert_not_stored(
        tmp_path / "miss",
        [
            {
                "outcome": "failed",
                "parish_key": "memorywin",
                "site_type": "http_scrape_newest_pdf",
                "listing_url": "https://parish.ie/bulletins/",
                "url": THIS_WEEK_FILE,
                "bulletin_date": "2026-11-08",
            }
        ],
    )
    _assert_not_stored(
        tmp_path / "no-date",
        [
            {
                "outcome": "ok",
                "parish_key": "memorywin",
                "site_type": "http_scrape_newest_pdf",
                "listing_url": "https://parish.ie/bulletins/",
                "url": "https://parish.ie/bulletins/",
            }
        ],
    )
    _assert_not_stored(
        tmp_path / "facebook",
        [
            {
                "outcome": "ok",
                "parish_key": "memorywin",
                "site_type": "http_scrape_newest_pdf",
                "listing_url": "https://www.facebook.com/memorywin/",
                "url": THIS_WEEK_FILE,
                "bulletin_date": "2026-11-08",
            }
        ],
    )
    _assert_not_stored(
        tmp_path / "facebook-type",
        [
            _Result(
                "memorywin",
                "https://www.facebook.com/memorywin/posts/1",
                bulletin_date="2026-11-08",
            )
        ],
    )
    _assert_not_stored(
        tmp_path / "facebook-strategy",
        [
            {
                "outcome": "ok",
                "parish_key": "memorywin",
                "site_type": "facebook_link_only",
                "listing_url": "https://parish.ie/bulletins/",
                "url": "https://parish.ie/bulletins/",
                "bulletin_date": "2026-11-08",
            }
        ],
    )


def test_harvest_calls_memory_after_results_are_final() -> None:
    source = Path("main.py").read_text(encoding="utf-8")
    assert "remember_harvest_results(all_results, target)" in source
