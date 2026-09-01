/**
 * Parish Press — in-page PDF viewer (desktop + mobile)
 *
 * Phone and desktop both run PDF.js so Jump-to can find
 * `.pdf-inpage-pages` / `[data-page]` slots and call
 * window.parishPressScrollPdfToPage. Self-hosted
 * /assets/pdf.min.js. Megas ≤ 8 MB (Raphoe ~5 MB) use one
 * GET into getDocument({ data }) — Range-walking this
 * Ghostscript file was 12–20s. Larger files keep Range.
 * Never pass url to getDocument (that still full-GETs).
 * Never put the mega on iframe src.
 * Pages fit the PDF box width (no 720px minimum).
 * Locked 850px desktop / 450px phone boxes. Keep fixMobilePdfLinks.
 * Do not restore a tap-to-load button, enlarge control,
 * a same-tab native-link replacement, or a raw iPhone iframe.
 */
(function () {
  if (window.__parishPressPdfInpage) return;
  window.__parishPressPdfInpage = true;

  var PDFJS_SCRIPTS = [
    "/assets/pdf.min.js",
  ];
  var PDFJS_WORKERS = [
    "/assets/pdf.worker.min.js",
  ];

  var paintPdfPage = null;
  var refitPaintedPages = null;
  var refitTimer = null;

  function schedulePdfRefit() {
    if (refitTimer) window.clearTimeout(refitTimer);
    refitTimer = window.setTimeout(function () {
      refitTimer = null;
      if (typeof refitPaintedPages === "function") refitPaintedPages();
    }, 150);
  }

  function bindPdfRefit() {
    if (window.__parishPressPdfRefitBound) return;
    window.__parishPressPdfRefitBound = true;
    window.addEventListener("resize", schedulePdfRefit);
    window.addEventListener("orientationchange", schedulePdfRefit);
  }

  function isPhone() {
    var ua = navigator.userAgent || "";
    if (/Android/i.test(ua)) return true;
    if (/iPhone|iPod/i.test(ua)) return true;
    if (/iPad/i.test(ua)) return true;
    if (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1) return true;
    return false;
  }

  function isMobileView() {
    return isPhone() || (window.matchMedia && window.matchMedia("(max-width: 1024px)").matches);
  }

  function fixMobilePdfLinks() {
    if (!isPhone()) return;
    var nodes = document.querySelectorAll(
      'a[href*="mega_bulletin.pdf"], a.download-link, a.download-link-top, .pdf-inpage-backup a'
    );
    Array.prototype.forEach.call(nodes, function (a) {
      if (!a || (a.className && String(a.className).indexOf("pdf-annot-link") !== -1)) return;
      if (a.hasAttribute("download")) return;
      a.removeAttribute("target");
      a.removeAttribute("rel");
    });
  }

  function ensureStyles() {
    var style = document.getElementById("pdf-inpage-viewer-style");
    if (!style) {
      style = document.createElement("style");
      style.id = "pdf-inpage-viewer-style";
      document.head.appendChild(style);
    }
    /* Desktop PDF is a locked 850px window (wrap overflow hidden). OCR stays locked. */
    style.textContent =
      ".az-expand{display:none!important}" +
      ".pdf-inpage-viewer{display:flex!important;flex-direction:column;height:850px!important;min-height:850px!important;max-height:850px!important;overflow:hidden!important;flex:1 1 auto;background:#3a3f42;color:#e8eeed;border:1px solid #c9d4d3;box-sizing:border-box}" +
      ".pdf-inpage-toolbar{display:flex;flex-wrap:wrap;align-items:center;justify-content:flex-start;gap:8px;padding:8px 52px 8px 10px;background:#14524f;color:#fff;flex:0 0 auto}" +
      ".pdf-inpage-backup{display:flex;gap:8px;flex-wrap:wrap}" +
      ".pdf-inpage-backup a{color:#fff;font-weight:700;font-size:.85rem}" +
      ".pdf-inpage-status{padding:10px 12px;background:#1f3d3c;color:#d8f0ee;font-size:.9rem}" +
      ".pdf-inpage-pages{box-sizing:border-box;flex:0 0 auto;height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important;overflow-x:hidden!important;scrollbar-gutter:stable;background:#525659;padding:8px 0 16px;touch-action:pan-x pan-y pinch-zoom}" +
      "#panel-pdf.az-expanded .pdf-inpage-pages{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important}" +
      "#ocr-panel{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important;scrollbar-gutter:stable}" +
      ".pdf-inpage-page-slot{margin:0 auto 10px;background:#3a3f42;min-height:180px;max-width:100%;position:relative}" +
      ".pdf-inpage-page-slot canvas{display:block;width:100%;height:auto;background:#fff}" +
      ".pdf-first-preview{display:block;width:100%;height:auto;background:#fff}" +
      ".pdf-link-layer{position:absolute;left:0;top:0;width:100%;height:100%;overflow:hidden;pointer-events:none}" +
      ".pdf-annot-link{position:absolute;z-index:2;pointer-events:auto;background:rgba(26,107,107,0.08);border-radius:2px}" +
      ".pdf-annot-link:focus{outline:2px solid #1a6b6b;outline-offset:1px}" +
      ".pdf-frame-wrap,.pdf-standalone-shell{display:flex;flex-direction:column;height:850px!important;min-height:850px!important;max-height:850px!important;overflow:hidden!important;border:1px solid #c9d4d3;box-sizing:border-box}" +
      ".pdf-frame-wrap iframe,.pdf-standalone-shell iframe.pdf-frame," +
      "body.is-native-pdf iframe.pdf-frame{display:none!important;height:850px!important;min-height:850px!important;max-height:850px!important}" +
      ".pdf-frame-wrap.is-iframe-fallback iframe," +
      ".pdf-standalone-shell.is-iframe-fallback iframe.pdf-frame," +
      "body.is-iframe-fallback iframe.pdf-frame{display:block!important}" +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf," +
      "body.is-native-pdf .pdf-standalone-shell{" +
      "display:flex;flex-direction:column;height:850px!important;min-height:850px!important;max-height:850px!important;overflow:hidden!important;background:#3a3f42}" +
      ".ocr-sticky-chrome{position:relative!important;top:auto;z-index:8;background:#fff;padding:8px 0 10px;margin:0 0 8px}" +
      ".ocr-sticky-chrome.is-searching{position:sticky!important;top:0!important}" +
      "html.is-ocr-searching{scroll-padding-top:10rem}" +
      "mark.search-active{scroll-margin-top:10rem}" +
      ".scroll-top-btn{position:fixed;right:16px;bottom:20px;z-index:9999;width:46px;height:46px;border:0;border-radius:999px;background:#1a6b6b;color:#fff;font-size:1.35rem;line-height:1;cursor:pointer;box-shadow:0 4px 14px rgba(17,75,75,0.28);opacity:0;pointer-events:none;transform:translateY(8px)}" +
      ".scroll-top-btn.is-visible{opacity:1;pointer-events:auto;transform:none}" +
      "@media (max-width:1024px){" +
      ".pdf-frame-wrap,.pdf-standalone-shell," +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf," +
      "body.is-native-pdf .pdf-standalone-shell,.pdf-inpage-viewer{" +
      "height:450px!important;min-height:450px!important;max-height:450px!important;overflow:hidden!important}" +
      ".pdf-inpage-pages{height:450px!important;min-height:450px!important;max-height:450px!important;overflow:auto!important;overflow-y:auto!important}" +
      "#panel-pdf.az-expanded .pdf-inpage-pages{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important}" +
      "#ocr-panel,.pdf-frame-wrap iframe," +
      ".pdf-standalone-shell iframe.pdf-frame{height:450px!important;min-height:450px!important;max-height:450px!important;overflow:auto!important;overflow-y:auto!important}" +
      ".pdf-inpage-pages{overflow-x:hidden!important}" +
      ".pdf-inpage-page-slot{max-width:100%}" +
      "#panel-pdf.az-expanded .pdf-frame-wrap,#panel-pdf.az-expanded .pdf-inpage-viewer{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:hidden!important}" +
      "#panel-ocr.az-expanded #ocr-panel{height:850px!important;min-height:850px!important;max-height:850px!important}" +
      "}" +
      "@media (min-width:701px) and (min-height:501px){" +
      ".pdf-frame-wrap,.pdf-standalone-shell," +
      ".pdf-frame-wrap.is-native-pdf,.pdf-standalone-shell.is-native-pdf," +
      "body.is-native-pdf .pdf-standalone-shell,.pdf-inpage-viewer," +
      ".pdf-mobile-fallback{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:hidden!important}" +
      ".pdf-inpage-pages{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important}" +
      "#panel-pdf.az-expanded .pdf-inpage-pages{height:850px!important;min-height:850px!important;max-height:850px!important;overflow:auto!important;overflow-y:auto!important}" +
      "#ocr-panel,.pdf-frame-wrap iframe," +
      ".pdf-standalone-shell iframe.pdf-frame{height:850px!important;min-height:850px!important;" +
      "max-height:850px!important;overflow:auto!important;overflow-y:auto!important}" +
      ".pdf-inpage-pages{overflow-x:hidden!important}" +
      ".az-expand{display:none}" +
      "}";
  }

  function syncOcrSearchSticky() {
    var chrome = document.querySelector(".ocr-sticky-chrome");
    var input = document.getElementById("ocr-search");
    if (!chrome || !input) return;
    var active = Boolean((input.value || "").trim());
    chrome.classList.toggle("is-searching", active);
    document.documentElement.classList.toggle("is-ocr-searching", active);
  }

  function ensureOcrStickyChrome() {
    var chrome = document.querySelector(".ocr-sticky-chrome");
    var zoom = document.querySelector(".ocr-zoom-bar");
    var bar = document.querySelector(".ocr-search-bar");
    var tools = document.querySelector(".ocr-search-tools");
    if (!chrome) {
      var first = bar || tools || zoom;
      if (first && first.parentNode) {
        chrome = document.createElement("div");
        chrome.className = "ocr-sticky-chrome";
        first.parentNode.insertBefore(chrome, first);
      }
    }
    if (chrome) {
      if (bar) chrome.insertBefore(bar, chrome.firstChild);
      if (tools) {
        if (bar) chrome.insertBefore(tools, bar.nextSibling);
        else chrome.appendChild(tools);
      }
      if (zoom && zoom.parentNode === chrome) {
        var row = document.querySelector(".ocr-controls-row");
        if (row) row.appendChild(zoom);
        else if (chrome.parentNode) chrome.parentNode.insertBefore(zoom, chrome.nextSibling);
      }
    }
    syncOcrSearchSticky();
  }

  function ensureStickySearch() {
    ensureOcrStickyChrome();
  }

  document.addEventListener(
    "input",
    function (event) {
      if (event.target && event.target.id === "ocr-search") syncOcrSearchSticky();
    },
    true
  );
  document.addEventListener(
    "click",
    function (event) {
      if (event.target && event.target.id === "clear-search") {
        window.setTimeout(syncOcrSearchSticky, 0);
      }
    },
    true
  );

  function ensureScrollTop() {
    var btn = document.getElementById("scroll-top-btn");
    if (!btn) {
      if (!document.body) return;
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "scroll-top-btn";
      btn.id = "scroll-top-btn";
      btn.setAttribute("aria-label", "Back to top");
      btn.textContent = "↑";
      document.body.appendChild(btn);
    }
    function innerBoxes() {
      return Array.prototype.slice.call(
        document.querySelectorAll(".pdf-inpage-pages, #ocr-panel")
      );
    }
    function maxInnerScroll() {
      return innerBoxes().reduce(function (max, el) {
        return Math.max(max, el.scrollTop || 0);
      }, 0);
    }
    function shown() {
      var y = window.scrollY || document.documentElement.scrollTop || 0;
      btn.classList.toggle("is-visible", y > 80 || maxInnerScroll() > 16);
    }
    function shownSoon() {
      shown();
      if (window.requestAnimationFrame) window.requestAnimationFrame(shown);
      else window.setTimeout(shown, 16);
    }
    function bindBox(el) {
      if (!el || el.getAttribute("data-pp-scroll-top") === "1") return;
      el.setAttribute("data-pp-scroll-top", "1");
      el.addEventListener("scroll", shownSoon, { passive: true });
    }
    function bindBoxes() {
      innerBoxes().forEach(bindBox);
      shown();
    }
    window.parishPressBindScrollTopBoxes = bindBoxes;
    if (btn.getAttribute("data-pp-bound") !== "inner-2") {
      btn.setAttribute("data-pp-bound", "inner-2");
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.addEventListener("scroll", shownSoon, { passive: true });
      document.addEventListener("scroll", shownSoon, { capture: true, passive: true });
      document.addEventListener("wheel", shownSoon, { capture: true, passive: true });
      document.addEventListener("touchmove", shownSoon, { capture: true, passive: true });
      if (window.MutationObserver && document.body) {
        new MutationObserver(bindBoxes).observe(document.body, { childList: true, subtree: true });
      }
      btn.addEventListener("click", function () {
        var behavior = reduce ? "auto" : "smooth";
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

  var startMegaNow = null;
  var pendingJumpPage = 0;

  window.parishPressScrollPdfToPage = function (pageNum) {
    pendingJumpPage = parseInt(pageNum, 10) || 0;
    function tryScroll() {
      var pagesEl = document.querySelector(".pdf-inpage-pages");
      if (!pagesEl || !pendingJumpPage) return false;
      if (typeof paintPdfPage === "function") paintPdfPage(pendingJumpPage);
      var slot = pagesEl.querySelector('[data-page="' + pendingJumpPage + '"]');
      if (!slot) return false;
      pagesEl.scrollTop = slot.offsetTop;
      return true;
    }
    if (typeof startMegaNow === "function") startMegaNow();
    if (tryScroll()) return;
    var tries = 0;
    function again() {
      if (tryScroll()) return;
      if (tries++ < 80) window.setTimeout(again, 250);
    }
    again();
  };

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

  var pdfJsLoading = null;
  function loadPdfJs() {
    if (window.pdfjsLib) {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = "/assets/pdf.worker.min.js";
      return Promise.resolve(window.pdfjsLib);
    }
    if (pdfJsLoading) return pdfJsLoading;
    var i = 0;
    function next() {
      if (i >= PDFJS_SCRIPTS.length) {
        return Promise.reject(new Error("Could not load PDF.js"));
      }
      var src = PDFJS_SCRIPTS[i++];
      return loadScript(src).catch(next);
    }
    pdfJsLoading = next().then(function () {
      if (!window.pdfjsLib) throw new Error("pdfjsLib missing after load");
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = "/assets/pdf.worker.min.js";
      return window.pdfjsLib;
    });
    return pdfJsLoading;
  }

  function resolvePdfUrl(wrap) {
    if (!wrap) return "";
    var host = wrap.querySelector("[data-pdf-src], #pdf-inpage-viewer, #pdf-mobile-fallback, .pdf-inpage-viewer, .pdf-mobile-fallback");
    var fromData = host && host.getAttribute("data-pdf-src");
    if (fromData) return fromData;
    var iframe = wrap.querySelector("iframe");
    var fromIframe = iframe && iframe.getAttribute("data-pdf-url");
    if (fromIframe) return fromIframe;
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

  function pdfFilename(url) {
    var path = String(url || "").split("?")[0].split("#")[0];
    var name = path.split("/").pop() || "bulletin.pdf";
    try {
      name = decodeURIComponent(name);
    } catch (e) {}
    if (!/\.pdf$/i.test(name)) name = "bulletin.pdf";
    return name;
  }

  var pdfBytesPromises = Object.create(null);
  var pdfBlobCache = Object.create(null);

  function savePdfBlob(blob, filename) {
    var typed = new Blob([blob], {
      type: isPhone() ? "application/octet-stream" : "application/pdf",
    });
    var obj = URL.createObjectURL(typed);
    var tmp = document.createElement("a");
    tmp.href = obj;
    tmp.setAttribute("download", filename);
    tmp.style.display = "none";
    document.body.appendChild(tmp);
    tmp.click();
    document.body.removeChild(tmp);
    window.setTimeout(function () {
      URL.revokeObjectURL(obj);
    }, 60000);
  }

  function bindForceDownload(root) {
    var nodes = (root || document).querySelectorAll("a.pdf-force-download");
    Array.prototype.forEach.call(nodes, function (a) {
      if (!a || a.getAttribute("data-pp-dl") === "1") return;
      a.setAttribute("data-pp-dl", "1");
      a.addEventListener("click", function (ev) {
        var url = a.getAttribute("href") || "";
        var name = a.getAttribute("download") || pdfFilename(url);
        if (!url) return;
        ev.preventDefault();
        ev.stopPropagation();
        if (pdfBlobCache[url]) {
          savePdfBlob(pdfBlobCache[url], name);
          return;
        }
        prefetchPdfBytes(url)
          .then(function () {
            if (pdfBlobCache[url]) savePdfBlob(pdfBlobCache[url], name);
          })
          .catch(function () {
            window.location.href = url;
          });
      });
    });
  }

  function previewMarkup(previewUrl) {
    if (!previewUrl) return "";
    return (
      '<div class="pdf-inpage-page-slot" data-page="1">' +
      '<img class="pdf-first-preview" src="' +
      previewUrl.replace(/"/g, "&quot;") +
      '" alt="" style="display:block;width:100%;height:auto">' +
      "</div>"
    );
  }

  function buildViewer(host, pdfUrl) {
    var previewUrl = host.getAttribute("data-pdf-preview") || "";
    host.classList.add("pdf-inpage-viewer");
    host.setAttribute("data-pdf-src", pdfUrl);
    if (previewUrl) host.setAttribute("data-pdf-preview", previewUrl);
    host.innerHTML =
      '<div class="pdf-inpage-toolbar">' +
      '<div class="pdf-inpage-backup">' +
      '<a href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '">Open PDF</a>' +
      '<a class="pdf-force-download" href="' +
      pdfUrl.replace(/"/g, "&quot;") +
      '" download="' +
      pdfFilename(pdfUrl).replace(/"/g, "") +
      '">Download</a>' +
      "</div></div>" +
      '<div class="pdf-inpage-status">This file can take a few moments to open.</div>' +
      '<div class="pdf-inpage-pages" role="document" aria-label="Bulletin PDF pages">' +
      previewMarkup(previewUrl) +
      "</div>";
    if (typeof window.parishPressBindScrollTopBoxes === "function") {
      window.parishPressBindScrollTopBoxes();
    }
    fixMobilePdfLinks();
    bindForceDownload(host);
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

  function restoreNativeIframe() {
    /* Never put the PDF URL on iframe src. That starts a full download. */
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
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var scale = (cssWidth / unscaled.width) * dpr;
    var viewport = page.getViewport({ scale: scale });
    var canvas = slot.querySelector("canvas") || document.createElement("canvas");
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = "100%";
    canvas.style.height = "auto";
    if (!canvas.parentNode) slot.appendChild(canvas);
    slot.style.position = "relative";
    slot.style.width = cssWidth + "px";
    slot.style.maxWidth = "100%";
    slot.style.minHeight = Math.floor(unscaled.height * (cssWidth / unscaled.width)) + "px";
    return page
      .render({ canvasContext: canvas.getContext("2d", { alpha: false }), viewport: viewport })
      .promise.then(function () {
        var preview = slot.querySelector(".pdf-first-preview");
        if (preview) preview.remove();
        return overlayPageLinks(page, slot, cssWidth);
      });
  }

  function pdfByteLength(pdfUrl) {
    return fetch(pdfUrl, { method: "HEAD", credentials: "same-origin" }).then(function (res) {
      var len = parseInt(res.headers.get("content-length") || "0", 10);
      if (len > 0) return len;
      return fetch(pdfUrl, {
        credentials: "same-origin",
        headers: { Range: "bytes=0-0" },
      }).then(function (r) {
        var cr = r.headers.get("content-range") || "";
        var m = /\/(\d+)\s*$/.exec(cr);
        if (m) return parseInt(m[1], 10);
        throw new Error("PDF size unknown");
      });
    });
  }

  var WHOLE_FILE_MAX = 8 * 1024 * 1024;

  function prefetchPdfBytes(pdfUrl) {
    if (!pdfUrl) return Promise.reject(new Error("no pdf url"));
    if (pdfBytesPromises[pdfUrl]) return pdfBytesPromises[pdfUrl];
    pdfBytesPromises[pdfUrl] = fetch(pdfUrl, {
      credentials: "same-origin",
      cache: "force-cache",
    }).then(function (res) {
      if (!res.ok) throw new Error("PDF fetch " + res.status);
      var len = parseInt(res.headers.get("content-length") || "0", 10);
      if (len > WHOLE_FILE_MAX) {
        if (res.body && typeof res.body.cancel === "function") {
          try { res.body.cancel(); } catch (e) {}
        }
        throw new Error("PDF too large for whole-file");
      }
      return res.arrayBuffer();
    }).then(function (buf) {
      pdfBlobCache[pdfUrl] = new Blob([buf], { type: "application/pdf" });
      return buf;
    });
    return pdfBytesPromises[pdfUrl];
  }

  function fetchWholePdf(pdfjsLib, pdfUrl) {
    return prefetchPdfBytes(pdfUrl).then(function (buf) {
      /* One arrayBuffer — never pass url to getDocument. */
      return pdfjsLib.getDocument({
        data: new Uint8Array(buf),
        disableAutoFetch: true,
        disableStream: true,
      }).promise;
    });
  }

  function openRangePdf(pdfjsLib, pdfUrl, knownLength) {
    /* Custom Range transport — never pass url to getDocument.
       A url+disableStream still starts one un-ranged full GET. */
    var Transport = pdfjsLib.PDFDataRangeTransport;
    if (!Transport) throw new Error("PDFDataRangeTransport missing");
    var start = knownLength > 0 ? Promise.resolve(knownLength) : pdfByteLength(pdfUrl);
    return start.then(function (length) {
      var transport = new Transport(length, new Uint8Array(0));
      transport.requestDataRange = function (begin, end) {
        var self = this;
        fetch(pdfUrl, {
          credentials: "same-origin",
          headers: { Range: "bytes=" + begin + "-" + (end - 1) },
        })
          .then(function (res) {
            if (!res.ok && res.status !== 206) throw new Error("PDF range " + res.status);
            return res.arrayBuffer();
          })
          .then(function (buf) {
            self.onDataRange(begin, new Uint8Array(buf));
          })
          .catch(function (err) {
            console.warn("PDF range chunk failed", begin, end, err);
            throw err;
          });
      };
      return pdfjsLib.getDocument({
        range: transport,
        length: length,
        disableAutoFetch: true,
        disableStream: true,
        disableRange: false,
        rangeChunkSize: 262144,
      }).promise;
    });
  }

  function openPdfDocument(pdfjsLib, pdfUrl) {
    /* Raphoe is ~5 MB. One GET is seconds on normal 4G.
       Range-walking this Ghostscript file was 12–20s. */
    return fetchWholePdf(pdfjsLib, pdfUrl).catch(function (err) {
      console.warn("Whole-file PDF failed, trying Range", err);
      return openRangePdf(pdfjsLib, pdfUrl, 0);
    });
  }

  function startViewer(host, pdfUrl) {
    if (host.getAttribute("data-pdf-started") === "1") return;
    host.setAttribute("data-pdf-started", "1");
    var pagesEl = host.querySelector(".pdf-inpage-pages");
    if (pagesEl && !pagesEl.querySelector(".pdf-first-preview")) pagesEl.innerHTML = "";
    var pdfDoc = null;
    var rendering = Object.create(null);

    function pageWidth() {
      return Math.max(240, Math.floor((pagesEl.clientWidth || host.clientWidth || 320) - 4));
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

    paintPdfPage = paint;

    refitPaintedPages = function () {
      if (!pdfDoc || !pagesEl) return;
      Object.keys(rendering).forEach(function (k) {
        delete rendering[k];
      });
      var top = pagesEl.scrollTop - 200;
      var bottom = pagesEl.scrollTop + pagesEl.clientHeight + 200;
      var any = false;
      var slots = pagesEl.querySelectorAll("[data-page]");
      Array.prototype.forEach.call(slots, function (slot) {
        var num = parseInt(slot.getAttribute("data-page"), 10);
        if (!num) return;
        var slotTop = slot.offsetTop;
        var slotBottom = slotTop + (slot.offsetHeight || 0);
        if (slotBottom >= top && slotTop <= bottom) {
          any = true;
          paint(num);
        }
      });
      if (!any) paint(1);
    };
    bindPdfRefit();

    function stackAllPages() {
      if (!pdfDoc) return;
      var n;
      for (n = 1; n <= pdfDoc.numPages; n++) ensureSlot(n);
      var boxBefore = pagesEl.clientWidth;
      var hasPreview = pagesEl.querySelector(".pdf-first-preview");
      var firstPaint = hasPreview ? Promise.resolve() : paint(1);
      firstPaint.then(function () {
        setStatus(host, "");
        if (!hasPreview && pagesEl.clientWidth && pagesEl.clientWidth !== boxBefore) {
          delete rendering[1];
          return paint(1);
        }
      }).then(function () {
        if (!window.IntersectionObserver) {
          var next = 2;
          function paintNext() {
            if (next > pdfDoc.numPages) return;
            var num = next++;
            paint(num).then(paintNext);
          }
          paintNext();
          return;
        }
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
        for (n = 2; n <= pdfDoc.numPages; n++) io.observe(ensureSlot(n));
      });
    }

    setStatus(host, "This file can take a few moments to open.");
    var megaPromise = null;
    function beginMega() {
      if (megaPromise) return megaPromise;
      megaPromise = loadPdfJs()
        .then(function (pdfjsLib) {
          return openPdfDocument(pdfjsLib, pdfUrl);
        })
        .then(function (pdf) {
          pdfDoc = pdf;
          rendering = Object.create(null);
          stackAllPages();
          if (pendingJumpPage) {
            paint(pendingJumpPage);
            var jumpSlot = pagesEl.querySelector('[data-page="' + pendingJumpPage + '"]');
            if (jumpSlot) pagesEl.scrollTop = jumpSlot.offsetTop;
          }
        })
        .catch(function (err) {
          console.warn("PDF.js failed", err);
          setStatus(host, "Could not show the PDF here. Use Open PDF or Download.", true);
          host.setAttribute("data-pdf-started", "0");
          restoreNativeIframe();
          megaPromise = null;
        });
      return megaPromise;
    }
    startMegaNow = beginMega;
    function waitPreview() {
      var img = pagesEl && pagesEl.querySelector(".pdf-first-preview");
      if (!img) return Promise.resolve();
      if (img.complete && img.naturalWidth > 0) {
        setStatus(host, "");
        return Promise.resolve();
      }
      return new Promise(function (resolve) {
        var done = function () {
          setStatus(host, "");
          resolve();
        };
        img.addEventListener("load", done, { once: true });
        img.addEventListener("error", done, { once: true });
        window.setTimeout(done, 4000);
      });
    }
    /* Start the mega GET immediately (prefetch + one arrayBuffer).
       Page 1 stays the tiny JPEG. Jump-to is ready when the 4–5 MB
       file is in. Drive / 365 hosting is not used. */
    waitPreview();
    beginMega();
  }

  function activateWrap(wrap, pdfUrl) {
    if (!wrap || !pdfUrl) return;
    prefetchPdfBytes(pdfUrl);
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
    document.querySelectorAll(".az-expand").forEach(function (btn) { btn.remove(); });
    ensureStyles();
    ensureOcrStickyChrome();
    ensureScrollTop();
    fixMobilePdfLinks();
    document.querySelectorAll("a.download-link-top[href*='.pdf']").forEach(function (a) {
      a.classList.add("pdf-force-download");
      if (!a.getAttribute("download")) {
        a.setAttribute("download", pdfFilename(a.getAttribute("href")));
      }
    });
    bindForceDownload(document);

    document.querySelectorAll(".pdf-frame-wrap").forEach(function (wrap) {
      activateWrap(wrap, resolvePdfUrl(wrap));
    });

    var standalone = document.querySelector("iframe.pdf-frame");
    if (standalone && !standalone.closest(".pdf-frame-wrap")) {
      var pdfUrl =
        standalone.getAttribute("data-pdf-url") ||
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
      prefetchPdfBytes(pdfUrl);
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
