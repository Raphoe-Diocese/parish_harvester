from harvester.recipe_brain import hint_for_url


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
