#!/usr/bin/env python3
# Requires: pip install openai pdf2image Pillow mistralai
import os
import base64
import io
import re
import html as html_utils
import sys

from ocr.bulletin_layout import split_heading_prefix
from ocr.sparse_page_ocr import choose_vision_page_indexes, merge_vision_into_pages
from ocr.text_extract import (
    extract_all_page_lines,
    extract_text_pages,
    prefer_embedded_page_text,
)

# Keep in sync with ocr.generate_bulletin_pages.ocr_reading_css (presentation only).
CSS = """
<style>
  html, body {
    margin: 0;
    padding: 0;
    overflow-x: hidden;
    background: #eef1f0;
    color: #1a1f1e;
  }
  .scrollable-viewer {
    max-width: min(72ch, 100%);
    margin: 0 auto;
    background: #eef1f0;
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, "Times New Roman", Times, serif;
    font-size: 1.125rem;
    line-height: 1.65;
    padding: 22px 26px 36px;
    overflow-wrap: anywhere;
    word-wrap: break-word;
    -webkit-text-size-adjust: 100%;
  }
  .page-label {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin: 1.6em 0 0.55em;
    color: #5a6a68;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .page-label:first-child {
    margin-top: 0;
  }
  .ocr-failed-banner {
    margin: 12px 0;
    padding: 12px 14px;
    background: #fff4df;
    border: 1px solid #f5d08d;
    border-radius: 8px;
    color: #713f12;
    font-weight: 600;
    font-size: 0.9rem;
    line-height: 1.45;
  }
  p {
    margin: 0 0 0.9em;
  }
  hr {
    margin: 1.35em 0;
    border: none;
    border-top: 1px solid #d4ddd9;
  }
  .b-title {
    font-size: 1.28em;
    font-weight: 700;
    color: #0f2b5b;
    margin: 1.5em 0 0.45em;
    border-bottom: 2px solid #c5d0c9;
    padding-bottom: 0.18em;
    line-height: 1.3;
  }
  .ocr-parish-masthead {
    margin: 2.1em 0 1.15em;
    padding: 0.85em 0 0.7em;
    border-top: 3px solid #14524f;
    border-bottom: 1px solid #c5d0c9;
  }
  .ocr-parish-masthead:first-child { margin-top: 0; }
  .ocr-parish-name {
    font-family: Georgia, "Iowan Old Style", "Palatino Linotype", Palatino, "Times New Roman", Times, serif;
    font-size: 1.45em;
    font-weight: 700;
    letter-spacing: 0.02em;
    color: #14524f;
    margin: 0 0 0.2em;
    line-height: 1.25;
  }
  .ocr-parish-date {
    margin: 0;
    font-size: 0.88rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: #5a6a68;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .b-head {
    font-size: 1.12em;
    font-weight: 700;
    color: #134e9c;
    margin: 1.45em 0 0.5em;
    padding-bottom: 0.12em;
    border-bottom: 1px solid #d4ddd9;
    line-height: 1.35;
  }
  .b-sub {
    font-size: 1.04em;
    font-weight: 700;
    color: #1f6f4a;
    margin: 0.95em 0 0.3em;
    line-height: 1.35;
  }
  strong { color: #0f2b5b; }
  a { color: #1a6b6b; font-weight: 600; overflow-wrap: anywhere; }
  table.b-table {
    border-collapse: collapse;
    width: 100%;
    max-width: 100%;
    margin: 0.55em 0 1em;
    font-size: 0.95em;
    display: block;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
  }
  table.b-table td, table.b-table th {
    border: 1px solid #c9d4cf;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
  }
  table.b-table th {
    background: #e4ebe8;
    color: #0f2b5b;
  }
  table.b-table tr:nth-child(even) td {
    background: #f7f9f8;
  }
  @media (max-width: 600px) {
    .scrollable-viewer {
      padding: 16px 14px 28px;
    }
  }
</style>
"""

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Parish Bulletin {date}</title>
  {css}
