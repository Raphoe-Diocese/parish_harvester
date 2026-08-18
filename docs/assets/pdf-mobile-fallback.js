/**
 * Parish Press — mobile PDF embed fallback
 *
 * Phones/tablets often cannot show a PDF inside <iframe>/<embed>.
 * This script replaces the broken frame with View PDF + Download buttons
 * that open the browser's native PDF viewer. Desktop is left alone.
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

  if (!prefersNativePdf()) return;

  function ensureStyles() {
    if (document.getElementById("pdf-mobile-fallback-style")) return;
    var style = document.createElement("style");
    style.id = "pdf-mobile-fallback-style";
    style.textContent =
      ".pdf-mobile-fallback{display:none;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:36px 20px;text-align:center;min-height:220px;background:#eef2f2}" +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf{height:auto;min-height:0;background:#eef2f2}" +
      ".pdf-frame-wrap.is-native-pdf iframe,.pdf-frame-wrap.is-native-pdf .fullscreen-btn,body.is-native-pdf iframe.pdf-frame{display:none!important}" +
      ".pdf-frame-wrap.is-native-pdf .pdf-mobile-fallback,body.is-native-pdf .pdf-mobile-fallback,.pdf-standalone-shell.is-native-pdf .pdf-mobile-fallback{display:flex;flex:1 1 auto}" +
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

  function activateWrap(wrap, pdfUrl) {
    if (!wrap || !pdfUrl) return;
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
    var panel = wrap.querySelector(".pdf-mobile-fallback");
    if (!panel) {
      panel = buildPanel(pdfUrl);
      wrap.appendChild(panel);
    } else {
      panel.removeAttribute("hidden");
    }
  }

  function run() {
    ensureStyles();

    document.querySelectorAll(".pdf-frame-wrap").forEach(function (wrap) {
      var iframe = wrap.querySelector("iframe");
      var pdfUrl = (iframe && (iframe.getAttribute("src") || iframe.src)) || "";
      if (!pdfUrl || pdfUrl === "about:blank") {
        var openBtn = document.querySelector(
          '#panel-pdf a.toolbar-btn[target="_blank"], .panel-toolbar a.toolbar-btn[target="_blank"]'
        );
        if (openBtn) pdfUrl = openBtn.getAttribute("href") || "";
      }
      activateWrap(wrap, pdfUrl);
    });

    var standalone = document.querySelector("iframe.pdf-frame");
    if (standalone && !standalone.closest(".pdf-frame-wrap")) {
      var pdfUrl =
        standalone.getAttribute("src") ||
        standalone.src ||
        (document.querySelector(".download-link") || {}).href ||
        "";
      if (!pdfUrl || pdfUrl.indexOf("about:blank") === 0) return;
      document.body.classList.add("is-native-pdf");
      var shell = standalone.parentElement;
      if (shell && shell.classList.contains("pdf-standalone-shell")) {
        shell.classList.add("is-native-pdf");
      }
      standalone.setAttribute("hidden", "");
      try {
        standalone.removeAttribute("src");
      } catch (e) {}
      var panel = document.getElementById("pdf-mobile-fallback") || document.querySelector(".pdf-mobile-fallback");
      if (!panel) {
        panel = buildPanel(pdfUrl);
        if (shell) shell.appendChild(panel);
        else document.body.appendChild(panel);
      } else {
        panel.removeAttribute("hidden");
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
