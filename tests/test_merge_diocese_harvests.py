from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_merge_diocese_harvests_script_puts_repo_on_sys_path() -> None:
    text = (REPO / "scripts" / "merge_diocese_harvests.py").read_text(encoding="utf-8")
    assert "sys.path.insert" in text
    assert "parent.parent" in text
    # Stale referee gate imports freshness helpers (not bare FetchResult stubs).
    assert "from harvester.bulletin_freshness import" in text
    assert "build_mega_stitch_results" in text
    assert "reclassify_stale_downloaded_in_report" in text
