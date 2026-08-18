/**
 * Parish Press — in-page PDF viewer (mobile / tablet)
 *
 * Phones cannot embed a raw PDF in <iframe> (sad-document icon). This script
 * paints the bulletin on a canvas with Mozilla PDF.js, streaming the first
 * page as soon as range requests allow. Desktop keeps the native iframe.
 *
 * Progressive load: disableAutoFetch + streaming + HTTP Range. Mega PDFs are
 * 14–20 MB; we must not wait for the whole file before showing page 1.
 */
(function () {
  if (window.__parishPressPdfInpage) return;
  window.__parishPressPdfInpage = true;

  var PDFJS_SCRIPTS = [
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js",
    "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js",
  ];
  var PDFJS_WORKERS = [
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js",
    "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js",
  ];

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

  function needsInpage() {
    return prefersNativePdf() || narrowViewport();
  }

  function ensureStyles() {
    if (document.getElementById("pdf-inpage-viewer-style")) return;
    var style = document.createElement("style");
    style.id = "pdf-inpage-viewer-style";
    style.textContent =
      ".pdf-inpage-viewer{display:none;flex-direction:column;min-height:0;flex:1 1 auto;background:#3a3f42;color:#e8eeed}" +
      ".pdf-inpage-toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px;background:#14524f;color:#fff;flex:0 0 auto}" +
      ".pdf-inpage-nav{display:flex;align-items:center;gap:8px}" +
      ".pdf-inpage-nav button{min-width:44px;min-height:40px;border:1px solid rgba(255,255,255,.35);border-radius:6px;background:#1a6b6b;color:#fff;font-size:1.25rem;font-weight:700}" +
      ".pdf-inpage-page-label{font-size:.9rem;font-weight:700;min-width:7rem;text-align:center}" +
      ".pdf-inpage-backup{display:flex;gap:8px;flex-wrap:wrap}" +
      ".pdf-inpage-backup a{color:#fff;font-weight:700;font-size:.85rem}" +
      ".pdf-inpage-status{padding:10px 12px;background:#1f3d3c;color:#d8f0ee;font-size:.9rem}" +
      ".pdf-inpage-pages{flex:1 1 auto;overflow:auto;-webkit-overflow-scrolling:touch;background:#525659;padding:8px 0 16px}" +
      ".pdf-inpage-page-slot{margin:0 auto 10px;background:#3a3f42;min-height:180px}" +
      ".pdf-inpage-page-slot canvas{display:block;width:100%;height:auto;background:#fff}" +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf,body.is-native-pdf .pdf-standalone-shell{" +
      "height:70vh!important;min-height:450px!important;display:flex;flex-direction:column;background:#3a3f42}" +
      ".pdf-frame-wrap.is-native-pdf iframe,.pdf-frame-wrap.is-native-pdf .fullscreen-btn," +
      "body.is-native-pdf iframe.pdf-frame,.pdf-standalone-shell.is-native-pdf iframe.pdf-frame{display:none!important}" +
      ".pdf-frame-wrap.is-native-pdf .pdf-inpage-viewer,.pdf-frame-wrap.is-native-pdf .pdf-mobile-fallback," +
      "body.is-native-pdf .pdf-inpage-viewer,body.is-native-pdf .pdf-mobile-fallback," +
      ".pdf-standalone-shell.is-native-pdf .pdf-inpage-viewer{display:flex!important;flex:1 1 auto;min-height:0}" +
      "@media (max-width:1024px){" +
      ".pdf-frame-wrap,.pdf-standalone-shell{height:70vh!important;min-height:450px!important;display:flex;flex-direction:column;background:#3a3f42}" +
      ".pdf-frame-wrap iframe,.pdf-frame-wrap .fullscreen-btn,.pdf-standalone-shell iframe.pdf-frame{display:none!important}" +
      ".pdf-inpage-viewer,.pdf-mobile-fallback{display:flex!important;flex:1 1 auto;min-height:0}" +
      "}";
    document.head.appendChild(style);
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = function () {
        resolve(src);
      };
      s.onerror = function () {
        reject(new Error("Failed to load " + src));
      };
      document.head.appendChild(s);
    });
  }

  function loadPdfJs() {
    if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
    var i = 0;
    function next() {
      if (i >= PDFJS_SCRIPTS.length) {
        return Promise.reject(new Error("Could not load PDF.js"));
      }
      var src = PDFJS_SCRIPTS[i++];
      return loadScript(src).catch(next);
    }
    return next().then(function () {
      if (!window.pdfjsLib) throw new Error("pdfjsLib missing after load");
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKERS[0];
      return window.pdfjsLib;
    });
  }

  function resolvePdfUrl(wrap) {
    if (!wrap) return "";
    var host = wrap.querySelector("[data-pdf-src], #pdf-inpage-viewer, #pdf-mobile-fallback, .pdf-inpage-viewer, .pdf-mobile-fallback");
    var fromData = host && host.getAttribute("data-pdf-src");
    if (fromData) return fromData;
    var iframe = wrap.querySelector("iframe");
    var pdfUrl = (iframe && (iframe.getAttribute("src") || iframe.src)) || "";
    if (pdfUrl && pdfUrl.indexOf("about:blank") !== 0) return pdfUrl;
    var openBtn = document.querySelector(
      '#panel-pdf a[href*=".pdf"], .quiet-links a[href*=".pdf"], .download-link[href], .download-link-top[href], a.pdf-mobile-fallback-btn[href]'
    );
    return (openBtn && (openBtn.getAttribute("href") || openBtn.href)) || "";
  }

  function setStatus(host, text, isError) {
    var el = host.querySelector(".pdf-inpage-status");
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = text;
    el.style.background = isError ? "#7f1d1d" : "#1f3d3c";
  }

  function buildViewer(host, pdfUrl) {
    host.classList.add("pdf-inpage-viewer");
    host.setAttribute("data-pdf-src", pdfUrl);
    host.innerHTML =
      '<div class="pdf-inpage-toolbar">' +
      '<div class="pdf-inpage-nav">' +
      '<button type="button" class="pdf-inpage-prev" aria-label="Previous page">‹</button>' +
      '<span class="pdf-inpage-page-label">Loading…</span>' +
      '<button type="button" class="pdf-inpage-next" aria-label="Next page">›</button>' +
      "</div>" +
      '<div class="pdf-inpage-backup">' +
      '<a href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '" target="_blank" rel="noopener noreferrer">Open PDF</a>' +
      '<a href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '" download>Download</a>' +
      "</div></div>" +
      '<div class="pdf-inpage-status">Showing first page…</div>' +
      '<div class="pdf-inpage-pages" role="document" aria-label="Bulletin PDF pages"></div>';
    return host;
  }

  function unloadIframe(wrap) {
    if (!wrap) return;
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

  function renderPageToSlot(page, slot, width) {
    var unscaled = page.getViewport({ scale: 1 });
    var cssWidth = Math.max(240, width || slot.clientWidth || 320);
    var dpr = window.devicePixelRatio || 1;
    var scale = (cssWidth / unscaled.width) * dpr;
    var viewport = page.getViewport({ scale: scale });
    var canvas = slot.querySelector("canvas") || document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = cssWidth + "px";
    canvas.style.height = Math.floor(unscaled.height * (cssWidth / unscaled.width)) + "px";
    if (!canvas.parentNode) slot.appendChild(canvas);
    slot.style.width = cssWidth + "px";
    return page.render({ canvasContext: canvas.getContext("2d", { alpha: false }), viewport: viewport }).promise;
  }

  function startViewer(host, pdfUrl) {
    if (host.getAttribute("data-pdf-started") === "1") return;
    host.setAttribute("data-pdf-started", "1");
    var pagesEl = host.querySelector(".pdf-inpage-pages");
    var label = host.querySelector(".pdf-inpage-page-label");
    var prevBtn = host.querySelector(".pdf-inpage-prev");
    var nextBtn = host.querySelector(".pdf-inpage-next");
    var currentPage = 1;
    var pdfDoc = null;
    var rendering = Object.create(null);

    function pageWidth() {
      return Math.floor((pagesEl && pagesEl.clientWidth) || host.clientWidth || 320);
    }

    function updateLabel() {
      if (!label || !pdfDoc) return;
      label.textContent = "Page " + currentPage + " of " + pdfDoc.numPages;
      if (prevBtn) prevBtn.disabled = currentPage <= 1;
      if (nextBtn) nextBtn.disabled = currentPage >= pdfDoc.numPages;
    }

    function ensureSlot(num) {
      var slot = pagesEl.querySelector('[data-page="' + num + '"]');
      if (slot) return slot;
      slot = document.createElement("div");
      slot.className = "pdf-inpage-page-slot";
      slot.dataset.page = String(num);
      pagesEl.appendChild(slot);
      return slot;
    }

    function paint(num) {
      if (!pdfDoc || rendering[num]) return rendering[num];
      var slot = ensureSlot(num);
      rendering[num] = pdfDoc
        .getPage(num)
        .then(function (page) {
          return renderPageToSlot(page, slot, pageWidth());
        })
        .catch(function (err) {
          slot.textContent = "Could not draw page " + num + ".";
          console.warn("PDF page render failed", num, err);
        });
      return rendering[num];
    }

    function showPage(num) {
      if (!pdfDoc) return;
      currentPage = Math.max(1, Math.min(pdfDoc.numPages, num));
      updateLabel();
      var slot = ensureSlot(currentPage);
      paint(currentPage).then(function () {
        try {
          slot.scrollIntoView({ block: "nearest" });
        } catch (e) {}
      });
      if (currentPage < pdfDoc.numPages) paint(currentPage + 1);
    }

    setStatus(host, "Showing first page…");
    loadPdfJs()
      .then(function (pdfjsLib) {
        return pdfjsLib.getDocument({
          url: pdfUrl,
          disableAutoFetch: true,
          disableStream: false,
          disableRange: false,
          rangeChunkSize: 65536,
        }).promise;
      })
      .then(function (pdf) {
        pdfDoc = pdf;
        setStatus(host, "");
        showPage(1);
      })
      .catch(function (err) {
        console.warn("PDF.js failed", err);
        setStatus(host, "Could not show the PDF here. Use Open PDF or Download.", true);
        host.setAttribute("data-pdf-started", "0");
      });

    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        showPage(currentPage - 1);
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        showPage(currentPage + 1);
      });
    }

    var touchStartX = 0;
    pagesEl.addEventListener(
      "touchstart",
      function (ev) {
        if (!ev.changedTouches || !ev.changedTouches[0]) return;
        touchStartX = ev.changedTouches[0].clientX;
      },
      { passive: true }
    );
    pagesEl.addEventListener(
      "touchend",
      function (ev) {
        if (!ev.changedTouches || !ev.changedTouches[0]) return;
        var dx = ev.changedTouches[0].clientX - touchStartX;
        if (dx > 60) showPage(currentPage - 1);
        else if (dx < -60) showPage(currentPage + 1);
      },
      { passive: true }
    );
  }

  function activateWrap(wrap, pdfUrl) {
    if (!wrap || !pdfUrl) return;
    unloadIframe(wrap);
    var host =
      wrap.querySelector(".pdf-inpage-viewer") ||
      wrap.querySelector(".pdf-mobile-fallback") ||
      wrap.querySelector("#pdf-inpage-viewer") ||
      wrap.querySelector("#pdf-mobile-fallback");
    if (!host) {
      host = document.createElement("div");
      wrap.appendChild(host);
    }
    host = buildViewer(host, pdfUrl);
    startViewer(host, pdfUrl);
  }

  function run() {
    ensureStyles();
    if (!needsInpage()) return;

    document.querySelectorAll(".pdf-frame-wrap").forEach(function (wrap) {
      activateWrap(wrap, resolvePdfUrl(wrap));
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
      if (shell) shell.classList.add("is-native-pdf");
      try {
        standalone.setAttribute("hidden", "");
        standalone.removeAttribute("src");
      } catch (e) {}
      var host =
        document.getElementById("pdf-inpage-viewer") ||
        document.getElementById("pdf-mobile-fallback") ||
        document.querySelector(".pdf-inpage-viewer") ||
        document.querySelector(".pdf-mobile-fallback");
      if (!host) {
        host = document.createElement("div");
        if (shell) shell.appendChild(host);
        else document.body.appendChild(host);
      }
      host = buildViewer(host, pdfUrl);
      startViewer(host, pdfUrl);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
