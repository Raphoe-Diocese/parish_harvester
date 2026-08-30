"""Shared public-site chrome: sticky OCR search and a back-to-top button."""

TEAL = "#1a6b6b"
DEEP_TEAL = "#14524f"


def favicon_link_tags() -> str:
    """Parish Press tab icon. Files live at the Pages root (`docs/`)."""
    return (
        '<link rel="icon" type="image/png" href="/favicon.png" />\n'
        '  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />'
    )


def sticky_search_css(paper: str) -> str:
    """Search chrome scrolls away until a term is typed, then it sticks."""
    return f"""
    .ocr-sticky-chrome {{
      position: relative;
      top: auto;
      z-index: 40;
      background: {paper};
      padding: 8px 0 10px;
      margin: 0 0 8px;
    }}
    .ocr-sticky-chrome.is-searching {{
      position: sticky;
      top: 0;
      box-shadow: 0 8px 16px {paper};
    }}
    .ocr-sticky-chrome .ocr-zoom-bar {{
      position: relative;
      top: auto;
    }}
    html.is-ocr-searching {{ scroll-padding-top: 8rem; }}
    mark.search-active {{ scroll-margin-top: 8rem; }}
    """


def scroll_top_css() -> str:
    return f"""
    .scroll-top-btn {{
      position: fixed;
      right: 16px;
      bottom: 20px;
      z-index: 30;
      width: 46px;
      height: 46px;
      border: 0;
      border-radius: 999px;
      background: {TEAL};
      color: #fff;
      font-size: 1.35rem;
      line-height: 1;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(17, 75, 75, 0.28);
      opacity: 0;
      pointer-events: none;
      transform: translateY(8px);
      transition: opacity 160ms ease, transform 160ms ease;
    }}
    .scroll-top-btn.is-visible {{
      opacity: 1;
      pointer-events: auto;
      transform: none;
    }}
    .scroll-top-btn:focus-visible {{
      outline: 3px solid {DEEP_TEAL};
      outline-offset: 2px;
    }}
    @media (prefers-reduced-motion: reduce) {{
      .scroll-top-btn {{ transition: none; }}
    }}
    """


def scroll_top_html() -> str:
    return (
        '<button type="button" class="scroll-top-btn" id="scroll-top-btn" '
        'aria-label="Back to top">↑</button>'
    )


def sticky_search_js() -> str:
    """Pin the search bar only while the box has a search term."""
    return """
    (function () {
      function syncOcrSearchSticky() {
        var chrome = document.querySelector('.ocr-sticky-chrome');
        var input = document.getElementById('ocr-search');
        if (!chrome || !input) return;
        var active = Boolean((input.value || '').trim());
        chrome.classList.toggle('is-searching', active);
        document.documentElement.classList.toggle('is-ocr-searching', active);
      }
      document.addEventListener('input', function (event) {
        if (event.target && event.target.id === 'ocr-search') syncOcrSearchSticky();
      }, true);
      document.addEventListener('click', function (event) {
        if (event.target && event.target.id === 'clear-search') {
          window.setTimeout(syncOcrSearchSticky, 0);
        }
      }, true);
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncOcrSearchSticky);
      } else {
        syncOcrSearchSticky();
      }
    })();
    """


def scroll_top_js() -> str:
    return """
    (function () {
      var btn = document.getElementById('scroll-top-btn');
      if (!btn) return;
      var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      function shown() {
        var y = window.scrollY || document.documentElement.scrollTop || 0;
        btn.classList.toggle('is-visible', y > 240);
      }
      window.addEventListener('scroll', shown, { passive: true });
      shown();
      btn.addEventListener('click', function () {
        window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
      });
    })();
    """
