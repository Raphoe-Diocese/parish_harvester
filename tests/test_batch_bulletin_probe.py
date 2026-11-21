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
    def test_kerry_shared_upload_without_printed_parish_identity_is_demoted(self):
        row = {
            "parish": "adrigole", "name": "Adrigole",
            "verdict": "candidate_verified_masthead", "masthead_verified": True,
            "document_url": "https://www.dioceseofkerry.ie/wp-content/uploads/2026/11/newsletter-22nd-Nov-2026.pdf",
        }
        result = batch.audit_existing_candidate(row)
        self.assertEqual(result["verdict"], "candidate_requires_manual_review")
        self.assertEqual(result["reason"], "shared_kerry_upload_parish_identity_unverified")
        self.assertEqual(result["previous_verdict"], "candidate_verified_masthead")

    def test_kerry_shared_upload_with_printed_parish_identity_is_retained(self):
        row = {
            "parish": "adrigole", "name": "Adrigole", "body_text": "Adrigole Parish Newsletter",
            "verdict": "candidate_verified_masthead", "masthead_verified": True,
            "document_url": "https://www.dioceseofkerry.ie/wp-content/uploads/2026/11/newsletter.pdf",
        }
        self.assertEqual(batch.audit_existing_candidate(row)["verdict"], "candidate_verified_masthead")

    def test_image_with_valueless_alt_has_an_empty_caption(self):
        page = batch.Links()
        page.feed('<img src="newsletter.jpg" alt>')
        self.assertEqual(page.links, [("newsletter.jpg", "")])

    def test_mcn_identity_must_match_before_and_after_fetch(self):
        seed = "https://d3gxiup807zlof.cloudfront.net/live/Uploads/606/NewsLetter/old.pdf"
        current = seed.replace("old.pdf", "new.pdf")
        other = current.replace("/606/", "/607/")
        for url, resolved in [(other, other), (current, other), (current, current)]:
            with (
                self.subTest(url=url, resolved=resolved),
                patch("harvester.webcam_bulletin_dig._http_json", return_value={"newsletter": {"newsLetterUrl": url}}),
                patch.object(batch, "fetch", return_value=(b"%PDF-" + b"x"*4000, "application/pdf", resolved)) as fetch,
                patch("harvester.bulletin_freshness.heading_date_in_pdf_bytes", return_value=SUNDAY),
            ):
                result = batch.probe_one(sample(seed), SUNDAY)
                self.assertEqual(result["verdict"] == "candidate_verified_masthead", resolved == current)
                if url == other:
                    fetch.assert_not_called()

    def test_discovery_rolls_forward_on_saturday(self):
        for day, expected in ((20, 15), (21, 22), (22, 22), (23, 22)):
            with self.subTest(day=day):
                self.assertEqual(batch.discovery_sunday(date(2026, 11, day)),
                                 date(2026, 11, expected))

    def test_stale_shared_pdf_does_not_search_other_parishes_uploads(self):
        for host in ("churchtv.ie", "dioceseofkerry.ie"):
            with self.subTest(host=host):
                stale = f"https://www.{host}/wp-content/uploads/2026/11/Old.pdf"
                with patch.object(batch, "fetch", return_value=(b"%PDF-1.5", "application/pdf", stale)) as fetch:
                    result = batch.probe_one(sample(stale), SUNDAY)
                self.assertEqual(result["reason"], "direct_pdf_stale_or_undated")
                fetch.assert_called_once_with(stale, batch.MAX_FILE)

    def test_saved_shared_root_fallback_requires_identity_review(self):
        for host in ("churchtv.ie", "dioceseofkerry.ie"):
            with self.subTest(host=host):
                row = batch.audit_existing_candidate({
                    "verdict": "candidate_verified_masthead",
                    "document_url": f"https://www.{host}/wp-content/uploads/2026/11/Bulletin.pdf",
                    "fallback_website": f"https://www.{host}/",
                    "file_kind": "pdf",
                })
                self.assertEqual(row["verdict"], "candidate_requires_manual_review")

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


    def test_wordpress_media_recovers_current_pdf_without_homepage_link(self):
        import json
        media = HOME + "wp-json/wp/v2/media?per_page=75&orderby=date&order=desc"
        html = b"<html><h1>Parish notices</h1></html>"
        payload = [{"source_url": PDF,
                    "title": {"rendered": "Parish Bulletin 15 November 2026"},
                    "date": "2026-11-14T10:00:00"}]
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            if url == media:
                return json.dumps(payload).encode(), "application/json", media
            return b"%PDF-1.5\\n" + b"X" * 6000, "application/pdf", PDF
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_bytes_and_link_date")
        self.assertEqual(result["document_url"], PDF)

    def test_wordpress_upload_date_not_mistaken_for_issue_date(self):
        payload = [{"source_url": HOME + "files/Parish-Newsletter.pdf",
                    "title": {"rendered": "Weekly Parish Newsletter"},
                    "date": "2026-11-15T10:00:00"}]
        import json
        with patch.object(batch, "fetch", return_value=(json.dumps(payload).encode(), "application/json", HOME)):
            found = batch.wordpress_media_candidates(HOME, SUNDAY)
        self.assertEqual(found, [])

    def test_admin_documents_not_accepted(self):
        bad = HOME + "wp-content/Consent-15-November-2026.pdf"
        html = ('<a href="' + bad + '">Parish Newsletter 15 November 2026</a>').encode()
        with patch.object(batch, "fetch", return_value=(html, "text/html", HOME)):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")



    def test_stale_wordpress_pdf_retries_parish_homepage(self):
        stale = HOME + "wp-content/uploads/2026/11/Bulletin-8-November-2026.pdf"
        current = HOME + "wp-content/uploads/2026/11/Bulletin-15-November-2026.pdf"
        html = ('<html><a href="' + current + '">Parish Bulletin 15 November 2026</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == stale:
                return b"%PDF-1.4\\n" + b"Z" * 6000, "application/pdf", stale
            if url == HOME:
                return html, "text/html", HOME
            if url == current:
                return b"%PDF-1.5\\n" + b"Y" * 6000, "application/pdf", current
            return b"", "", ""
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            with patch("harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                       side_effect=[date(2026, 11, 8), SUNDAY]):
                result = batch.probe_one(sample(stale), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_masthead")
        self.assertEqual(result["document_url"], current)
        self.assertEqual(result["fallback_website"], HOME)

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

    def test_date_only_pdf_in_newsletter_directory(self):
        dated = HOME + "images/newsletter/15.11.2026.pdf"
        html = ('<html><a href="' + dated + '">Download</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            return b"%PDF-1.7\\n" + b"X" * 6000, "application/pdf", dated
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_bytes_and_link_date")

    def test_date_only_admin_pdf_not_accepted(self):
        dated = HOME + "documents/15.11.2026.pdf"
        html = ('<html><a href="' + dated + '">Download</a></html>').encode()
        with patch.object(batch, "fetch", return_value=(html, "text/html", HOME)):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")


    def test_undated_newsletter_pdf_requires_current_masthead(self):
        undated = HOME + "wp-content/uploads/newsletter.pdf"
        html = ('<html><a href="' + undated + '">Weekly Parish Newsletter</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            return b"%PDF-1.5\n" + b"X" * 6000, "application/pdf", undated
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            with patch("harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                       return_value=SUNDAY):
                result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "candidate_verified_masthead")
        self.assertEqual(result["document_url"], undated)

    def test_undated_newsletter_pdf_with_old_masthead_not_accepted(self):
        undated = HOME + "wp-content/uploads/newsletter.pdf"
        html = ('<html><a href="' + undated + '">Weekly Parish Newsletter</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            return b"%PDF-1.5\n" + b"X" * 6000, "application/pdf", undated
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            with patch("harvester.bulletin_freshness.heading_date_in_pdf_bytes",
                       return_value=date(2026, 11, 8)):
                result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")

    def test_thumbnail_uses_full_size_image_when_available(self):
        small = HOME + "wp-content/uploads/Newsletter-15-November-2026-front-180x180.png"
        full = HOME + "wp-content/uploads/Newsletter-15-November-2026-front.png"
        html = ('<html><a href="' + small + '">Parish Newsletter 15 November 2026</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            if url == small:
                return b"\x89PNG\r\n\x1a\n" + b"X" * 4000, "image/png", small
            if url == full:
                return b"\x89PNG\r\n\x1a\n" + b"Y" * 8000, "image/png", full
            return b"", "", ""
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["document_url"], full)
        self.assertEqual(result["file_kind"], "png")

    def test_page_two_only_image_is_not_complete_newsletter(self):
        page = HOME + "images/newsletter/2026-11-15-Newsletter-Page-2.jpg"
        html = ('<html><a href="' + page + '">Parish Bulletin 15 November 2026</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            return b"\xff\xd8\xff" + b"X" * 6000, "image/jpeg", page
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")

    def test_wrong_named_parish_pdf_not_misassigned(self):
        other = HOME + "wp-content/uploads/Gurteen-Parish-Newsletter-15-November-2026.pdf"
        html = ('<html><a href="' + other + '">Weekly Parish Newsletter 15 November 2026</a></html>').encode()
        def fake_fetch(url, limit, timeout=12):
            if url == HOME:
                return html, "text/html", HOME
            return b"%PDF-1.5\n" + b"X" * 6000, "application/pdf", other
        with patch.object(batch, "fetch", side_effect=fake_fetch):
            result = batch.probe_one(sample(), SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")

    def test_cumulative_ledger_demotes_cross_parish_pdf(self):
        row = {"verdict": "candidate_verified_masthead", "file_kind": "pdf",
               "document_url": HOME + "Gurteen-Parish-Newsletter-15-November-2026.pdf",
               "name": "Headford", "parish": "headford", "masthead_verified": True}
        checked = batch.audit_existing_candidate(row)
        self.assertEqual(checked["verdict"], "candidate_requires_manual_review")
        self.assertEqual(checked["reason"], "different_parish_named_in_file")

    def test_same_parish_after_month_prefix_is_not_falsely_rejected(self):
        row = {
            "verdict": "candidate_verified_masthead", "file_kind": "pdf",
            "document_url": HOME + "15th-November-Crossmolina-Parish-Newsletter.pdf",
            "name": "Crossmolina", "parish": "crossmolina", "masthead_verified": True,
        }
        self.assertEqual(batch.audit_existing_candidate(row)["verdict"], "candidate_verified_masthead")

    def test_malformed_source_url_is_a_miss_not_batch_exception(self):
        from http.client import InvalidURL
        with patch.object(batch, "urlopen", side_effect=InvalidURL("bad URL")):
            self.assertEqual(batch.fetch(HOME, 1024), (b"", "", ""))

    def test_dated_prefix_cannot_disguise_another_parish(self):
        row = {
            "verdict": "candidate_verified_masthead",
            "file_kind": "pdf",
            "document_url": HOME + "20261115-Caltra-Parish-Newsletter-for-14th-Nov.pdf",
            "name": "Crossmolina",
            "parish": "crossmolina",
            "masthead_verified": True,
        }
        flagged = batch.audit_existing_candidate(row)
        self.assertEqual(flagged["verdict"], "candidate_requires_manual_review")
        self.assertEqual(flagged["reason"], "different_parish_named_in_file")

    def test_cumulative_ledger_demotes_small_and_page_two_images(self):
        for path, expected in (
            ("Newsletter-15-November-2026-front-180x180.png", "thumbnail_not_full_bulletin"),
            ("20261115-Newsletter-Page-2.jpg", "only_later_page_found"),
        ):
            row = {"verdict": "candidate_verified_bytes_and_link_date", "file_kind": "png"
                   if path.endswith(".png") else "jpeg",
                   "document_url": HOME + path, "name": "Example", "parish": "example"}
            self.assertEqual(batch.audit_existing_candidate(row)["reason"], expected)

    def test_final_batch_only_processes_remaining_leads(self):
        queue = {"leads": [
            {"url": HOME + str(i), "matched_parish": str(i),
             "status_hint": "failed", "validation": "unverified_seed"}
            for i in range(3)
        ]}
        with patch.object(batch, "probe_one",
                          side_effect=lambda row, sunday: {
                              "seed": row["url"], "verdict": "not_verified"
                          }) as scan:
            report, cursor = batch.run(queue, {"offset": 2}, SUNDAY, 120, 3)
        self.assertEqual(report["summary"]["probed"], 1)
        self.assertEqual(cursor["offset"], 0)
        self.assertEqual(scan.call_count, 1)

    def test_one_broken_parish_does_not_abort_120_source_batch(self):
        queue = {"leads": [
            {"name": "Broken", "url": HOME + "broken", "matched_parish": "broken",
             "status_hint": "failed", "validation": "unverified_seed"},
            {"name": "Working", "url": HOME + "working", "matched_parish": "working",
             "status_hint": "failed", "validation": "unverified_seed"},
        ]}
        def simulate(row, target):
            if row["matched_parish"] == "broken":
                raise RuntimeError("site parser crashed")
            return {"seed": row["url"], "parish": "working", "verdict": "not_verified"}
        with patch.object(batch, "probe_one", side_effect=simulate):
            report, _state = batch.run(queue, {}, SUNDAY, 2, 2)
        self.assertEqual(report["summary"]["probed"], 2)
        self.assertEqual(report["summary"]["probe_exceptions"], 1)
        self.assertEqual(len(report["rows"]), 2)

    def test_unsupported_links_not_requested(self):
        with patch.object(batch, "fetch") as fetch:
            result = batch.probe_one({"name": "Unknown", "url": "https://facebook.com/example"}, SUNDAY)
        self.assertEqual(result["verdict"], "not_verified")
        fetch.assert_not_called()
