from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from harvester.fetcher import _is_real_pdf
from harvester.utils import (
    looks_like_image_bytes,
    wrap_image_file_as_pdf,
    write_image_bytes_as_pdf,
)


def _jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (80, 110), "white").save(buf, format="JPEG")
    return buf.getvalue()


class ImageWrapPdfTests(unittest.TestCase):
    def test_jpeg_magic(self) -> None:
        data = _jpeg_bytes()
        self.assertTrue(looks_like_image_bytes(data))
        self.assertFalse(looks_like_image_bytes(b"%PDF-1.4"))
        self.assertFalse(looks_like_image_bytes(b"<html>not a picture"))

    def test_wrap_turns_jpeg_file_into_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "parish.pdf"
            dest.write_bytes(_jpeg_bytes())
            self.assertTrue(wrap_image_file_as_pdf(dest))
            self.assertTrue(dest.read_bytes().startswith(b"%PDF"))

    def test_unmarked_picture_download_counts_as_real_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "parish.pdf"
            dest.write_bytes(_jpeg_bytes())
            self.assertTrue(_is_real_pdf(dest, "stgerardsparish", min_bytes=10))
            self.assertTrue(dest.read_bytes().startswith(b"%PDF"))

    def test_write_helper_makes_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.pdf"
            write_image_bytes_as_pdf(dest, _jpeg_bytes())
            self.assertTrue(dest.read_bytes().startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main()
