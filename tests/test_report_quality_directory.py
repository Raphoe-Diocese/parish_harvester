"""A diocesan parish directory is not a weekly bulletin."""
import unittest

from harvester.report_quality import is_directory_html_result, reject_directory_downloads, reject_future_dated_downloads, reject_known_diocesan_admin_downloads


class ReportQualityTests(unittest.TestCase):
    def test_directory_html_capture_rejected_for_major_dioceses(self):
        urls = [
            "https://cashel-emly.ie/parish/anacarty-donohill/",
            "https://clonfertgalway.ie/parish/example/",
            "https://achonryelphin.ie/parish/castlerea/",
            "https://www.killaladiocese.org/parishes-ministries/parish-details/?parishID=10",
            "https://www.dioceseofmeath.ie/map-of-parishes",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertTrue(is_directory_html_result({"url": url, "file_type": "html_render"}))

    def test_real_downloadable_diocesan_pdf_is_not_blocked(self):
        self.assertFalse(is_directory_html_result({
            "url": "https://www.dioceseofkerry.ie/wp-content/uploads/2026/11/Newsletter-15-November-2026.pdf",
            "file_type": "pdf",
        }))

    def test_real_parish_news_article_is_not_blocked(self):
        self.assertFalse(is_directory_html_result({
            "url": "https://parishofroslea.com/parish-bulletin/bulletin-sunday-15th-november-2026/",
            "file_type": "html_render",
        }))


    def test_future_edition_rejected_from_prior_sunday(self):
        report = {
            "target_date": "2026-11-15",
            "downloaded": [
                {"parish": "next_week", "bulletin_date": "2026-11-22", "url": "https://example.com/22.pdf"},
                {"parish": "this_week", "bulletin_date": "2026-11-15", "url": "https://example.com/15.pdf"},
                {"parish": "weekday", "bulletin_date": "2026-11-13", "url": "https://example.com/13.pdf"},
                {"parish": "undated", "url": "https://example.com/latest.pdf"},
            ],
            "stale_rejected": [],
            "summary": {"downloaded": 4, "stale_rejected": 0},
        }
        self.assertEqual(reject_future_dated_downloads(report), 1)
        self.assertEqual(len(report["downloaded"]), 3)
        self.assertEqual(report["stale_rejected"][0]["reason"], "date_ahead_of_target")
        self.assertEqual(report["summary"]["downloaded"], 3)

    def test_repeated_diocesan_safeguarding_pdf_rejected(self):
        admin = "https://www.kandle.ie/wp-content/uploads/2026/02/Safeguarding-Sunday-Newsletter-2026.pdf"
        weekly = "https://www.kandle.ie/wp-content/uploads/2026/11/Parish-Newsletter-15th-November-2026.pdf"
        report = {
            "downloaded": [
                {"parish": "abbeyleix", "url": admin, "file_type": "pdf"},
                {"parish": "real", "url": weekly, "file_type": "pdf"},
            ],
            "failed": [],
            "summary": {"downloaded": 2, "failed": 0},
        }
        self.assertEqual(reject_known_diocesan_admin_downloads(report), 1)
        self.assertEqual(report["downloaded"][0]["parish"], "real")
        self.assertEqual(report["summary"]["downloaded"], 1)

    def test_reclassify_without_counting_fake_as_success(self):
        report = {
            "downloaded": [
                {"parish": "oldcastle", "display_name": "Oldcastle", "url": "https://www.dioceseofmeath.ie/map-of-parishes", "file_type": "html_render"},
                {"parish": "real", "display_name": "Real", "url": "https://example.com/newsletter.pdf", "file_type": "pdf"},
            ],
            "failed": [],
            "summary": {"downloaded": 2, "failed": 0},
        }
        self.assertEqual(reject_directory_downloads(report), 1)
        self.assertEqual([x["parish"] for x in report["downloaded"]], ["real"])
        self.assertEqual(report["failed"][0]["reason"], "directory_html_false_positive")
        self.assertEqual(report["summary"]["downloaded"], 1)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertEqual(reject_directory_downloads(report), 0)


if __name__ == "__main__":
    unittest.main()
