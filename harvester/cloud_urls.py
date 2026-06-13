"""
cloud_urls.py — Normalize Google Drive, OneDrive, and SharePoint embed URLs.

Public files only. Password-protected or login-gated files cannot be fetched
without operator credentials (not supported).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

_GDRIVE_FILE_RE = re.compile(r"drive\.google\.com/file/d/([^/?#]+)")
_GDRIVE_OPEN_RE = re.compile(r"drive\.google\.com/open\?[^#]*\bid=([^&#]+)")
_GDRIVE_UC_RE = re.compile(r"drive\.google\.com/uc\?[^#]*\bid=([^&#]+)")
_ONEDRIVE_SHARE_RE = re.compile(
    r"(?:1drv\.ms|onedrive\.live\.com|sharepoint\.com|officeapps\.live\.com)",
    re.IGNORECASE,
)


def unwrap_docs_viewer_url(url: str) -> str:
    """Extract embedded file URL from Google Docs viewer / gview wrappers."""
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "docs.google.com" not in host:
        return url
    if "viewer" not in parsed.path and "viewerng" not in parsed.path and "gview" not in parsed.path:
        return url
    raw = parse_qs(parsed.query).get("url", [""])[0].strip()
    return unquote(raw) if raw else url


def rewrite_gdrive_download_url(url: str) -> str:
    """Convert Google Drive view/share URLs to direct download when possible."""
    text = unwrap_docs_viewer_url(url)
    for pattern in (_GDRIVE_FILE_RE, _GDRIVE_OPEN_RE, _GDRIVE_UC_RE):
        match = pattern.search(text)
        if match:
            file_id = match.group(1)
            return (
                "https://drive.usercontent.google.com/download"
                f"?id={file_id}&export=download"
            )
    return text


def is_cloud_document_url(url: str) -> bool:
    lower = rewrite_gdrive_download_url(url).lower()
    if lower.endswith(".pdf") or lower.endswith(".docx"):
        return True
    markers = (
        "drive.google.com/",
        "docs.google.com/viewer",
        "docs.google.com/gview",
        "1drv.ms/",
        "onedrive.live.com/",
        "sharepoint.com/",
        "officeapps.live.com/op/",
    )
    return any(m in lower for m in markers)


def normalize_document_url(url: str) -> str:
    """Best-effort direct URL for harvester download."""
    text = (url or "").strip()
    if not text:
        return text
    text = unwrap_docs_viewer_url(text)
    text = rewrite_gdrive_download_url(text)
    # OneDrive short links and SharePoint embeds often need browser navigation;
    # return as-is so Playwright can follow redirects.
    if _ONEDRIVE_SHARE_RE.search(text):
        return text
    return text
