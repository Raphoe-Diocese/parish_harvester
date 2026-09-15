from __future__ import annotations

import io
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

from ocr.convert_bulletin import _image_png_bytes, ocr_images_with_gemini


def _ppm_page() -> Image.Image:
    rgb = Image.new("RGB", (8, 8), "white")
    buf = io.BytesIO()
    rgb.save(buf, format="PPM")
    buf.seek(0)
    return Image.open(buf)


class GeminiPngTests(unittest.TestCase):
    def test_ppm_encodes_as_png(self) -> None:
        ppm = _ppm_page()
        self.assertEqual(ppm.format, "PPM")
        data = _image_png_bytes(ppm)
        self.assertTrue(data.startswith(b"\x89PNG"), "Gemini must receive PNG bytes")

    def test_gemini_sends_png_mime_not_raw_ppm(self) -> None:
        captured: list = []

        class FakeModel:
            def generate_content(self, parts):
                captured.append(parts)
                return SimpleNamespace(text="Mass times")

        fake_genai = MagicMock()
        fake_genai.GenerativeModel.return_value = FakeModel()
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            with patch.dict(sys.modules, {"google.generativeai": fake_genai}):
                pages, provider = ocr_images_with_gemini([_ppm_page()])
        self.assertEqual(provider, "Gemini fallback")
        self.assertEqual(pages, [["Mass times"]])
        self.assertEqual(captured[0][1]["mime_type"], "image/png")
        self.assertTrue(captured[0][1]["data"].startswith(b"\x89PNG"))
        self.assertNotEqual(captured[0][1].get("mime_type"), "image/x-portable-pixmap")


if __name__ == "__main__":
    unittest.main()
