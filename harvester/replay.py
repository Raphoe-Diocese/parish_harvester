from __future__ import annotations

import asyncio
import fnmatch
import io
import json
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from .cloud_folders import is_cloud_folder_click_step, rewrite_cloud_folder_click_step
from .cloud_urls import is_cloud_document_url, normalize_document_url, unwrap_docs_viewer_url
from .config import PAGE_LOAD_TIMEOUT_MS, PARISHES_DIR
from .utils import (
    extract_date_from_string,
    oneweb_newsletter_download_urls,
    rewrite_date_url,
    rewrite_newsletter_number_for_target,
)


class RecipeReplayError(RuntimeError):
    """Raised when replaying a trained parish recipe fails."""


DOCX_CONVERSION_TIMEOUT_S = 60
RECIPE_STEP_TIMEOUT_MS = 15_000
POST_CLICK_WAIT_TIMEOUT_MS = 3_000
MAX_SELECTOR_ERRORS = 3
DROPFILES_DOWNLOAD_SELECTORS = (
    "a.mod_downloadlink[href]",
    ".mod_dropfiles_latest a.mod_downloadlink[href]",
    ".mod_dropfiles_list a.mod_downloadlink[href]",
)
PDFEMB_SELECTOR = "a.pdfemb-viewer[href]"
PDFEMB_HREF_EXTRACT_JS = "(els) => els.map(el => el.getAttribute('href')).filter(Boolean)"

_NON_BULLETIN_RE = re.compile(
    r"dataentry|giftaid|standingorder|donation|prayer|safeguarding|privacy|gdpr|diocese|"
    r"sitemap|application|registration|volunteer|finances|financial|parishdraw|mcn\s*media|"
    r"gaza|bishops-call|draw_poster|poster_20\d{2}|fbcdn\.net|facebook\.com",
    re.IGNORECASE,
)
_BULLETIN_KEYWORD_RE = re.compile(r"\b(bulletin|newsletter)\b", re.IGNORECASE)
_D_M_YY_IN_URL_RE = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})-(\d{2})(?!\d)")


def _is_non_bulletin_url(url: str) -> bool:
    text = unquote(url or "")
    if _BULLETIN_KEYWORD_RE.search(text):
        return False
    return bool(_NON_BULLETIN_RE.search(text))


def _looks_like_http_url(url: str) -> bool:
    return (url or "").strip().lower().startswith(("http://", "https://"))


def _looks_like_direct_document_url(url: str) -> bool:
    lower = unquote((url or "").strip()).lower()
    if not _looks_like_http_url(lower):
        return False
    if "drive.usercontent.google.com/download" in lower:
        return True
    path = urlparse(lower).path
    return path.endswith((".pdf", ".docx", ".doc")) or "/pdf/" in path


async def _goto_or_download(
    page: Page,
    dest: Path,
    url: str,
    downloads: list,
    timeout_ms: int,
    *,
    wait_until: str = "domcontentloaded",
) -> tuple[Path, str, str] | None:
    """Navigate or fetch a direct document URL (Drive downloads abort normal goto)."""
    if _looks_like_direct_document_url(url):
        tried = await _try_browser_nav_download(page, dest, url, timeout_ms)
        if tried:
            return dest, tried[1], tried[0]
        tried = await _try_download_page_url(page, dest, url, timeout_ms=timeout_ms)
        if tried:
            return dest, tried[1], tried[0]
    await _navigate_page(page, url, timeout_ms, wait_until=wait_until)
    return await _capture_document_after_navigation(page, dest, url, downloads, timeout_ms)


async def _capture_document_after_navigation(
    page: Page,
    dest: Path,
    nav_url: str,
    downloads: list,
    timeout_ms: int,
) -> tuple[Path, str, str] | None:
    if downloads:
        file_type = await _save_download_to_pdf(downloads.pop(0), dest)
        return dest, file_type, nav_url or page.url
    if nav_url and _looks_like_direct_document_url(nav_url):
        tried = await _try_download_page_url(page, dest, nav_url, timeout_ms=timeout_ms)
        if tried:
            return dest, tried[1], tried[0]
    if _looks_like_http_url(page.url) and _is_document_url(page.url):
        source_url, file_type = await _download_document_url(
            page, page.url, dest, timeout_ms=timeout_ms
        )
        return dest, file_type, source_url
    return None


def _score_bulletin_url(url: str) -> tuple[int, int]:
    """Higher = better. (date_score, keyword_bonus)."""
    text = unquote(url or "").lower()
    keyword_bonus = 10 if _BULLETIN_KEYWORD_RE.search(text) else 0
    date_score = 0
    for match in _D_M_YY_IN_URL_RE.finditer(text):
        try:
            day, month, year = int(match.group(1)), int(match.group(2)), 2000 + int(match.group(3))
            date_score = max(date_score, year * 10000 + month * 100 + day)
        except ValueError:
            continue
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(\d{2})(?!\d)", text)
    if m:
        try:
            day, month, year = int(m.group(1)), int(m.group(2)), 2000 + int(m.group(3))
            date_score = max(date_score, year * 10000 + month * 100 + day)
        except ValueError:
            pass
    parsed = extract_date_from_string(text)
    if parsed:
        date_score = max(date_score, parsed.year * 10000 + parsed.month * 100 + parsed.day)
    return date_score, keyword_bonus


