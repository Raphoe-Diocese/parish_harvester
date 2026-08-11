from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

import harvester.site_builder as site_builder


class LandingPageTests(unittest.TestCase):
    def test_landing_lists_all_dioceses_and_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            docs = root / "docs"
            recipes = root / "parishes" / "recipes"
            bulletins = docs / "bulletins"
            report = root / "Bulletins" / "report.json"

            (recipes / "derry").mkdir(parents=True, exist_ok=True)
            (recipes / "down_and_connor").mkdir(parents=True, exist_ok=True)
            (root / "parishes").mkdir(parents=True, exist_ok=True)
            (recipes / "derry" / "ardmoreparish.json").write_text(
                json.dumps({"parish_key": "ardmoreparish", "parish_name": "Ardmore", "start_url": "https://example.com/a"}),
                encoding="utf-8",
            )
            (recipes / "down_and_connor" / "antrimparish.json").write_text(
                json.dumps({"parish_key": "antrimparish", "parish_name": "Antrim", "start_url": "https://example.com/b"}),
                encoding="utf-8",
            )
            (root / "parishes" / "raphoe_diocese_bulletin_urls.txt").write_text(
                "\n".join(
                    [
                        "# --- Parish of Raphoe ---",
                        "# key: drive-raphoe-town",
                        "# page: https://drive.google.com/file/d/abc/view",
                        "https://drive.usercontent.google.com/download?id=abc&export=download",
                    ]
                ),
                encoding="utf-8",
            )

            bulletins.mkdir(parents=True, exist_ok=True)
            (bulletins / "derry-2026-05-22.html").write_text(
                '<div id="ocr-panel">Derry text</div><div class="note-box">note</div>',
                encoding="utf-8",
            )
            (bulletins / "down_and_connor-2026-05-22.html").write_text(
                '<div id="ocr-panel">Down text</div><div class="note-box">note</div>',
                encoding="utf-8",
            )
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps({"downloaded": [{"parish": "ardmoreparish"}, {"parish": "antrimparish"}]}),
                encoding="utf-8",
            )
            (docs / "reliability.json").write_text(
                json.dumps(
                    {
                        "parishes": {
                            "ardmoreparish": {"success_rate": 0.9},
                            "antrimparish": {"success_rate": 0.4},
                        }
                    }
                ),
                encoding="utf-8",
            )

            old = (site_builder.RECIPES_DIR, site_builder.BULLETINS_DIR, site_builder.RELIABILITY_PATH, site_builder.REPO_ROOT)
            site_builder.RECIPES_DIR = recipes
            site_builder.BULLETINS_DIR = bulletins
            site_builder.RELIABILITY_PATH = docs / "reliability.json"
            site_builder.REPO_ROOT = root
            try:
                site_builder.run(report_path=report, docs_dir=docs)
            finally:
                site_builder.RECIPES_DIR, site_builder.BULLETINS_DIR, site_builder.RELIABILITY_PATH, site_builder.REPO_ROOT = old

            index_html = (docs / "index.html").read_text(encoding="utf-8")

            # The 3 live dioceses are prominent, near the top, each with a
            # one-click link to its collated (mega) bulletin and its text
            # bulletin — not a full-size "coming soon" card.
            self.assertIn("Live dioceses", index_html)
            self.assertEqual(index_html.count("live-card\""), 3)
            self.assertIn("Derry Diocese", index_html)
            self.assertIn("Down and Connor Diocese", index_html)
            self.assertIn("Raphoe Diocese", index_html)
            self.assertIn("Open Collated Bulletin", index_html)
            self.assertIn("Mega PDF", index_html)
            self.assertIn("Text Bulletin", index_html)
            self.assertIn("🟢", index_html)
            self.assertIn("🔴", index_html)

            # The other 23 dioceses collapse into one small expandable list.
            self.assertIn("More dioceses — coming soon (23)", index_html)
            self.assertNotIn("Parish of Raphoe", index_html)

            links = re.findall(r'href="dioceses/([a-z0-9-]+)/"', index_html)
            self.assertEqual(len(links), 26)
            for key in links:
                self.assertTrue((docs / "dioceses" / key / "index.html").exists(), key)

            # Homepage hero image/gradient slider: auto-advancing carousel
            # with prev/next controls, dot indicators, and reduced-motion
            # support — plain CSS/vanilla JS, no framework.
            self.assertIn('data-hero-slider', index_html)
            self.assertEqual(
                index_html.count('aria-roledescription="slide"'), len(site_builder.HERO_SLIDES)
            )
            self.assertIn('hero-prev', index_html)
            self.assertIn('hero-next', index_html)
            self.assertEqual(index_html.count('data-slide-index="'), len(site_builder.HERO_SLIDES))
            self.assertIn('prefers-reduced-motion', index_html)
            self.assertIn('matchMedia', index_html)

            # Real cathedral photos (not gradient placeholders) with the
            # legally-required CC attribution credit shown on each slide.
            self.assertIn('upload.wikimedia.org', index_html)
            self.assertIn('Wikimedia Commons', index_html)
            self.assertIn('hero-slide-credit', index_html)


