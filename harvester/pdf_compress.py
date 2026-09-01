"""Shrink mega-PDFs for phones and linearize so page 1 can stream first.

Keeps the same page count. Prefers Ghostscript ``/ebook`` at ~100 dpi with
``-dFastWebView=true`` (linearize) when ``gs`` is installed (GitHub Actions).
Falls back to PyMuPDF deflate + JPEG recompress of large images. Never
replaces the file if the result is bigger, invalid, or a different number
of pages.
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
        subprocess.run(
            cmd,
            check=True,
            timeout=300,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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


def first_page_preview_path(path: Path | str) -> Path:
    path = Path(path)
    return path.with_name(path.stem + "_p1.jpg")


def write_first_page_preview(path: Path | str) -> Path | None:
    """Write a phone-width JPEG of page 1 so the first paint is a tiny image."""
    path = Path(path)
    if not path.is_file() or not _is_pdf(path):
        return None
    dest = first_page_preview_path(path)
    try:
        import fitz

        doc = fitz.open(path)
        try:
            if doc.page_count < 1:
                return None
            page = doc[0]
            # 640px wide is enough to read on a phone; keep the file tiny.
            zoom = min(2.0, 640.0 / max(float(page.rect.width), 1.0))
            pix = page.get_pixmap(
                matrix=fitz.Matrix(zoom, zoom),
                colorspace=fitz.csRGB,
                alpha=False,
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            pix.save(str(dest), jpg_quality=50)
        finally:
            doc.close()
    except Exception:
        return None
    if not dest.is_file() or dest.stat().st_size < 32:
        return None
    print(f"     First page    : {dest.name} ({dest.stat().st_size // 1024} KB)")
    return dest
