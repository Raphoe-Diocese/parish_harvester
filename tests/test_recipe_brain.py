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


def test_theparishioner_listing_is_joomla_pdf() -> None:
    hint = hint_for_url("https://theparishioner.ie/newsletter")
    assert hint is not None
    assert hint.site_type == "http_scrape_newest_pdf"
    assert hint.pattern_key == "joomla_images_newsletter+direct_download"
    assert any("pin" in line.lower() for line in hint.do_not)
    onefaith = hint_for_url("https://onefaith.ie/newsletter")
    assert onefaith is not None
    assert onefaith.key == "joomla_images_newsletter"


def test_arklow_homepage_date_is_in_brackets() -> None:
    hint = hint_for_url("https://www.arklowparish.ie/")
    assert hint is not None
    assert hint.key == "homepage_bracket_date"
    assert hint.site_type == "http_scrape_newest_pdf"


def test_armagh_yearless_filename_stays_a_listing() -> None:
    hint = hint_for_url("https://armaghparish.net/parish-bulletin/")
    assert hint is not None
    assert hint.key == "yearless_month_pdf"
    assert any("September" in line for line in hint.do_not)


def test_adamstown_listing_stays_stale() -> None:
    hint = hint_for_url("http://saintabbans.com/?page_id=21")
    assert hint is not None
    assert hint.key == "html_listing_still_stale"
    assert any("pin" in line.lower() for line in hint.do_not)


def test_ashbourne_403_is_not_a_missing_file() -> None:
    hint = hint_for_url("https://ashbourneparish.ie/newsletters/")
    assert hint is not None
    assert hint.site_type == "wp_json_newest_media"
    assert any("403" in line for line in hint.notes)


def test_birr_bodyke_and_kerry_listings() -> None:
    birr = hint_for_url("https://www.stbrendansbirr.ie/newsletter/")
    assert birr is not None and birr.key == "ddmmyyyy_listing_pdf"
    bodyke = hint_for_url("https://www.bodyketuamgraneyparish.ie/newsletter/")
    assert bodyke is not None and bodyke.key == "spelled_month_listing_pdf"
    kerry = hint_for_url("https://www.dioceseofkerry.ie/parish/baile-an-fheirtearaigh/")
    assert kerry is not None and kerry.key == "kerry_card_yyyymmdd_pdf"
    assert any("Facebook" in line for line in kerry.do_not)


def test_bree_and_booterstown_use_the_media_library() -> None:
    bree = hint_for_url("https://www.bree.ie/")
    assert bree is not None and bree.site_type == "wp_json_newest_media"
    assert any("pin" in line.lower() for line in bree.do_not)
    boot = hint_for_url("https://booterstownparish.ie/")
    assert boot is not None and boot.key == "booterstown_sunday_pdf"
    assert any("wp-json-only" in line for line in boot.do_not)
    assert any("Sun-25-October" in line for line in boot.notes)


def test_listing_pdfs_proved_31_october() -> None:
    borris = hint_for_url("https://borrisokaneparish.ie/")
    assert borris is not None and borris.site_type == "http_scrape_newest_pdf"
    assert any("404" in line for line in borris.notes)
    together = hint_for_url("https://parishestogether.ie/notices/newsletters")
    assert together is not None and together.key == "prefix_ddmmyy_pdf"
    assert any("prefix" in line.lower() for line in together.do_not)
    bantry = hint_for_url("https://bantryfamilyofparishes.ie/notices")
    assert bantry is not None and bantry.key == "bantry_family_pdf"
    assert any("schull" in line for line in bantry.do_not)
    castle = hint_for_url("https://www.castleconnellparish.ie/newsletter/")
    assert castle is not None and castle.key == "spelled_month_listing_pdf"
    church = hint_for_url("https://churchtownparish.com/newsletter/")
    assert church is not None and church.key == "iso_newsletter_pdf"
    assert any("01/11/2026" in line or "2026-11-01" in line for line in church.notes)
    clare = hint_for_url("https://www.clarecastleballyeaparish.ie/newsletter/")
    assert clare is not None and clare.key == "spelled_month_listing_pdf"
    corofin = hint_for_url("https://imeallboirne.ie/newsletter/")
    assert corofin is not None and any("25th-October-2026" in line for line in corofin.notes)
    doora = hint_for_url("https://www.doorabarefieldparish.ie/newsletter/")
    assert doora is not None and doora.key == "link_text_undated_pdf"
    assert any("1st November" in line for line in doora.notes)
    durrow = hint_for_url("https://www.durrow.ie/category/newsletter/")
    assert durrow is not None and durrow.site_type == "http_scrape_newest_images"
    doonbeg = hint_for_url("https://doonbegparish.com/newsletter")
    assert doonbeg is not None and any("card" in line.lower() for line in doonbeg.do_not)
    ennis = hint_for_url("https://www.ennisparish.com/newsletter/")
    assert ennis is not None and any("25th-October.pdf" in line for line in ennis.notes)
    assert any("1stB-November" in line for line in ennis.do_not)
    inagh = hint_for_url("https://inaghkilnamonaparish.ie/newsletter/")
    assert inagh is not None and any("25th-October-2026" in line for line in inagh.notes)
    kilb = hint_for_url("https://kilbrittainparish.ie/bulletin")
    assert kilb is not None and kilb.key == "yy_mm_d_pdf"
    assert any("26-11-1" in line for line in kilb.notes)


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
    assert any("disable_stale_rescrape_fallback" in line for line in hint.notes)
    assert any("homepage" in line.lower() for line in hint.do_not)


