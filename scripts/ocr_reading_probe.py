"""Score three parish PDFs with the real reader. No mega PDF. No full harvest.

Annagry and Gortahork are image pages, so this calls vision.
Newtown & Killea is typed, so embedded text is enough.
Exits 1 when any reading fails. Prints every missing line.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ocr.convert_bulletin import (  # noqa: E402
    ocr_selected_images_with_fallbacks,
    pdf_images_for_pages,
)
from ocr.reading_check import (  # noqa: E402
    ANNAGRY_BANNED,
    ANNAGRY_MUST,
    GORT_MUST,
    NEWTOWN_MUST,
    fold_reading,
    score_reading,
)
from ocr.sparse_page_ocr import (  # noqa: E402
    choose_vision_page_indexes,
    merge_vision_into_pages,
)
from ocr.text_extract import extract_all_page_lines  # noqa: E402

CASES = [
    (
        "Annagry",
        ROOT / "docs" / "parishes" / "raphoe" / "annagryparish.pdf",
        ANNAGRY_MUST,
        ANNAGRY_BANNED,
    ),
    (
        "Gortahork",
        ROOT / "docs" / "parishes" / "raphoe" / "gort-a-choirce.pdf",
        GORT_MUST,
        [],
    ),
    (
        "Newtown & Killea",
        ROOT / "docs" / "parishes" / "raphoe" / "newtownkilleaparish.pdf",
        NEWTOWN_MUST,
        [],
    ),
]


def read_pdf(path: Path) -> tuple[str, str]:
    native = extract_all_page_lines(path) or []
    indexes = choose_vision_page_indexes(native)
    if indexes == []:
        text = "\n".join("\n".join(page) for page in native)
        return text, "embedded"
    page_indexes = list(range(len(native))) if indexes is None else list(indexes)
    images = pdf_images_for_pages(str(path), page_indexes)
    vision_pages, provider = ocr_selected_images_with_fallbacks(images)
    if not vision_pages:
        text = "\n".join("\n".join(page) for page in native)
        return text, "vision-failed"
    merged = merge_vision_into_pages(
        [list(page) for page in native], page_indexes, vision_pages
    )
    text = "\n".join("\n".join(page) for page in merged)
    return text, provider or "vision"


def main() -> int:
    failed = 0
    lines: list[str] = []
    for name, path, must, banned in CASES:
        if not path.is_file():
            failed += 1
            lines.append(f"{name}: FAIL — PDF missing ({path.name})")
            continue
        text, provider = read_pdf(path)
        score = score_reading(text, must, banned)
        mark = "PASS" if score.ok else "FAIL"
        if not score.ok:
            failed += 1
        lines.append(f"{name}: {mark} via {provider}")
        if score.missing:
            lines.append("  missing: " + "; ".join(score.missing))
        if score.banned_hits:
            lines.append("  banned: " + "; ".join(score.banned_hits))
        if not score.ok:
            lines.append("  read: " + fold_reading(text)[:700])
    report = "\n".join(lines)
    print(report)
    out = ROOT / "ocr-reading-probe.txt"
    out.write_text(report + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