def _score_bulletin_link(href: str, label: str = "") -> tuple[int, int, int]:
    """Return (total_score, date_score, dom_tiebreak) for ranking bulletin links."""
    combined = f"{unquote(href or '')} {label or ''}"
    date_score, keyword_bonus = _score_bulletin_url(combined)
    notice_bonus = 5 if re.search(r"\b(notice|parish news|latest bulletin)\b", combined, re.I) else 0
    total = date_score * 100 + keyword_bonus + notice_bonus
    return total, date_score, keyword_bonus


def _url_matches_pattern(url: str, pattern: str) -> bool:
    lower = unquote(url).lower()
    pat = (pattern or "*.pdf").strip().lower() or "*.pdf"
    if fnmatch.fnmatch(lower, pat):
        return True
    if pat == "*.pdf":
        return ".pdf" in lower
    if pat == "*.docx":
        return ".docx" in lower
    return False


def _pattern_prefers_docx(pattern: str) -> bool:
    pat = (pattern or "").strip().lower()
    return ".docx" in pat or pat.endswith("docx")


async def _collect_document_candidates(page: Page, pattern: str) -> list[str]:
    """Unwrap viewer URLs, drop admin docs, prefer newest newsletter."""
    pdfemb_links = await page.eval_on_selector_all(PDFEMB_SELECTOR, PDFEMB_HREF_EXTRACT_JS)
    raw_links = await page.eval_on_selector_all(
        "a[href],iframe[src],embed[src],object[data]",
        """
        (els) => els.map(el => el.getAttribute('href') || el.getAttribute('src') || el.getAttribute('data') || '').filter(Boolean)
        """,
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in [*pdfemb_links, *raw_links]:
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = unwrap_docs_viewer_url(urljoin(page.url, raw.strip()))
        if not _url_matches_pattern(resolved, pattern):
            continue
        if _is_non_bulletin_url(resolved):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved)
    candidates.sort(
        key=lambda u: (_score_bulletin_url(u)[0], _score_bulletin_url(u)[1]),
        reverse=True,
    )
    return candidates


def _recipe_step_timeout_ms(recipe: dict) -> int:
    """Return recipe-specific step timeout in milliseconds.

    Uses ``timeout_ms`` first, then ``timeout`` for backward compatibility.
    Values are clamped to [1_000, 120_000] ms:
    - 1,000 ms minimum avoids accidental 0/negative values that disable timeouts
      entirely (Playwright treats 0 as "wait indefinitely"), which can stall runs.
    - 180,000 ms maximum prevents malformed recipe values from stalling runs.
    """
    raw = recipe.get("timeout_ms", recipe.get("timeout"))
    try:
        if raw is None:
            return RECIPE_STEP_TIMEOUT_MS
        value = int(raw)
    except (TypeError, ValueError):
        return RECIPE_STEP_TIMEOUT_MS
    return min(max(value, 1_000), 180_000)


_VALID_NAV_WAIT_UNTIL = frozenset({"commit", "domcontentloaded", "load", "networkidle"})
_HOST_PROFILES_RAW: dict | None = None


