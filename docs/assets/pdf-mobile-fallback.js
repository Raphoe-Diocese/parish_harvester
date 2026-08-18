/**
 * Parish Press — mobile PDF embed fallback
 *
 * Phones/tablets often cannot show a PDF inside <iframe>/<embed>.
 * CSS @media (max-width: 1024px) is the primary fix (hides iframe, shows
 * View PDF + Download). This script injects that CSS when missing, builds
 * the panel if the page has none, and unloads the iframe on narrow screens
 * or known mobile UAs (backup for wide tablets that still can't embed).
 */
(function () {
  function prefersNativePdf() {
    var ua = navigator.userAgent || "";
    if (/Android/i.test(ua)) return true;
    if (/iPhone|iPod/i.test(ua)) return true;
    if (/iPad/i.test(ua)) return true;
    if (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) return true;
    return false;
  }

  function narrowViewport() {
    try {
      return window.matchMedia && window.matchMedia("(max-width: 1024px)").matches;
    } catch (e) {
      return false;
    }
  }

  function ensureStyles() {
    if (document.getElementById("pdf-mobile-fallback-style")) return;
    var style = document.createElement("style");
    style.id = "pdf-mobile-fallback-style";
    style.textContent =
      ".pdf-mobile-fallback{display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:36px 20px;text-align:center;min-height:220px;background:#eef2f2}" +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf{height:auto;min-height:0;background:#eef2f2}" +
      ".pdf-frame-wrap.is-native-pdf iframe,.pdf-frame-wrap.is-native-pdf .fullscreen-btn,body.is-native-pdf iframe.pdf-frame{display:none!important}" +
      ".pdf-frame-wrap.is-native-pdf .pdf-mobile-fallback,body.is-native-pdf .pdf-mobile-fallback,.pdf-standalone-shell.is-native-pdf .pdf-mobile-fallback{display:flex!important;flex:1 1 auto}" +
      "@media (max-width:1024px){" +
      ".pdf-frame-wrap{height:auto!important;min-height:0!important;background:#eef2f2}" +
      ".pdf-frame-wrap iframe,.pdf-frame-wrap .fullscreen-btn,.pdf-standalone-shell iframe.pdf-frame{display:none!important}" +
      ".pdf-standalone-shell{height:auto;min-height:0;background:#eef2f2}" +
      ".pdf-mobile-fallback{display:flex!important;flex:1 1 auto}" +
      "}" +
      ".pdf-mobile-fallback-title{margin:0;font-size:1.15rem;font-weight:800;color:#14524f}" +
      ".pdf-mobile-fallback-note{margin:0;max-width:28rem;color:#4b5563;font-size:.95rem;line-height:1.45}" +
      ".pdf-mobile-fallback-actions{display:flex;flex-direction:column;gap:10px;width:min(100%,22rem);margin-top:4px}" +
      ".pdf-mobile-fallback-btn{display:inline-flex;align-items:center;justify-content:center;min-height:48px;padding:12px 18px;border-radius:8px;border:2px solid #1a6b6b;background:#1a6b6b;color:#fff;font-weight:700;font-size:1rem;text-decoration:none}" +
      ".pdf-mobile-fallback-btn.secondary{background:#fff;color:#1a6b6b}" +
      "body.is-native-pdf{background:#eef2f2}";
    document.head.appendChild(style);
  }

  function buildPanel(pdfUrl) {
    var panel = document.createElement("div");
    panel.className = "pdf-mobile-fallback";
    panel.innerHTML =
      '<p class="pdf-mobile-fallback-title">View this bulletin PDF</p>' +
      '<p class="pdf-mobile-fallback-note">On phones, PDFs open best in the browser\u2019s built-in viewer. Tap below to read or download.</p>' +
      '<div class="pdf-mobile-fallback-actions">' +
      '<a class="pdf-mobile-fallback-btn" href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '" target="_blank" rel="noopener noreferrer">View PDF</a>' +
      '<a class="pdf-mobile-fallback-btn secondary" href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '" download>Download PDF</a>' +
      "</div>";
    return panel;
  }

  function ensurePanel(wrap, pdfUrl) {
    if (!wrap || !pdfUrl) return;
    var panel = wrap.querySelector(".pdf-mobile-fallback");
    if (!panel) {
      panel = buildPanel(pdfUrl);
      wrap.appendChild(panel);
    }
  }

  function activateWrap(wrap, pdfUrl) {
    if (!wrap || !pdfUrl) return;
    ensurePanel(wrap, pdfUrl);
    wrap.classList.add("is-native-pdf");
    var iframe = wrap.querySelector("iframe");
    if (iframe) {
      iframe.setAttribute("hidden", "");
      try {
        iframe.removeAttribute("src");
      } catch (e) {}
    }
    var fs = wrap.querySelector(".fullscreen-btn");
    if (fs) fs.setAttribute("hidden", "");
  }

  function resolvePdfUrl(wrap) {
    var iframe = wrap.querySelector("iframe");
    var pdfUrl = (iframe && (iframe.getAttribute("src") || iframe.src)) || "";
    if (!pdfUrl || pdfUrl === "about:blank") {
      var openBtn = document.querySelector(
        '#panel-pdf a.toolbar-btn[target="_blank"], .panel-toolbar a.toolbar-btn[target="_blank"], #panel-pdf .quiet-links a[target="_blank"]'
      );
      if (openBtn) pdfUrl = openBtn.getAttribute("href") || "";
    }
    return pdfUrl;
  }

  function run() {
    // Always inject CSS so the media-query path works without UA sniffing.
    ensureStyles();

    document.querySelectorAll(".pdf-frame-wrap").forEach(function (wrap) {
      var pdfUrl = resolvePdfUrl(wrap);
      // Ensure the panel exists so CSS can show it at <=1024px.
      ensurePanel(wrap, pdfUrl);
      if (prefersNativePdf() || narrowViewport()) {
        activateWrap(wrap, pdfUrl);
      }
    });

    var standalone = document.querySelector("iframe.pdf-frame");
    if (standalone && !standalone.closest(".pdf-frame-wrap")) {
      var pdfUrl =
        standalone.getAttribute("src") ||
        standalone.src ||
        (document.querySelector(".download-link") || {}).href ||
        "";
      if (!pdfUrl || pdfUrl.indexOf("about:blank") === 0) return;
      var shell = standalone.parentElement;
      var panel =
        document.getElementById("pdf-mobile-fallback") ||
        document.querySelector(".pdf-mobile-fallback");
      if (!panel) {
        panel = buildPanel(pdfUrl);
        if (shell) shell.appendChild(panel);
        else document.body.appendChild(panel);
      }
      if (prefersNativePdf() || narrowViewport()) {
        document.body.classList.add("is-native-pdf");
        if (shell && shell.classList.contains("pdf-standalone-shell")) {
          shell.classList.add("is-native-pdf");
        }
        standalone.setAttribute("hidden", "");
        try {
          standalone.removeAttribute("src");
        } catch (e) {}
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
