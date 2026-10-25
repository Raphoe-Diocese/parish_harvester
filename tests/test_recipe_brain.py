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


def test_cloyne_upload_is_the_forbidden_page_trick() -> None:
    hint = hint_for_url(
        "https://cloyneparish.com/wp-content/uploads/2026/10/"
        "Newsletter-18th-October-2026-29th-Sunday-in-Ordinary-Time.pdf"
    )
    assert hint is not None
    assert hint.key == "forbidden_page_browser_pdf"
    assert hint.site_type == "wp_json_newest_media"
    assert any("403" in line for line in hint.notes)
    assert any("pin" in line.lower() for line in hint.do_not)


def test_longford_pdf_folder_is_a_stored_step() -> None:
    hint = hint_for_url("https://longfordparish.com/pdf/270926.pdf")
    assert hint is not None
    assert hint.key == "predicted_dated_pdf"


def test_brain_steps_hold_the_hunt_lessons() -> None:
    from harvester.recipe_brain import brain_steps

    steps = brain_steps()
    assert len(steps) == 28
    by_id = {item["id"]: item["how"] for item in steps}
    assert "403" in by_id["sunday_named_upload"]
    assert "Crossmolina" in by_id["http_scrape_newest_pdf"]
    assert "Duilleog" in by_id["http_scrape_newest_pdf"]
    assert "Mohill" in by_id["print_html_newsletter"]
    assert "Carrigtwohill" in by_id["wp_json_newest_media"]


def test_facebook_is_not_probed() -> None:
    assert candidate_probe_urls("https://www.facebook.com/someparish/") == []


def test_parish_site_gets_current_newsletter_and_wp_json_probes() -> None:
    urls = candidate_probe_urls("https://exampleparish.ie/")
    joined = " ".join(u for u, _site, _key in urls)
    assert "/current-newsletter/" in joined
    assert "wp-json" in joined
    assert "/wp-content/uploads/" in joined
    assert "/pdf/" in joined


def test_sunday_guess_includes_cloyne_and_longford_names() -> None:
    from harvester.recipe_brain import _sunday_guess_probes

    urls = _sunday_guess_probes("https://cloyneparish.com", date(2026, 10, 18))
    joined = " ".join(url for url, _site, _key in urls)
    assert "Newsletter-18th-October-2026-29th-Sunday-in-Ordinary-Time.pdf" in joined
    assert "/wp-content/uploads/2026/10/" in joined
    assert "/pdf/181026.pdf" in joined
    assert "n18october2026.pdf" in joined


def test_bree_weekend_name_is_18_october_not_2018() -> None:
    from harvester.utils import extract_date_from_string

    url = "https://www.bree.ie/wp-content/uploads/2026/10/Newsletter-3742-Oct-17th-18th.pdf"
    assert extract_date_from_string(url) == date(2026, 10, 18)
    assert extract_date_from_string("Newsletter-3742-Oct-17th-18th.pdf") is None
    assert extract_date_from_string("Sunday-Sept-06-26.pdf") == date(2026, 9, 6)
    later = "https://www.bree.ie/wp-content/uploads/2026/10/Newsletter-3743-Oct-24th-25th_page-0001.jpg"
    assert extract_date_from_string(later) == date(2026, 10, 25)


def test_bree_page_photo_is_this_sunday_once_the_week_rolls() -> None:
    from harvester.utils import extract_date_from_string, image_newsletter_is_newer

    photo = (
        "https://www.bree.ie/wp-content/uploads/2026/10/"
        "Newsletter-3743-Oct-24th-25th_page-0001.jpg"
    )
    older = (
        "https://www.bree.ie/wp-content/uploads/2026/10/"
        "Newsletter-3742-Oct-17th-18th.pdf"
    )
    photo_date = extract_date_from_string(photo)
    pdf_date = extract_date_from_string(older)
    assert photo_date == date(2026, 10, 25)
    assert pdf_date == date(2026, 10, 18)
    assert image_newsletter_is_newer(photo_date, pdf_date, date(2026, 10, 18)) is False
    assert image_newsletter_is_newer(photo_date, pdf_date, date(2026, 10, 25)) is True


def test_horeswood_thirtieth_sunday_is_25_october() -> None:
    from harvester.bulletin_freshness import extract_bulletin_date

    url = (
        "https://horeswoodparish.ie/wp-content/uploads/2026/10/"
        "Thirtieth-Sunday-in-Ordinary-Time-2026-page-001-scaled.jpg"
    )
    assert extract_bulletin_date(url) == date(2026, 10, 25)


