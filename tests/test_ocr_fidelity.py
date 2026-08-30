from __future__ import annotations

import unittest

from ocr.fidelity import missing_phrases, normalize_for_compare


class OcrFidelityTests(unittest.TestCase):
    def test_reports_pdf_notice_missing_from_vision_ocr(self) -> None:
        pdf = (
            "Coffee morning Saturday 22nd August. "
            "Church Car Park will be closed immediately after 12noon Mass on Sunday 23rd August. "
            "Enda Hill, R.I.P. The family of the late Edna Hill would like to express their thanks."
        )
        ocr = "Coffee morning Saturday 2nd August. Dorothy McKinley died recently."
        gaps = missing_phrases(pdf, ocr, window=6)
        joined = " ".join(gaps)
        self.assertIn("church car park", joined)
        self.assertIn("edna hill", joined)

    def test_ok_when_ocr_has_the_pdf_words(self) -> None:
        text = "Church Car Park will be closed immediately after 12noon Mass on Sunday 23rd August"
        self.assertEqual(missing_phrases(text, text, window=6), [])

    def test_normalize_strips_tags(self) -> None:
        self.assertEqual(
            normalize_for_compare("<p>Enda Hill, R.I.P.</p>"),
            "enda hill r i p",
        )

    def test_parish_name_glue_is_not_a_gap(self) -> None:
        pdf = "12noon Mass on Sunday 23rd August Ballycastle We pray for the dead."
        ocr = (
            "Ballycastle. Church Car Park closed after 12noon Mass on Sunday 23rd August. "
            "We pray for the dead."
        )
        self.assertEqual(missing_phrases(pdf, ocr, window=6), [])


if __name__ == "__main__":
    unittest.main()