</head>
<body>
<div class="scrollable-viewer">
{content}
</div>
</body>
</html>
"""

OCR_PROMPT = (
    "Extract this parish bulletin PDF page as clean, human-readable Markdown. "
    "Focus on readability and preserving the document structure. "
    "Irish Catholic bulletins may mix English and Irish (Gaeilge) — preserve both faithfully; never translate. "
    "Do NOT wrap the response in markdown code fences or backticks. "
    "Do NOT include image references like !img-0.jpeg. "
    "Do NOT summarise, rewrite, invent, rephrase, or autocorrect content. "
    "Mass times, church names, deceased names, and personal names (including Mc/Mac/O'/Ní) must be letter-perfect. "
    "Never guess a name, date, or mass time — if illegible write [illegible]. "
    "Do NOT repeat words or headings (never ORDINARYORDINARY or word word). "
    "\nInstructions:\n"
    "- Preserve the correct reading order.\n"
    "- Correctly process multi-column layouts.\n"
    "- Read columns separately before moving to the next column (top-to-bottom within a column, then left-to-right).\n"
    "- Preserve headings and section titles.\n"
    "- Merge broken lines into complete paragraphs.\n"
    "- Remove unnecessary line breaks.\n"
    "- Correct spacing errors caused by OCR (only spacing — never change letters).\n"
    "- Preserve bullet points and numbered lists.\n"
    "- Preserve tables where possible (markdown tables with a header row).\n"
    "- Preserve dates, times, phone numbers, email addresses and web links exactly.\n"
    "- Remove page numbers.\n"
    "- Remove repeated headers and footers.\n"
    "- Remove scanning artefacts.\n"
    "- Remove decorative elements that do not contain information.\n"
    "- Keep content grouped under its original heading.\n"
    "- Use consistent spacing between sections (one blank line between major blocks).\n"
    "\nFormatting:\n"
    "# Main Title\n"
    "## Section Heading\n"
    "### Subsection Heading\n"
    "Use short readable paragraphs.\n"
    "Output clean publication-quality Markdown suitable for display in a modern document viewer."
)

MARKDOWN_FENCE_PATTERN = re.compile(r"^\s*```(?:[A-Za-z0-9_-]+)?\s*$")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_PATTERN = re.compile(r"(?<!@)\b(?:https?://|www\.)[^\s<>\"]+", re.IGNORECASE)
DIGITS_ONLY_PATTERN = re.compile(r"\D")
# Irish + NI/UK phone formats commonly seen on parish bulletins.
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:"
    r"\+353[\s.-]*\d{1,2}[\s.-]*\d{3}[\s.-]*\d{4}"
    r"|\+44[\s.-]*\d{2,4}[\s.-]*\d{3,4}[\s.-]*\d{3,4}"
    r"|0(?:28|74|1\d|2\d|4\d|5\d|6\d|7\d|8\d|9\d)"
    r"[\s.-]*\d{2,4}[\s.-]*\d{3,5}"
    r")(?!\w)"
)
HEADING_MD_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
HR_MD_PATTERN = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
BOLD_MD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
_WORD_DUP_RE = re.compile(r"\b([A-Za-zÀ-ÿ0-9'’&./+-]{2,})\b(?:\s+\1\b)+", re.IGNORECASE)
_ORDINAL_DUP_RE = re.compile(r"\b(\d{2,})\1(st|nd|rd|th)\b", re.IGNORECASE)
_SPACE_ORDINAL_RE = re.compile(r"\b(\d)\s+(\d)(st|nd|rd|th)\b", re.IGNORECASE)
_WORD_TH_DUP_RE = re.compile(
    r"\b([A-Za-zÀ-ÿ]{3,})(st|nd|rd|th)\s+\1\b", re.IGNORECASE
)
_PUNCT_DUP_RE = re.compile(r"([.,;:!?\u2019'])\1+")
_PHRASE_DUP_RE = re.compile(
    r"\b((?:[A-Za-zÀ-ÿ0-9'’&./+-]+(?:\s+[A-Za-zÀ-ÿ0-9'’&./+-]+){1,6}))\s+\1\b",
    re.IGNORECASE,
)
# Mistral OCR emits image placeholders like ![img-0.jpeg](img-0.jpeg); strip them.
IMAGE_MD_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def pdf_to_images(pdf_path):
    from pdf2image import convert_from_path

    return convert_from_path(pdf_path, dpi=150)


def pdf_images_for_pages(pdf_path, indexes_0based):
    from pdf2image import convert_from_path

    images = []
    for index in indexes_0based:
        images.extend(
            convert_from_path(pdf_path, dpi=150, first_page=index + 1, last_page=index + 1)
        )
    return images


def ocr_selected_images_with_fallbacks(images):
    """Gemini, then GitHub Models, then OpenAI — sparse pages only."""
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    github_token = os.environ.get("GITHUB_TOKEN")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if gemini_api_key:
        print("Sparse-page image OCR via Gemini ...")
        try:
            return ocr_images_with_gemini(images)
        except Exception as e:
            print(f"  Gemini OCR failed ({type(e).__name__}: {e}).")
    if github_token:
        print("Sparse-page image OCR via GitHub Models ...")
        try:
            return ocr_images_with_github_models(images)
        except Exception as e:
            print(f"  GitHub Models OCR failed ({type(e).__name__}: {e}).")
    if openai_api_key:
        print("Sparse-page image OCR via OpenAI ...")
        try:
            return ocr_images_with_openai(images)
        except Exception as e:
            print(f"  OpenAI OCR failed ({type(e).__name__}: {e}).")
    return None, None


def ocr_with_mistral(pdf_path):
    """Run Mistral OCR on a PDF and return list of page strings."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set.")

    try:
        from mistralai import Mistral
    except ImportError:
        from mistralai.client import Mistral

    client = Mistral(api_key=api_key)

    with open(pdf_path, "rb") as f:
        pdf_data = base64.standard_b64encode(f.read()).decode("utf-8")

    ocr_response = client.ocr.process(
        model="mistral-ocr-latest",
        document={
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{pdf_data}",
        },
    )

    pages = []
    for page in ocr_response.pages:
        text = page.markdown or ""
        lines = [
            line for line in text.splitlines()
            if line.strip() and not MARKDOWN_FENCE_PATTERN.match(line)
        ]
        pages.append("\n".join(lines))
    return pages


def _image_png_bytes(image) -> bytes:
    """pdf2image often yields PPM. Gemini rejects image/x-portable-pixmap."""
    buffer = io.BytesIO()
    to_save = image
    mode = getattr(image, "mode", None)
    if mode not in ("RGB", "RGBA", "L"):
        to_save = image.convert("RGB")
    to_save.save(buffer, format="PNG")
    return buffer.getvalue()


def _image_to_base64_png(image):
    return base64.b64encode(_image_png_bytes(image)).decode("utf-8")


