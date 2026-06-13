from __future__ import annotations

import unittest

from harvester.browser_launch import looks_like_bot_block


class BrowserLaunchTests(unittest.TestCase):
    def test_looks_like_bot_block_detects_aborted_and_403(self) -> None:
        self.assertTrue(looks_like_bot_block("Page.goto: net::ERR_ABORTED"))
        self.assertTrue(looks_like_bot_block("HTTP 403 Forbidden"))
        self.assertFalse(looks_like_bot_block("HTTP 404 Not Found"))


if __name__ == "__main__":
    unittest.main()