def _load_host_profiles_raw() -> dict:
    global _HOST_PROFILES_RAW
    if _HOST_PROFILES_RAW is not None:
        return _HOST_PROFILES_RAW
    fallback: dict = {"_default": {}, "hosts": {}}
    profiles_path = PARISHES_DIR / "host_profiles.json"
    try:
        loaded = json.loads(profiles_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            if isinstance(loaded.get("_default"), dict):
                fallback["_default"] = loaded["_default"]
            if isinstance(loaded.get("hosts"), dict):
                fallback["hosts"] = loaded["hosts"]
    except Exception:
        pass
    _HOST_PROFILES_RAW = fallback
    return fallback


def _host_profile_for_start_url(start_url: str) -> dict:
    profiles = _load_host_profiles_raw()
    merged = dict(profiles.get("_default", {}))
    host = urlparse(start_url).netloc.lower().split(":", 1)[0]
    candidates = [host]
    if host.startswith("www."):
        candidates.append(host[4:])
    elif host:
        candidates.append(f"www.{host}")
    hosts = profiles.get("hosts", {})
    if isinstance(hosts, dict):
        for key in candidates:
            override = hosts.get(key)
            if isinstance(override, dict):
                merged.update(override)
                break
    return merged


def _recipe_navigation_wait_until(recipe: dict) -> str:
    """How eagerly goto waits — slow WordPress hosts often need ``commit``."""
    raw = str(recipe.get("navigation_wait_until") or "").strip().lower()
    if raw in _VALID_NAV_WAIT_UNTIL:
        return raw
    start_url = (recipe.get("start_url") or "").strip()
    host_wait = str(_host_profile_for_start_url(start_url).get("navigation_wait_until") or "").strip().lower()
    if host_wait in _VALID_NAV_WAIT_UNTIL:
        return host_wait
    return "domcontentloaded"


async def _find_mdocs_pdf_urls(page: Page) -> list[str]:
    """mDocs plugin lists — latest bulletin is first row (site copy)."""
    raw_links = await page.eval_on_selector_all(
        "table.mdocs a[href], a.mdocs-download[href], .mdocs a[href], .mdocs-file a[href]",
        "(els) => els.map(el => el.getAttribute('href') || '').filter(Boolean)",
    )
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in raw_links:
        if not isinstance(raw, str) or not raw.strip():
            continue
        resolved = urljoin(page.url, raw.strip())
        lower = resolved.lower()
        if ".pdf" not in lower:
            continue
        if _is_non_bulletin_url(resolved):
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        candidates.append(resolved)
    candidates.sort(
        key=lambda u: (_score_bulletin_url(u)[0], _score_bulletin_url(u)[1]),
        reverse=True,
    )
    return candidates


async def _wait_for_bulletin_content(page: Page, recipe: dict, timeout_ms: int) -> None:
    """Slow hosts: wait for mdocs table or wp-block-file embed after commit navigation."""
    playbook = str(recipe.get("playbook_type") or recipe.get("site_type") or "").lower()
    probes = []
    if "mdocs" in playbook:
        probes.extend(["table.mdocs", "a.mdocs-download", ".mdocs a[href]"])
    if "wp_block" in playbook or "permanent_bulletin" in playbook:
        probes.extend(["object.wp-block-file__embed", ".wp-block-file a[href$='.pdf']"])
    if not probes:
        probes = ["table.mdocs", "object.wp-block-file__embed", "a[href$='.pdf']"]
    budget = min(max(int(timeout_ms), 15_000), 240_000)
    for sel in probes:
        try:
            await page.wait_for_selector(sel, timeout=budget)
            return
        except PlaywrightTimeoutError:
            continue
    try:
        wait_after = int(_host_profile_for_start_url(recipe.get("start_url") or page.url).get("wait_after_load_ms") or 0)
    except (TypeError, ValueError):
        wait_after = 0
    if wait_after > 0:
        await asyncio.sleep(min(wait_after / 1000, 120))


async def _navigate_page(
    page: Page,
    url: str,
    timeout_ms: int,
    *,
    wait_until: str = "domcontentloaded",
) -> None:
    """Navigate with recipe/host wait policy — commit avoids hung domcontentloaded."""
    mode = wait_until if wait_until in _VALID_NAV_WAIT_UNTIL else "domcontentloaded"
    if mode == "commit":
        await page.goto(url, timeout=timeout_ms, wait_until="commit")
        try:
            await page.wait_for_load_state(
                "domcontentloaded",
                timeout=min(max(timeout_ms // 2, 15_000), 90_000),
            )
        except PlaywrightTimeoutError:
            pass
        return
    await page.goto(url, timeout=timeout_ms, wait_until=mode)


def recipe_path_for(parish_key: str, parishes_dir: Path = PARISHES_DIR) -> Path:
    """Return the path to the recipe JSON for *parish_key*.

    Searches diocese subfolders (derry/, down_and_connor/, unknown/, and any
    other subdirectory) before falling back to the legacy flat path so that
    both old flat layouts and the new subfolder layout work transparently.
    """
    recipes_dir = parishes_dir / "recipes"
    # Search existing subdirectories first (new layout)
    for sub in sorted(recipes_dir.iterdir()) if recipes_dir.exists() else []:
        if sub.is_dir():
            candidate = sub / f"{parish_key}.json"
            if candidate.exists():
                return candidate
    # Fall back to flat path (legacy layout or file not yet moved)
    return recipes_dir / f"{parish_key}.json"


def load_recipe(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RecipeReplayError(f"Recipe not found: {path}") from exc
    except Exception as exc:
        raise RecipeReplayError(f"Invalid recipe JSON: {path}") from exc

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RecipeReplayError("Recipe has no steps")
    return data


def _is_pdf_content(data: bytes) -> bool:
    return data[:4] == b"%PDF"


def _is_document_url(url: str) -> bool:
    return is_cloud_document_url(url)


def _normalize_doc_url(url: str) -> str:
    return normalize_document_url(url)


async def _convert_docx_to_pdf_bytes(docx_bytes: bytes) -> bytes:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        docx_path = tmp_path / "bulletin.docx"
        out_pdf = tmp_path / "bulletin.pdf"
        docx_path.write_bytes(docx_bytes)
        libreoffice_error = ""

        try:
            result = subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmp_path),
                    str(docx_path),
                ],
                capture_output=True,
                timeout=DOCX_CONVERSION_TIMEOUT_S,
            )
            if result.returncode == 0 and out_pdf.exists():
                return out_pdf.read_bytes()
            libreoffice_error = (result.stderr or b"").decode("utf-8", errors="ignore").strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            import docx as _docx  # type: ignore[import]
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
        except ImportError as exc:
            suffix = f" LibreOffice error: {libreoffice_error}" if libreoffice_error else ""
            raise RecipeReplayError(
                f"Could not convert DOCX to PDF (missing converter dependencies).{suffix}"
            ) from exc

        doc = _docx.Document(str(docx_path))
        lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
        if not lines:
            raise RecipeReplayError("DOCX has no text content")

        fallback_pdf = tmp_path / "fallback.pdf"
        styles = getSampleStyleSheet()
        pdf_doc = SimpleDocTemplate(
            str(fallback_pdf),
            pagesize=A4,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            leftMargin=2.5 * cm,
            rightMargin=2.5 * cm,
        )
        story = []
        for line in lines:
            safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["Normal"]))
            story.append(Spacer(1, 0.15 * cm))
        pdf_doc.build(story)
        return fallback_pdf.read_bytes()


async def _save_download_to_pdf(download, dest: Path) -> str:
    suggested = (download.suggested_filename or "").lower()
    if suggested.endswith(".docx") or suggested.endswith(".doc"):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_docx = Path(tmpdir) / "download.docx"
            await download.save_as(str(tmp_docx))
            pdf_bytes = await _convert_docx_to_pdf_bytes(tmp_docx.read_bytes())
            dest.write_bytes(pdf_bytes)
            return "docx_to_pdf"

    await download.save_as(str(dest))
    return "pdf"


