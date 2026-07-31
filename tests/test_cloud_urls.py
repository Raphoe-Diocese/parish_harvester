from __future__ import annotations

import unittest

from harvester.cloud_urls import (
    gdrive_confirm_token,
    gdrive_confirm_uuid,
    gdrive_download_url_with_confirm,
    gdrive_file_id_from_url,
    gdrive_view_url,
    is_cloud_document_url,
    normalize_document_url,
    rewrite_gdrive_download_url,
)


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

    def test_pdfjs_viewer_unwraps_embedded_pdf(self) -> None:
        url = (
            "https://portaferryparish.com/plugins/content/pdf_embed/assets/viewer/"
            "pdfjs/web/viewer.html?file=https%3A%2F%2Fportaferryparish.com%2Fimages%2Fdownloads%2FBulletin2019A.pdf"
        )
        out = normalize_document_url(url)
        self.assertIn("portaferryparish.com/images/downloads/Bulletin2019A.pdf", out)

    def test_gdrive_file_id_from_view_and_download_urls(self) -> None:
        view = "https://drive.google.com/file/d/1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5/view?pli=1"
        download = (
            "https://drive.usercontent.google.com/download?"
            "id=1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5&export=download"
        )
        self.assertEqual(gdrive_file_id_from_url(view), "1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5")
        self.assertEqual(gdrive_file_id_from_url(download), "1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5")
        self.assertEqual(
            gdrive_view_url("1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5"),
            "https://drive.google.com/file/d/1jmslbrliw1BTtdrxHbqpUbhQEf6wXHy5/view",
        )

    def test_gdrive_confirm_token_appended(self) -> None:
        html = '<form action="/download"><input name="confirm" value="t123"></form>'
        token = gdrive_confirm_token(html)
        self.assertEqual(token, "t123")
        out = gdrive_download_url_with_confirm(
            "https://drive.usercontent.google.com/download?id=ABC&export=download",
            token,
        )
        self.assertIn("confirm=t123", out)

    def test_gdrive_confirm_token_tolerates_extra_attributes(self) -> None:
        # Attribute order isn't guaranteed on the virus-scan interstitial.
        html = '<input name="confirm" type="hidden" value="t456">'
        self.assertEqual(gdrive_confirm_token(html), "t456")

    def test_gdrive_confirm_uuid_extracted_and_forwarded(self) -> None:
        html = '<input name="uuid" value="abc-123-def">'
        self.assertEqual(gdrive_confirm_uuid(html), "abc-123-def")
        out = gdrive_download_url_with_confirm(
            "https://drive.usercontent.google.com/download?id=ABC&export=download",
            "t123",
            "abc-123-def",
        )
        self.assertIn("confirm=t123", out)
        self.assertIn("uuid=abc-123-def", out)

    def test_gdrive_download_url_without_uuid_unchanged(self) -> None:
        out = gdrive_download_url_with_confirm(
            "https://drive.usercontent.google.com/download?id=ABC&export=download",
            "t123",
        )
        self.assertIn("confirm=t123", out)
        self.assertNotIn("uuid=", out)

    def test_gdrive_resourcekey_preserved_on_rewrite(self) -> None:
        url = (
            "https://drive.google.com/file/d/ABC123xyz/view"
            "?usp=sharing&resourcekey=0-someKey"
        )
        out = rewrite_gdrive_download_url(url)
        self.assertIn("id=ABC123xyz", out)
        self.assertIn("resourcekey=0-someKey", out)

    def test_gdrive_workspace_style_file_url_id_extracted(self) -> None:
        url = "https://drive.google.com/a/parish.org/file/d/WORKSPACE_ID/view"
        out = rewrite_gdrive_download_url(url)
        self.assertIn("id=WORKSPACE_ID", out)


if __name__ == "__main__":
    unittest.main()