class HeroSliderRenderTests(unittest.TestCase):
    def test_hero_slider_html_uses_gradient_when_no_image(self) -> None:
        original = site_builder.HERO_SLIDES
        try:
            site_builder.HERO_SLIDES = [
                site_builder.HeroSlide(
                    image=None,
                    gradient="linear-gradient(135deg, #000, #fff)",
                    eyebrow="Test",
                    title="Test title",
                    subtitle="Test subtitle",
                )
            ]
            markup = site_builder._hero_slider_html()
        finally:
            site_builder.HERO_SLIDES = original
        self.assertIn('linear-gradient', markup)
        self.assertNotIn('url(', markup)

    def test_hero_slider_html_uses_photo_when_image_set(self) -> None:
        original = site_builder.HERO_SLIDES
        try:
            site_builder.HERO_SLIDES = [
                site_builder.HeroSlide(
                    image="assets/hero/slide-1.jpg",
                    gradient="linear-gradient(135deg, #000, #fff)",
                    eyebrow="Test",
                    title="Test title",
                    subtitle="Test subtitle",
                )
            ]
            markup = site_builder._hero_slider_html()
        finally:
            site_builder.HERO_SLIDES = original
        self.assertIn("url('assets/hero/slide-1.jpg')", markup)
        self.assertIn("Test title", markup)

    def test_hero_slider_html_supports_full_url_image_and_custom_position(self) -> None:
        original = site_builder.HERO_SLIDES
        try:
            site_builder.HERO_SLIDES = [
                site_builder.HeroSlide(
                    image="https://upload.wikimedia.org/wikipedia/commons/thumb/x/y/photo.jpg/1280px-photo.jpg",
                    position="center 25%",
                    gradient="linear-gradient(135deg, #000, #fff)",
                    eyebrow="Test",
                    title="Test title",
                    subtitle="Test subtitle",
                )
            ]
            markup = site_builder._hero_slider_html()
        finally:
            site_builder.HERO_SLIDES = original
        self.assertIn(
            "url('https://upload.wikimedia.org/wikipedia/commons/thumb/x/y/photo.jpg/1280px-photo.jpg') "
            "center 25%/cover no-repeat",
            markup,
        )

    def test_hero_slider_html_renders_required_cc_attribution_credit(self) -> None:
        original = site_builder.HERO_SLIDES
        try:
            site_builder.HERO_SLIDES = [
                site_builder.HeroSlide(
                    image="assets/hero/slide-1.jpg",
                    credit="Photo: Jane Doe / Wikimedia Commons / CC BY-SA 4.0",
                    gradient="linear-gradient(135deg, #000, #fff)",
                    eyebrow="Test",
                    title="Test title",
                    subtitle="Test subtitle",
                ),
                site_builder.HeroSlide(
                    image="assets/hero/slide-2.jpg",
                    credit=None,
                    gradient="linear-gradient(135deg, #000, #fff)",
                    eyebrow="Test 2",
                    title="Test title 2",
                    subtitle="Test subtitle 2",
                ),
            ]
            markup = site_builder._hero_slider_html()
        finally:
            site_builder.HERO_SLIDES = original
        self.assertIn('hero-slide-credit">Photo: Jane Doe / Wikimedia Commons / CC BY-SA 4.0<', markup)
        self.assertEqual(markup.count('class="hero-slide-credit"'), 1)

    def test_default_hero_slides_are_real_cathedral_photos_with_cc_credit(self) -> None:
        # Frank asked for real cathedral photos (not gradient placeholders)
        # for the 3 live dioceses — each must be a verified CC-licensed
        # Wikimedia Commons photo with an on-image attribution credit.
        self.assertEqual(len(site_builder.HERO_SLIDES), 3)
        for slide in site_builder.HERO_SLIDES:
            self.assertTrue(slide.image and slide.image.startswith("https://upload.wikimedia.org/"))
            self.assertTrue(slide.credit and "Wikimedia Commons" in slide.credit)
            self.assertTrue(any(lic in slide.credit for lic in ("CC BY-SA", "CC BY")))

        titles = {slide.title for slide in site_builder.HERO_SLIDES}
        self.assertIn("Cathedral of St. Eunan and St. Columba, Letterkenny", titles)
        self.assertIn("St Eugene's Cathedral, Derry", titles)
        self.assertIn("St Peter's Cathedral, Belfast", titles)

        eyebrows = {slide.eyebrow for slide in site_builder.HERO_SLIDES}
        self.assertEqual(eyebrows, {"Raphoe Diocese", "Derry Diocese", "Down & Connor Diocese"})

    def test_hero_slider_html_empty_when_no_slides(self) -> None:
        original = site_builder.HERO_SLIDES
        try:
            site_builder.HERO_SLIDES = []
            markup = site_builder._hero_slider_html()
        finally:
            site_builder.HERO_SLIDES = original
        self.assertEqual(markup, "")


if __name__ == "__main__":
    unittest.main()
