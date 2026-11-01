"""Reading checks against phrases seen on the printed page.

Green tests here mean the checker still sees the same result. They do not
mean vision OCR has been re-run. This PC has no vision API key.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import pymupdf

from ocr.fidelity import ocr_html_plain_text
from ocr.reading_check import (
    ANNAGRY_BANNED,
    ANNAGRY_MUST,
    GORT_MUST,
    NEWTOWN_MUST,
    score_reading,
)

ROOT = Path(__file__).resolve().parents[1]
RAPHOE = ROOT / "docs" / "parishes" / "raphoe"


def _pdf_text(name: str) -> str:
    path = RAPHOE / name
    doc = pymupdf.open(str(path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


class ReadingCheckTests(unittest.TestCase):
    def test_clean_annagry_phrases_pass(self) -> None:
        score = score_reading("\n".join(ANNAGRY_MUST), ANNAGRY_MUST, ANNAGRY_BANNED)
        self.assertTrue(score.ok)
        self.assertEqual(score.missing, [])
        self.assertEqual(score.banned_hits, [])

    def test_smash_tokens_fail_even_when_mass_names_are_present(self) -> None:
        text = "\n".join(ANNAGRY_MUST) + "\naodui Gallachsir"
        score = score_reading(text, ANNAGRY_MUST, ANNAGRY_BANNED)
        self.assertFalse(score.ok)
        self.assertEqual(score.banned_hits, ["aodui", "Gallachsir"])

    def test_annagry_pdf_text_layer_is_not_the_bulletin(self) -> None:
        score = score_reading(_pdf_text("annagryparish.pdf"), ANNAGRY_MUST, ANNAGRY_BANNED)
        self.assertFalse(score.ok)
        self.assertEqual(score.missing, ANNAGRY_MUST)

    def test_published_annagry_ocr_is_not_a_clean_reading(self) -> None:
        text = ocr_html_plain_text(RAPHOE / "annagryparish-ocr.html")
        score = score_reading(text, ANNAGRY_MUST, ANNAGRY_BANNED)
        self.assertFalse(score.ok)
        self.assertEqual(
            score.missing,
            ["30th Sunday of Ordinary Time", "Aifrinn na Seachtaine"],
        )
        self.assertEqual(score.banned_hits, ["aodui", "Gallachsir"])
        self.assertNotIn("Jimmy Boyle", score.missing)
        self.assertNotIn("Missa Pro Populo", score.missing)

    def test_gort_pdf_text_layer_is_not_the_bulletin(self) -> None:
        score = score_reading(_pdf_text("gort-a-choirce.pdf"), GORT_MUST)
        self.assertFalse(score.ok)
        self.assertEqual(score.missing, GORT_MUST)

    def test_published_gort_ocr_keeps_mass_list_and_drops_one_name(self) -> None:
        text = ocr_html_plain_text(RAPHOE / "gort-a-choirce-ocr.html")
        score = score_reading(text, GORT_MUST)
        self.assertFalse(score.ok)
        self.assertEqual(score.missing, ["Brid O Donnell"])

    def test_newtown_typed_pdf_and_ocr_keep_the_bulletin(self) -> None:
        for text in (
            _pdf_text("newtownkilleaparish.pdf"),
            ocr_html_plain_text(RAPHOE / "newtownkilleaparish-ocr.html"),
        ):
            score = score_reading(text, NEWTOWN_MUST)
            self.assertTrue(score.ok, score.missing)

    def test_published_kilbarron_ocr_is_only_the_parish_name(self) -> None:
        text = ocr_html_plain_text(RAPHOE / "kilbarron-ocr.html")
        words = text.split()
        self.assertLessEqual(len(words), 12)
        self.assertNotIn("aifrinn", text)
        self.assertNotIn("mass", text)

    def test_published_dunfanaghy_ocr_is_a_name_only_match(self) -> None:
        self.assertFalse((RAPHOE / "holy-cross-church.pdf").is_file())
        text = ocr_html_plain_text(RAPHOE / "holy-cross-church-ocr.html")
        score = score_reading(text, ["Mass of the Assumption"])
        self.assertTrue(score.name_only)
        self.assertFalse(score.ok)


if __name__ == "__main__":
    unittest.main()
