"""Offline regression tests: batch recovery never accepts stale or fake PDFs."""
from __future__ import annotations

from datetime import date
from unittest import TestCase
from unittest.mock import patch

from scripts import batch_bulletin_probe as batch

SUNDAY = date(2026, 11, 15)
HOME = "https://exampleparish.ie/"
PDF = "https://exampleparish.ie/uploads/Bulletin-15-November-2026.pdf"
OLD = "https://exampleparish.ie/uploads/Bulletin-8-November-2026.pdf"


def sample(url=HOME):
    return {"name": "Example Parish", "matched_parish": "example",
            "url": url, "source_type": "website", "status_hint": "failed"}


class BatchProbeTests(TestCase):
    def test_current_pdf_requires_signature_and_week(self):
        html = ('<html><a href="' + PDF + '">Sunday 15th November 2026 Bulletin</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            return b"%PDF-1.5\n" + b"X" * 6000, "application/pdf", PDF
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_bytes_and_link_date")
        self.assertEqual(result["issue_date"], SUNDAY.isoformat())

    def test_old_week_not_accepted(self):
        html = ('<html><a href="' + OLD + '">Parish Bulletin 8 November 2026</a></html>').encode()
        with patch.object(batch, "fetch", return_value=(html, "text/html", HOME)):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")

    def test_html_disguised_as_pdf_rejected(self):
        html = ('<html><a href="' + PDF + '">Parish Bulletin 15 November 2026</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            return (html, "text/html", HOME) if url == HOME else (b"<html>Forbidden</html>", "text/html", PDF)
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")

    def test_one_hop_current_pdf(self):
        article = HOME + "weekly-newsletter/"
        landing = ('<html><a href="/weekly-newsletter/">Weekly Parish Newsletter</a></html>').encode()
        page = ('<a href="' + PDF + '">Sunday 15 November 2026</a>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return landing, "text/html", HOME
            if url == article:
                return page, "text/html", article
            return b"%PDF-1.4\n" + b"X" * 6000, "application/pdf", PDF
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_bytes_and_link_date")

    def test_admin_documents_not_accepted(self):
        bad = HOME + "wp-content/Consent-15-November-2026.pdf"
        html = ('<a href="' + bad + '">Parish Newsletter 15 November 2026</a>').encode()
        with patch.object(batch, "fetch", return_value=(html, "text/html", HOME)):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")


    def test_direct_pdf_with_stale_masthead_rejected(self):
        source = "https://exampleparish.ie/Bulletin-15-November-2026.pdf"
        pdf = b"%PDF-1.4\n" + b"X" * 6000
        with patch.object(batch, "fetch", return_value=(pdf, "application/pdf", source)):
            with patch("harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                       return_value=date(2026, 11, 8)):
                result = batch.probe_one(sample(source), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")

    def test_direct_pdf_with_correct_masthead_is_candidate(self):
        source = "https://exampleparish.ie/Bulletin-15-November-2026.pdf"
        pdf = b"%PDF-1.4\n" + b"X" * 6000
        with patch.object(batch, "fetch", return_value=(pdf, "application/pdf", source)):
            with patch("harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                       return_value=SUNDAY):
                result = batch.probe_one(sample(source), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_masthead")

    def test_unsupported_links_not_requested(self):
        with patch.object(batch, "fetch") as fetch:
            result = batch.probe_one({"name": "Unknown", "url": "https://facebook.com/example"}, SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")
        fetch.assert_not_called()
