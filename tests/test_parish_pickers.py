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


if __name__ == "__main__":
    unittest.main()
