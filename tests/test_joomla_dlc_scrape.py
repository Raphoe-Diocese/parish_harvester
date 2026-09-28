from datetime import date
from harvester.replay import _score_http_scrape_pdf_hrefs

def test_joomla_dlc_php_scores_by_label_date():
    href = "https://www.kilmactigueparish.com/modules/download_gallery/dlc.php?file=247&id=1790354086&sid=140"
    scored = _score_http_scrape_pdf_hrefs(
        [href],
        date(2026, 9, 27),
        labels={href: "27th September 2026"},
    )
    assert scored == [(date(2026, 9, 27), href)]
