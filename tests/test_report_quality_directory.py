"""A diocesan parish directory is not a weekly bulletin."""
import unittest

from harvester.report_quality import is_directory_html_result, reject_directory_downloads


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
