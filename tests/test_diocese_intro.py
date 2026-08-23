from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import PyPDF2
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas

from harvester.diocese_intro import (
    NEVER_PUBLISH_HEADING,
    NEVER_PUBLISH_NOTE,
    REPO_ROOT,
    build_diocese_week_summary,
    render_diocese_intro_html,
    share_url,
    welcome_line,
)
from harvester.stitcher import stitch_mega_pdf
from ocr.generate_bulletin_pages import render_bulletin_viewer_shell


class DioceseIntroTests(unittest.TestCase):
    def test_welcome_uses_diocese_name_without_inventing_contacts(self) -> None:
        self.assertEqual(welcome_line("Raphoe Diocese"), "Welcome to the Diocese of Raphoe.")
        self.assertEqual(
            welcome_line("Down and Connor"),
            "Welcome to the Diocese of Down & Connor.",
        )
        html = render_diocese_intro_html(
            build_diocese_week_summary(
                "raphoe",
                diocese_display_name="Raphoe Diocese",
                recipes_root=Path(tempfile.gettempdir()) / "no-such-recipes",
                parish_status={},
            )
        )
        self.assertIn("Welcome to the Diocese of Raphoe.", html)
        self.assertNotIn("Bishop", html)
        self.assertNotIn("@", html)
        self.assertNotIn("074", html)

    def test_counts_and_names_come_from_status_after_alias_collapse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            recipes = Path(tmp) / "raphoe"
            recipes.mkdir()
            (recipes / "drumholm-parish.json").write_text(
                json.dumps(
                    {
                        "parish_key": "drumholm-parish",
                        "display_name": "Drumholm",
                        "start_url": "https://example.com/drumholm.pdf",
                    }
                ),
                encoding="utf-8",
            )
            (recipes / "ballintra.json").write_text(
                json.dumps(
                    {
                        "parish_key": "ballintra",
                        "display_name": "Ballintra Parish",
                        "skip": True,
                        "alias_of": "drumholm-parish",
                    }
                ),
                encoding="utf-8",
            )
            (recipes / "carrigart.json").write_text(
                json.dumps(
                    {
                        "parish_key": "carrigart",
                        "display_name": "Mevagh",
                        "skip": True,
                        "start_url": "https://www.facebook.com/example",
                    }
                ),
                encoding="utf-8",
            )
            (recipes / "stranorlarparish.json").write_text(
                json.dumps(
                    {
                        "parish_key": "stranorlarparish",
                        "display_name": "Stranolar",
                        "start_url": "https://www.stranorlarparish.ie/newsletter/",
                    }
                ),
                encoding="utf-8",
            )
            status = {
                "drumholm-parish": {"outcome": "ok", "display_name": "Drumholm"},
                "ballintra": {"outcome": "skipped", "display_name": "Ballintra Parish"},
                "carrigart": {
                    "outcome": "skipped",
                    "display_name": "Mevagh",
                    "url": "https://www.facebook.com/example",
                },
                "stranorlarparish": {
                    "outcome": "stale",
                    "display_name": "Stranolar",
                    "url": "https://www.stranorlarparish.ie/newsletter/",
                },
            }
            summary = build_diocese_week_summary(
                "raphoe",
                diocese_display_name="Raphoe Diocese",
                recipes_root=Path(tmp),
                parish_status=status,
            )
            self.assertEqual(summary.total, 3)
            self.assertEqual(summary.found, 1)
            self.assertEqual([item.name for item in summary.never_publish], ["Mevagh"])
            self.assertEqual([item.name for item in summary.stale], ["Stranolar"])
            html = render_diocese_intro_html(summary)
            self.assertIn("1 of 3 parish bulletins were found", html)
            self.assertIn("Mevagh", html)
            self.assertIn("Stranolar", html)
            self.assertIn(NEVER_PUBLISH_HEADING, html)
            self.assertIn(NEVER_PUBLISH_NOTE, html)
            self.assertNotIn("do not publish a downloadable bulletin online", html)
            self.assertNotIn("last known link", html)
            self.assertIn("https://www.facebook.com/example", html)
            self.assertIn("https://www.stranorlarparish.ie/newsletter/", html)
            self.assertNotIn("Ballintra Parish", html)
            self.assertNotIn("20 of 32", html)

    def test_viewer_shell_puts_intro_and_az_jump_above_the_boxes(self) -> None:
        html = render_bulletin_viewer_shell(
            page_title="Raphoe Diocese Collated Bulletin",
            diocese_label="RAPHOE",
            display_name="Raphoe Diocese",
            headline="Raphoe Collated Bulletin",
            meta_line="This week's bulletin — 23/08/2026.",
            back_href="../../index.html",
            back_label="← Back to home",
            pdf_href="/mega_pdf/raphoe_mega_bulletin.pdf",
            pdf_download_href="/mega_pdf/raphoe_mega_bulletin.pdf",
            pdf_standalone_href="/mega_pdf/raphoe_mega_bulletin.pdf",
            ocr_standalone_href="../../bulletins/raphoe-2026-08-23-ocr.html",
            ocr_fragment='<header class="ocr-parish-masthead" data-parish-name="Drumholm (Ballintra)"><h2 class="ocr-parish-name">Drumholm (Ballintra)</h2></header>',
            parish_section_heading="RAPHOE Parishes with Working Bulletin Links",
            parish_links_html='<ul class="parish-grid"><li class="parish-item">Drumholm (Ballintra)</li></ul>',
            intro_html='<section class="diocese-intro"><p class="intro-count">This week\'s collated bulletin: 1 of 2 parish bulletins were found.</p></section>',
            az_names=["Drumholm (Ballintra)", "Ardara"],
            parish_page_index={"Drumholm (Ballintra)": 8, "Ardara": 2},
        )
        self.assertIn("diocese-intro", html)
        self.assertIn("1 of 2 parish bulletins were found", html)
        self.assertLess(html.index("diocese-intro"), html.index("Bulletin — Original PDF Version"))
        self.assertIn('class="az-jump"', html)
        self.assertIn("Jump to a parish", html)
        self.assertIn('data-az-target="pdf"', html)
        self.assertIn('data-az-target="ocr"', html)
        self.assertIn("Drumholm (Ballintra)", html)
        self.assertIn("Ardara", html)
        self.assertIn('id="parish-page-index"', html)
        self.assertIn("parishPressScrollPdfToPage", html)
        self.assertIn("data-az-target", html)
        self.assertNotIn("Missing &amp; Online-Only", html)
        self.assertNotIn("Missing & Online-Only", html)

    def test_share_url_prefers_proved_facebook_and_does_not_invent(self) -> None:
        self.assertEqual(share_url({}, {}), "")
        self.assertEqual(
            share_url(
                {"url": "https://www.kilbarron.org/bulletin"},
                {"start_url": "https://www.facebook.com/kilbarronparishpastoralcouncil"},
            ),
            "https://www.facebook.com/kilbarronparishpastoralcouncil",
        )
        summary = build_diocese_week_summary(
            "raphoe",
            diocese_display_name="Raphoe Diocese",
            recipes_root=REPO_ROOT / "parishes" / "recipes",
        )
        html = render_diocese_intro_html(summary)
        self.assertIn(NEVER_PUBLISH_HEADING, html)
        self.assertIn(NEVER_PUBLISH_NOTE, html)
        self.assertNotIn("do not publish a downloadable bulletin online", html)
        gweedore = [item for item in summary.never_publish if "Gaoth Dobhair" in item.name]
        self.assertEqual(len(gweedore), 1)
        self.assertEqual(
            gweedore[0].url,
            "https://www.facebook.com/paroisteghaothdobhair",
        )
        self.assertIn("https://www.facebook.com/paroisteghaothdobhair", html)
        kilbarron = [item for item in summary.never_publish if item.name == "Kilbarron"]
        self.assertEqual(len(kilbarron), 1)
        self.assertIn("facebook.com/kilbarronparishpastoralcouncil", kilbarron[0].url)
        mevagh = [item for item in summary.never_publish if item.name == "Mevagh"]
        self.assertEqual(len(mevagh), 1)
        self.assertIn("facebook.com", mevagh[0].url)
        for item in summary.never_publish + summary.stale:
            if item.url:
                self.assertTrue(item.url.startswith(("http://", "https://")), item.name)


