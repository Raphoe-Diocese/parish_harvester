"""Reject non-bulletin diocesan directory pages mislabelled as HTML PDFs.

Only blocks known diocese *directory* HTML captures, not actual downloadable
PDFs or genuine parish newsletter articles. Used at harvest and mega stitch.
"""
from __future__ import annotations

from urllib.parse import urlparse
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
