"""Parish URL inference rules — keep in sync with extension/parish_pickers.js."""
from __future__ import annotations

import re
import unittest

_SHARED_HOSTS = {"mcn.live", "www.mcn.live"}
_PATH_SKIP = {"camera", "wp-content", "uploads", "index.html"}


def path_slug_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parts = urlparse(url).path.split("/")
    parts = [p for p in parts if p]
    for seg in reversed(parts):
        low = seg.lower()
        if low in _PATH_SKIP or len(low) < 3:
            continue
        return re.sub(r"[^a-z0-9_-]+", "-", low).strip("-")
    return ""


def infer_key(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).hostname.lower().replace("www.", "")
    if host in _SHARED_HOSTS:
        return path_slug_from_url(url)
    return host.split(".")[0]


def is_junk_parish_key(key: str) -> bool:
    k = str(key or "").strip().lower()
    if not k or len(k) < 4:
        return True
    if re.fullmatch(r"\d{6,8}(-pdf)?", k):
        return True
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{2}(-pdf)?", k):
        return True
    if k.endswith("-pdf") and re.search(r"\d{5,}", k):
        return True
    return False


class ParishPickerInferenceTests(unittest.TestCase):
    def test_mcn_holy_cross(self) -> None:
        url = "https://mcn.live/Camera/holy-cross-church"
        self.assertEqual(infer_key(url), "holy-cross-church")

    def test_mcn_killybegs(self) -> None:
        url = "https://mcn.live/Camera/st-mary-of-the-visitation-church-killybegs"
        self.assertEqual(infer_key(url), "st-mary-of-the-visitation-church-killybegs")

    def test_normal_parish_site(self) -> None:
        url = "https://www.buncranaparish.com/bulletin"
        self.assertEqual(infer_key(url), "buncranaparish")

    def test_junk_pdf_slug_keys_rejected(self) -> None:
        self.assertTrue(is_junk_parish_key("050426-pdf"))
        self.assertTrue(is_junk_parish_key("220326-pdf"))
        self.assertTrue(is_junk_parish_key("26.06.14-pdf"))
        self.assertFalse(is_junk_parish_key("buncranaparish"))


if __name__ == "__main__":
    unittest.main()