def test_ferns_parish_weekend_file_is_this_sunday_not_2018() -> None:
    from harvester.bulletin_freshness import extract_bulletin_date
    from harvester.utils import extract_date_from_string

    older = (
        "https://fernsparish.ie/wp-content/uploads/2026/10/"
        "October-17th-October-18th-2026.pdf"
    )
    current = (
        "https://fernsparish.ie/wp-content/uploads/2026/10/"
        "October-24th-October-25th-2026.pdf"
    )
    assert extract_date_from_string(older) == date(2026, 10, 18)
    assert extract_date_from_string(current) == date(2026, 10, 25)
    assert extract_bulletin_date(older) == date(2026, 10, 18)
    assert extract_bulletin_date(current) == date(2026, 10, 25)


def test_anspideal_irish_october_name_is_25_october() -> None:
    from harvester.bulletin_freshness import extract_bulletin_date
    from harvester.utils import extract_date_from_string

    url = (
        "https://cilleinde.ie/newsletters/2026/q4/"
        "30ú Domhnach A 25 Deireadh  Fómhair 2026.pdf"
    )
    assert extract_date_from_string(url) == date(2026, 10, 25)
    assert extract_bulletin_date(url) == date(2026, 10, 25)


def test_salthill_october_page_name_is_25_october() -> None:
    from harvester.bulletin_freshness import extract_bulletin_date
    from harvester.utils import yearless_slug_date

    named = (
        "https://salthillparish.ie/wp-content/uploads/2026/10/"
        "Newsletter-25th-Oct-1.pdf"
    )
    flipped = (
        "https://salthillparish.ie/wp-content/uploads/2026/10/"
        "Newsletter-Oct-25th-1.pdf"
    )
    sunday = date(2026, 10, 25)
    assert extract_bulletin_date(named) == sunday
    assert extract_bulletin_date(flipped) == sunday
    assert yearless_slug_date(named, 2026, near=sunday) == sunday
    assert yearless_slug_date(flipped, 2026, near=sunday) == sunday


def test_kilmyshall_october_name_keeps_the_th() -> None:
    from harvester.utils import extract_date_from_string, rewrite_date_url

    url = "https://kilmyshallparish.com/wp-content/uploads/2026/10/October-18th-2026.pdf"
    assert extract_date_from_string(url) == date(2026, 10, 18)
    assert rewrite_date_url(url, date(2026, 10, 18)).endswith("October-18th-2026.pdf")
    rolled = rewrite_date_url(url, date(2026, 10, 25))
    assert rolled.endswith("/2026/10/October-25th-2026.pdf")
    kept = rewrite_date_url(
        "https://tawnawillyparish.ie/wp-content/uploads/Sunday-Sept-06-26.pdf",
        date(2026, 9, 13),
    )
    assert kept.endswith("Sunday-Sept-13-26.pdf")


def test_clonard_keeps_the_scan_on_or_before_this_sunday() -> None:
    from harvester.utils import extract_date_from_string, newest_dated_url_on_or_before

    this_sunday = (
        "https://clonardparish.ie/wp-content/uploads/2026/10/"
        "SKM_C550i26101608340-scaled.jpg"
    )
    next_sheet = (
        "https://clonardparish.ie/wp-content/uploads/2026/10/"
        "SKM_C550i26102111250-scaled.jpg"
    )
    later_scan = (
        "https://clonardparish.ie/wp-content/uploads/2026/10/"
        "SKM_C550i26102308570-scaled.jpg"
    )
    assert extract_date_from_string(this_sunday) == date(2026, 10, 16)
    assert extract_date_from_string(next_sheet) == date(2026, 10, 21)
    chosen = newest_dated_url_on_or_before(
        [later_scan, next_sheet, this_sunday],
        date(2026, 10, 18),
    )
    assert chosen == this_sunday
    newsletter = (
        "https://clonardparish.ie/wp-content/uploads/2026/10/"
        "SKM_C550i26102308570-scaled.jpg"
    )
    lotto = (
        "https://clonardparish.ie/wp-content/uploads/2026/10/"
        "SKM_C550i26102120120-scaled.jpg"
    )
    assert extract_date_from_string(newsletter) == date(2026, 10, 23)
    assert newest_dated_url_on_or_before(
        [lotto, next_sheet, newsletter],
        date(2026, 10, 25),
    ) == newsletter


def test_st_senan_glued_name_is_18_october_and_rolls() -> None:
    from harvester.utils import extract_date_from_string, rewrite_date_url

    url = "https://stsenansenniscorthy.ie/wp-content/uploads/2026/10/n18october2026.pdf"
    assert extract_date_from_string(url) == date(2026, 10, 18)
    assert rewrite_date_url(url, date(2026, 10, 18)).endswith("n18october2026.pdf")
    rolled = rewrite_date_url(url, date(2026, 10, 25))
    assert rolled.endswith("/2026/10/n25october2026.pdf")


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