async def _download_document_url(
    page: Page,
    raw_url: str,
    dest: Path,
    *,
    timeout_ms: int = PAGE_LOAD_TIMEOUT_MS,
) -> tuple[str, str]:
    url = _normalize_doc_url(raw_url)
    if _is_non_bulletin_url(url):
        raise RecipeReplayError(f"Refusing non-bulletin document URL: {raw_url}")
    response = await page.request.get(url, timeout=timeout_ms)
    if not response.ok:
        raise RecipeReplayError(f"HTTP {response.status} for {raw_url}")

    body = await response.body()
    path = urlparse(url.lower()).path
    if path.endswith(".docx"):
        pdf_bytes = await _convert_docx_to_pdf_bytes(body)
        dest.write_bytes(pdf_bytes)
        return raw_url, "docx_to_pdf"

    if _is_pdf_content(body):
        dest.write_bytes(body)
        return raw_url, "pdf"

    if body[:3] == b"\xff\xd8\xff" or body[:8] == b"\x89PNG\r\n\x1a\n":
        try:
            from PIL import Image as PILImage
        except ImportError as exc:
            raise RecipeReplayError(
                "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
            ) from exc
        try:
            img = PILImage.open(io.BytesIO(body)).convert("RGB")
            img.save(str(dest), "PDF")
            return raw_url, "image_to_pdf"
        except Exception as exc:
            raise RecipeReplayError(f"Invalid image content for bulletin conversion: {raw_url}") from exc

    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise RecipeReplayError(f"Server returned HTML instead of document for {raw_url}")

    dest.write_bytes(body)
    return raw_url, "pdf"


async def _try_joomla_dropfiles_click_download(
    page: Page,
    dest: Path,
    timeout_ms: int,
) -> tuple[str, str] | None:
    """Click the first Joomla Dropfiles cloud-download link and save the file."""
    for selector in DROPFILES_DOWNLOAD_SELECTORS:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=min(timeout_ms, 10_000))
            href = (await locator.get_attribute("href") or "").strip()
            async with page.expect_download(timeout=timeout_ms) as dl_info:
                await locator.click(timeout=timeout_ms)
            download = await dl_info.value
            file_type = await _save_download_to_pdf(download, dest)
            source = urljoin(page.url, href) if href else page.url
            return source, file_type
        except Exception:
            continue
    return None


async def _try_browser_nav_download(
    page: Page,
    dest: Path,
    raw_url: str,
    timeout_ms: int,
) -> tuple[str, str] | None:
    """Navigate in a real browser tab — required when bare HTTP gets 403."""
    url = (raw_url or "").strip()
    if not url:
        return None

    try:
        async with page.expect_download(timeout=timeout_ms) as dl_info:
            response = await page.goto(url, timeout=timeout_ms, wait_until="commit")
        download = await dl_info.value
        file_type = await _save_download_to_pdf(download, dest)
        return url, file_type
    except Exception:
        pass

    response = None
    try:
        response = await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
    except Exception:
        return None

    if response is not None:
        try:
            body = await response.body()
            if _is_pdf_content(body):
                dest.write_bytes(body)
                return url, "pdf"
        except Exception:
            pass

    picked = await _try_joomla_dropfiles_click_download(page, dest, timeout_ms)
    if picked:
        return picked

    if _is_document_url(page.url):
        try:
            return await _download_document_url(page, page.url, dest)
        except RecipeReplayError:
            pass

    return None


def _resolve_download_candidates(
    step_url: str,
    *,
    target_date: date | None,
    use_captured_url: bool = False,
) -> list[str]:
    step_url = (step_url or "").strip()
    if not step_url:
        return []
    if use_captured_url or not target_date:
        return [step_url]
    if "newsletter" in step_url.lower() and "onewebmedia" in step_url.lower():
        return oneweb_newsletter_download_urls(step_url, target_date)
    if re.search(r"/(?:Newsletters|Weekly-Bulletins)/\d+/", step_url, re.I):
        return [rewrite_newsletter_number_for_target(step_url, target_date)]
    return [rewrite_date_url(step_url, target_date)]


async def _try_download_page_url(
    page: Page,
    dest: Path,
    raw_url: str | None = None,
    timeout_ms: int = PAGE_LOAD_TIMEOUT_MS,
) -> tuple[str, str] | None:
    """Download a URL that serves PDF bytes without a .pdf suffix (e.g. cappaghparish.com/b/2)."""
    url = (raw_url or page.url or "").strip()
    if not url or url.startswith(("about:", "chrome:", "blob:", "data:")):
        return None
    try:
        return await _download_document_url(page, url, dest, timeout_ms=timeout_ms)
    except RecipeReplayError:
        pass
    return await _try_browser_nav_download(page, dest, url, timeout_ms)


