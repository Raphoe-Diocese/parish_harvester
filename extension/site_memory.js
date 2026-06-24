/**
 * Institutional memory for unusual parish bulletin sites.
 * Saved into recipe JSON on Push and into parishes/site_patterns.json on GitHub.
 */
(() => {
  const CATALOG = {
    oneweb_docx: {
      playbook_type: "oneweb_docx",
      site_type: "oneweb_newsletter",
      page_type: "oneweb_docx",
      recipe_flow: "direct_docx",
      label: "One.com + slow Google preview iframes",
      auto_direct: true,
      skip_goto_on_push: true,
      operator_notes: [
        "Many docs.google.com/viewer iframes load slowly (2–4 min) — ignore previews.",
        "Bulletin is a Word file at onewebmedia/NEWSLETTER D-M-YY.docx — download directly.",
        "Iframe src URLs are in the HTML immediately; no need to wait for previews.",
        "Harvester rewrites the date each Sunday and tries filename variants (spaces before .docx).",
      ],
      do_not: [
        "Do not pick the first iframe PDF — often a GDPR or Privacy notice.",
        "Do not use goto-only recipes on this page.",
        "Do not train on financial-statement or admin docx files.",
      ],
    },
    cloud_folder: {
      playbook_type: "cloud_folder",
      site_type: "cloud_folder",
      page_type: "cloud_folder",
      recipe_flow: "click_then_pdf",
      label: "Google Drive / OneDrive dated folder",
      operator_notes: [
        "Pick the row dated YY.MM.DD for this Sunday.",
        "Harvester replays the click with the target date each week.",
      ],
      do_not: ["Do not pin a single static file — pick the dated row pattern."],
    },
    parish_messenger: {
      playbook_type: "parish_messenger",
      site_type: "parish_messenger",
      page_type: "parish_messenger_embed",
      recipe_flow: "click_then_pdf",
      label: "Parish Messenger widget",
      operator_notes: [
        "Wait for widget to load, then pick newest View Newsletter row.",
        "Ignore Gift Aid and Data Entry PDFs in the menu.",
      ],
      do_not: ["Do not pick admin PDFs from the widget list."],
    },
    weekly_bulletin_download: {
      playbook_type: "weekly_bulletin_download",
      site_type: "sequential_bulletin_number",
      page_type: "weekly_bulletin_download",
      recipe_flow: "direct_download",
      label: "Weekly bulletin list with auto-download",
      auto_direct: true,
      skip_goto_on_push: true,
      operator_notes: [
        "Homepage shows dated rows — click the cloud download on this Sunday's bulletin.",
        "PDF downloads automatically; trainer records the download URL.",
        "Harvester advances /Weekly-Bulletins/NNN/ by weeks since the example date.",
        "Joomla Dropfiles widget: cloud icon is a.mod_downloadlink — clicking the icon inside still counts.",
      ],
      do_not: [
        "Do not use Pick bulletin image — this is a PDF download site.",
        "Do not stop at click-only — need a download capture step.",
      ],
    },
    wix_html: {
      playbook_type: "wix_html",
      site_type: "html_text_bulletin",
      page_type: "wix_html",
      recipe_flow: "html_capture",
      label: "HTML text bulletin (WordPress, Wix, or similar)",
      operator_notes: [
        "Bulletin text is on the web page — not a downloadable PDF file.",
        "Use Save page as PDF on the newsletter article page.",
        "Harvester prints the page to PDF each Sunday (Pattern clonleigh uses predicted WP post URLs).",
      ],
      do_not: [
        "Do not use Pick bulletin image when the page is mostly text paragraphs.",
        "Do not stop at click-only — need print_to_pdf as the final step.",
      ],
    },
    dated_pdf_bulletin: {
      playbook_type: "dated_pdf_bulletin",
      site_type: "dated_pdf_path",
      page_type: "direct_pdf",
      recipe_flow: "direct_download",
      label: "Word → PDF bulletin at /pdf/DDMMYY.pdf",
      operator_notes: [
        "Bulletin is a real PDF (often made in Microsoft Word → Print to PDF).",
        "Tab title may say .docx or .jpg — ignore that; check the address bar ends in .pdf.",
        "On the PDF page: tap Save this PDF — saves the full https://… address for Sunday harvest.",
        "Or start on parishnews.html → point at this week's link → Yes → Save this PDF.",
        "Harvester rewrites DDMMYY in the URL each Sunday (e.g. 140626 → 210626).",
      ],
      do_not: [
        "Do not use use_page_url only — GitHub cannot read Chrome's internal PDF viewer address.",
        "Do not worry if Document Properties title mentions Microsoft Word.",
      ],
    },
    mdocs_download_list: {
      playbook_type: "mdocs_download_list",
      site_type: "mdocs_bulletin_list",
      page_type: "mdocs_bulletin_list",
      recipe_flow: "click_then_pdf",
      label: "mDocs PDF bulletin table",
      operator_notes: [
        "mDocs WordPress plugin lists dated PDFs — newest row is usually at the top.",
        "Click Download on this week's row, then capture PDF download (not Save page as PDF).",
        "Slow sites: use http:// if HTTPS certificate is expired (portstewartparish.website).",
        "Harvester waits up to 7 minutes for the table on very slow hosts.",
      ],
      do_not: [
        "Do not use Save page as PDF — bulletins are real PDF files in the mDocs table.",
        "Do not use https://portstewartparish.website — certificate expired; use http://.",
      ],
    },
    wp_block_file_bulletin: {
      playbook_type: "permanent_bulletin_page",
      site_type: "wp_block_file_bulletin",
      page_type: "wp_block_file_bulletin",
      recipe_flow: "direct_download",
      label: "WordPress permanent bulletin page (wp-block-file)",
      operator_notes: [
        "Permanent /parish-bulletin/ URL — PDF filename changes weekly under /wp-content/uploads/YYYY/MM/.",
        "PDF is in object.wp-block-file__embed[data] — harvest scrapes the embed URL.",
        "Use url_pattern *bulletin*.pdf — never pin a dated filename.",
      ],
      do_not: [
        "Do not train on the homepage — use the dedicated bulletin page only.",
        "Do not pin saintanthony.co.uk if the parish moved to saintanthonys.uk.",
      ],
    },
    joomla_dropfiles: {
      playbook_type: "weekly_bulletin_download",
      site_type: "joomla_dropfiles",
      page_type: "weekly_bulletin_download",
      recipe_flow: "click_then_download",
      label: "Joomla Dropfiles cloud download (.docx → PDF)",
      operator_notes: [
        "Joomla Dropfiles — cloud ↓ icon (a.mod_downloadlink) serves Word .docx.",
        "Click the cloud on this Sunday's row — harvester converts docx → PDF automatically.",
        "Do not record diocese GDPR/Privacy PDFs — only mod_downloadlink on the parish host.",
      ],
      do_not: [
        "Do not save a download URL from downandconnor.org or other diocese admin PDFs.",
        "Do not use Pick bulletin image — this is a file download site.",
      ],
    },
    stacked_image_bulletin: {
      playbook_type: "stacked_image_bulletin",
      site_type: "stacked_image_bulletin",
      page_type: "stacked_image_bulletin",
      recipe_flow: "image_stack",
      label: "Stacked JPEG bulletin images (top N each week)",
      operator_notes: [
        "Bulletins are full-page images stacked on one page — newest week at the top.",
        "Pick the first two images, or use Pick another image too after the first.",
        "Harvester grabs the top N large images automatically each Sunday — no dated URLs.",
      ],
      do_not: [
        "Do not hardcode one image URL — it goes stale every week.",
        "Do not Save page as PDF — that captures every old bulletin on the page.",
      ],
    },
    pdf_download_list: {
      playbook_type: "pdf_download_list",
      site_type: "pdf_link_list",
      page_type: "pdf_link_list",
      recipe_flow: "click_then_pdf",
      label: "PDF download list (newest dated row each week)",
      operator_notes: [
        "This page lists bulletin PDFs — the newest is usually at the top, but some parishes put it at the bottom.",
        "Point at this week's bulletin link (Download File / Parish News). Harvester picks the newest dated PDF each Sunday.",
        "Do not worry if the filename or date in the link text changes every week.",
      ],
      do_not: [
        "Do not pin a dated filename in the selector (e.g. 14th_june_2026.pdf) — it breaks next week.",
        "Do not pick GDPR, Gift Aid, or financial statement PDFs.",
      ],
    },
  };

  const _DDMMYY_PDF_RE = /\/pdf\/\d{6}\.pdf/i;

  const _recipeUsesDatedPdfPath = (recipe = {}) => {
    const urls = [
      String(recipe.start_url || ""),
      ...(Array.isArray(recipe.steps) ? recipe.steps : []).map((s) =>
        String(s?.url || s?.href || "")
      ),
    ];
    return urls.some((u) => _DDMMYY_PDF_RE.test(u));
  };

  const _recipeUsesImageStack = (recipe = {}) =>
    (Array.isArray(recipe.steps) ? recipe.steps : []).some(
      (step) => String(step?.action || "").trim() === "image_stack"
    );

  const _recipeLooksLikeMdocs = (recipe = {}) => {
    if (String(recipe.site_type || "").includes("mdocs")) return true;
    if (String(recipe.playbook_type || "").includes("mdocs")) return true;
    return (Array.isArray(recipe.steps) ? recipe.steps : []).some((step) => {
      const blob = `${step?.href || ""} ${step?.url || ""} ${step?.selector || ""}`;
      return /mdocs-file|table\.mdocs|mdocs-download/i.test(blob);
    });
  };

  const _recipeLooksLikeDropfiles = (recipe = {}) => {
    if (String(recipe.site_type || "").includes("dropfiles")) return true;
    return (Array.isArray(recipe.steps) ? recipe.steps : []).some((step) =>
      /mod_downloadlink/i.test(String(step?.selector || ""))
    );
  };

  const getForPageType = (pageType, recipe = null, pageCtx = null) => {
    const key = String(pageType || "").trim();
    const fpId = String(pageCtx?.htmlFingerprint || "").trim();
    if (fpId === "mdocs_bulletin_table" || _recipeLooksLikeMdocs(recipe)) {
      return CATALOG.mdocs_download_list;
    }
    if (fpId === "wp_block_file_bulletin" || key === "wp_block_file_bulletin") {
      return CATALOG.wp_block_file_bulletin;
    }
    if (fpId === "joomla_dropfiles_weekly" || _recipeLooksLikeDropfiles(recipe)) {
      return CATALOG.joomla_dropfiles;
    }
    if (fpId === "stacked_image_bulletin" || (recipe && _recipeUsesImageStack(recipe))) {
      return CATALOG.stacked_image_bulletin;
    }
    if (recipe && _recipeUsesDatedPdfPath(recipe)) {
      return CATALOG.dated_pdf_bulletin;
    }
    if (key === "pdf_link_list" || key === "pdf_links") {
      return CATALOG.pdf_download_list;
    }
    return CATALOG[key] || null;
  };

  const enrichRecipe = (recipe, pageCtx = {}) => {
    const base = recipe && typeof recipe === "object" ? { ...recipe } : {};
    const memory = getForPageType(pageCtx.type, base, pageCtx);
    if (!memory) return base;

    base.playbook_type = memory.playbook_type;
    base.site_type = memory.site_type;
    if (memory.auto_direct) base.auto_direct = true;
    base.operator_notes = [...memory.operator_notes];
    base.do_not = [...memory.do_not];

    if (memory.skip_goto_on_push && Array.isArray(base.steps)) {
      const hasDownload = base.steps.some((s) => String(s?.action || "").toLowerCase() === "download");
      if (hasDownload) {
        base.steps = base.steps.filter((s) => String(s?.action || "").toLowerCase() !== "goto");
      }
    }

    return base;
  };

  const patternPayloadFromPage = (pageCtx = {}, recipe = {}) => {
    const memory = getForPageType(pageCtx.type, recipe, pageCtx);
    const lib = globalThis.PhPatternLibrary;
    if (!lib) return null;
    const page = lib.fingerprintFromPage(pageCtx);
    const rec = lib.fingerprintFromRecipe(recipe);
    if (memory) {
      page.page_type = memory.page_type;
      rec.recipe_flow = memory.recipe_flow;
    }
    return {
      page,
      recipe: rec,
      operator_notes: memory?.operator_notes || recipe.operator_notes || [],
      do_not: memory?.do_not || recipe.do_not || [],
      label: memory?.label || "",
      html: globalThis.PhHtmlFingerprint?.toPatternPayload?.(pageCtx.fingerprintScan) || undefined,
    };
  };

  const formatHintBlock = (memoryOrNotes) => {
    if (!memoryOrNotes) return "";
    const notes = Array.isArray(memoryOrNotes)
      ? memoryOrNotes
      : memoryOrNotes.operator_notes || [];
    const donts = memoryOrNotes.do_not || [];
    const lines = [];
    if (notes.length) {
      lines.push("Remember:");
      notes.forEach((n) => lines.push(`• ${n}`));
    }
    if (donts.length) {
      lines.push("Avoid:");
      donts.forEach((n) => lines.push(`• ${n}`));
    }
    return lines.join("\n");
  };

  window.ph_site_memory = {
    CATALOG,
    getForPageType,
    enrichRecipe,
    patternPayloadFromPage,
    formatHintBlock,
  };
})();
