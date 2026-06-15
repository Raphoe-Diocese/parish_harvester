/**
 * Full-page HTML/DOM fingerprint scanner — no AI keys.
 * Reads live page source (same data as view-source, plus post-JS DOM)
 * to detect CMS plugins and the easiest capture path.
 *
 * DOM validators prevent false positives from og:image meta tags and logos.
 */
(() => {
  const CONTENT_SELECTOR =
    ".entry-content, .post-content, article .entry-content, article.post, [role='main'] article";
  const BULLETIN_IMG_ALT_RE = /bulletin|newsletter|notice|weekly/i;
  const DECORATIVE_IMG_RE = /logo|icon|avatar|gravatar|emoji|spinner|badge|social|wp-smiley/i;

  const _imageWidth = (img) => {
    const widthAttr = Number(img.getAttribute("width") || 0);
    if (Number.isFinite(widthAttr) && widthAttr > 0) return widthAttr;
    const renderWidth = Number(img.width || 0);
    if (Number.isFinite(renderWidth) && renderWidth > 0) return renderWidth;
    const naturalWidth = Number(img.naturalWidth || 0);
    if (Number.isFinite(naturalWidth) && naturalWidth > 0) return naturalWidth;
    return 0;
  };

  const _entryContentRoot = (doc) => {
    try {
      return (
        doc.querySelector(".entry-content") ||
        doc.querySelector(".post-content") ||
        doc.querySelector("article.post") ||
        doc.querySelector("article") ||
        null
      );
    } catch (_e) {
      return null;
    }
  };

  const _plainTextLen = (el) => {
    if (!el) return 0;
    return String(el.innerText || el.textContent || "")
      .replace(/\s+/g, " ")
      .trim().length;
  };

  /** WordPress (or similar) HTML text newsletter — not a JPEG bulletin. */
  const isWordPressHtmlBulletinPage = (doc = document) => {
    const root = _entryContentRoot(doc);
    if (!root) return false;
    const textLen = _plainTextLen(root);
    if (textLen < 400) return false;

    const paragraphCount = root.querySelectorAll(
      "p, .wp-block-paragraph, li"
    ).length;
    if (paragraphCount < 4 && textLen < 800) return false;

    const html = doc.documentElement?.innerHTML || "";
    const path = doc.location?.pathname || "";
    const title = doc.title || "";
    const hasWpSignals =
      /wp-block-paragraph|wp-content|wordpress|wp-json/i.test(html) ||
      /wp-content/i.test(path);
    const hasNewsletterSignals =
      /newsletter|bulletin|pastoral area/i.test(`${title} ${path}`) ||
      /category-newsletter|tag-newsletter/i.test(html);

    if (!hasWpSignals && !hasNewsletterSignals) return false;

    const largeContentImages = Array.from(root.querySelectorAll("img")).filter(
      (img) => _imageWidth(img) >= 500 && !DECORATIVE_IMG_RE.test(
        `${img.className} ${img.alt || ""} ${img.src || ""}`
      )
    );
    if (largeContentImages.length === 1 && textLen < 600) return false;

    return true;
  };

  /** True only when a large bulletin-like image is in the article body (not og:meta). */
  const hasBulletinImageInContent = (doc = document, minWidth = 400) => {
    const root = _entryContentRoot(doc);
    if (!root) return false;

    const candidates = Array.from(root.querySelectorAll("img")).filter((img) => {
      const blob = `${img.className} ${img.alt || ""} ${img.src || ""} ${img.id || ""}`;
      if (DECORATIVE_IMG_RE.test(blob)) return false;
      if (_imageWidth(img) < minWidth) return false;
      if (BULLETIN_IMG_ALT_RE.test(blob)) return true;
      if (/\/wp-content\/uploads\//i.test(img.src || "")) return true;
      return false;
    });

    return candidates.length > 0;
  };

  const FINGERPRINTS = [
    {
      id: "joomla_dropfiles_weekly",
      label: "Joomla Dropfiles — weekly bulletin list",
      pageType: "weekly_bulletin_download",
      captureMethod: "direct_download",
      playbookType: "weekly_bulletin_download",
      minScore: 35,
      markers: [
        { re: /mod_dropfiles_latest|mod_dropfiles_list/i, weight: 20, label: "Dropfiles widget" },
        { re: /com_dropfiles/i, weight: 12, label: "com_dropfiles plugin" },
        { re: /mod_downloadlink|zmdi-cloud-download/i, weight: 18, label: "cloud download link" },
        { re: /weekly-bulletins/i, weight: 15, label: "Weekly-Bulletins path" },
      ],
      pickDownloadUrl: (doc) => {
        const links = Array.from(doc.querySelectorAll("a.mod_downloadlink[href]"));
        for (const a of links) {
          const href = a.getAttribute("href") || "";
          if (/weekly-bulletins|\/files\/\d+\//i.test(href)) {
            try {
              return new URL(href, doc.location?.href || "").href;
            } catch (_e) {
              continue;
            }
          }
        }
        return "";
      },
      advice:
        "Joomla Dropfiles — click the cloud ↓ on this Sunday's row on the page, then tap 📥 2. Click cloud download in the toolbar to save that URL to the recipe.",
      doNot: ["Do not use Pick bulletin image — PDF downloads from mod_downloadlink."],
    },
    {
      id: "oneweb_newsletter_docx",
      label: "One.com Word newsletter (onewebmedia)",
      pageType: "oneweb_docx",
      captureMethod: "direct_docx",
      playbookType: "oneweb_docx",
      minScore: 30,
      markers: [
        { re: /onewebmedia\/.*newsletter.*\.docx/i, weight: 25, label: "onewebmedia newsletter docx" },
        { re: /onewebstatic|one\.com/i, weight: 10, label: "One.com host" },
        { re: /docs\.google\.com\/viewer/i, weight: 8, label: "Google preview iframes" },
      ],
      pickDownloadUrl: (doc) => {
        const iframes = Array.from(doc.querySelectorAll("iframe[src]"));
        for (const frame of iframes) {
          let src = frame.getAttribute("src") || "";
          if (/docs\.google\.com\/viewer/i.test(src)) {
            try {
              const p = new URL(src, doc.location?.href || "").searchParams.get("url");
              if (p) src = decodeURIComponent(p);
            } catch (_e) {}
          }
          if (/onewebmedia/i.test(src) && /newsletter/i.test(src) && /\.docx/i.test(src)) {
            try {
              return new URL(src, doc.location?.href || "").href;
            } catch (_e2) {
              return src;
            }
          }
        }
        const html = doc.documentElement?.innerHTML?.slice(0, 120000) || "";
        const m = html.match(/https?:\/\/[^\s"'<>]+onewebmedia\/[^\s"'<>]*newsletter[^\s"'<>]*\.docx/i);
        return m ? m[0] : "";
      },
      advice: "One.com — newsletter is a .docx at onewebmedia/. Tap 📄 2. Save newsletter (auto) — do not wait for slow Google preview iframes. Never pick GDPR/Privacy PDFs.",
      doNot: ["Do not pick the first iframe PDF — often GDPR. Do not use image capture."],
    },
    {
      id: "wordpress_pdfemb",
      label: "WordPress PDF Embedder list",
      pageType: "wp_pdfemb_list",
      captureMethod: "click_then_pdf",
      playbookType: "pdfemb",
      minScore: 28,
      markers: [
        { re: /pdfemb-viewer|pdf-embedder|pdfemb-embed/i, weight: 22, label: "PDF Embedder plugin" },
        { re: /wp-content\/plugins\/pdf-embedder/i, weight: 15, label: "pdf-embedder plugin path" },
      ],
      pickDownloadUrl: (doc) => {
        const anchors = doc.querySelectorAll(
          'a.pdfemb-viewer[href], a[class*="pdfemb"][href], a[href$=".pdf"]'
        );
        for (const a of anchors) {
          const href = a.getAttribute("href") || "";
          if (/\.pdf/i.test(href) || /bulletin|newsletter/i.test(href + (a.textContent || ""))) {
            try {
              return new URL(href, doc.location?.href || "").href;
            } catch (_e) {
              continue;
            }
          }
        }
        return "";
      },
      advice: "WordPress PDF Embedder — pick the newest dated bulletin card, then Save PDF.",
      doNot: [],
    },
    {
      id: "parish_messenger_widget",
      label: "Parish Messenger (theparishmessenger.com)",
      pageType: "parish_messenger_embed",
      captureMethod: "click_then_pdf",
      playbookType: "parish_messenger",
      minScore: 25,
      markers: [
        { re: /theparishmessenger\.com/i, weight: 25, label: "Parish Messenger script" },
        { re: /parishservices\.co/i, weight: 10, label: "Parish Services host" },
      ],
      pickDownloadUrl: (doc) => {
        const links = Array.from(doc.querySelectorAll('a[href*=".pdf"]'));
        for (const a of links) {
          const text = (a.innerText || a.textContent || "").toLowerCase();
          if (/gift aid|data entry|financial/i.test(text)) continue;
          if (/newsletter|bulletin|view/i.test(text + (a.getAttribute("href") || ""))) {
            try {
              return new URL(a.getAttribute("href") || "", doc.location?.href || "").href;
            } catch (_e) {
              continue;
            }
          }
        }
        return "";
      },
      advice: "Parish Messenger — pick newest View Newsletter row. Ignore Gift Aid / admin PDFs.",
      doNot: ["Do not pick Gift Aid or Data Entry PDFs from the widget menu."],
    },
    {
      id: "wix_html_bulletin",
      label: "Wix HTML bulletin page",
      pageType: "wix_html",
      captureMethod: "html_capture",
      playbookType: "wix_html",
      minScore: 28,
      markers: [
        { re: /static\.wixstatic\.com|wix\.com/i, weight: 15, label: "Wix static assets" },
        { re: /#SITE_CONTAINER|wixBiSession/i, weight: 18, label: "Wix site container" },
        { re: /(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[_-]\d{4}/i, weight: 8, label: "dated slug in URL" },
      ],
      pickDownloadUrl: () => "",
      advice: "Wix HTML bulletin — Save page as PDF. Harvester prints this page each Sunday.",
      doNot: [],
    },
    {
      id: "wix_pdf_viewer",
      label: "Wix PDF viewer iframe",
      pageType: "wix_pdf_viewer",
      captureMethod: "click_then_pdf",
      playbookType: "wix_viewer",
      minScore: 30,
      markers: [
        { re: /wixlabs-pdf/i, weight: 28, label: "Wix PDF viewer iframe" },
      ],
      pickDownloadUrl: (doc) => {
        const frames = doc.querySelectorAll('iframe[src*="wixlabs-pdf"]');
        for (const f of frames) {
          const src = f.getAttribute("src") || "";
          const m = src.match(/fileUrl=([^&]+)/i);
          if (m) {
            try {
              return decodeURIComponent(m[1]);
            } catch (_e) {
              return m[1];
            }
          }
        }
        return "";
      },
      advice: "Wix PDF viewer — use Find bulletin; real PDF URL is often hidden in the viewer iframe.",
      doNot: [],
    },
    {
      id: "google_drive_folder",
      label: "Google Drive dated folder",
      pageType: "cloud_folder",
      captureMethod: "click_then_pdf",
      playbookType: "cloud_folder",
      minScore: 30,
      markers: [
        { re: /drive\.google\.com\/drive\/folders/i, weight: 30, label: "Drive folder URL" },
        { re: /\d{2}\.\d{2}\.\d{2}/, weight: 10, label: "YY.MM.DD dated rows" },
      ],
      pickDownloadUrl: () => "",
      advice: "Google Drive folder — pick this Sunday's YY.MM.DD row, then Save PDF on preview.",
      doNot: [],
    },
    {
      id: "iframe_google_viewer",
      label: "PDF inside Google Docs viewer iframe",
      pageType: "iframe_viewer",
      captureMethod: "click_then_pdf",
      playbookType: "iframe",
      minScore: 22,
      markers: [
        { re: /docs\.google\.com\/viewer|docs\.google\.com\/gview/i, weight: 22, label: "Google Docs viewer iframe" },
      ],
      pickDownloadUrl: (doc) => {
        const frames = doc.querySelectorAll('iframe[src*="docs.google.com"]');
        for (const f of frames) {
          let src = f.getAttribute("src") || "";
          try {
            const inner = new URL(src, doc.location?.href || "").searchParams.get("url");
            if (inner) return decodeURIComponent(inner);
          } catch (_e) {}
          if (/\.pdf|\.docx/i.test(src)) return src;
        }
        return "";
      },
      advice: "PDF is inside a Google viewer iframe — tap 📐 2. Bulletin in frame (under Extra) and pick the bulletin frame.",
      doNot: [],
    },
    {
      id: "wp_uploads_pdf_list",
      label: "WordPress media library PDF links",
      pageType: "pdf_link_list",
      captureMethod: "click_then_pdf",
      playbookType: "pdf_links",
      minScore: 22,
      markers: [
        { re: /wp-content\/uploads\/.*\.pdf/i, weight: 18, label: "wp-content PDF uploads" },
        { re: /wordpress|wp-json/i, weight: 8, label: "WordPress signals" },
      ],
      pickDownloadUrl: (doc) => {
        const links = Array.from(doc.querySelectorAll('a[href*="/wp-content/uploads/"][href$=".pdf"]'));
        for (const a of links) {
          const t = (a.innerText || a.textContent || a.getAttribute("href") || "").toLowerCase();
          if (/bulletin|newsletter|notice|\d{4}/i.test(t)) {
            try {
              return new URL(a.getAttribute("href") || "", doc.location?.href || "").href;
            } catch (_e) {
              continue;
            }
          }
        }
        return links[0] ? new URL(links[0].getAttribute("href") || "", doc.location?.href || "").href : "";
      },
      advice: "WordPress PDF links in uploads — pick the newest dated bulletin PDF.",
      doNot: [],
    },
    {
      id: "sequential_weekly_bulletins",
      label: "Sequential weekly bulletin URLs",
      pageType: "weekly_bulletin_download",
      captureMethod: "direct_download",
      playbookType: "weekly_bulletin_download",
      minScore: 20,
      markers: [
        { re: /weekly-bulletins\/\d+\//i, weight: 22, label: "Weekly-Bulletins/NNN path" },
        { re: /sunday\s+\d/i, weight: 8, label: "Sunday dated rows" },
      ],
      pickDownloadUrl: (doc) => {
        const links = Array.from(
          doc.querySelectorAll('a[href*="Weekly-Bulletins"], a[href*="weekly-bulletins"]')
        );
        for (const a of links) {
          const href = a.getAttribute("href") || "";
          if (!/preview|\.pdf\?/i.test(href)) {
            try {
              return new URL(href, doc.location?.href || "").href;
            } catch (_e) {
              continue;
            }
          }
        }
        return "";
      },
      advice: "Weekly bulletin list — click cloud download on this Sunday's row.",
      doNot: ["Do not stop at click-only — need a download capture step."],
    },
    {
      id: "wordpress_html_post",
      label: "WordPress HTML newsletter (text on page)",
      pageType: "wix_html",
      captureMethod: "html_capture",
      playbookType: "wix_html",
      minScore: 30,
      domRequired: true,
      domValidate: isWordPressHtmlBulletinPage,
      markers: [
        { re: /wp-block-paragraph|class="entry-content/i, weight: 14, label: "WP entry content blocks" },
        { re: /wordpress|wp-json|wp-content\/themes/i, weight: 10, label: "WordPress signals" },
        { re: /newsletter|bulletin|pastoral area/i, weight: 12, label: "newsletter in title/slug" },
        { re: /category-newsletter|tag-newsletter/i, weight: 8, label: "newsletter taxonomy" },
      ],
      pickDownloadUrl: () => "",
      advice:
        "WordPress HTML newsletter — Save page as PDF. Harvester prints this page each Sunday (not an image bulletin).",
      doNot: ["Do not use Pick bulletin image — the bulletin is text on this page."],
    },
    {
      id: "image_bulletin_wp",
      label: "Image bulletin (WordPress uploads)",
      pageType: "image_bulletin",
      captureMethod: "image_capture",
      playbookType: "image",
      minScore: 24,
      domRequired: true,
      domValidate: (doc) => hasBulletinImageInContent(doc, 400),
      markers: [
        {
          re: /wp-content\/uploads\/.*\.(jpg|jpeg|png|webp)/i,
          weight: 14,
          label: "WP uploaded images in body",
          scope: "body",
        },
        { re: /bulletin|newsletter|notice/i, weight: 10, label: "bulletin keywords" },
      ],
      pickDownloadUrl: () => "",
      advice: "Bulletin is a large image — use Pick an image on this page.",
      doNot: ["Do not use Save page as PDF when the bulletin is a single JPEG/PNG."],
    },
  ];

  const _collectHtmlBlob = (doc) => {
    const head = doc.head?.innerHTML?.slice(0, 40000) || "";
    const body = doc.body?.innerHTML?.slice(0, 120000) || "";
    const generator =
      doc.querySelector('meta[name="generator"]')?.getAttribute("content") || "";
    return { head, body, combined: `${head}\n${body}`, generator };
  };

  const _markerHaystack = (blob, marker) => {
    if (marker.scope === "body") return blob.body;
    if (marker.scope === "head") return blob.head;
    return blob.combined;
  };

  const _scoreFingerprint = (fp, blob) => {
    const markersFound = [];
    let score = 0;
    for (const m of fp.markers || []) {
      const haystack = _markerHaystack(blob, m);
      if (m.re.test(haystack) || m.re.test(blob.generator)) {
        score += Number(m.weight) || 10;
        markersFound.push(m.label || m.re.source);
      }
    }
    return { score, markersFound };
  };

  const scanPage = (doc = document) => {
    const blob = _collectHtmlBlob(doc);
    const matches = [];

    for (const fp of FINGERPRINTS) {
      let { score, markersFound } = _scoreFingerprint(fp, blob);
      if (fp.domValidate) {
        let domOk = false;
        try {
          domOk = Boolean(fp.domValidate(doc));
        } catch (_e) {
          domOk = false;
        }
        if (!domOk) {
          if (fp.domRequired) continue;
          score = Math.floor(score * 0.35);
        }
      }
      if (score < (fp.minScore || 20)) continue;
      let bestDownloadUrl = "";
      try {
        bestDownloadUrl = String(fp.pickDownloadUrl?.(doc) || "").trim();
      } catch (_e) {
        bestDownloadUrl = "";
      }
      matches.push({
        id: fp.id,
        label: fp.label,
        score,
        pageType: fp.pageType,
        captureMethod: fp.captureMethod,
        playbookType: fp.playbookType,
        markersFound,
        bestDownloadUrl,
        advice: fp.advice,
        doNot: fp.doNot || [],
        autoDirect: Boolean(bestDownloadUrl && /direct_/.test(fp.captureMethod)),
      });
    }

    matches.sort((a, b) => b.score - a.score);
    const best = matches[0] || null;

    const allDownloadUrls = [];
    try {
      doc.querySelectorAll('a[href]').forEach((a) => {
        const href = a.getAttribute("href") || "";
        if (
          /\.pdf|weekly-bulletins|\/files\/\d+\/|onewebmedia.*newsletter|drive\.google\.com\/file/i.test(
            href
          )
        ) {
          try {
            allDownloadUrls.push(new URL(href, doc.location?.href || "").href);
          } catch (_e) {}
        }
      });
    } catch (_e2) {}

    return {
      scannedAt: new Date().toISOString(),
      generator: blob.generator,
      best,
      matches: matches.slice(0, 6),
      allDownloadUrls: Array.from(new Set(allDownloadUrls)).slice(0, 12),
    };
  };

  const formatScanSummary = (scan) => {
    if (!scan?.best) {
      return "HTML scan: no strong CMS/plugin fingerprint — use Find bulletin or record steps manually.";
    }
    const b = scan.best;
    const lines = [
      `HTML scan: ${b.label} (score ${b.score})`,
      `Markers: ${b.markersFound.slice(0, 4).join(", ")}`,
      b.advice,
    ];
    if (b.bestDownloadUrl) {
      lines.push(`Detected download URL: ${b.bestDownloadUrl.split("/").slice(-2).join("/")}`);
    }
    if (scan.generator) {
      lines.push(`Generator: ${scan.generator.slice(0, 60)}`);
    }
    return lines.join("\n");
  };

  const toPatternPayload = (scan) => {
    const b = scan?.best;
    if (!b) return null;
    return {
      fingerprint_id: b.id,
      html_markers: b.markersFound,
      capture_method: b.captureMethod,
      generator: scan.generator || "",
      best_download_url: b.bestDownloadUrl || "",
    };
  };

  const globalApi = {
    FINGERPRINTS,
    scanPage,
    formatScanSummary,
    toPatternPayload,
    isWordPressHtmlBulletinPage,
    hasBulletinImageInContent,
    imageWidth: _imageWidth,
  };

  if (typeof globalThis !== "undefined") {
    globalThis.PhHtmlFingerprint = globalApi;
  }
})();
