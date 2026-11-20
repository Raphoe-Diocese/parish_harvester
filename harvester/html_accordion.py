"""Isolate exactly one current-week issue from an HTML accordion archive.

Never print an archive of old newsletters in place of a current bulletin.
"""
from __future__ import annotations

from datetime import date, timedelta


_ISOLATE_CURRENT_ACCORDION_JS = r"""
(args) => {
  const {sunday, month, monthAbbr, year} = args;
  const selectors = 'button, summary, [role="tab"], .accordion-toggle, .accordion-header, .rlta-panel-title';
  const candidates = Array.from(document.querySelectorAll(selectors));
  const current = (value) => {
    const text = String(value || '').replace(/\s+/g, ' ').toLowerCase().trim();
    if (!text || text.length > 180) return false;
    if (!new RegExp('\\b' + year + '\\b').test(text)) return false;
    if (!new RegExp('\\b' + month + '\\b|\\b' + monthAbbr + '\\b').test(text)) return false;
    const days = Array.from(text.matchAll(/\b(\d{1,2})(?:st|nd|rd|th)?\b/g))
      .map(match => Number(match[1]));
    return days.includes(sunday);
  };
  for (const title of candidates) {
    const label = String(title.innerText || title.textContent || '').replace(/\s+/g, ' ').trim();
    if (!current(label)) continue;
    const container = title.closest(
      '.accordion-item, .accordion-group, .rlta-panel, .panel, details, .card'
    );
    let panel = null;
    const panelId = (title.getAttribute('aria-controls') ||
      title.getAttribute('data-bs-target') ||
      title.getAttribute('data-target') || '').replace(/^#/, '').trim();
    if (panelId && /^[a-zA-Z0-9_-]+$/.test(panelId)) panel = document.getElementById(panelId);
    if (!panel && container) {
      panel = container.querySelector(
        '.accordion-body, .accordion-inner, .panel-body, .rlta-panel-content, .card-body, [role="region"], .collapse'
      );
    }
    if (!panel) panel = title.nextElementSibling ||
      (title.parentElement && title.parentElement.nextElementSibling);
    if (!panel || panel === document.body || panel === container) continue;
    const text = String(panel.innerText || panel.textContent || '').replace(/\s+/g, ' ').trim();
    if (text.length < 230 || !/(mass|aifrinn|weekly|parish|intention|sunday)/i.test(text)) continue;
    // CarrickOnline repeats this distinctive masthead once per weekly
    // accordion entry. More than one means the panel contains an archive,
    // not the single selected issue; never publish a stitched fake week.
    const mastheads = text.match(/nuachtlitir na carraige agus mhin an aoire/gi) || [];
    if (mastheads.length > 1) continue;
    const nested = Array.from(panel.querySelectorAll(selectors));
    if (nested.some(node => {
      const other = String(node.innerText || node.textContent || '');
      return other !== label && /\b20\d{2}\b/.test(other);
    })) continue;
    const body = document.createElement('main');
    body.setAttribute('data-ph-bulletin-root', '1');
    body.id = 'ph-current-issue';
    const heading = document.createElement('h1');
    heading.textContent = label;
    body.appendChild(heading);
    const copy = panel.cloneNode(true);
    copy.removeAttribute('hidden');
    copy.removeAttribute('aria-hidden');
    copy.style.display = 'block';
    copy.style.visibility = 'visible';
    copy.classList.remove('collapse', 'collapsed', 'd-none', 'hidden');
    body.appendChild(copy);
    const style = document.createElement('style');
    style.textContent = [
      'body{margin:0;padding:12mm;background:#fff;color:#111;font:12pt/1.45 Arial,sans-serif;}',
      '#ph-current-issue{display:block!important;max-width:100%!important;}',
      '#ph-current-issue .collapse,#ph-current-issue .accordion-body,' +
        '#ph-current-issue .panel-body{display:block!important;visibility:visible!important;height:auto!important;}',
      '#ph-current-issue img{max-width:100%!important;height:auto!important;}',
      '#ph-current-issue table{width:100%;border-collapse:collapse;}',
      '#ph-current-issue td,#ph-current-issue th{border:1px solid #ddd;padding:4px;}'
    ].join('\n');
    document.head.appendChild(style);
    document.body.replaceChildren(body);
    return {ok:true, chars:text.length, heading:label};
  }
  return {ok:false, reason:'No isolated current-week accordion bulletin with sufficient text'};
}
"""


async def isolate_current_accordion_bulletin(page, target: date) -> dict:
    """Keep the target Sunday issue only, or raise rather than print old issues."""
    if not isinstance(target, date) or target.weekday() != 6:
        raise ValueError("Current accordion capture requires a Sunday harvest date")
    args = {
        "sunday": target.day,
        "month": target.strftime("%B").lower(),
        "monthAbbr": target.strftime("%b").lower(),
        "year": target.year,
    }
    result = await page.evaluate(_ISOLATE_CURRENT_ACCORDION_JS, args)
    if not isinstance(result, dict) or result.get("ok") is not True:
        reason = result.get("reason", "Current accordion issue absent") if isinstance(result, dict) else "Invalid browser result"
        raise ValueError(str(reason))
    if int(result.get("chars") or 0) < 230:
        raise ValueError("Accordion issue text too short to be complete")
    return result