def test_unskip_permanent_redirect_disables_homepage_rescrape(tmp_path: Path) -> None:
    from harvester.recipe_brain import _unskip_recipe

    recipe_path = tmp_path / "bellaghyparish.json"
    recipe_path.write_text(
        json.dumps(
            {
                "parish_key": "bellaghyparish",
                "skip": True,
                "start_url": "https://bellaghyparish.com/",
                "steps": [],
            }
        ),
        encoding="utf-8",
    )
    _unskip_recipe(
        {"_path": str(recipe_path)},
        site_type="permanent_redirect_document",
        start_url="https://bellaghyparish.com/current-newsletter/",
        note="test win",
    )
    data = json.loads(recipe_path.read_text(encoding="utf-8"))
    assert data["disable_stale_rescrape_fallback"] is True
    assert data["site_type"] == "permanent_redirect_document"
    assert any("homepage" in line.lower() for line in data.get("do_not") or [])


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
    assert len(steps) == 30
    by_id = {item["id"]: item["how"] for item in steps}
    assert "403" in by_id["sunday_named_upload"]
    assert "Crossmolina" in by_id["http_scrape_newest_pdf"]
    assert "Duilleog" in by_id["http_scrape_newest_pdf"]
    assert "Mohill" in by_id["print_html_newsletter"]
    assert "Carrigtwohill" in by_id["wp_json_newest_media"]
    assert "Current Newsletter" in by_id["parish_messenger"]
    assert "090820" in by_id["parish_messenger"]
    assert "Banagher" in by_id["joomla_dropfiles"]
    assert "disable_stale_rescrape_fallback" in by_id["permanent_bulletin_pdf"]
    assert "max_bulletin_pages" in by_id["oneweb_docx"]
    assert "2026/10/25" in by_id["clonleigh_homepage_not_category"]


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


def test_blanchardstown_iso_and_day_span_takes_sunday() -> None:
    from harvester.bulletin_freshness import check_bulletin_freshness, extract_bulletin_date
    from harvester.utils import extract_date_from_string

    name = "newsletter-2026-10-18and25_new.pdf"
    url = (
        "https://www.blanchardstownparish.ie/wp-content/uploads/newsletters/2026/10/"
        + name
    )
    assert extract_date_from_string(name) == date(2026, 10, 25)
    assert extract_bulletin_date(url) == date(2026, 10, 25)
    verdict = check_bulletin_freshness(url, date(2026, 10, 25))
    assert verdict.status == "fresh"


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


def test_annagry_251025_in_the_2026_folder_is_25_october() -> None:
    from harvester.bulletin_freshness import extract_bulletin_date
    from harvester.utils import extract_date_from_string

    current = "https://annagryparish.ie/wp-content/uploads/2026/10/251025.pdf"
    last_week = "https://annagryparish.ie/wp-content/uploads/2026/10/181026.pdf"
    real_2025 = "https://annagryparish.ie/wp-content/uploads/2025/10/251025.pdf"
    assert extract_date_from_string(current) == date(2026, 10, 25)
    assert extract_bulletin_date(current) == date(2026, 10, 25)
    assert extract_bulletin_date(last_week) == date(2026, 10, 18)
    assert extract_bulletin_date(real_2025) == date(2025, 10, 25)


def test_tawnawilly_dot_after_oct_is_25_october() -> None:
    from harvester.utils import extract_date_from_string, month_first_sunday_upload_urls

    url = "https://tawnawillyparish.ie/wp-content/uploads/Sunday-25th-Oct.-26.pdf"
    assert extract_date_from_string(url) == date(2026, 10, 25)
    guesses = month_first_sunday_upload_urls(
        "https://tawnawillyparish.ie/wp-content/uploads/Sunday-27th-Sept-26.pdf",
        date(2026, 10, 25),
    )
    assert any(item.endswith("Sunday-25th-Oct.-26.pdf") for item in guesses)


def test_week_audit_stops_the_book_when_last_week_was_kept() -> None:
    from datetime import date as day
    from harvester.week_audit import book_is_blocked

    class Row:
        def __init__(self, key: str, url: str, *, is_stale: bool = False, status: str = "ok") -> None:
            self.key = key
            self.url = url
            self.is_stale = is_stale
            self.status = status

    old_url = "https://annagryparish.ie/wp-content/uploads/2026/10/181026.pdf"
    current_url = "https://annagryparish.ie/wp-content/uploads/2026/10/251025.pdf"
    old = book_is_blocked([Row("annagryparish", old_url)], day(2026, 10, 25))
    assert old
    already_out = book_is_blocked(
        [Row("annagryparish", old_url, is_stale=True)],
        day(2026, 10, 25),
    )
    assert already_out == []
    current = book_is_blocked(
        [Row("annagryparish", current_url)],
        day(2026, 10, 25),
    )
    assert current == []


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
