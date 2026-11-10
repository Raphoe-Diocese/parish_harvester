from __future__ import annotations

import io
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from ocr import parish_pages
from ocr.parish_pages import _write_text


def _make_pdf(num_pages: int) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i in range(1, num_pages + 1):
        c.drawString(72, 700, f"Test page {i}")
        c.showPage()
    c.save()
    return buf.getvalue()


_RAW_FRAGMENT = """
<p class="page-label">Page 1</p>
<h2 class="b-title">Index</h2>
<p>Welcome to the diocese bulletin.</p>
<hr>
<p class="page-label">Page 2</p>
<p>Ardara Parish<br>
http://ardara.ie</p>
<p>Sunday mass at 10am. Recently deceased: John Smith.</p>
<hr>
<p class="page-label">Page 3</p>
<p>Annagry<br>
https://annagryparish.ie/newsletter-2/</p>
<p>Mass at 11am.</p>
"""


class LoadOkParishesTests(unittest.TestCase):
    def test_filters_by_diocese_and_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status_path = Path(tmpdir) / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "url": "http://ardara.ie",
                            },
                            "annagryparish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Annagry",
                                "url": "https://annagryparish.ie/newsletter-2/",
                            },
                            "broken-parish": {
                                "outcome": "failed",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Broken",
                            },
                            "other-diocese-parish": {
                                "outcome": "ok",
                                "diocese": "Derry Diocese",
                                "display_name": "Other",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            parishes = parish_pages.load_ok_parishes("raphoe", parish_status_path=status_path)
            keys = [p.key for p in parishes]
            self.assertEqual(keys, ["annagryparish", "ardara"])  # sorted A-Z by display name

    def test_missing_file_returns_empty(self) -> None:
        parishes = parish_pages.load_ok_parishes("raphoe", parish_status_path=Path("/nonexistent/path.json"))
        self.assertEqual(parishes, [])


class SlicePdfPagesTests(unittest.TestCase):
    def test_slices_expected_page_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mega.pdf"
            pdf_path.write_bytes(_make_pdf(4))
            sliced = parish_pages.slice_pdf_pages(pdf_path, 2, 3)
            self.assertIsNotNone(sliced)
            reader = PdfReader(io.BytesIO(sliced))
            self.assertEqual(len(reader.pages), 2)

    def test_clamps_out_of_range_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "mega.pdf"
            pdf_path.write_bytes(_make_pdf(2))
            sliced = parish_pages.slice_pdf_pages(pdf_path, 5, 9)
            reader = PdfReader(io.BytesIO(sliced))
            self.assertEqual(len(reader.pages), 1)

    def test_missing_pdf_returns_none(self) -> None:
        self.assertIsNone(parish_pages.slice_pdf_pages(Path("/nonexistent/mega.pdf"), 1, 1))


class LoadMegaPageIndexTests(unittest.TestCase):
    """The OCR workflow OCRs a mega PDF staged in a temp folder, so the
    sibling ``*.pages.json`` lookup found nothing and every parish fell back
    to name-banner matching. Image-only banner pages never match, which left
    Annagry's page blank."""

    def _index(self, path: Path, pages: int = 1) -> None:
        path.write_text(
            json.dumps(
                {
                    "parishes": {
                        "annagryparish": {
                            "display_name": "Annagry",
                            "start_page": 1,
                            "end_page": pages,
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

    def test_falls_back_to_docs_copy_of_the_same_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_mega = root / "docs" / "mega_pdf"
            docs_mega.mkdir(parents=True)
            body = _make_pdf(3)
            staged = root / "staged" / "raphoe_mega_bulletin.pdf"
            staged.parent.mkdir()
            staged.write_bytes(body)
            (docs_mega / "raphoe_mega_bulletin.pdf").write_bytes(body)
            self._index(docs_mega / "raphoe_mega_bulletin.pages.json")

            with unittest.mock.patch.object(parish_pages, "DOCS_DIR", root / "docs"):
                self.assertEqual(
                    parish_pages.load_mega_page_index(staged),
                    {"annagryparish": (1, 1)},
                )

    def test_ignores_docs_index_for_a_different_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs_mega = root / "docs" / "mega_pdf"
            docs_mega.mkdir(parents=True)
            staged = root / "staged" / "raphoe_mega_bulletin.pdf"
            staged.parent.mkdir()
            staged.write_bytes(_make_pdf(2))
            (docs_mega / "raphoe_mega_bulletin.pdf").write_bytes(_make_pdf(9))
            self._index(docs_mega / "raphoe_mega_bulletin.pages.json", pages=9)

            with unittest.mock.patch.object(parish_pages, "DOCS_DIR", root / "docs"):
                self.assertEqual(parish_pages.load_mega_page_index(staged), {})


class WriteParishPagesForDioceseTests(unittest.TestCase):
    def test_writes_pages_with_sliced_pdf_and_ocr_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "url": "http://ardara.ie",
                            },
                            "annagryparish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Annagry",
                                "url": "https://annagryparish.ie/newsletter-2/",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pdf_path = root / "raphoe_mega_bulletin.pdf"
            pdf_path.write_bytes(_make_pdf(3))
            out_dir = root / "docs" / "parishes" / "raphoe"

            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-09",
                pdf_path,
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )

            self.assertEqual(set(written), {"ardara", "annagryparish"})

            ardara_html = (out_dir / "ardara.html").read_text(encoding="utf-8")
            self.assertIn("Ardara Parish Bulletin", ardara_html)
            self.assertIn("Sunday mass at 10am", ardara_html)
            self.assertIn("Recently deceased", ardara_html)
            self.assertIn("Annagry", ardara_html)  # appears in the "other parishes" grid
            self.assertIn('href="../../dioceses/raphoe/index.html"', ardara_html)
            self.assertIn('href="ardara.pdf"', ardara_html)
            self.assertTrue((out_dir / "ardara.pdf").exists())
            reader = PdfReader(str(out_dir / "ardara.pdf"))
            self.assertEqual(len(reader.pages), 1)  # just page 2 of the mega PDF

            annagry_html = (out_dir / "annagryparish.html").read_text(encoding="utf-8")
            self.assertIn("Mass at 11am", annagry_html)
            self.assertIn('href="annagryparish.pdf"', annagry_html)

            self.assertTrue((out_dir / "ardara-ocr.html").exists())
            self.assertTrue((out_dir / "ardara-pdf.html").exists())

    def test_no_ok_parishes_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(json.dumps({"parishes": {}}), encoding="utf-8")
            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-09",
                root / "missing.pdf",
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=root / "docs" / "parishes" / "raphoe",
                parish_status_path=status_path,
            )
            self.assertEqual(written, [])

    def test_falls_back_gracefully_when_parish_not_found_in_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "unmatched-parish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Totally Unmatched Parish Name",
                                "url": "http://example.com",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pdf_path = root / "raphoe_mega_bulletin.pdf"
            pdf_path.write_bytes(_make_pdf(3))
            out_dir = root / "docs" / "parishes" / "raphoe"

            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-09",
                pdf_path,
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )
            self.assertEqual(written, ["unmatched-parish"])
            html_out = (out_dir / "unmatched-parish.html").read_text(encoding="utf-8")
            self.assertIn("could not be cut from the collated bulletin", html_out)
            self.assertIn("Totally Unmatched Parish Name", html_out)
            self.assertIn('class="stale-note"', html_out)
            self.assertNotIn(
                "Exact PDF pages for this parish could not be auto-detected this week, so this links to the full diocese bulletin instead.",
                html_out,
            )
            self.assertFalse((out_dir / "unmatched-parish.pdf").exists())
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertTrue(status["parishes"]["unmatched-parish"]["slice_missing"])
            self.assertEqual(status["parishes"]["unmatched-parish"]["outcome"], "ok")

    def test_skips_holy_cross_even_when_marked_ok(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "holy-cross-church": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Dunfanaghy",
                            },
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            keys = [p.key for p in parish_pages.load_ok_parishes("raphoe", parish_status_path=status_path)]
            self.assertEqual(keys, ["ardara"])
            self.assertNotIn("holy-cross-church", keys)

    def test_page_index_writes_non_empty_parish_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "url": "http://ardara.ie",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pdf_path = root / "raphoe_mega_bulletin.pdf"
            pdf_path.write_bytes(_make_pdf(3))
            (root / "raphoe_mega_bulletin.pages.json").write_text(
                json.dumps(
                    {
                        "date": "2026-08-16",
                        "pdf": "raphoe_mega_bulletin.pdf",
                        "parishes": {"ardara": {"display_name": "Ardara", "start_page": 2, "end_page": 3}},
                    }
                ),
                encoding="utf-8",
            )
            out_dir = root / "docs" / "parishes" / "raphoe"
            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-16",
                pdf_path,
                _RAW_FRAGMENT,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )
            self.assertEqual(written, ["ardara"])
            parish_pdf = out_dir / "ardara.pdf"
            self.assertTrue(parish_pdf.exists())
            self.assertGreater(parish_pdf.stat().st_size, 32)
            reader = PdfReader(str(parish_pdf))
            self.assertEqual(len(reader.pages), 2)
            html_out = (out_dir / "ardara.html").read_text(encoding="utf-8")
            self.assertIn("Sunday mass at 10am", html_out)
            self.assertIn('href="ardara.pdf"', html_out)


class PreferEmbeddedParishPagesTests(unittest.TestCase):
    def test_prefers_embedded_slice_text_over_incomplete_vision(self) -> None:
        rich = (
            "MASS TIMES and parish notices for this week.\n"
            "Vigil Mass on Saturday 22nd August at 6.30pm in St Patrick's.\n"
            "Please do not park in the Church Car Park during funerals this week.\n"
            "Recently deceased: please keep the family in your prayers this Sunday.\n"
            "Community notices continue below with weekday Masses and contacts."
        )
        vision_fragment = """
<p class="page-label">Page 1</p>
<p>Ardara Parish<br>
http://ardara.ie</p>
<p>Vigil Mass on Saturday 2nd August at 6.30pm.</p>
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "url": "http://ardara.ie",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            buf = io.BytesIO()
            c = canvas.Canvas(buf)
            y = 760
            for line in rich.splitlines():
                c.drawString(72, y, line)
                y -= 16
            c.showPage()
            c.save()
            pdf_path = root / "raphoe_mega_bulletin.pdf"
            pdf_path.write_bytes(buf.getvalue())
            (root / "raphoe_mega_bulletin.pages.json").write_text(
                json.dumps(
                    {
                        "date": "2026-08-23",
                        "pdf": "raphoe_mega_bulletin.pdf",
                        "parishes": {"ardara": {"display_name": "Ardara", "start_page": 1, "end_page": 1}},
                    }
                ),
                encoding="utf-8",
            )
            out_dir = root / "docs" / "parishes" / "raphoe"
            written = parish_pages.write_parish_pages_for_diocese(
                "raphoe",
                "2026-08-23",
                pdf_path,
                vision_fragment,
                diocese_pdf_href="../../mega_pdf/raphoe_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )
            self.assertEqual(written, ["ardara"])
            html_out = (out_dir / "ardara-ocr.html").read_text(encoding="utf-8")
            self.assertIn("Church Car Park", html_out)
            self.assertIn("22nd", html_out)
            self.assertNotIn("Saturday 2nd August", html_out)

    def test_filename_sunday_does_not_caption_a_november_body(self) -> None:
        fragment = """
<p class="page-label">Page 1</p>
<p>Bantry Parish<br>
https://bantry.ie/newsletter</p>
<p>FEAST OF ALL SAINTS 1st November 2026 Vol. 41. No.45</p>
<p>Sunday 8th November Caheragh Old Cemetery after 11.15am Mass.</p>
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            status_path = root / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "bantry": {
                                "outcome": "ok",
                                "diocese": "Cork and Ross Diocese",
                                "display_name": "Bantry",
                                "bulletin_date": "2026-11-08",
                                "url": "https://bantryfamilyofparishes.ie/pdf/8th_November_2026.pdf",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            pdf_path = root / "cork_and_ross_mega_bulletin.pdf"
            pdf_path.write_bytes(_make_pdf(1))
            out_dir = root / "docs" / "parishes" / "cork_and_ross"
            written = parish_pages.write_parish_pages_for_diocese(
                "cork_and_ross",
                "2026-11-08",
                pdf_path,
                fragment,
                diocese_pdf_href="../../mega_pdf/cork_and_ross_mega_bulletin.pdf",
                out_dir=out_dir,
                parish_status_path=status_path,
            )
            self.assertEqual(written, ["bantry"])
            html_out = (out_dir / "bantry.html").read_text(encoding="utf-8")
            self.assertIn("There is no bulletin for this Sunday.", html_out)
            self.assertNotIn("1st November 2026", html_out)
            self.assertNotIn("FEAST OF ALL SAINTS", html_out)
            self.assertNotIn("Caheragh", html_out)
            self.assertNotIn("08/11/2026", html_out)
            self.assertNotIn("01/11/2026", html_out)
            self.assertNotIn("Bulletin — 08/11/2026", html_out)
            self.assertNotIn('class="ocr-parish-date"', html_out)
            self.assertNotIn("This week's bulletin", html_out)
            self.assertNotIn('href="bantry.pdf"', html_out)
            self.assertIn("height: 850px", html_out)
            self.assertIn("height: 450px", html_out)
            self.assertFalse((out_dir / "bantry.pdf").exists())

    def test_write_text_strips_nuls_and_leaves_no_tmp(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "note.html"
            _write_text(path, "hello\x00world")
            self.assertEqual(path.read_text(encoding="utf-8"), "helloworld")
            self.assertEqual(list(Path(tmpdir).glob("*.tmp")), [])


class StaleParishCaptionTests(unittest.TestCase):
    def test_ok_page_does_not_call_last_sunday_this_week(self) -> None:
        uk, meta, masthead = parish_pages.parish_page_date_bits(
            "2026-11-08",
            "2026-11-01",
            "Ardboe",
            "Armagh Diocese",
        )
        self.assertEqual(uk, "")
        self.assertEqual(masthead, "")
        self.assertEqual(meta, "There is no bulletin for this Sunday.")
        self.assertNotIn("08/11/2026", meta)
        self.assertNotIn("01/11/2026", meta)
        self.assertNotIn("This week's bulletin", meta)

    def test_ok_page_keeps_this_sunday_caption(self) -> None:
        uk, meta, masthead = parish_pages.parish_page_date_bits(
            "2026-11-08",
            "2026-11-08",
            "Kerry parish",
            "Kerry Diocese",
        )
        self.assertEqual(uk, "08/11/2026")
        self.assertEqual(masthead, "2026-11-08")
        self.assertIn("This week's bulletin for Kerry parish — 08/11/2026", meta)

    def test_blank_date_does_not_invent_harvest_sunday(self) -> None:
        uk, meta, masthead = parish_pages.parish_page_date_bits(
            "2026-11-08",
            "",
            "Gurranabraher",
            "Cork and Ross Diocese",
        )
        self.assertEqual(uk, "")
        self.assertEqual(masthead, "")
        self.assertNotIn("08/11/2026", meta)
        self.assertNotIn("This week's bulletin", meta)

    def test_november_body_is_not_rendered_as_this_weeks_bulletin_text(self) -> None:
        """A 1 November paper is not this Sunday's reading, even if the file says 8 November."""
        page = (
            "<html><head><title>Bantry Bulletin — 08/11/2026</title></head><body>"
            "<h1>Bantry Parish Bulletin</h1>"
            '<p class="meta">This week&#x27;s bulletin for Bantry — 08/11/2026. '
            "Part of the Cork and Ross Diocese collated bulletin.</p>"
            '<a class="download-link-top pdf-force-download" href="bantry.pdf" '
            'download="bantry.pdf">Download PDF</a>'
            '<div id="ocr-panel"><header class="ocr-parish-masthead" '
            'data-parish-name="Bantry"><h2 class="ocr-parish-name">Bantry</h2>'
            '<p class="ocr-parish-date">08/11/2026</p></header>'
            "<p>FEAST OF ALL SAINTS 1st November 2026 Vol. 41. No.45</p>"
            "<p>Sunday 8th November Caheragh Old Cemetery after 11.15am Mass.</p>"
            "</div><div class=\"note-box\">Note</div></body></html>"
        )
        updated, uk = parish_pages.refresh_parish_page_html(
            page,
            "2026-11-08",
            "Bantry",
            "Cork and Ross Diocese",
        )
        self.assertEqual(uk, "")
        self.assertIn("<title>Bantry Bulletin</title>", updated)
        self.assertIn("There is no bulletin for this Sunday.", updated)
        self.assertIn("Bantry", updated)
        self.assertNotIn("1st November 2026", updated)
        self.assertNotIn("FEAST OF ALL SAINTS", updated)
        self.assertNotIn("Caheragh", updated)
        self.assertNotIn("08/11/2026", updated)
        self.assertNotIn("01/11/2026", updated)
        self.assertNotIn("Bulletin — 08/11/2026", updated)
        self.assertNotIn('class="ocr-parish-date"', updated)
        self.assertNotIn("This week's bulletin", updated)
        self.assertNotIn("This week&#x27;s bulletin", updated)
        self.assertNotIn('href="bantry.pdf"', updated)
        again, uk_again = parish_pages.refresh_parish_page_html(
            updated,
            "2026-11-08",
            "Bantry",
            "Cork and Ross Diocese",
        )
        self.assertEqual(again, updated)
        self.assertEqual(uk_again, "")

    def test_caption_uses_real_date_not_harvest_sunday(self) -> None:
        meta, note = parish_pages.stale_parish_caption("2026-08-30")
        self.assertEqual(note, "Latest bulletin we have: 30/08/2026 (not this week)")
        self.assertEqual(meta, "Latest bulletin we have: 30/08/2026 (not this week).")
        self.assertNotIn("06/09/2026", meta)
        self.assertNotIn("This week's bulletin", meta)

    def test_caption_without_date_does_not_invent_one(self) -> None:
        meta, note = parish_pages.stale_parish_caption("")
        self.assertEqual(note, "Latest bulletin we have is not from this week")
        self.assertNotRegex(meta, r"\d{2}/\d{2}/\d{4}")

    def test_leftover_page_loses_this_week_caption(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "parishes"
            out_dir.mkdir()
            status_path = Path(tmpdir) / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardara": {
                                "outcome": "stale",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "bulletin_date": "2026-08-30",
                            },
                            "annagryparish": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Annagry",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            (out_dir / "ardara.html").write_text(
                "<html><head><style>\n    .meta { color: #6b7280; }\n    </style></head>"
                "<body><h1>Ardara Parish Bulletin</h1>"
                '<p class="meta">This week&#x27;s bulletin for Ardara — 06/09/2026. '
                "Part of the Raphoe Diocese collated bulletin.</p></body></html>",
                encoding="utf-8",
            )
            (out_dir / "annagryparish.html").write_text(
                "<html><body><h1>Annagry Parish Bulletin</h1>"
                '<p class="meta">This week&#x27;s bulletin for Annagry — 06/09/2026.</p>'
                "</body></html>",
                encoding="utf-8",
            )
            (out_dir / "ardara.pdf").write_bytes(b"%PDF-1.4 stale-slice")
            relabelled = parish_pages.relabel_leftover_parish_pages(
                out_dir,
                parish_status_path=status_path,
                ok_keys={"annagryparish"},
            )
            self.assertEqual(relabelled, ["ardara"])
            ardara = (out_dir / "ardara.html").read_text(encoding="utf-8")
            self.assertIn("Latest bulletin we have: 30/08/2026 (not this week)", ardara)
            self.assertIn('class="stale-note"', ardara)
            self.assertNotIn("This week's bulletin", ardara)
            self.assertNotIn("This week&#x27;s bulletin", ardara)
            self.assertFalse((out_dir / "ardara.pdf").exists())
            keep = (out_dir / "annagryparish.html").read_text(encoding="utf-8")
            self.assertIn("This week&#x27;s bulletin for Annagry", keep)


class SliceMissingTests(unittest.TestCase):
    def test_apply_preserves_ok_and_homepage_ready_excludes_flag(self) -> None:
        from harvester.parish_status import apply_slice_missing, build_parish_status
        from harvester.site_builder import DioceseWeekSummary, _card_counts_from_summary

        with tempfile.TemporaryDirectory() as tmpdir:
            status_path = Path(tmpdir) / "parish_status.json"
            status_path.write_text(
                json.dumps(
                    {
                        "parishes": {
                            "kincasslagh": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Kincasslagh",
                                "slice_missing": True,
                            },
                            "ardara": {
                                "outcome": "ok",
                                "diocese": "Raphoe Diocese",
                                "display_name": "Ardara",
                                "slice_missing": True,
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            apply_slice_missing(
                sliced_keys={"ardara"},
                missing_keys={"kincasslagh"},
                status_path=status_path,
            )
            data = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertTrue(data["parishes"]["kincasslagh"]["slice_missing"])
            self.assertFalse(data["parishes"]["ardara"]["slice_missing"])

            rebuilt = build_parish_status(
                {
                    "target_date": "2026-09-13",
                    "downloaded": [
                        {"parish": "kincasslagh", "display_name": "Kincasslagh", "url": "https://k.ie"},
                        {"parish": "ardara", "display_name": "Ardara", "url": "https://a.ie"},
                    ],
                },
                parishes_dir=Path(tmpdir),
                previous_status=data,
                consecutive_failures={},
                disabled_keys=set(),
            )
            self.assertEqual(rebuilt["parishes"]["kincasslagh"]["outcome"], "ok")
            self.assertTrue(rebuilt["parishes"]["kincasslagh"]["slice_missing"])
            self.assertFalse(rebuilt["parishes"]["ardara"]["slice_missing"])

            ready, total = _card_counts_from_summary(
                DioceseWeekSummary(diocese_display_name="Raphoe", found=12, total=32),
                parish_status=rebuilt,
                diocese_name="Raphoe",
            )
            self.assertEqual((ready, total), (11, 32))


if __name__ == "__main__":
    unittest.main()
