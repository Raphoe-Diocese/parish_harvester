"""Shrink mega PDFs for phones and put page 1 at the front of the file.

Keeps the same page count. Ghostscript downsample (~100 dpi) plus
``FastWebView`` (linearize) when ``gs`` is installed. Falls back to
PyMuPDF deflate. Never replaces the file if the result is bigger, invalid,
or a different number of pages.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

_MIN_PDF = b"%PDF-"


def _page_count(path: Path) -> int:
    import fitz

    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def _is_pdf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(5) == _MIN_PDF
    except OSError:
        return False


def _ghostscript_bin() -> str | None:
    for name in ("gs", "gswin64c", "gswin32c"):
        if shutil.which(name):
            return name
    return None


def _ghostscript_cmd(bin_name: str, src: Path, dest: Path) -> list[str]:
    return [
        bin_name,
        "-sDEVICE=pdfwrite",
        "-dCompatibilityLevel=1.4",
        "-dPDFSETTINGS=/ebook",
        "-dDownsampleColorImages=true",
        "-dDownsampleGrayImages=true",
        "-dColorImageDownsampleType=/Bicubic",
        "-dGrayImageDownsampleType=/Bicubic",
        "-dColorImageResolution=100",
        "-dGrayImageResolution=100",
        "-dFastWebView=true",
        "-dNOPAUSE",
        "-dQUIET",
        "-dBATCH",
        f"-sOutputFile={dest}",
        str(src),
    ]


def _run_ghostscript(src: Path, dest: Path) -> bool:
    bin_name = _ghostscript_bin()
    if not bin_name:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = _ghostscript_cmd(bin_name, src, dest)
    try:
        subprocess.run(cmd, check=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        return False
    return dest.is_file() and dest.stat().st_size > 0


def _run_pymupdf(src: Path, dest: Path) -> bool:
    import fitz

    doc = fitz.open(src)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        doc.save(dest, deflate=True, garbage=4, clean=True)
    except Exception:
        return False
    finally:
        doc.close()
    return dest.is_file() and dest.stat().st_size > 0


def compress_pdf_inplace(path: Path | str) -> bool:
    """Replace *path* with a smaller same-page-count PDF when possible."""
    path = Path(path)
    if not path.is_file() or not _is_pdf(path):
        return False
    before = path.stat().st_size
    try:
        pages_before = _page_count(path)
    except Exception:
        return False
    if pages_before < 1:
        return False

    with tempfile.TemporaryDirectory(prefix="pp-pdf-") as tmp:
        dest = Path(tmp) / path.name
        made = _run_ghostscript(path, dest)
        if not made:
            made = _run_pymupdf(path, dest)
        if not made or not _is_pdf(dest):
            return False
        after = dest.stat().st_size
        if after < 32 or after >= before:
            return False
        try:
            if _page_count(dest) != pages_before:
                return False
        except Exception:
            return False
        shutil.copy2(dest, path)
        print(f"     Compressed    : {before // 1024} KB → {after // 1024} KB")
        return True