def ocr_images_with_gemini(images):
    """Run Gemini OCR across images and return (pages_text, provider_summary)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    pages_text = []
    for i, image in enumerate(images, start=1):
        print(f"  OCR on page {i}/{len(images)} via Gemini ...", flush=True)
        response = model.generate_content(
            [OCR_PROMPT, {"mime_type": "image/png", "data": _image_png_bytes(image)}]
        )
        text = getattr(response, "text", "") or ""
        lines = [
            line for line in text.splitlines()
            if line.strip() and not MARKDOWN_FENCE_PATTERN.match(line)
        ]
        pages_text.append(lines)
    return pages_text, "Gemini fallback"


def ocr_images_with_github_models(images):
    """Run GitHub Models OCR across images (free in Actions) and return (pages_text, provider_summary)."""
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise RuntimeError("GITHUB_TOKEN is not set.")

    from openai import OpenAI

    client = OpenAI(
        api_key=github_token,
        base_url="https://models.inference.ai.azure.com",
    )
    pages_text = []
    for i, image in enumerate(images, start=1):
        print(f"  OCR on page {i}/{len(images)} via GitHub Models ...", flush=True)
        b64 = _image_to_base64_png(image)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        )
        text = response.choices[0].message.content or ""
        lines = [
            line for line in text.splitlines()
            if line.strip() and not MARKDOWN_FENCE_PATTERN.match(line)
        ]
        pages_text.append(lines)
    return pages_text, "GitHub Models fallback"


def ocr_images_with_openai(images):
    """Run OpenAI OCR across images and return (pages_text, provider_summary)."""
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    from openai import OpenAI

    client = OpenAI(api_key=openai_api_key)
    pages_text = []
    for i, image in enumerate(images, start=1):
        print(f"  OCR on page {i}/{len(images)} via OpenAI ...", flush=True)
        b64 = _image_to_base64_png(image)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": OCR_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
        )
        text = response.choices[0].message.content or ""
        lines = [
            line for line in text.splitlines()
            if line.strip() and not MARKDOWN_FENCE_PATTERN.match(line)
        ]
        pages_text.append(lines)
    return pages_text, "OpenAI fallback"


def to_tel_href(display):
    """Normalize matched phone display text to tel: href (+353 IE, +44 UK/NI)."""
    digits = DIGITS_ONLY_PATTERN.sub("", display)
    if not digits:
        return None
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("353"):
        national = digits[3:].lstrip("0")
        return f"+353{national}" if national else None
    if digits.startswith("44"):
        national = digits[2:].lstrip("0")
        return f"+44{national}" if national else None
    if digits.startswith("028"):
        # Northern Ireland landline → +44 28…
        return f"+44{digits[1:]}"
    if digits.startswith("0"):
        national = digits[1:]
        if national:
            return f"+353{national}"
    return None


def collapse_glued_duplicate_token(token: str) -> str:
    """ORDINARYORDINARY / REST IN PEACE.REST → single copy when halves match."""
    raw = token.strip()
    if len(raw) < 8:
        return token
    # Exact doubled token (no space): ABAB where A==B
    n = len(raw)
    if n % 2 == 0:
        half = n // 2
        a, b = raw[:half], raw[half:]
        if a.lower() == b.lower():
            return a
    # Doubled with trailing punctuation on both halves: WORD.WORD.
    for sep in (".", ",", ";", ":", "!", "?"):
        if sep in raw:
            parts = raw.split(sep)
            parts = [p for p in parts if p != ""]
            if len(parts) >= 2 and all(p.lower() == parts[0].lower() for p in parts):
                return parts[0] + (sep if raw.endswith(sep) else "")
    return token


# Born-digital PDF extractors often emit letter-spaced titles (P A R I S H)
# or mid-word splits (S unday, We e k, Fune ral). Spacing-only repairs — never
# change letters. Tuned against Ardara-style dumps (Frank 24/09/2026).
_KNOWN_SPACE_FRAGMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bS\s+unday\b", re.I), "Sunday"),
    (re.compile(r"\bS\s+undays\b", re.I), "Sundays"),
    (re.compile(r"\bSunda\s+y\b", re.I), "Sunday"),
    (re.compile(r"\bS\s+eptember\b", re.I), "September"),
    (re.compile(r"\bPARIS\s+HIONE\s+R\b", re.I), "PARISHIONER"),
    (re.compile(r"\bThe\s+PARIS\s+HIONE\s+R\b", re.I), "The PARISHIONER"),
    (re.compile(r"\bf\s+aithf\s+ul\b", re.I), "faithful"),
    (re.compile(r"\bWebsiteandhos\s*ting\b", re.I), "Website and hosting"),
    (re.compile(r"\bhos\s+ting\b", re.I), "hosting"),
    (re.compile(r"\bM\s+onday\b", re.I), "Monday"),
    (re.compile(r"\bT\s+uesday\b", re.I), "Tuesday"),
    (re.compile(r"\bW\s+ednesday\b", re.I), "Wednesday"),
    (re.compile(r"\bWe\s+dne\s+sday\b", re.I), "Wednesday"),
    (re.compile(r"\bT\s+hursday\b", re.I), "Thursday"),
    (re.compile(r"\bF\s+riday\b", re.I), "Friday"),
    (re.compile(r"\bS\s+aturday\b", re.I), "Saturday"),
    (re.compile(r"\bSa\s+tur\s+da\s+y\b", re.I), "Saturday"),
    # Letter-spaced function words (Ardara dump): w ho w as → who was
    (re.compile(r"\bw\s+ho\s+w\s+as\b", re.I), "who was"),
    (re.compile(r"\bw\s+ho\b", re.I), "who"),
    (re.compile(r"\bw\s+as\b", re.I), "was"),
    (re.compile(r"\bw\s+e\s+re\b", re.I), "were"),
    (re.compile(r"\bw\s+ere\b", re.I), "were"),
    (re.compile(r"\baw\s+ay\b", re.I), "away"),
    (re.compile(r"\be\s+v\s+e\s+ry\b", re.I), "every"),
    (re.compile(r"\bWe\s+e\s+k\s+e\s+nding\b", re.I), "Week ending"),
    (re.compile(r"\bWe\s+e\s+k\s+e\s+nd\b", re.I), "Weekend"),
    (re.compile(r"\bWe\s+e\s+k\b", re.I), "Week"),
    (re.compile(r"\bw\s+e\s+e\s+k\b", re.I), "week"),
    (re.compile(r"\bWeek\s+e\s+nding\b", re.I), "Week ending"),
    (re.compile(r"\bTw\s+e\s+nty\b", re.I), "Twenty"),
    (re.compile(r"\bS\s+e\s+pte\s+mbe\s+r\b", re.I), "September"),
    (re.compile(r"\bM\s+ass\b", re.I), "Mass"),
    (re.compile(r"\bO\s+rdinary\b", re.I), "Ordinary"),
    (re.compile(r"\bbe\s+ginning\b", re.I), "beginning"),
    (re.compile(r"\bBe\s+ginne\s+rs\b", re.I), "Beginners"),
    (re.compile(r"\bw\s+e\s+lcome\b", re.I), "welcome"),
    (re.compile(r"\bFune\s+ral\b", re.I), "Funeral"),
    (re.compile(r"\barrange\s+me\s+nts\b", re.I), "arrangements"),
    (re.compile(r"\blate\s+r\b", re.I), "later"),
    (re.compile(r"\bEt\s+ern\s+a\s+l\b", re.I), "Eternal"),
    (re.compile(r"\bSou\s+l\b", re.I), "Soul"),
    (re.compile(r"\bCh\s+rist\b", re.I), "Christ"),
    (re.compile(r"\bsa\s+n\s+ct\s+ify\b", re.I), "sanctify"),
    (re.compile(r"\bsa\s+ve\b", re.I), "save"),
    (re.compile(r"\bPa\s+ssion\b", re.I), "Passion"),
    (re.compile(r"\bst\s+ren\s+gthen\b", re.I), "strengthen"),
    (re.compile(r"\bIr\s+ish\b", re.I), "Irish"),
    (re.compile(r"\bD\s+a\s+ncing\b", re.I), "Dancing"),
    (re.compile(r"\bCla\s+sse\s+s\b", re.I), "Classes"),
    (re.compile(r"\bw\s+ith\b", re.I), "with"),
    (re.compile(r"\bC\s+e\s+ntre\b", re.I), "Centre"),
    (re.compile(r"\bEnv\s+elope\s+s\b", re.I), "Envelopes"),
    (re.compile(r"\bJe\s+ssie\b", re.I), "Jessie"),
    (re.compile(r"\bC\s+harle\s+s\b", re.I), "Charles"),
    (re.compile(r"\bC\s+unningham\b", re.I), "Cunningham"),
    (re.compile(r"\bS\s+e\s+attle\b", re.I), "Seattle"),
    (re.compile(r"\bw\s+hose\b", re.I), "whose"),
    (re.compile(r"\binte\s+rre\s+d\b", re.I), "interred"),
    (re.compile(r"\bC\s+athle\s+en\b", re.I), "Cathleen"),
    (re.compile(r"\bC\s+athle\s+e\s+n\b", re.I), "Cathleen"),
    (re.compile(r"\bMc\s*Ne\s+lis\b", re.I), "McNelis"),
    (re.compile(r"\benMcNe\s+lis\b", re.I), "en McNelis"),
    (re.compile(r"\bM\s+c\s+", re.I), "Mc"),
    (re.compile(r"\bburie\s+d\b", re.I), "buried"),
    (re.compile(r"\bw\s+ill\b", re.I), "will"),
    (re.compile(r"\bw\s+ish\b", re.I), "wish"),
    (re.compile(r"\bcov\s+e\s+r\b", re.I), "cover"),
    (re.compile(r"\by\s+our\b", re.I), "your"),
    (re.compile(r"\bgrav\s+e\s+s\b", re.I), "graves"),
    (re.compile(r"\bBonne\s+r\b", re.I), "Bonner"),
    (re.compile(r"\bC\s+annon\b", re.I), "Cannon"),
    (re.compile(r"\bS\s+chool\b", re.I), "School"),
    (re.compile(r"\bt\s+h\s+e\b", re.I), "the"),
    (re.compile(r"\bashe\s+s\b", re.I), "ashes"),
    (re.compile(r"\bashes?\s*were\s*in\b", re.I), "ashes were in"),
    (re.compile(r"\bashe\s+swerein\b", re.I), "ashes were in"),
    (re.compile(r"\bwere\s*in\b", re.I), "were in"),
    (re.compile(r"\bCathle\s+en\b", re.I), "Cathleen"),
    (re.compile(r"\bMc\s*Nelis\b", re.I), "McNelis"),
    (re.compile(r"\bMc\s+Nelis\b", re.I), "McNelis"),
    (re.compile(r"\bfam\s+ily\b", re.I), "family"),
    (re.compile(r"\byou\s+r\b", re.I), "your"),
    (re.compile(r"\bwoun\s+ds\b", re.I), "wounds"),
    (re.compile(r"\bpra\s+ise\b", re.I), "praise"),
    (re.compile(r"\bcome\s+t\s+o\b", re.I), "come to"),
    (re.compile(r"\bTha\s+t\b", re.I), "That"),
    (re.compile(r"\bAm\s+en\b", re.I), "Amen"),
    (re.compile(r"\bevera\s+n\s+d\b", re.I), "ever and"),
    (re.compile(r"\ben\s+emy\b", re.I), "enemy"),
    (re.compile(r"\bF\s+rom\b", re.I), "From"),
    (re.compile(r"\bEnv\s+e\s+lope\s+s\b", re.I), "Envelopes"),
    (re.compile(r"\bcallmeand\b", re.I), "call me and"),
    (re.compile(r"\bcall\s*me\s*and\b", re.I), "call me and"),
    (re.compile(r"\brsaints\s*Imay\b", re.I), "r saints I may"),
    (re.compile(r"\byoursaintsImay\b", re.I), "your saints I may"),
    (re.compile(r"\bImay\b", re.I), "I may"),
    (re.compile(r"\bpassa?\s*d\s*away\s*on\b", re.I), "passed away on"),
    (re.compile(r"\bpasse\s+dawayon\b", re.I), "passed away on"),
    (re.compile(r"\bwho\s*was\b", re.I), "who was"),
    (re.compile(r"\bwhowas\b", re.I), "who was"),
    (re.compile(r"\bbegwho\b", re.I), "beg who"),
    (re.compile(r"\bKilcloone\s+y\b", re.I), "Kilclooney"),
    (re.compile(r"\bTully\s+be\s+g\b", re.I), "Tullybeg"),
    (re.compile(r"\bbe\s+g\b", re.I), "beg"),
    (re.compile(r"\bAr\s+da\s+r\s+a\b", re.I), "Ardara"),
    (re.compile(r"\bM\s+e\s+e\s+ntashask\b", re.I), "Meentashask"),
    (re.compile(r"\bgra\s+nt\s+unto\s+them\b", re.I), "grant unto them"),
    (re.compile(r"\bgra\s*ntuntothem\b", re.I), "grant unto them"),
    (re.compile(r"\bgra\s+n\s+t\s+u\s+n\s+t\s+o\s+t\s+h\s+em\b", re.I), "grant unto them"),
    (re.compile(r"\bntuntothem\b", re.I), "unto them"),
    (re.compile(r"\bSchool\s+e\s+v\s+e\s+ry\b", re.I), "School every"),
    (re.compile(r"\bSchoole\s*very\b", re.I), "School every"),
    (re.compile(r"\bh\s+our\s+of\s+my\b", re.I), "hour of my"),
    (re.compile(r"\btheh\s*ourofmy\b", re.I), "the hour of my"),
    (re.compile(r"\bAt\s+theh\b", re.I), "At the"),
    (re.compile(r"\bpassed\s*awayon\b", re.I), "passed away on"),
    (re.compile(r"\bawayon\b", re.I), "away on"),
    (re.compile(r"\bashesw\s*erein\b", re.I), "ashes were in"),
    (re.compile(r"\bashes\s*w\s*erein\b", re.I), "ashes were in"),
    (re.compile(r"\bdefen\s+d\b", re.I), "defend"),
    (re.compile(r"\bsepa\s+ra\s+t\s+ed\b", re.I), "separated"),
    (re.compile(r"\bSu\s+ffer\b", re.I), "Suffer"),
    (re.compile(r"\bJ\s+esu\s+s\b", re.I), "Jesus"),
    (re.compile(r"\bh\s+ide\b", re.I), "hide"),
    (re.compile(r"\bWit\s+h\b", re.I), "With"),
    (re.compile(r"\bin\s+ebria\s+teme\b", re.I), "inebriate me"),
    (re.compile(r"\binebria\s*te\s*me\b", re.I), "inebriate me"),
    (re.compile(r"\bwashme\b", re.I), "wash me"),
    (re.compile(r"\bgthenme\b", re.I), "gthen me"),
    (re.compile(r"\bstrengthenme\b", re.I), "strengthen me"),
    (re.compile(r"\bhearme\b", re.I), "hear me"),
    (re.compile(r"\bdefen\s*dme\b", re.I), "defend me"),
    (re.compile(r"\bcallme\b", re.I), "call me"),
    (re.compile(r"\bdea\s+t\s+h\b", re.I), "death"),
    (re.compile(r"\bAmen\s*\.\b", re.I), "Amen."),
)


def _alpha_len(token: str) -> int:
    return len(re.sub(r"[^A-Za-zÀ-ÿ]", "", token or ""))


def _joinable_alpha_len(token: str) -> int:
    """Alpha length for short-token joining. Digits block joining (dates/ordinals)."""
    if not token or re.search(r"\d", token):
        return 0
    return _alpha_len(token)


def _apply_known_fragments(text: str) -> str:
    cleaned = text
    for pattern, repl in _KNOWN_SPACE_FRAGMENTS:
        if callable(repl):
            cleaned = pattern.sub(repl, cleaned)
        else:
            cleaned = pattern.sub(repl, cleaned)
    return cleaned


def collapse_ocr_spacing(text: str) -> str:
    """Fix letter-spaced / mid-split OCR without changing any letters."""
    if not text:
        return text
    cleaned = str(text)
    cleaned = _apply_known_fragments(cleaned)
    # Twenty -fourth → Twenty-fourth (space before hyphen only)
    cleaned = re.sub(r"(?<=\w)\s+-(?=\w)", "-", cleaned)
    # Letter glued to a clock time: y6.00pm / y9.30am
    cleaned = re.sub(
        r"([A-Za-zÀ-ÿ])(\d{1,2}[.:]\d{2}\s*(?:[ap]\.?m\.?))",
        r"\1 \2",
        cleaned,
        flags=re.I,
    )
    # am/pm glued to the next place name: 6.00pmArdara
    cleaned = re.sub(
        r"((?:[ap]\.?m\.?))([A-ZÀ-ÿ])",
        r"\1 \2",
        cleaned,
        flags=re.I,
    )
    # lowercase glued to Capital mid-sentence: themO
    cleaned = re.sub(r"([a-zà-ÿ])([A-ZÀ-Ÿ])", r"\1 \2", cleaned)
    # Missing space after . , ; : before a letter: me.Water / s,hearme
    cleaned = re.sub(r"([.,:;])([A-Za-zÀ-ÿ])", r"\1 \2", cleaned)
    # Trailing letter of a broken word: burie d / Kilcloone y / Sunda y / classe s.
    # Only join common *suffix* letters. Never join w/a/i/o/u (start of who/was/and/…).
    cleaned = re.sub(
        r"\b([A-Za-zÀ-ÿ]{3,})\s+([dysge])\b",
        r"\1\2",
        cleaned,
        flags=re.I,
    )
    # Do NOT join "A bhráithre" / "I am" — that breaks Irish and English.
    # Mc names still spaced: M c Gill → McGill
    cleaned = re.sub(r"\bM\s+c\s+", "Mc", cleaned, flags=re.I)
    cleaned = re.sub(r"\bMc\s+([A-ZÀ-Ÿ][a-zà-ÿ]*)", r"Mc\1", cleaned)
    # Spaced clock times: 7: 00 pm / 10: 30 am
    cleaned = re.sub(r"\b(\d{1,2})\s*:\s*(\d{2})\s*([ap]\.?m\.?)\b", r"\1:\2\3", cleaned, flags=re.I)
    cleaned = re.sub(r"\b(\d{1,2})\s*:\s*(\d{2})\b", r"\1:\2", cleaned)
    # 7 th → ordinal
    cleaned = re.sub(r"\b(\d{1,2})\s+(st|nd|rd|th)\b", r"\1\2", cleaned, flags=re.I)

    words = cleaned.split()
    if not words:
        return cleaned

    # Heavily fragmented lines: join runs of short alpha tokens (len <= 3).
    # Never join tokens that contain digits (17th, 6.00pm, etc.).
    alpha = [w for w in words if _joinable_alpha_len(w) > 0]
    short_ratio = (
        (sum(1 for w in alpha if _joinable_alpha_len(w) <= 3) / len(alpha))
        if alpha
        else 0.0
    )
    max_join = 3 if short_ratio >= 0.4 else 2
    min_run = 3 if short_ratio >= 0.4 else 4

    out: list[str] = []
    i = 0
    while i < len(words):
        j = i
        while j < len(words) and 1 <= _joinable_alpha_len(words[j]) <= max_join:
            j += 1
        if j - i >= min_run:
            out.append("".join(words[i:j]))
            i = j
            continue
        out.append(words[i])
        i += 1
    cleaned = " ".join(out)

    # Re-run known fragments after joining (Et ern a l → Eternal may need a second pass).
    cleaned = _apply_known_fragments(cleaned)
    # grantuntothem / unto themO leftovers after join
    cleaned = re.sub(r"\bgrantuntothem\b", "grant unto them", cleaned, flags=re.I)
    cleaned = re.sub(r"\bntuntothem\b", "unto them", cleaned, flags=re.I)
    # camelCase split (themO) but keep McGill / MacBride together
    cleaned = re.sub(r"([a-zà-ÿ])([A-ZÀ-Ÿ])", r"\1 \2", cleaned)
    cleaned = re.sub(r"\b(Mc|Mac|MC)\s+([A-ZÀ-Ÿ])", r"\1\2", cleaned)
    cleaned = re.sub(r"([.,:;])([A-Za-zÀ-ÿ])", r"\1 \2", cleaned)
    # who was / passed away style glues still left as one token
    cleaned = re.sub(r"\bwhowas\b", "who was", cleaned, flags=re.I)
    cleaned = re.sub(r"\bpassedawayon\b", "passed away on", cleaned, flags=re.I)
    cleaned = re.sub(r"\basheswerein\b", "ashes were in", cleaned, flags=re.I)
    cleaned = re.sub(r"\bashes were in interred\b", "ashes were interred", cleaned, flags=re.I)
    cleaned = re.sub(r"\bashesw\s*erein\b", "ashes were in", cleaned, flags=re.I)
    cleaned = re.sub(r"\bwerein\b", "were in", cleaned, flags=re.I)
    cleaned = re.sub(r"\bawayon\b", "away on", cleaned, flags=re.I)
    cleaned = re.sub(r"\bpassed\s+away\s+on\b", "passed away on", cleaned, flags=re.I)
    cleaned = re.sub(r"\bgran\s*t\s*untothem\b", "grant unto them", cleaned, flags=re.I)
    cleaned = re.sub(r"\bgrantunto\s*them\b", "grant unto them", cleaned, flags=re.I)
    cleaned = re.sub(r"\bSchoole\s*very\b", "School every", cleaned, flags=re.I)
    cleaned = re.sub(r"\btheh\s*ourofmy\b", "the hour of my", cleaned, flags=re.I)
    cleaned = re.sub(r"\bin\s+ebriat\s*eme\b", "inebriate me", cleaned, flags=re.I)
    cleaned = re.sub(r"\bbegwho\b", "beg who", cleaned, flags=re.I)
    cleaned = re.sub(r"\bwashme\b", "wash me", cleaned, flags=re.I)
    cleaned = re.sub(r"\bstrengthenme\b", "strengthen me", cleaned, flags=re.I)
    cleaned = re.sub(r"\bdefendme\b", "defend me", cleaned, flags=re.I)
    cleaned = re.sub(r"\bhearme\b", "hear me", cleaned, flags=re.I)
    cleaned = re.sub(r"\bcallmeand\b", "call me and", cleaned, flags=re.I)
    cleaned = re.sub(r"\bcallme\b", "call me", cleaned, flags=re.I)
    cleaned = re.sub(r"\binebriateme\b", "inebriate me", cleaned, flags=re.I)
    cleaned = re.sub(r"\bAtthehourofmy\b", "At the hour of my", cleaned, flags=re.I)
    cleaned = re.sub(r"\byoursaintsImay\b", "your saints I may", cleaned, flags=re.I)
    cleaned = re.sub(r"\bmenottobe\b", "me not to be", cleaned, flags=re.I)
    cleaned = re.sub(r"\bsepa\s*rated\b", "separated", cleaned, flags=re.I)
    cleaned = re.sub(r"\bWith\s+in\b", "Within", cleaned)
    cleaned = re.sub(r"\bF\s+or\b", "For", cleaned)
    cleaned = re.sub(r"\bMc\s+Nelis\b", "McNelis", cleaned)
    # Common letter-spaced function words left after fragment pass
    cleaned = re.sub(r"\ba\s+n\s+d\b", "and", cleaned, flags=re.I)
    cleaned = re.sub(r"\bt\s+o\b", "to", cleaned, flags=re.I)
    cleaned = re.sub(r"\bFor\s+ever\s+and\s+ever\b", "For ever and ever", cleaned)

    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned


def clean_ocr_line(text: str) -> str:
    """Remove common OCR duplication artefacts before HTML render."""
    if not text:
        return text
    cleaned = collapse_ocr_spacing(str(text))
    # 1717th → 17th
    cleaned = _ORDINAL_DUP_RE.sub(r"\1\2", cleaned)
    # 1 7th → 17th (common OCR split)
    cleaned = _SPACE_ORDINAL_RE.sub(r"\1\2\3", cleaned)
    # SUNDAYth SUNDAY → SUNDAY
    cleaned = _WORD_TH_DUP_RE.sub(r"\1", cleaned)
    # word word / short phrase phrase
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = _WORD_DUP_RE.sub(r"\1", cleaned)
        cleaned = _PHRASE_DUP_RE.sub(r"\1", cleaned)
    # Glued duplicates per whitespace token
    cleaned = " ".join(collapse_glued_duplicate_token(tok) for tok in cleaned.split(" "))
    # Also collapse whole-line glued duplicates with no spaces
    cleaned = collapse_glued_duplicate_token(cleaned)
    # Glued phrase repeats: WE PRAY FOR OUR DEADWE PRAY FOR OUR DEAD
    prev = None
    while prev != cleaned:
        prev = cleaned
        cleaned = re.sub(r"([A-Z][A-Z0-9'’ ]{4,60}?)\1", r"\1", cleaned)
    cleaned = _PUNCT_DUP_RE.sub(r"\1", cleaned)
    # ORDINARY TIME.ORDINARY TIME. → ORDINARY TIME.
    cleaned = re.sub(r"\b([A-Z][A-Z ]{2,40})\.\1\b", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned


def linkify(text):
    """Convert escaped text emails, URLs, and phone numbers into HTML links."""
    placeholders = []

    def stash(replacement):
        token = f"__LINKIFY_{len(placeholders)}__"
        placeholders.append(replacement)
        return token

    def split_trailing_punctuation(value):
        trailing = ""
        while value and value[-1] in ".,;:!?":
            trailing = value[-1] + trailing
            value = value[:-1]
        open_parens = value.count("(")
        close_parens = value.count(")")
        while value.endswith(")") and close_parens > open_parens:
            trailing = ")" + trailing
            value = value[:-1]
            close_parens -= 1
        return value, trailing

    def replace_email(match):
        email = match.group(0)
        escaped_email = html_utils.escape(email, quote=True)
        return stash(
            f'<a href="mailto:{escaped_email}" target="_blank" rel="noopener noreferrer">'
            f"{escaped_email}</a>"
        )

    def replace_url(match):
        url = match.group(0)
        trimmed_url, trailing = split_trailing_punctuation(url)
        href = trimmed_url if trimmed_url.startswith(("http://", "https://")) else f"https://{trimmed_url}"
        escaped_href = html_utils.escape(href, quote=True)
        escaped_text = html_utils.escape(trimmed_url)
        link = (
            f'<a href="{escaped_href}" target="_blank" rel="noopener noreferrer">'
            f"{escaped_text}</a>"
        )
        return f"{stash(link)}{trailing}"

    def replace_phone(match):
        phone = match.group(0)
        href = to_tel_href(phone)
        if not href:
            return phone
        escaped_phone = html_utils.escape(phone)
        escaped_href = html_utils.escape(href, quote=True)
        return stash(
            f'<a href="tel:{escaped_href}" style="color:#1d4ed8;font-weight:600;">'
            f"{escaped_phone}</a>"
        )

    linked = EMAIL_PATTERN.sub(replace_email, text)
    linked = URL_PATTERN.sub(replace_url, linked)
    linked = PHONE_PATTERN.sub(replace_phone, linked)

    for i, replacement in enumerate(placeholders):
        linked = linked.replace(f"__LINKIFY_{i}__", replacement)
    return linked


def _escape_html(value):
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _render_inline(text):
    """Escape one line of OCR text and apply bold + links."""
    text = clean_ocr_line(text)
    text = _escape_html(text)
    text = BOLD_MD_PATTERN.sub(r"<strong>\1</strong>", text)
    return linkify(text)


def _is_table_row(line):
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_table_separator(line):
    s = line.strip()
    return bool(re.fullmatch(r"\|?[\s:\-|]+\|?", s)) and "-" in s


def _table_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _render_table(rows):
    """Turn a block of markdown table rows into a styled HTML table."""
    has_header = any(_is_table_separator(r) for r in rows)
    body = [r for r in rows if not _is_table_separator(r)]
    if not body:
        return ""
    out = ['<table class="b-table">']
    for idx, row in enumerate(body):
        tag = "th" if has_header and idx == 0 else "td"
        cells = _table_cells(row)
        out.append("<tr>" + "".join(f"<{tag}>{_render_inline(c)}</{tag}>" for c in cells) + "</tr>")
    out.append("</table>")
    return "\n".join(out)


def render_markdown_lines(lines: list[str]) -> list[str]:
    """Render one page's OCR lines into HTML.

    Consecutive body lines become one ``<p>`` joined with ``<br>`` so the
    reader is not full of empty gaps (one paragraph tag per OCR line).
    """
    parts: list[str] = []
    body_buf: list[str] = []
    i = 0
    total = len(lines)

    def flush_body() -> None:
        nonlocal body_buf
        if not body_buf:
            return
        rendered = "<br>\n".join(_render_inline(line) for line in body_buf)
        parts.append(f"<p>{rendered}</p>")
        body_buf = []

    while i < total:
        line = IMAGE_MD_PATTERN.sub("", lines[i]).rstrip()
        if not line.strip():
            flush_body()
            i += 1
            continue
        if _is_table_row(line):
            flush_body()
            block = []
            while i < total:
                row = IMAGE_MD_PATTERN.sub("", lines[i]).rstrip()
                if _is_table_row(row):
                    block.append(row)
                    i += 1
                else:
                    break
            table_html = _render_table(block)
            if table_html:
                parts.append(table_html)
            continue
        if HR_MD_PATTERN.match(line):
            flush_body()
            parts.append("<hr>")
            i += 1
            continue
        heading = HEADING_MD_PATTERN.match(line)
        if heading:
            flush_body()
            level = min(len(heading.group(1)), 3)
            tag = {1: "h2", 2: "h3", 3: "h4"}[level]
            css_class = {1: "b-title", 2: "b-head", 3: "b-sub"}[level]
            parts.append(
                f'<{tag} class="{css_class}">{_render_inline(heading.group(2).strip())}</{tag}>'
            )
            i += 1
            continue
        head, rest = split_heading_prefix(line.strip())
        if head and not rest:
            flush_body()
            parts.append(f'<h3 class="b-head">{_render_inline(head)}</h3>')
            i += 1
            continue
        if head and rest:
            flush_body()
            parts.append(f'<h3 class="b-head">{_render_inline(head)}</h3>')
            body_buf.append(rest)
            i += 1
            continue
        body_buf.append(line)
        i += 1
    flush_body()
    return parts


def build_html_content(pages_text):
    parts = []
    for i, lines in enumerate(pages_text, start=1):
        if i > 1:
            parts.append("<hr>")
        parts.append(f'<p class="page-label">Page {i}</p>')
        parts.extend(render_markdown_lines(lines))
    return "\n".join(parts)


def build_stub_html_content(reason: str) -> str:
    safe = html_utils.escape(reason)
    return (
        '<div class="ocr-failed-banner" role="alert">'
        "⚠️ OCR failed this week — use the original PDF above for the full text."
        "</div>\n"
        '<p class="page-label">Page 1</p>\n'
        f"<p><strong>OCR text is temporarily unavailable.</strong> {safe}</p>\n"
        "<p>Please use the original PDF until the next harvest run completes.</p>"
    )


def write_stub_and_fail(date: str, reason: str) -> None:
    """Write a failed-OCR page and exit so CI cannot treat the stub as success."""
    content = build_stub_html_content(reason)
    output_filename = f"bulletin-{date}.html"
    html = HTML_TEMPLATE.format(date=date, css=CSS, content=content)
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Stub output saved to: {output_filename}")
    print(f"::error::OCR stub written — {reason}")
    sys.exit(1)


def main():
    if len(sys.argv) != 3:
        print("Usage: python convert_bulletin.py <pdf_file> <YYYY-MM-DD>")
        sys.exit(1)

    pdf_file = sys.argv[1]
    date = sys.argv[2]

    if not os.path.isfile(pdf_file):
        print(f"Error: '{pdf_file}' not found.")
        sys.exit(1)

    print(f"Converting '{pdf_file}' for date {date} ...")
    pages_text = None
    provider_used = None
    images = None
    native_all = None
    vision_indexes = None

    try:
        native_all = extract_all_page_lines(pdf_file)
        vision_indexes = choose_vision_page_indexes(native_all)
        if vision_indexes == []:
            pages_text = native_all
            provider_used = "Tier0-text"
            print(
                f"  Embedded PDF text on all {len(native_all)} page(s) — skipping vision OCR."
            )
            print("0 sparse pages sent to vision")
        elif vision_indexes is not None:
            pages_text = [list(lines or []) for lines in native_all]
            provider_used = "Tier0-text"
            print(
                f"{len(vision_indexes)} sparse pages sent to vision"
            )
    except Exception as e:
        print(f"  Embedded-text check failed ({type(e).__name__}: {e}).")

    mistral_api_key = os.environ.get("MISTRAL_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    github_token = os.environ.get("GITHUB_TOKEN")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    has_vision_keys = bool(mistral_api_key or gemini_api_key or github_token or openai_api_key)

    if not has_vision_keys:
        print("No vision OCR keys set — trying Tier 0 text extraction only ...")
        try:
            tier0_pages = extract_text_pages(pdf_file)
            if tier0_pages:
                pages_text = tier0_pages
                provider_used = "Tier0-text"
                print(f"  Tier 0 succeeded on {len(tier0_pages)} page(s).")
            else:
                print("  Tier 0 skipped — PDF looks scanned or image-only.")
        except Exception as e:
            print(f"  Tier 0 failed ({type(e).__name__}: {e}).")

    if pages_text is None and not has_vision_keys:
        print("No OCR API keys set and Tier 0 did not apply — writing stub HTML.")
        write_stub_and_fail(date, "No OCR provider configured for this run.")

    if pages_text is not None and vision_indexes and has_vision_keys:
        try:
            sparse_images = pdf_images_for_pages(pdf_file, vision_indexes)
            vision_pages, sparse_provider = ocr_selected_images_with_fallbacks(sparse_images)
            if vision_pages:
                pages_text = merge_vision_into_pages(pages_text, vision_indexes, vision_pages)
                provider_used = f"Tier0+{sparse_provider}"
        except Exception as e:
            print(f"  Sparse-page vision failed ({type(e).__name__}: {e}).")
    elif pages_text is None and native_all:
        print(f"{len(native_all)} sparse pages sent to vision")

    if pages_text is None and mistral_api_key:
        for attempt in (1, 2):
            label = "Trying" if attempt == 1 else "Retrying"
            print(f"{label} Mistral OCR (mistral-ocr-latest) on PDF ...")
            try:
                mistral_pages = ocr_with_mistral(pdf_file)
                pages_text = [page_text.splitlines() for page_text in mistral_pages]
                provider_used = "Mistral"
                print(f"  Mistral OCR succeeded on {len(mistral_pages)} page(s).")
                break
            except Exception as e:
                print(f"  Mistral OCR failed ({type(e).__name__}: {e}).")
    elif pages_text is None:
        print("MISTRAL_API_KEY not set, skipping Mistral OCR ...")

    if pages_text is None:
        if not gemini_api_key:
            print("GEMINI_API_KEY not set, skipping Gemini OCR ...")
        else:
            if images is None:
                print("Preparing PDF pages for image OCR ...")
                images = pdf_to_images(pdf_file)
                print(f"  {len(images)} page(s) found.")
            print("Running image OCR with Gemini (gemini-2.5-flash) fallback ...")
            try:
                pages_text, provider_used = ocr_images_with_gemini(images)
            except Exception as e:
                print(f"  Gemini OCR failed ({type(e).__name__}: {e}).")

    if pages_text is None:
        if not github_token:
            print("GITHUB_TOKEN not set, skipping GitHub Models OCR ...")
        else:
            if images is None:
                print("Preparing PDF pages for image OCR ...")
                images = pdf_to_images(pdf_file)
                print(f"  {len(images)} page(s) found.")
            print("Running image OCR with GitHub Models (gpt-4o-mini) fallback ...")
            try:
                pages_text, provider_used = ocr_images_with_github_models(images)
            except Exception as e:
                print(f"  GitHub Models OCR failed ({type(e).__name__}: {e}).")

    if pages_text is None:
        if not openai_api_key:
            print("OPENAI_API_KEY not set, skipping OpenAI OCR ...")
        else:
            if images is None:
                print("Preparing PDF pages for image OCR ...")
                images = pdf_to_images(pdf_file)
                print(f"  {len(images)} page(s) found.")
            print("Running image OCR with OpenAI gpt-4o-mini fallback ...")
            try:
                pages_text, provider_used = ocr_images_with_openai(images)
            except Exception as e:
                print(f"  OpenAI OCR failed ({type(e).__name__}: {e}).")
                pages_text = None

    if pages_text is None and has_vision_keys:
        print("Vision OCR unavailable — trying Tier 0 text extraction as fallback ...")
        try:
            tier0_pages = extract_text_pages(pdf_file)
            if tier0_pages:
                pages_text = tier0_pages
                provider_used = "Tier0-text"
                print(f"  Tier 0 fallback succeeded on {len(tier0_pages)} page(s).")
                print(
                    "::warning::Tier 0 plain PDF text was used — "
                    "bulletin will lack formatted tables and headings."
                )
            else:
                print("  Tier 0 fallback skipped — PDF looks scanned or image-only.")
        except Exception as e:
            print(f"  Tier 0 fallback failed ({type(e).__name__}: {e}).")

    if pages_text is None:
        print("All OCR providers failed — writing stub HTML.")
        write_stub_and_fail(date, "Vision OCR failed and no embedded PDF text was found.")

    try:
        from ocr.quota_log import record_convert_run

        record_convert_run(provider_used, pages_text, vision_indexes)
    except Exception as exc:  # noqa: BLE001
        print(f"  OCR quota log skipped ({type(exc).__name__}: {exc}).")

    from ocr.sparse_page_ocr import fill_sparse_ocr_pages, repair_image_page_ocr

    print("Filling sparse / banner-only mega pages from page images ...")
    pages_text = fill_sparse_ocr_pages(pdf_file, pages_text)
    pages_text = prefer_embedded_page_text(pdf_file, pages_text)
    print("Repairing smashed image-only pages with column OCR ...")
    pages_text = repair_image_page_ocr(pdf_file, pages_text)

    print("Building HTML ...")
    content = build_html_content(pages_text)

    output_filename = f"bulletin-{date}.html"
    html = HTML_TEMPLATE.format(date=date, css=CSS, content=content)

    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\nDone! Output saved to: {output_filename}")
    print(f"Summary: Processed {len(pages_text)} page(s) using {provider_used}.")


if __name__ == "__main__":
    main()
