"""Shared public-site chrome: sticky OCR search and a back-to-top button."""

TEAL = "#1a6b6b"
DEEP_TEAL = "#14524f"


def sticky_search_css(paper: str) -> str:
    """Search chrome scrolls away until a term is typed, then it sticks."""
    return f"""
    .ocr-sticky-chrome {{
      position: relative;
      top: auto;
      z-index: 8;
      background: {paper};
      padding: 8px 0 10px;
      margin: 0 0 8px;
    }}
    .ocr-sticky-chrome.is-searching {{
      position: sticky;
      top: 0;
    }}
    .ocr-sticky-chrome .ocr-zoom-bar {{
      position: relative;
      top: auto;
    }}
    html.is-ocr-searching {{ scroll-padding-top: 10rem; }}
    mark.search-active {{ scroll-margin-top: 10rem; }}
    """


def scroll_top_css() -> str:
    return f"""
    .scroll-top-btn {{
      position: fixed;
      right: 16px;
      bottom: 20px;
      z-index: 9999;
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


def favicon_link_tags() -> str:
    return (
        '<link rel="icon" type="image/png" href="/favicon.png" />\n'
        '  <link rel="apple-touch-icon" href="/apple-touch-icon.png" />'
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
    """Show ↑ when the page *or* the locked PDF/OCR box is scrolled.

    Raphoe keeps `.pdf-inpage-pages` and ``#ocr-panel`` at a locked 850px /
    450px with ``overflow: auto``. Readers scroll *inside* those boxes, so
    ``window.scrollY`` stays near 0.

    Live Raphoe HTML puts this script *before* ``#scroll-top-btn``, so the
    old ``if (!btn) return`` died on parse. Document-capture ``scroll`` also
    misses inner ``overflow: auto`` boxes in Safari / some Chromium builds.
    Bind the boxes themselves, wait until the button exists, and re-bind
    after PDF.js replaces ``.pdf-inpage-pages``. Click jumps the boxes and
    the window.
    """
    return """
    (function () {
      function boot() {
        var btn = document.getElementById('scroll-top-btn');
        if (!btn) {
          if (!document.body) return;
          btn = document.createElement('button');
          btn.type = 'button';
          btn.className = 'scroll-top-btn';
          btn.id = 'scroll-top-btn';
          btn.setAttribute('aria-label', 'Back to top');
          btn.textContent = '↑';
          document.body.appendChild(btn);
        }
        function innerBoxes() {
          return Array.prototype.slice.call(
            document.querySelectorAll('.pdf-inpage-pages, #ocr-panel')
          );
        }
        function maxInnerScroll() {
          return innerBoxes().reduce(function (max, el) {
            return Math.max(max, el.scrollTop || 0);
          }, 0);
        }
        function shown() {
          var y = window.scrollY || document.documentElement.scrollTop || 0;
          btn.classList.toggle('is-visible', y > 80 || maxInnerScroll() > 16);
        }
        function shownSoon() {
          shown();
          if (window.requestAnimationFrame) window.requestAnimationFrame(shown);
          else window.setTimeout(shown, 16);
        }
        function bindBox(el) {
          if (!el || el.getAttribute('data-pp-scroll-top') === '1') return;
          el.setAttribute('data-pp-scroll-top', '1');
          el.addEventListener('scroll', shownSoon, { passive: true });
        }
        function bindBoxes() {
          innerBoxes().forEach(bindBox);
          shown();
        }
        window.parishPressBindScrollTopBoxes = bindBoxes;
        if (btn.getAttribute('data-pp-bound') !== 'inner-2') {
          btn.setAttribute('data-pp-bound', 'inner-2');
          var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          window.addEventListener('scroll', shownSoon, { passive: true });
          document.addEventListener('scroll', shownSoon, { capture: true, passive: true });
          document.addEventListener('wheel', shownSoon, { capture: true, passive: true });
          document.addEventListener('touchmove', shownSoon, { capture: true, passive: true });
          if (window.MutationObserver && document.body) {
            new MutationObserver(bindBoxes).observe(document.body, { childList: true, subtree: true });
          }
          btn.addEventListener('click', function () {
            var behavior = reduce ? 'auto' : 'smooth';
            window.scrollTo({ top: 0, behavior: behavior });
            innerBoxes().forEach(function (el) {
              el.scrollTop = 0;
              if (el.scrollTo) el.scrollTo({ top: 0, behavior: behavior });
            });
            window.setTimeout(shown, reduce ? 0 : 400);
          });
        }
        bindBoxes();
      }
      if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
      } else {
        boot();
      }
    })();
    """
