from __future__ import annotations

import unittest

from harvester.cloud_urls import is_cloud_document_url, normalize_document_url, rewrite_gdrive_download_url


class CloudUrlTests(unittest.TestCase):
    def test_gdrive_file_url_rewrites_to_download(self) -> None:
        url = "https://drive.google.com/file/d/ABC123xyz/view?usp=sharing"
        out = rewrite_gdrive_download_url(url)
        self.assertIn("ABC123xyz", out)
        self.assertIn("export=download", out)

    def test_docs_viewer_unwraps_embedded_pdf(self) -> None:
        url = "https://docs.google.com/viewer?url=https%3A%2F%2Fexample.com%2Fbulletin.pdf"
        out = normalize_document_url(url)
        self.assertIn("example.com/bulletin.pdf", out)

    def test_onedrive_share_is_document(self) -> None:
        url = "https://1drv.ms/b/s!abc123"
        self.assertTrue(is_cloud_document_url(url))

    def test_sharepoint_embed_is_document(self) -> None:
        url = "https://contoso.sharepoint.com/sites/parish/Shared%20Documents/bulletin.pdf"
        self.assertTrue(is_cloud_document_url(url))


if __name__ == "__main__":
    unittest.main()
