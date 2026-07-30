#!/usr/bin/env python3
# Requires: pip install openai pdf2image Pillow mistralai
import os
import base64
import io
import re
import html as html_utils
import sys

import google.generativeai as genai
from openai import OpenAI
# mistralai package layouts differ across versions; support both import paths.
try:
    from mistralai import Mistral
except ImportError:
    from mistralai.client import Mistral
from pdf2image import convert_from_path

from ocr.text_extract import extract_text_pages

CSS = """
<style>
  html, body {
    margin: 0;
    padding: 0;
    overflow-x: hidden;
  }
  .scrollable-viewer {
    max-width: min(52rem, 100%);
    margin: 0 auto;
    background: #ffffff;
    font-family: Georgia, "Times New Roman", Times, serif;
    font-size: 1.125rem;
    line-height: 1.45;
    padding: 12px 16px 28px;
  }
  .page-label {
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin: 1.1em 0 0.4em;
    color: #64748b;
    font-family: system-ui, sans-serif;
  }
  .page-label:first-child {
    margin-top: 0;
  }
  p {
    margin: 0 0 0.65em;
  }
  hr {
    margin: 0.9em 0;
    border: none;
    border-top: 1px solid #e2e8f0;
  }
  .b-title {
    font-size: 1.28em;
    font-weight: 700;
    color: #0f2b5b;
    margin: 0.85em 0 0.25em;
    border-bottom: 2px solid #c8d6f0;
    padding-bottom: 0.12em;
  }
  .b-head {
    font-size: 1.12em;
    font-weight: 700;
    color: #134e9c;
    margin: 0.7em 0 0.2em;
  }
  .b-sub {
    font-size: 1.02em;
    font-weight: 700;
    color: #1f6f4a;
    margin: 0.55em 0 0.15em;
  }
  strong { color: #0f2b5b; }
  a { color: #1d4ed8; }
  table.b-table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.45em 0 0.75em;
    font-size: 0.95em;
  }
  table.b-table td, table.b-table th {
    border: 1px solid #d0d8e8;
    padding: 4px 8px;
    text-align: left;
    vertical-align: top;
  }
  table.b-table th {
    background: #eef3fb;
    color: #0f2b5b;
  }
  table.b-table tr:nth-child(even) td {
    background: #f7f9fd;
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
    "You are an OCR assistant reading an Irish Catholic parish bulletin page (English and Irish Gaeilge). "
    "Extract ALL text exactly as it appears — faithful transcription only. "
    "Do NOT translate Irish/Gaeilge to English — preserve both languages faithfully. "
    "Do NOT wrap your response in markdown code fences or backticks. "
    "Do NOT include image references like !img-0.jpeg. "
    "Do NOT repeat words or headings — each word/phrase once only (never ORDINARYORDINARY or word word). "
    "Mass times, church names, deceased names, and personal names (including Mc/Mac/O'/Ní) must be letter-perfect. "
    "Never invent, autocorrect, or guess a name, date, or mass time. "
    "LAYOUT (structure only — do not rewrite wording):\n"
    "- Read columns top-to-bottom, left-to-right; keep reading order natural for a parish newsletter.\n"
    "- One blank line between major blocks (title, contacts, mass times, notices, intentions).\n"
    "- Put the parish or church name on its own line as a markdown heading: # Parish / church title.\n"
    "- Use ## for section titles exactly as printed (Mass Times, Anniversaries, Notices, etc.).\n"
    "- Mass grids and timetables → markdown tables with header row, e.g. | Day | Time | Intention |.\n"
    "- Contact lines (phone, email, website, address) each on their own line; keep digits and emails exact.\n"
    "- Keep lists as separate lines (one intention / notice per line); do not glue columns into one run-on sentence.\n"
    "- Ignore decorative lines, watermarks, and page furniture that are not readable text.\n"
    "If text is illegible, write [illegible] — never guess."
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
_ORDINAL_DUP_RE = re.compile(r"\b(\d+)\1(st|nd|rd|th)\b", re.IGNORECASE)
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
    return convert_from_path(pdf_path, dpi=150)


def ocr_with_mistral(pdf_path):
    """Run Mistral OCR on a PDF and return list of page strings."""
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY is not set.")

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


def _image_to_base64_png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    buffer.close()
    return encoded


def ocr_images_with_gemini(images):
    """Run Gemini OCR across images and return (pages_text, provider_summary)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")
    pages_text = []
    for i, image in enumerate(images, start=1):
        print(f"  OCR on page {i}/{len(images)} via Gemini ...", flush=True)
        response = model.generate_content([OCR_PROMPT, image])
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


def clean_ocr_line(text: str) -> str:
    """Remove common OCR duplication artefacts before HTML render."""
    if not text:
        return text
    cleaned = str(text)
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
        '<p class="page-label">Page 1</p>\n'
        f"<p><strong>OCR text is temporarily unavailable.</strong> {safe}</p>\n"
        "<p>Please use the original PDF until the next harvest run completes.</p>"
    )


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
        print("Warning: No OCR API keys set and Tier 0 did not apply — writing stub HTML.")
        content = build_stub_html_content("No OCR provider configured for this run.")
        output_filename = f"bulletin-{date}.html"
        html = HTML_TEMPLATE.format(date=date, css=CSS, content=content)
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Stub output saved to: {output_filename}")
        return

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
        print("Warning: All OCR providers failed — writing stub HTML.")
        content = build_stub_html_content("Vision OCR failed and no embedded PDF text was found.")
        output_filename = f"bulletin-{date}.html"
        html = HTML_TEMPLATE.format(date=date, css=CSS, content=content)
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Stub output saved to: {output_filename}")
        return

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