class StitcherMissingPageTests(unittest.TestCase):
    def _pdf(self, path: Path, text: str) -> None:
        buf_path = path
        c = rl_canvas.Canvas(str(buf_path), pagesize=A4)
        c.drawString(72, 750, text)
        c.showPage()
        c.save()

    def test_stitcher_skips_ballintra_alias_and_omits_missing_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current"
            bulletins = root / "bulletins"
            current.mkdir()
            bulletins.mkdir()
            pdf = current / "drumholm-parish.pdf"
            self._pdf(pdf, "Drumholm parish bulletin for Sunday 23 August 2026.")
            results = [
                SimpleNamespace(
                    key="drumholm-parish",
                    display_name="Drumholm",
                    status="ok",
                    url="https://example.com/drumholm.pdf",
                    file_path=pdf,
                    file_type="pdf",
                    is_stale=False,
                    is_fallback=False,
                ),
                SimpleNamespace(
                    key="ballintra",
                    display_name="Ballintra Parish",
                    status="skipped",
                    url="https://www.facebook.com/donalquinn1959",
                    file_path=None,
                    is_stale=False,
                    is_fallback=False,
                ),
                SimpleNamespace(
                    key="carrigart",
                    display_name="Mevagh",
                    status="skipped",
                    url="https://www.facebook.com/profile.php?id=1",
                    file_path=None,
                    is_stale=False,
                    is_fallback=False,
                ),
            ]
            stitch_mega_pdf(results, current, bulletins, date(2026, 8, 23))
            mega = bulletins / "all_bulletins_2026-08-23.pdf"
            self.assertTrue(mega.exists())
            reader = PyPDF2.PdfReader(str(mega))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            self.assertNotIn("Missing & Online-Only", text)
            self.assertNotIn("Ballintra Parish", text)
            self.assertIn("Drumholm (Ballintra)", text)
            index = json.loads(
                (bulletins / "all_bulletins_2026-08-23.pages.json").read_text(encoding="utf-8")
            )
            self.assertIn("drumholm-parish", index["parishes"])
            self.assertEqual(
                index["parishes"]["drumholm-parish"]["display_name"],
                "Drumholm (Ballintra)",
            )
            self.assertNotIn("ballintra", index["parishes"])


if __name__ == "__main__":
    unittest.main()
