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
  };

  const getForPageType = (pageType) => {
    const key = String(pageType || "").trim();
    return CATALOG[key] || null;
  };

  const enrichRecipe = (recipe, pageCtx = {}) => {
    const base = recipe && typeof recipe === "object" ? { ...recipe } : {};
    const memory = getForPageType(pageCtx.type);
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
    const memory = getForPageType(pageCtx.type);
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
