/**
 * Parish Press — in-page PDF viewer (desktop + mobile)
 *
 * Phones cannot embed a raw PDF in <iframe> (sad-document icon). Desktop
 * Chrome/Edge iframes show a "Page X of Y" toolbar Frank asked to remove.
 * This script paints pages on stacked canvases with Mozilla PDF.js inside
 * a locked 850px box (450px on phones) with inner scroll — not every
 * parish down the page. Open PDF / Download stay.
 *
 * Progressive load: disableAutoFetch + streaming + HTTP Range on phone and
 * desktop, so page 1 can show before the whole mega arrives. If Range fails,
 * fall back to a full-file load. Paint page 1 first; other pages draw when
 * they near the screen.
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

  function ensureStyles() {
    if (document.getElementById("pdf-inpage-viewer-style")) return;
    var style = document.createElement("style");
    style.id = "pdf-inpage-viewer-style";
    style.textContent =
      ".pdf-inpage-viewer{display:flex!important;flex-direction:column;min-height:850px!important;flex:1 1 auto;background:#3a3f42;color:#e8eeed}" +
      ".pdf-inpage-toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:8px;padding:8px 10px;background:#14524f;color:#fff;flex:0 0 auto}" +
      ".pdf-inpage-backup{display:flex;gap:8px;flex-wrap:wrap}" +
      ".pdf-inpage-backup a{color:#fff;font-weight:700;font-size:.85rem}" +
      ".pdf-inpage-status{padding:10px 12px;background:#1f3d3c;color:#d8f0ee;font-size:.9rem}" +
      ".pdf-inpage-pages,#panel-pdf .pdf-inpage-pages,#panel-pdf.az-expanded .pdf-inpage-pages{" +
      "box-sizing:border-box;flex:1 1 auto;height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important;background:#525659;padding:8px 0 16px}" +
      ".pdf-inpage-page-slot{margin:0 auto 10px;background:#3a3f42;min-height:180px;position:relative}" +
      ".pdf-inpage-page-slot canvas{display:block;width:100%;height:auto;background:#fff}" +
      ".pdf-link-layer{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none}" +
      ".pdf-annot-link{position:absolute;z-index:2;pointer-events:auto;background:rgba(26,107,107,0.08);border-radius:2px}" +
      ".pdf-annot-link:focus{outline:2px solid #1a6b6b;outline-offset:1px}" +
      ".pdf-frame-wrap,.pdf-standalone-shell{display:flex;flex-direction:column;height:auto!important;overflow:visible!important}" +
      ".pdf-frame-wrap{min-height:850px!important;overflow:visible!important}" +
      ".pdf-frame-wrap iframe,.pdf-standalone-shell iframe.pdf-frame," +
      "body.is-native-pdf iframe.pdf-frame{display:none!important;height:auto!important;min-height:850px}" +
      ".pdf-frame-wrap.is-iframe-fallback iframe{display:block!important;width:100%!important;min-height:850px!important;height:850px!important;border:0}" +
      ".pdf-frame-wrap.is-iframe-fallback .pdf-inpage-viewer{display:none!important}" +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf," +
      "body.is-native-pdf .pdf-standalone-shell{" +
      "display:flex;flex-direction:column;height:auto!important;min-height:850px!important;overflow:visible!important;background:#3a3f42}" +
      "#ocr-panel{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important}" +
      ".viewer-block,#panel-pdf{overflow:visible!important}" +
      ".ocr-sticky-chrome{position:sticky;top:0;z-index:40;background:#fff;padding:8px 0 10px;margin:0 0 8px;box-shadow:0 8px 16px #fff}" +
      "html{scroll-padding-top:8rem}" +
      "mark.search-active{scroll-margin-top:8rem}" +
      ".scroll-top-btn{position:fixed;right:16px;bottom:20px;z-index:30;width:46px;height:46px;border:0;border-radius:999px;background:#1a6b6b;color:#fff;font-size:1.35rem;line-height:1;cursor:pointer;box-shadow:0 4px 14px rgba(17,75,75,.28);opacity:0;pointer-events:none}" +
      ".scroll-top-btn.is-visible{opacity:1;pointer-events:auto}" +
      ".az-expand{display:none!important}" +
      "@media (max-width:1024px){" +
      ".pdf-frame-wrap,.pdf-standalone-shell," +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf," +
      "body.is-native-pdf .pdf-standalone-shell," +
      ".pdf-inpage-viewer{min-height:450px!important}" +
      ".pdf-inpage-pages,#panel-pdf .pdf-inpage-pages,#panel-pdf.az-expanded .pdf-inpage-pages," +
      "#ocr-panel{" +
      "height:450px!important;min-height:450px!important;max-height:450px!important;overflow:auto!important;overflow-y:auto!important}" +
      "}";
    document.head.appendChild(style);
  }

  function ensureOcrStickyChrome() {
    if (document.querySelector(".ocr-sticky-chrome")) return;
    var panel = document.getElementById("panel-ocr");
    if (!panel) return;
    var zoom = panel.querySelector(".ocr-zoom-bar");
    var search = panel.querySelector(".ocr-search-bar");
    var tools = panel.querySelector(".ocr-search-tools");
    if (!zoom && !search) return;
    var wrap = document.createElement("div");
    wrap.className = "ocr-sticky-chrome";
    var first = zoom || search;
    first.parentNode.insertBefore(wrap, first);
    if (zoom) wrap.appendChild(zoom);
    if (search) wrap.appendChild(search);
    if (tools) wrap.appendChild(tools);
  }

  function ensureScrollTop() {
    if (document.getElementById("scroll-top-btn")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "scroll-top-btn";
    btn.id = "scroll-top-btn";
    btn.setAttribute("aria-label", "Back to top");
    btn.textContent = "↑";
    document.body.appendChild(btn);
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function shown() {
      var y = window.scrollY || document.documentElement.scrollTop || 0;
      btn.classList.toggle("is-visible", y > 240);
    }
    window.addEventListener("scroll", shown, { passive: true });
    shown();
    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
  }

  window.parishPressBindScrollTopBoxes = ensureScrollTop;

  function isPhone() {
    var ua = navigator.userAgent || "";
    if (/Android|iPhone|iPod/i.test(ua)) return true;
    if (/iPad/i.test(ua)) return true;
    if (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) return true;
    return !!(window.matchMedia && window.matchMedia("(max-width: 1024px)").matches);
  }

  function fixMobilePdfLinks() {
    if (!isPhone()) return;
    var nodes = document.querySelectorAll(
      'a[href*="_mega_bulletin.pdf"], a[href*="/mega_pdf/"], .mobile-jump-download, .download-link-top, .download-link, .pdf-inpage-backup a'
    );
    Array.prototype.forEach.call(nodes, function (a) {
      var href = a.getAttribute("href") || "";
      if (!/\.pdf(\?|#|$)/i.test(href)) return;
      a.removeAttribute("download");
      a.removeAttribute("target");
      a.removeAttribute("rel");
      var t = (a.textContent || "").replace(/\s+/g, " ").trim();
      if (/download/i.test(t)) a.textContent = "Open PDF";
    });
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
      '<div class="pdf-inpage-backup">' +
      '<a href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '">Open PDF</a>' +
      '<a href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '">Download</a>' +
      "</div></div>" +
      '<div class="pdf-inpage-status">Showing first page…</div>' +
      '<div class="pdf-inpage-pages" role="document" aria-label="Bulletin PDF pages"></div>';
    return host;
  }

  function unloadIframe(wrap) {
    if (!wrap) return;
    wrap.classList.add("is-native-pdf");
    wrap.classList.remove("is-iframe-fallback");
    var iframe = wrap.querySelector("iframe");
    if (iframe) {
      iframe.setAttribute("hidden", "");
      try {
        iframe.removeAttribute("src");
      } catch (e) {}
    }
  }

  function restoreIframe(wrap, pdfUrl) {
    if (!wrap || !pdfUrl) return;
    wrap.classList.add("is-iframe-fallback");
    wrap.classList.remove("is-native-pdf");
    var iframe = wrap.querySelector("iframe");
    if (!iframe) return;
    iframe.removeAttribute("hidden");
    iframe.setAttribute("src", pdfUrl);
  }

  function overlayPageLinks(page, slot, cssWidth) {
    var unscaled = page.getViewport({ scale: 1 });
    var cssScale = cssWidth / unscaled.width;
    var cssViewport = page.getViewport({ scale: cssScale });
    var layer = slot.querySelector(".pdf-link-layer");
    if (!layer) {
      layer = document.createElement("div");
      layer.className = "pdf-link-layer";
      slot.appendChild(layer);
    }
    layer.innerHTML = "";
    var Util = (window.pdfjsLib && window.pdfjsLib.Util) || null;
    return page.getAnnotations({ intent: "display" }).then(function (annots) {
      (annots || []).forEach(function (annot) {
        if (!annot || String(annot.subtype || annot.annotationType || "") === "") return;
        var isLink = annot.subtype === "Link" || annot.annotationType === 2;
        if (!isLink) return;
        var url = annot.url || annot.unsafeUrl || "";
        if (!url && annot.dest) return;
        if (!url) return;
        if (!/^https?:\/\//i.test(url) && /^www\./i.test(url)) url = "https://" + url;
        if (!/^https?:\/\//i.test(url)) return;
        var rect = annot.rect || [0, 0, 0, 0];
        var viewed = cssViewport.convertToViewportRectangle(rect);
        if (Util && Util.normalizeRect) viewed = Util.normalizeRect(viewed);
        else {
          var x1 = Math.min(viewed[0], viewed[2]);
          var y1 = Math.min(viewed[1], viewed[3]);
          var x2 = Math.max(viewed[0], viewed[2]);
          var y2 = Math.max(viewed[1], viewed[3]);
          viewed = [x1, y1, x2, y2];
        }
        var a = document.createElement("a");
        a.className = "pdf-annot-link";
        a.href = url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.title = url;
        a.setAttribute("aria-label", "Open parish website in a new tab");
        a.style.left = Math.max(0, viewed[0]) + "px";
        a.style.top = Math.max(0, viewed[1]) + "px";
        a.style.width = Math.max(18, viewed[2] - viewed[0]) + "px";
        a.style.height = Math.max(18, viewed[3] - viewed[1]) + "px";
        layer.appendChild(a);
      });
    }).catch(function (err) {
      console.warn("PDF link overlay failed", err);
    });
  }

  function renderPageToSlot(page, slot, width) {
    var unscaled = page.getViewport({ scale: 1 });
    var cssWidth = Math.max(240, width || slot.clientWidth || 320);
    var dpr = isPhone() ? 1 : Math.min(2, window.devicePixelRatio || 1);
    var scale = (cssWidth / unscaled.width) * dpr;
    var viewport = page.getViewport({ scale: scale });
    var canvas = slot.querySelector("canvas") || document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = cssWidth + "px";
    canvas.style.height = Math.floor(unscaled.height * (cssWidth / unscaled.width)) + "px";
    if (!canvas.parentNode) slot.appendChild(canvas);
    slot.style.position = "relative";
    slot.style.width = cssWidth + "px";
    slot.style.minHeight = canvas.style.height;
    return page
      .render({ canvasContext: canvas.getContext("2d", { alpha: false }), viewport: viewport })
      .promise.then(function () {
        return overlayPageLinks(page, slot, cssWidth);
      });
  }

  function startViewer(host, pdfUrl, wrap) {
    if (host.getAttribute("data-pdf-started") === "1") return;
    host.setAttribute("data-pdf-started", "1");
    var pagesEl = host.querySelector(".pdf-inpage-pages");
    var pdfDoc = null;
    var rendering = Object.create(null);

    function pageWidth() {
      return Math.floor((pagesEl && pagesEl.clientWidth) || host.clientWidth || 320);
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

    window.parishPressPaintPdfPage = paint;
    window.parishPressScrollPdfToPage = function (pageNum) {
      var slot = pagesEl && pagesEl.querySelector('[data-page="' + pageNum + '"]');
      if (!slot) return;
      paint(pageNum);
      pagesEl.scrollTop = slot.offsetTop;
    };

    function stackAllPages() {
      if (!pdfDoc) return;
      var n;
      for (n = 1; n <= pdfDoc.numPages; n++) ensureSlot(n);
      paint(1).then(function () {
        setStatus(host, "");
      });
      if (window.IntersectionObserver) {
        var io = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry) {
              if (!entry.isIntersecting) return;
              var num = parseInt(entry.target.getAttribute("data-page"), 10);
              if (num) paint(num);
            });
          },
          { root: pagesEl, rootMargin: "200px 0px", threshold: 0.01 }
        );
        pagesEl.querySelectorAll(".pdf-inpage-page-slot").forEach(function (slot) {
          io.observe(slot);
        });
        return;
      }
      var next = 2;
      function paintNext() {
        if (next > pdfDoc.numPages) return;
        var num = next++;
        paint(num).then(paintNext);
      }
      paintNext();
    }

    setStatus(host, "Showing first page…");
    loadPdfJs()
      .then(function (pdfjsLib) {
        return pdfjsLib
          .getDocument({
            url: pdfUrl,
            disableAutoFetch: true,
            disableStream: false,
            disableRange: false,
            rangeChunkSize: 65536,
          })
          .promise.catch(function () {
            return pdfjsLib.getDocument({
              url: pdfUrl,
              disableAutoFetch: false,
              disableStream: true,
              disableRange: true,
            }).promise;
          });
      })
      .then(function (pdf) {
        pdfDoc = pdf;
        stackAllPages();
      })
      .catch(function (err) {
        console.warn("PDF.js failed", err);
        setStatus(host, "Could not show the PDF here. Use Open PDF.", true);
        host.setAttribute("data-pdf-started", "0");
        if (!isPhone()) restoreIframe(wrap, pdfUrl);
      });
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
    startViewer(host, pdfUrl, wrap);
  }

  function run() {
    ensureStyles();
    ensureOcrStickyChrome();
    ensureScrollTop();
    fixMobilePdfLinks();
    document.querySelectorAll(".az-expand").forEach(function (btn) {
      btn.remove();
    });

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
      startViewer(host, pdfUrl, shell);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
