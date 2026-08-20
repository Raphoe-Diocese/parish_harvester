"""Inject the in-page PDF.js viewer script into existing bulletin HTML pages.

Uses binary I/O so Windows CRLF line endings are preserved (avoids huge noisy diffs).
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "docs"
MARKERS = (b"pdf-inpage-viewer.js", b"pdf-mobile-fallback.js")
TAG = b'<script src="/assets/pdf-inpage-viewer.js" defer></script>\n'


def needs_pdf_embed(data: bytes) -> bool:
    return (
        b"pdf-frame-wrap" in data
        or b'class="pdf-frame"' in data
        or b"class='pdf-frame'" in data
    )


def already_has_script(data: bytes) -> bool:
    return any(marker in data for marker in MARKERS)


def main() -> None:
    changed = 0
    skipped = 0
    missing_body = 0
    for path in sorted(ROOT.rglob("*.html")):
        data = path.read_bytes()
        if not needs_pdf_embed(data):
            continue
        if already_has_script(data):
            skipped += 1
            continue
        lower = data.lower()
        idx = lower.rfind(b"</body>")
        if idx < 0:
            missing_body += 1
            print(f"NO </body>: {path}")
            continue
        path.write_bytes(data[:idx] + TAG + data[idx:])
        changed += 1
    print(f"changed={changed} already_had_script={skipped} missing_body={missing_body}")


if __name__ == "__main__":
    main()
