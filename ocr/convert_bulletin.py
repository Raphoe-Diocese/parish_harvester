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
    max-width: 100%;
    margin: 0;
    background: #ffffff;
    font-family: Georgia, serif;
    font-size: 16px;
    line-height: 1.7;
    padding: 16px 20px;
  }
  .page-label {
    font-size: 1em;
    font-weight: 700;
    margin: 1.2em 0 0.35em;
    color: #0f2b5b;
  }
  .page-label:first-child {
    margin-top: 0;
  }
  p {
    margin: 4px 0;
  }
  hr {
    margin: 1em 0;
    border: none;
    border-top: 1px solid #ddd;
  }
  .b-title {
    font-size: 1.35em;
    font-weight: 700;
    color: #0f2b5b;
    margin: 0.9em 0 0.3em;
    border-bottom: 2px solid #c8d6f0;
    padding-bottom: 0.15em;
  }
  .b-head {
    font-size: 1.15em;
    font-weight: 700;
    color: #134e9c;
    margin: 0.75em 0 0.25em;
  }
  .b-sub {
    font-size: 1.02em;
    font-weight: 700;
    color: #1f6f4a;
    margin: 0.6em 0 0.2em;
  }
  strong { color: #0f2b5b; }
  a { color: #1d4ed8; }
  table.b-table {
    border-collapse: collapse;
    width: 100%;
    margin: 0.5em 0;
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
    "Extract ALL text exactly as it appears. "
    "Do NOT translate Irish/Gaeilge to English — preserve both languages faithfully. "
    "Do NOT wrap your response in markdown code fences or backticks. "
    "Do NOT include image references like !img-0.jpeg. "
    "Mass times, church names, and personal names (including Mc/Mac/O'/Ní) must be letter-perfect. "
    "Preserve multi-column layout using plain text spacing; use one row per line for timetable tables. "
    "If text is illegible, write [illegible] — never guess a name or time."
)

MARKDOWN_FENCE_PATTERN = re.compile(r"^\s*```(?:[A-Za-z0-9_-]+)?\s*$")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_PATTERN = re.compile(r"(?<!@)\b(?:https?://|www\.)[^\s<>\"]+", re.IGNORECASE)
DIGITS_ONLY_PATTERN = re.compile(r"\D")
# 074 Donegal-format landline, 087 Irish mobile prefix, +353 international Irish, 028 NI-format landline.
PHONE_074_PATTERN = r"074[\s-]*\d{3}[\s-]*\d{4}"
PHONE_087_PATTERN = r"087[\s-]*\d{3}[\s-]*\d{4}"
PHONE_353_PATTERN = r"\+353[\s-]*\d{2}[\s-]*\d{3}[\s-]*\d{4}"
PHONE_028_PATTERN = r"028[\s-]*\d{3}[\s-]*\d{4,5}"
PHONE_PATTERN = re.compile(
    rf"(?<!\w)(?:{PHONE_074_PATTERN}|{PHONE_087_PATTERN}|{PHONE_353_PATTERN}|{PHONE_028_PATTERN})(?!\w)"
)
HEADING_MD_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
HR_MD_PATTERN = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
BOLD_MD_PATTERN = re.compile(r"\*\*(.+?)\*\*")
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
    model = genai.GenerativeModel("gemini-1.5-flash")
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


def linkify(text):
    """Convert escaped text emails, URLs, and Irish-style phone numbers into HTML links."""
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
        return stash(f'<a href="mailto:{escaped_email}">{escaped_email}</a>')

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

    def to_tel_href(display):
        """Normalize matched phone display text to an Irish tel: href."""
        digits = DIGITS_ONLY_PATTERN.sub("", display)
        if digits.startswith("353"):
            national = digits[3:]
            return f"+353{national}" if national else None
        if digits.startswith("0"):
            national = digits[1:]
            if national:
                return f"+353{national}"
        return None

    def replace_phone(match):
        phone = match.group(0)
        href = to_tel_href(phone)
        if not href:
            return phone
        escaped_phone = html_utils.escape(phone)
        escaped_href = html_utils.escape(href, quote=True)
        return stash(f'<a href="tel:{escaped_href}">{escaped_phone}</a>')

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
    """Render one page's OCR lines, grouping markdown tables into HTML tables."""
    parts: list[str] = []
    i = 0
    total = len(lines)
    while i < total:
        line = IMAGE_MD_PATTERN.sub("", lines[i]).rstrip()
        if not line.strip():
            i += 1
            continue
        if _is_table_row(line):
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
            parts.append("<hr>")
            i += 1
            continue
        heading = HEADING_MD_PATTERN.match(line)
        if heading:
            level = min(len(heading.group(1)), 3)
            tag = {1: "h2", 2: "h3", 3: "h4"}[level]
            css_class = {1: "b-title", 2: "b-head", 3: "b-sub"}[level]
            parts.append(
                f'<{tag} class="{css_class}">{_render_inline(heading.group(2).strip())}</{tag}>'
            )
            i += 1
            continue
        parts.append(f"<p>{_render_inline(line)}</p>")
        i += 1
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

    print("Trying Tier 0 text extraction (born-digital PDF) ...")
    try:
        tier0_pages = extract_text_pages(pdf_file)
        if tier0_pages:
            pages_text = tier0_pages
            provider_used = "Tier0-text"
            print(f"  Tier 0 succeeded on {len(tier0_pages)} page(s) — skipping vision OCR.")
        else:
            print("  Tier 0 skipped — PDF looks scanned or image-only.")
    except Exception as e:
        print(f"  Tier 0 failed ({type(e).__name__}: {e}).")

    mistral_api_key = os.environ.get("MISTRAL_API_KEY")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")

    if pages_text is None and not mistral_api_key and not gemini_api_key and not openai_api_key:
        print("Warning: No OCR API keys set and Tier 0 did not apply — writing stub HTML.")
        content = build_stub_html_content("No OCR provider configured for this run.")
        output_filename = f"bulletin-{date}.html"
        html = HTML_TEMPLATE.format(date=date, css=CSS, content=content)
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Stub output saved to: {output_filename}")
        return

    if pages_text is None and mistral_api_key:
        print("Trying Mistral OCR (mistral-ocr-latest) on PDF ...")
        try:
            mistral_pages = ocr_with_mistral(pdf_file)
            pages_text = [page_text.splitlines() for page_text in mistral_pages]
            provider_used = "Mistral"
            print(f"  Mistral OCR succeeded on {len(mistral_pages)} page(s).")
        except Exception as e:
            print(f"  Mistral OCR failed ({type(e).__name__}: {e}).")
    elif pages_text is None:
        print("MISTRAL_API_KEY not set, skipping Mistral OCR ...")

    if pages_text is None:
        if not gemini_api_key:
            print("GEMINI_API_KEY not set, skipping Gemini OCR ...")
        else:
            if images is None:
                print("Preparing PDF pages for Gemini OCR ...")
                images = pdf_to_images(pdf_file)
                print(f"  {len(images)} page(s) found.")
            print("Running image OCR with Gemini (gemini-1.5-flash) fallback ...")
            try:
                pages_text, provider_used = ocr_images_with_gemini(images)
            except Exception as e:
                print(f"  Gemini OCR failed ({type(e).__name__}: {e}).")

    if pages_text is None:
        if not openai_api_key:
            print("OPENAI_API_KEY not set, skipping OpenAI OCR ...")
        else:
            if images is None:
                print("Preparing PDF pages for OpenAI OCR ...")
                images = pdf_to_images(pdf_file)
                print(f"  {len(images)} page(s) found.")
            print("Running image OCR with OpenAI gpt-4o-mini fallback ...")
            try:
                pages_text, provider_used = ocr_images_with_openai(images)
            except Exception as e:
                print(f"  OpenAI OCR failed ({type(e).__name__}: {e}).")
                pages_text = None

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