def _fit_image_to_a4_page(image):
    from PIL import Image  # type: ignore[import]

    page_width = 1240
    page_height = 1754
    source = image.convert("RGB")
    scale = min(page_width / source.width, page_height / source.height)
    scaled = source.resize(
        (
            max(1, int(round(source.width * scale))),
            max(1, int(round(source.height * scale))),
        ),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGB", (page_width, page_height), (255, 255, 255))
    offset = ((page_width - scaled.width) // 2, (page_height - scaled.height) // 2)
    canvas.paste(scaled, offset)
    return canvas


async def _download_image_bytes(
    page: Page, raw_url: str, timeout_ms: int = PAGE_LOAD_TIMEOUT_MS
) -> bytes:
    response = await page.request.get(raw_url, timeout=timeout_ms)
    if not response.ok:
        raise RecipeReplayError(f"HTTP {response.status} for {raw_url}")
    return await response.body()


async def _download_image_url_as_pdf(page: Page, raw_url: str, dest: Path) -> tuple[str, str]:
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        raise RecipeReplayError(
            "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
        ) from exc
    try:
        body = await _download_image_bytes(page, raw_url)
        img = Image.open(io.BytesIO(body)).convert("RGB")
        img.save(str(dest), "PDF")
    except RecipeReplayError:
        raise
    except Exception as exc:
        raise RecipeReplayError(f"Invalid image content for bulletin conversion: {raw_url}") from exc
    return raw_url, "image_to_pdf"


async def _download_image_urls_as_pdf(
    page: Page,
    image_urls: list[str],
    dest: Path,
    timeout_ms: int = PAGE_LOAD_TIMEOUT_MS,
) -> tuple[str, str]:
    if not image_urls:
        raise RecipeReplayError("Recipe image_stack step found no bulletin image URLs")
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError as exc:
        raise RecipeReplayError(
            "Pillow is required for image bulletin conversion. Install with: pip install Pillow"
        ) from exc

    pages = []
    for raw_url in image_urls:
        try:
            body = await _download_image_bytes(page, raw_url, timeout_ms=timeout_ms)
            with Image.open(io.BytesIO(body)) as img:
                pages.append(_fit_image_to_a4_page(img))
        except RecipeReplayError:
            raise
        except Exception as exc:
            raise RecipeReplayError(
                f"Invalid image content for bulletin conversion: {raw_url}"
            ) from exc

    if not pages:
        raise RecipeReplayError("Recipe image_stack step found no usable bulletin images")

    pages[0].save(
        str(dest),
        save_all=True,
        append_images=pages[1:],
        format="PDF",
        resolution=150,
    )
    return image_urls[0], "image_to_pdf"


async def _find_stacked_bulletin_image_urls(
    page: Page,
    count: int,
    *,
    selector: str = "",
    min_long_side: int = 800,
    min_short_side: int = 600,
) -> list[str]:
    """Return the first *count* large bulletin images on the page in DOM order."""
    if count < 1:
        return []

    eval_selector = selector.strip() or "img"
    raw_images = await page.eval_on_selector_all(
        eval_selector,
        """
        (els) => els.map((el, index) => {
            const src =
              el.currentSrc ||
              el.getAttribute('src') ||
              el.getAttribute('data-src') ||
              el.getAttribute('data-lazy-src') ||
              el.getAttribute('data-original') ||
              '';
            return {
              index,
              src,
              naturalWidth: Number(el.naturalWidth || 0),
              naturalHeight: Number(el.naturalHeight || 0),
            };
        })
        """,
    )

    candidates: list[tuple[int, str]] = []
    seen: set[str] = set()
    for item in raw_images:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src", "")).strip()
        if not src or src.startswith("data:"):
            continue
        resolved = urljoin(page.url, src)
        lower = resolved.lower()
        if lower in seen or lower.endswith(".svg") or "image/svg+xml" in lower:
            continue
        width = int(item.get("naturalWidth") or 0)
        height = int(item.get("naturalHeight") or 0)
        long_side = max(width, height)
        short_side = min(width, height)
        if long_side < min_long_side or short_side < min_short_side:
            continue
        seen.add(lower)
        candidates.append((int(item.get("index") or 0), resolved))

    candidates.sort(key=lambda item: item[0])
    return [url for _idx, url in candidates[:count]]


async def _print_page_to_pdf(page: Page, dest: Path) -> None:
    pdf_bytes = await page.pdf(
        format="A4",
        print_background=True,
        margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
    )
    dest.write_bytes(pdf_bytes)


async def _find_pdfemb_url(page: Page) -> str | None:
    links = await page.eval_on_selector_all(PDFEMB_SELECTOR, PDFEMB_HREF_EXTRACT_JS)
    candidates: list[str] = []
    for href in links:
        resolved = urljoin(page.url, href)
        lower = resolved.lower()
        if not (lower.endswith(".pdf") or ".pdf" in lower):
            continue
        if _is_non_bulletin_url(resolved):
            continue
        candidates.append(resolved)
    if not candidates:
        return None
    candidates.sort(key=lambda u: _score_bulletin_url(u), reverse=True)
    return candidates[0]


async def _find_iframe_pdf_url(page: Page) -> str | None:
    """Return the best embedded PDF URL (iframe, object, or embed)."""
    srcs = await page.eval_on_selector_all(
        "iframe[src], object[data], embed[src]",
        "(els) => els.map(el => el.getAttribute('src') || el.getAttribute('data') || '').filter(Boolean)",
    )
    candidates: list[str] = []
    for src in srcs:
        if not isinstance(src, str) or not src.strip():
            continue
        resolved = urljoin(page.url, src.strip())
        unwrapped = unwrap_docs_viewer_url(resolved)
        pick = unwrapped if unwrapped != resolved else resolved
        lower = pick.lower()
        if ".pdf" not in lower:
            continue
        if _is_non_bulletin_url(pick):
            continue
        candidates.append(pick)
    if not candidates:
        return None
    candidates.sort(
        key=lambda u: (_score_bulletin_url(u)[0], _score_bulletin_url(u)[1]),
        reverse=True,
    )
    return candidates[0]


async def _click_locator_match(
    page: Page,
    locator,
    step_timeout_ms: int,
) -> None:
    await locator.wait_for(state="visible", timeout=step_timeout_ms)
    await locator.click(timeout=step_timeout_ms)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=POST_CLICK_WAIT_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        pass


async def _replay_click_by_strategy(
    page: Page,
    step: dict,
    selectors: list[str],
    step_timeout_ms: int,
) -> bool:
    """Click the best bulletin link when pick_strategy is set. Returns True on success."""
    strategy = (step.get("pick_strategy") or "").strip().lower()
    if strategy not in {"newest_dated", "first_match", "last_match"}:
        return False

    position = (step.get("bulletin_position") or "top").strip().lower()
    errors: list[str] = []

    for sel in selectors:
        try:
            locator = page.locator(sel)
            count = await locator.count()
            if count <= 0:
                continue

            if strategy == "first_match":
                await _click_locator_match(page, locator.nth(0), step_timeout_ms)
                return True
            if strategy == "last_match":
                await _click_locator_match(page, locator.nth(count - 1), step_timeout_ms)
                return True

            best_idx = -1
            best_rank: tuple[int, int] = (-1, -1)
            for idx in range(count):
                item = locator.nth(idx)
                try:
                    href = (await item.get_attribute("href")) or ""
                    try:
                        label = (await item.inner_text(timeout=2_000)) or ""
                    except Exception:
                        label = ""
                    resolved = urljoin(page.url, href.strip())
                    if resolved and _is_non_bulletin_url(resolved):
                        continue
                    total, date_score, _keyword = _score_bulletin_link(resolved, label)
                    tiebreak = idx if position == "bottom" else -idx
                    rank = (total, tiebreak)
                    if rank > best_rank:
                        best_rank = rank
                        best_idx = idx
                except Exception as exc:
                    errors.append(f"{sel}[{idx}]: {exc}")

            if best_idx >= 0:
                await _click_locator_match(page, locator.nth(best_idx), step_timeout_ms)
                return True

            fallback_idx = count - 1 if position == "bottom" else 0
            await _click_locator_match(page, locator.nth(fallback_idx), step_timeout_ms)
            return True
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    if errors:
        raise RecipeReplayError("; ".join(errors[:MAX_SELECTOR_ERRORS]))
    return False


async def _replay_click(
    page: Page,
    step: dict,
    step_timeout_ms: int,
    *,
    target_date: date | None = None,
) -> None:
    if target_date and is_cloud_folder_click_step(step):
        step = rewrite_cloud_folder_click_step(step, target_date)

    selectors: list[str] = []
    selector = (step.get("selector") or "").strip()
    if selector:
        selectors.append(selector)
    selectors.extend(
        s.strip() for s in step.get("fallback_selectors", []) if isinstance(s, str) and s.strip()
    )

    if not selectors:
        raise RecipeReplayError("Recipe click step missing selector")

    if step.get("pick_strategy"):
        if await _replay_click_by_strategy(page, step, selectors, step_timeout_ms):
            return

    errors: list[str] = []
    for sel in selectors:
        try:
            await _click_locator_match(page, page.locator(sel).first, step_timeout_ms)
            return
        except Exception as exc:
            errors.append(f"{sel}: {exc}")

    detail = "; ".join(errors[:MAX_SELECTOR_ERRORS]) if errors else "no selector details available"
    raise RecipeReplayError(
        f"Recipe outdated — re-train with --train (all selectors failed: {detail})"
    )


async def replay_recipe(
    recipe_path: Path,
    dest: Path,
    browser: Browser,
    *,
    target_url: str | None = None,
    target_date: date | None = None,
) -> tuple[Path, str, str]:
    recipe = load_recipe(recipe_path)
    step_timeout_ms = _recipe_step_timeout_ms(recipe)
    nav_wait_until = _recipe_navigation_wait_until(recipe)
    steps = recipe["steps"]

    start_url = (recipe.get("start_url") or "").strip()
    if not start_url:
        start_url = (target_url or "").strip()
    host_profile = _host_profile_for_start_url(start_url)
    context_opts: dict = {"accept_downloads": True}
    if host_profile.get("ignore_https_errors"):
        context_opts["ignore_https_errors"] = True
    context = await browser.new_context(**context_opts)
    page = await context.new_page()
    downloads: list = []
    page.on("download", lambda d: downloads.append(d))

    first_action = (steps[0].get("action") if steps else "") or ""
    if start_url and first_action != "goto":
        if _looks_like_direct_document_url(start_url):
            captured = await _goto_or_download(
                page, dest, start_url, downloads, step_timeout_ms,
                wait_until=nav_wait_until,
            )
            if captured:
                return captured
        else:
            await _navigate_page(page, start_url, step_timeout_ms, wait_until=nav_wait_until)
            if _looks_like_http_url(start_url):
                last_http_url = start_url

    try:
        last_http_url = start_url if _looks_like_http_url(start_url) else ""
        for step in steps:
            action = step.get("action")
            if action == "goto":
                url = (step.get("url") or "").strip()
                if step.get("use_target_url") and target_url:
                    url = target_url.strip()
                if not url:
                    raise RecipeReplayError("Recipe goto step missing URL")
                captured = await _goto_or_download(
                    page, dest, url, downloads, step_timeout_ms,
                    wait_until=nav_wait_until,
                )
                if captured:
                    return captured
                if _looks_like_http_url(url):
                    last_http_url = url
                await _wait_for_bulletin_content(page, recipe, step_timeout_ms)
                continue

            if action == "click":
                await _replay_click(page, step, step_timeout_ms, target_date=target_date)
                if downloads:
                    file_type = await _save_download_to_pdf(downloads.pop(0), dest)
                    source_url = page.url
                    return dest, file_type, source_url
                picked = await _try_joomla_dropfiles_click_download(page, dest, step_timeout_ms)
                if picked:
                    return dest, picked[1], picked[0]
                if _is_document_url(page.url):
                    source_url, file_type = await _download_document_url(
                        page, page.url, dest, timeout_ms=step_timeout_ms
                    )
                    return dest, file_type, source_url
                click_href = (step.get("href") or "").strip()
                if click_href:
                    resolved_href = urljoin(page.url, click_href)
                    href_candidates = _resolve_download_candidates(
                        resolved_href,
                        target_date=target_date,
                        use_captured_url=bool(step.get("use_captured_url")),
                    )
                    for candidate in href_candidates:
                        tried = await _try_download_page_url(
                            page, dest, candidate, timeout_ms=step_timeout_ms
                        )
                        if tried:
                            return dest, tried[1], tried[0]
                tried = await _try_download_page_url(page, dest, timeout_ms=step_timeout_ms)
                if tried:
                    return dest, tried[1], tried[0]
                continue

            if action == "download":
                if downloads:
                    file_type = await _save_download_to_pdf(downloads.pop(0), dest)
                    source_url = page.url
                    return dest, file_type, source_url

                pattern = (step.get("url_pattern") or "*.pdf").strip() or "*.pdf"
                step_url = (step.get("url") or "").strip()
                use_captured = bool(step.get("use_captured_url"))
                if step.get("use_page_url"):
                    step_url = (page.url or "").strip()
                    if not _looks_like_http_url(step_url):
                        step_url = (last_http_url or start_url or "").strip()
                    use_captured = True
                download_candidates: list[str] = []
                if step_url:
                    download_candidates = _resolve_download_candidates(
                        step_url,
                        target_date=target_date,
                        use_captured_url=use_captured,
                    )
                for candidate in download_candidates:
                    tried = await _try_download_page_url(
                        page, dest, candidate, timeout_ms=step_timeout_ms
                    )
                    if tried:
                        return dest, tried[1], tried[0]

                if _is_document_url(page.url):
                    source_url, file_type = await _download_document_url(
                        page, page.url, dest, timeout_ms=step_timeout_ms
                    )
                    return dest, file_type, source_url

                tried = await _try_download_page_url(page, dest, timeout_ms=step_timeout_ms)
                if tried:
                    return dest, tried[1], tried[0]

                pdfemb_url = await _find_pdfemb_url(page)
                if pdfemb_url and not _pattern_prefers_docx(pattern):
                    source_url, file_type = await _download_document_url(page, pdfemb_url, dest)
                    return dest, file_type, source_url

                # PDF iframe shortcut — skip when recipe asks for Word newsletters
                if not _pattern_prefers_docx(pattern):
                    iframe_pdf_url = await _find_iframe_pdf_url(page)
                    if iframe_pdf_url:
                        source_url, file_type = await _download_document_url(page, iframe_pdf_url, dest)
                        return dest, file_type, source_url

                mdocs_urls = await _find_mdocs_pdf_urls(page)
                for mdocs_url in mdocs_urls:
                    try:
                        source_url, file_type = await _download_document_url(
                            page, mdocs_url, dest, timeout_ms=step_timeout_ms
                        )
                        return dest, file_type, source_url
                    except RecipeReplayError as exc:
                        last_err = str(exc)
                        continue

                last_err = ""
                for resolved in await _collect_document_candidates(page, pattern):
                    try:
                        source_url, file_type = await _download_document_url(page, resolved, dest)
                        return dest, file_type, source_url
                    except RecipeReplayError as exc:
                        last_err = str(exc)
                        continue

                if last_err:
                    raise RecipeReplayError(last_err)
                raise RecipeReplayError("Recipe download step did not find a matching document URL")

            if action == "image":
                raw_url = (step.get("url") or "").strip()
                if not raw_url:
                    raise RecipeReplayError("Recipe image step missing URL")
                source_url, file_type = await _download_image_url_as_pdf(page, raw_url, dest)
                return dest, file_type, source_url

            if action == "image_stack":
                try:
                    count = int(step.get("count") or 2)
                except (TypeError, ValueError) as exc:
                    raise RecipeReplayError("Recipe image_stack step has invalid count") from exc
                if count < 1:
                    raise RecipeReplayError("Recipe image_stack step count must be at least 1")

                try:
                    await page.wait_for_load_state("networkidle", timeout=min(step_timeout_ms, 30_000))
                except PlaywrightTimeoutError:
                    pass
                await asyncio.sleep(2.0)

                selector = (step.get("selector") or "").strip()
                try:
                    min_long_side = int(step.get("min_long_side") or 800)
                    min_short_side = int(step.get("min_short_side") or 600)
                except (TypeError, ValueError) as exc:
                    raise RecipeReplayError("Recipe image_stack step has invalid size filter") from exc

                image_urls = await _find_stacked_bulletin_image_urls(
                    page,
                    count,
                    selector=selector,
                    min_long_side=min_long_side,
                    min_short_side=min_short_side,
                )
                if len(image_urls) < count:
                    raise RecipeReplayError(
                        f"Recipe image_stack found {len(image_urls)} bulletin image(s) but expected {count}"
                    )

                source_url, file_type = await _download_image_urls_as_pdf(
                    page, image_urls, dest, timeout_ms=step_timeout_ms
                )
                return dest, file_type, source_url

            if action == "html":
                html_url = (step.get("url") or "").strip() or page.url
                if not html_url:
                    raise RecipeReplayError("Recipe html step missing URL")
                if (step.get("url") or "").strip():
                    await page.goto(html_url, timeout=step_timeout_ms, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=step_timeout_ms)
                except PlaywrightTimeoutError:
                    pass
                await asyncio.sleep(2.5)
                await _print_page_to_pdf(page, dest)
                return dest, "print_to_pdf", html_url

            if action == "print_to_pdf":
                raw_pdf_url = (step.get("url") or "").strip()
                pdf_url = raw_pdf_url or page.url
                if not pdf_url:
                    raise RecipeReplayError("Recipe print_to_pdf step missing URL")
                if raw_pdf_url:
                    await page.goto(pdf_url, timeout=step_timeout_ms, wait_until="domcontentloaded")
                try:
                    await page.wait_for_load_state("networkidle", timeout=step_timeout_ms)
                except PlaywrightTimeoutError:
                    pass
                await asyncio.sleep(2.5)
                await _print_page_to_pdf(page, dest)
                return dest, "print_to_pdf", pdf_url

            if action == "crop_screenshot":
                sections = step.get("sections")
                if isinstance(sections, list) and sections:
                    # Multi-section crop: capture each section and stack vertically.
                    try:
                        from PIL import Image as PILImage
                    except ImportError as exc:
                        raise RecipeReplayError(
                            "Pillow is required for crop-screenshot bulletin conversion. Install with: pip install Pillow"
                        ) from exc

                    # Take one full-page screenshot shared across all sections.
                    screenshot_bytes = await page.screenshot(full_page=True)

                    try:
                        full_img = PILImage.open(io.BytesIO(screenshot_bytes))
                        cropped_parts: list = []
                        for sec in sections:
                            sx = int(sec.get("page_x", sec.get("x", 0)) or 0)
                            sy = int(sec.get("page_y", sec.get("y", 0)) or 0)
                            sw = int(sec.get("width", 0) or 0)
                            sh = int(sec.get("height", 0) or 0)
                            if sw <= 0 or sh <= 0:
                                continue
                            part = full_img.crop((sx, sy, sx + sw, sy + sh)).convert("RGB")
                            cropped_parts.append(part)

                        if not cropped_parts:
                            raise RecipeReplayError("No valid sections found in multi-section crop")

                        total_width = max(p.width for p in cropped_parts)
                        total_height = sum(p.height for p in cropped_parts)
                        combined = PILImage.new("RGB", (total_width, total_height), (255, 255, 255))
                        y_offset = 0
                        for part in cropped_parts:
                            combined.paste(part, (0, y_offset))
                            y_offset += part.height

                        combined.save(str(dest), "PDF", resolution=150)
                    except RecipeReplayError:
                        raise
                    except Exception as exc:
                        raise RecipeReplayError(f"Multi-section crop screenshot failed: {exc}") from exc

                    return dest, "crop_screenshot_to_pdf", page.url

                x = int(step.get("x", 0) or 0)
                y = int(step.get("y", 0) or 0)
                page_x = int(step.get("page_x", x) or x)
                page_y = int(step.get("page_y", y) or y)
                width = int(step.get("width", 0) or 0)
                height = int(step.get("height", 0) or 0)
                element_selector = str(step.get("element_selector", "") or "").strip()

                if width <= 0 or height <= 0:
                    raise RecipeReplayError("Recipe crop_screenshot step requires positive width/height")

                if element_selector:
                    try:
                        await page.locator(element_selector).first.scroll_into_view_if_needed(timeout=5000)
                    except Exception:
                        pass

                use_page_coords = "page_x" in step or "page_y" in step
                # page_x/page_y are absolute document coordinates, so capture the full page
                # before cropping. Otherwise viewport-only screenshots can crop the wrong area.
                screenshot_bytes = await page.screenshot(full_page=use_page_coords)

                try:
                    from PIL import Image as PILImage

                    img = PILImage.open(io.BytesIO(screenshot_bytes))
                    left = page_x if use_page_coords else x
                    top = page_y if use_page_coords else y
                    right = left + width
                    bottom = top + height
                    cropped = img.crop((left, top, right, bottom)).convert("RGB")
                    cropped.save(str(dest), "PDF", resolution=150)
                except ImportError as exc:
                    raise RecipeReplayError(
                        "Pillow is required for crop-screenshot bulletin conversion. Install with: pip install Pillow"
                    ) from exc
                except Exception as exc:
                    raise RecipeReplayError(f"Crop screenshot failed: {exc}") from exc

                return dest, "crop_screenshot_to_pdf", page.url

            raise RecipeReplayError(f"Unsupported recipe action: {action}")

        if downloads:
            file_type = await _save_download_to_pdf(downloads.pop(0), dest)
            return dest, file_type, page.url
        if _is_document_url(page.url):
            source_url, file_type = await _download_document_url(page, page.url, dest)
            return dest, file_type, source_url

        raise RecipeReplayError("Recipe finished without downloading a document")
    finally:
        try:
            await context.close()
        except Exception:
            pass
