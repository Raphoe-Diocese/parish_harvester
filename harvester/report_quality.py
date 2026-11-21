"""Reject non-bulletin diocesan directory pages mislabelled as HTML PDFs.

Only blocks known diocese *directory* HTML captures, not actual downloadable
PDFs or genuine parish newsletter articles. Used at harvest and mega stitch.
"""
from __future__ import annotations

from urllib.parse import urlparse
from datetime import date
import re

_DIOCESE_DIRECTORY_HOSTS = {
    "cashel-emly.ie",
    "clonfertgalway.ie",
    "achonryelphin.ie",
    "killaladiocese.org",
    "dioceseofmeath.ie",
}
_DIRECTORY_PATH = re.compile(
    r"(?:/map-of-parishes/?$|/parishes-ministries/parish-details/?"
    r"|/parish-details/?|/parishes/?$|/parish/[^/]+/?$)",
    re.IGNORECASE,
)


def is_directory_html_result(row: dict) -> bool:
    """True for generic diocese parish directory pages printed as a PDF."""
    if str(row.get("file_type") or "").lower() not in {"html_render", "html_to_pdf"}:
        return False
    url = str(row.get("url") or "")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host not in _DIOCESE_DIRECTORY_HOSTS:
        return False
    return bool(_DIRECTORY_PATH.search(parsed.path))


def reject_directory_downloads(report: dict) -> int:
    """Move counterfeit HTML directory PDFs from downloaded to failed.

    Preserve audit evidence and exclude files from later mega stitch. Does not
    delete documents or suppress any genuine parish PDF hosted by a diocese.
    """
    good = []
    rejected = []
    for row in report.get("downloaded") or []:
        if not isinstance(row, dict) or not is_directory_html_result(row):
            good.append(row)
            continue
        rejected.append({
            "parish": row.get("parish"),
            "display_name": row.get("display_name"),
            "url": row.get("url"),
            "error": "Diocesan parish-directory HTML is not a weekly bulletin",
            "reason": "directory_html_false_positive",
        })
    if not rejected:
        return 0
    report["downloaded"] = good
    report.setdefault("failed", []).extend(rejected)
    summary = report.setdefault("summary", {})
    summary["downloaded"] = len(good)
    summary["failed"] = len(report["failed"])
    summary["directory_html_rejected"] = len(rejected)
    return len(rejected)


def reject_future_dated_downloads(report: dict) -> int:
    """A 22 November PDF must never be counted in the 15 November harvest.

    Relies on an explicit issue date already extracted by the harvester.
    Unknown dates are not guessed. Sunday or weekday editions from the
    current week remain eligible for the existing freshness referee.
    """
    try:
        target = date.fromisoformat(str(report.get("target_date") or ""))
    except ValueError:
        return 0
    good = []
    rejected = []
    for row in report.get("downloaded") or []:
        if not isinstance(row, dict):
            continue
        raw_date = str(row.get("bulletin_date") or "")
        try:
            issue = date.fromisoformat(raw_date)
        except ValueError:
            issue = None
        if issue is None or issue <= target:
            good.append(row)
            continue
        rejected.append({
            "parish": row.get("parish"),
            "display_name": row.get("display_name"),
            "url": row.get("url"),
            "bulletin_date": raw_date,
            "reason": "date_ahead_of_target",
            "error": f"Bulletin date {raw_date} is later than harvest target {target}",
        })
    if not rejected:
        return 0
    report["downloaded"] = good
    report.setdefault("stale_rejected", []).extend(rejected)
    summary = report.setdefault("summary", {})
    summary["downloaded"] = len(good)
    summary["stale_rejected"] = len(report["stale_rejected"])
    summary["future_dated_rejected"] = len(rejected)
    return len(rejected)


def reject_known_diocesan_admin_downloads(report: dict) -> int:
    """Block known one-off central documents repeatedly picked for parishes.

    This does not reject genuine parish weekly editions with 'safeguarding'
    in a notice; the exact document identity is required.
    """
    suspect = "kandle.ie/wp-content/uploads/2026/02/safeguarding-sunday-newsletter-2026.pdf"
    good = []
    rejected = []
    for row in report.get("downloaded") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").lower()
        if suspect not in url:
            good.append(row)
            continue
        rejected.append({
            "parish": row.get("parish"),
            "display_name": row.get("display_name"),
            "url": row.get("url"),
            "error": "Generic February diocesan Safeguarding Sunday file is not a current parish newsletter",
            "reason": "diocesan_admin_document_false_positive",
        })
    if not rejected:
        return 0
    report["downloaded"] = good
    report.setdefault("failed", []).extend(rejected)
    summary = report.setdefault("summary", {})
    summary["downloaded"] = len(good)
    summary["failed"] = len(report["failed"])
    summary["diocesan_admin_rejected"] = len(rejected)
    return len(rejected)
