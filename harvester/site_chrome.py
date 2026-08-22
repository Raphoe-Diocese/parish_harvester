"""Shared public-site chrome: sticky OCR search and a back-to-top button."""

TEAL = "#1a6b6b"
DEEP_TEAL = "#14524f"


def sticky_search_css(paper: str) -> str:
    """Keep zoom + search on screen while staff scroll a long text bulletin."""
    return f"""
    .ocr-sticky-chrome {{
      position: sticky;
      top: 0;
      z-index: 8;
      background: {paper};
      padding: 8px 0 10px;
      margin: 0 0 8px;
    }}
    .ocr-sticky-chrome .ocr-zoom-bar {{
      position: relative;
      top: auto;
    }}
    html {{ scroll-padding-top: 10rem; }}
    mark.search-active {{ scroll-margin-top: 10rem; }}
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
