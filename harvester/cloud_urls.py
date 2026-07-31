"""
cloud_urls.py — Normalize Google Drive, OneDrive, and SharePoint embed URLs.

Public files only. Password-protected or login-gated files cannot be fetched
without operator credentials (not supported).
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, unquote, urlparse

_GDRIVE_FILE_RE = re.compile(r"drive\.google\.com/(?:a/[^/]+/)?file/d/([^/?#]+)")
_GDRIVE_OPEN_RE = re.compile(r"drive\.google\.com/open\?[^#]*\bid=([^&#]+)")
_GDRIVE_UC_RE = re.compile(r"drive\.google\.com/uc\?[^#]*\bid=([^&#]+)")
_ONEDRIVE_SHARE_RE = re.compile(
    r"(?:1drv\.ms|onedrive\.live\.com|sharepoint\.com|officeapps\.live\.com)",
    re.IGNORECASE,
)


def unwrap_docs_viewer_url(url: str) -> str:
    """Extract embedded file URL from pdf.js / Google Docs viewer wrappers."""
    text = (url or "").strip()
    if not text:
        return text

    parsed = urlparse(text)
    path_lower = parsed.path.lower()
    if "viewer.html" in path_lower or "/pdfjs/" in path_lower:
        raw = parse_qs(parsed.query).get("file", [""])[0].strip()
        if raw:
            return unquote(raw)

    host = parsed.netloc.lower()
    if "docs.google.com" not in host:
        return text
    if "viewer" not in parsed.path and "viewerng" not in parsed.path and "gview" not in parsed.path:
        return text
    raw = parse_qs(parsed.query).get("url", [""])[0].strip()
    return unquote(raw) if raw else text


def rewrite_gdrive_download_url(url: str) -> str:
    """Convert Google Drive view/share URLs to direct download when possible."""
    text = unwrap_docs_viewer_url(url)
    for pattern in (_GDRIVE_FILE_RE, _GDRIVE_OPEN_RE, _GDRIVE_UC_RE):
        match = pattern.search(text)
        if match:
            file_id = match.group(1)
            download_url = (
                "https://drive.usercontent.google.com/download"
                f"?id={file_id}&export=download"
            )
            # Shared-drive / restricted files sometimes need the resourcekey
            # from the original share URL or the download returns an
            # error/permission page instead of the PDF.
            resourcekey = parse_qs(urlparse(text).query).get("resourcekey", [""])[0].strip()
            if resourcekey:
                download_url += f"&resourcekey={resourcekey}"
            return download_url
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


def gdrive_view_url(file_id: str) -> str:
    token = (file_id or "").strip()
    if not token:
        return ""
    return f"https://drive.google.com/file/d/{token}/view"


def gdrive_file_id_from_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    for pattern in (_GDRIVE_FILE_RE, _GDRIVE_OPEN_RE, _GDRIVE_UC_RE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    parsed = urlparse(text)
    if "drive.usercontent.google.com" in parsed.netloc.lower():
        return parse_qs(parsed.query).get("id", [""])[0].strip()
    return ""


def gdrive_confirm_token(html: str) -> str:
    text = html or ""
    for pattern in (
        r"confirm=([0-9A-Za-z_]+)",
        # Attribute order on the interstitial's hidden input isn't guaranteed
        # (e.g. name="confirm" type="hidden" value="t") — match value="..."
        # anywhere after name="confirm" rather than requiring them adjacent.
        r'name="confirm"[^>]*value="([0-9A-Za-z_]+)"',
        r"download_warning[^\"']*confirm=([0-9A-Za-z_]+)",
        r"uc-download-link[^>]+href=\"[^\"]*confirm=([0-9A-Za-z_]+)",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def gdrive_confirm_uuid(html: str) -> str:
    """Extract the large-file virus-scan interstitial's ``uuid`` field.

    Modern Drive confirm pages require both ``confirm`` and ``uuid`` on the
    retry request; without ``uuid`` the retry can still return the
    interstitial HTML instead of the file.
    """
    text = html or ""
    for pattern in (
        r"uuid=([-\w]+)",
        r'name="uuid"[^>]*value="([-\w]+)"',
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def gdrive_download_url_with_confirm(url: str, confirm: str, uuid: str = "") -> str:
    base = normalize_document_url(url)
    token = (confirm or "").strip()
    if not base or not token:
        return base
    joiner = "&" if "?" in base else "?"
    if f"confirm={token}" not in base:
        base = f"{base}{joiner}confirm={token}"
    uuid_token = (uuid or "").strip()
    if uuid_token and f"uuid={uuid_token}" not in base:
        base = f"{base}&uuid={uuid_token}"
    return base
