"""Reject non-bulletin diocesan directory pages mislabelled as HTML PDFs.

Only blocks known diocese *directory* HTML captures, not actual downloadable
PDFs or genuine parish newsletter articles. Used at harvest and mega stitch.
"""
from __future__ import annotations

from urllib.parse import urlparse
from datetime import date, timedelta
from pathlib import Path
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


def reject_future_dated_downloads(
    report: dict, *, current_dir: Path | None = None
) -> int:
    """Reject unproved future issues, while retaining a verified weekly range.

    A weekly bulletin can be dated at the end of its coverage range (for
    example 20–28 November) even though it contains the target Sunday. Keep
    that exception narrow: the issue date must be within seven days, and the
    saved PDF must explicitly show the target Sunday and a Mass time.
    """
    try:
        target = date.fromisoformat(str(report.get("target_date") or ""))
    except ValueError:
        return 0

    if current_dir is None:
        repo_current = Path(__file__).resolve().parent.parent / "Bulletins" / "current"
        current_dir = repo_current if repo_current.is_dir() else None

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

        pdf_path = None
        if current_dir is not None:
            key = str(row.get("parish") or "").strip()
            file_name = str(row.get("file") or f"{key}.pdf").strip() or f"{key}.pdf"
            for candidate in (
                Path(current_dir) / file_name,
                Path(current_dir) / f"{key}.pdf",
                Path(current_dir).parent / f"{key}.pdf",
            ):
                if candidate.is_file():
                    pdf_path = candidate
                    break

        if (
            issue <= target + timedelta(days=7)
            and pdf_path is not None
        ):
            from .bulletin_freshness import _issue_schedule_covers_target_sunday

            if _issue_schedule_covers_target_sunday(pdf_path, target, issue):
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
    suspects = {
        "kandle.ie/wp-content/uploads/2026/02/safeguarding-sunday-newsletter-2026.pdf": (
            "Generic February diocesan Safeguarding Sunday file is not a current parish newsletter",
            "diocesan_admin_document_false_positive",
        ),
        "kincasslagh.ie/app/uploads/2017/07/april-easter-2014.pdf": (
            "Historical 2014 Kincasslagh PDF is not a current weekly bulletin",
            "historical_bulletin_false_positive",
        ),
    }
    good = []
    rejected = []
    for row in report.get("downloaded") or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").lower()
        matched = next((details for marker, details in suspects.items() if marker in url), None)
        if matched is None:
            good.append(row)
            continue
        error, reason = matched
        rejected.append({
            "parish": row.get("parish"),
            "display_name": row.get("display_name"),
            "url": row.get("url"),
            "error": error,
            "reason": reason,
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
