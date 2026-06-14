/**
 * Rule-based site pattern library — no AI keys required.
 *
 * Learns from successful recipes pushed to GitHub (parishes/site_patterns.json)
 * and suggests workflows when a new site looks like a known archetype.
 */
(() => {
  const ARCHETYPE_ADVICE = {
    direct_pdf: {
      label: "Direct PDF page",
      steps: "You are already on the PDF — click Get a PDF.",
    },
    wp_pdfemb_list: {
      label: "WordPress PDF embed list",
      steps: "Click Follow a link → pick the newest dated bulletin → then Get a PDF.",
    },
    pdf_link_list: {
      label: "News page with PDF links",
      steps: "Click Find bulletin → Pick newest, or Follow a link to the latest PDF.",
    },
    iframe_viewer: {
      label: "PDF inside a frame/viewer",
      steps: "Click It's in a frame / viewer and choose the bulletin frame.",
    },
    wix_pdf_viewer: {
      label: "Wix PDF viewer",
      steps: "Use Find bulletin — Wix often hides the real PDF URL in the viewer.",
    },
    wix_html: {
      label: "Wix HTML bulletin page",
      steps: "Click Save page as PDF — harvester prints this page into the mega bulletin every Sunday.",
    },
    wix_date_grid: {
      label: "Wix bulletin date grid",
      steps: "Follow a link → pick this week's Sunday date → Save page as PDF.",
    },
    image_bulletin: {
      label: "Image bulletin",
      steps: "Click Get an image or Pick an image on this page.",
    },
    html_click_chain: {
      label: "HTML page — link chain needed",
      steps: "Click Follow a link to reach the bulletin, then Get a PDF or Mark as HTML.",
    },
    cloud_folder: {
      label: "Google Drive / OneDrive dated folder",
      steps: "Pick this Sunday's YY.MM.DD row → Save this PDF on file preview. Works across 2026, 2027, 2028…",
    },
    oneweb_docx: {
      label: "One.com Word bulletin (slow Google preview iframes)",
      steps: "Automatic — read newsletter URL from page HTML. Tap Save newsletter (auto) or Push. Harvester downloads onewebmedia/NEWSLETTER directly.",
    },
    weekly_bulletin_download: {
      label: "Weekly bulletin list (cloud auto-download)",
      steps: "Click cloud ↓ on this Sunday's row — PDF downloads automatically. Trainer records download, then Push.",
    },
    parish_messenger_embed: {
      label: "Parish Messenger widget (parishservices.co)",
      steps: "Wait for the page to load → Follow a link → pick newest View Newsletter / May 2026 row. Ignore Gift Aid and Data Entry PDFs.",
    },
    click_chain_menu: {
      label: "Menu navigation then PDF",
      steps: "Follow a link through the site menu (e.g. Newsletter), then Get a PDF on the redirect.",
    },
    unknown: {
      label: "Unknown layout",
      steps: "Click Find bulletin on this page to scan, then record steps manually.",
    },
  };

  const RECIPE_FLOW_ADVICE = {
    direct_download: "Recipe pattern: open page → download PDF.",
    direct_docx: "Recipe pattern: direct onewebmedia/NEWSLETTER download (skip slow iframe page).",
    click_then_pdf: "Recipe pattern: click a dated link → download PDF.",
    click_chain: "Recipe pattern: one or more clicks to reach the bulletin.",
    html_capture: "Recipe pattern: open bulletin page → print to PDF (Wix/HTML sites).",
    image_capture: "Recipe pattern: capture bulletin image(s).",
    mixed: "Recipe pattern: mixed steps — follow what worked on similar parishes.",
  };

  const WIX_SLUG_DATE_RE = /(\d{1,2})(?:st|nd|rd|th)?[_-](jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[_-](\d{4})/i;
  const MONTH_SLUG_NAMES = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
  ];

  const predictWixSlugUrl = (url, targetDate) => {
    const value = String(url || "");
    const m = WIX_SLUG_DATE_RE.exec(value);
    if (!m || !targetDate) return "";
    const sep = value[m.index + m[1].length] === "_" ? "_" : "-";
    const monthName = MONTH_SLUG_NAMES[targetDate.getMonth() + 1] || "";
    if (!monthName) return "";
    const slug = `${targetDate.getDate()}${sep}${monthName}${sep}${targetDate.getFullYear()}`;
    return value.slice(0, m.index) + slug + value.slice(m.index + m[0].length);
  };

  const fingerprintFromPage = (detectResult = {}) => {
    const type = String(detectResult.type || "unknown").trim();
    let pageType = "unknown";
    if (type === "direct_pdf") pageType = "direct_pdf";
    else if (type === "pdfemb") pageType = "wp_pdfemb_list";
    else if (type === "pdf_links") pageType = "pdf_link_list";
    else if (type === "iframe" || type === "iframe_maybe" || type === "embed") pageType = "iframe_viewer";
    else if (type === "wix_viewer") pageType = "wix_pdf_viewer";
    else if (type === "wix_html" || type === "wix_date_grid") pageType = "wix_html";
    else if (type === "parish_messenger") pageType = "parish_messenger_embed";
    else if (type === "oneweb_docx") pageType = "oneweb_docx";
    else if (type === "weekly_bulletin_download") pageType = "weekly_bulletin_download";
    else if (type === "cloud_folder") pageType = "cloud_folder";
    else if (type === "image") pageType = "image_bulletin";
    else if (type === "html" || type === "unknown") pageType = "html_click_chain";

    const pdfLinkCount = Array.isArray(detectResult.links) ? detectResult.links.length : 0;
    const hasDateLinks = Boolean(detectResult.bulletinLinks && detectResult.bulletinLinks.length > 0);

    return {
      page_type: pageType,
      pdf_link_count: pdfLinkCount,
      has_date_links: hasDateLinks,
      pattern_key: pageType,
    };
  };

  const fingerprintFromRecipe = (recipe = {}) => {
    const steps = Array.isArray(recipe.steps) ? recipe.steps : [];
    const actions = steps.map((s) => String(s?.action || "").trim().toLowerCase()).filter(Boolean);
    const hasClick = actions.includes("click");
    const hasDownload = actions.includes("download");
    const hasHtml = actions.includes("html") || actions.includes("print_to_pdf");
    const hasImage = actions.includes("image");
    const clickCount = actions.filter((a) => a === "click").length;

    let recipeFlow = "mixed";
    if (String(recipe.site_type || "").includes("oneweb") || String(recipe.playbook_type || "") === "oneweb_docx") {
      recipeFlow = "direct_docx";
    } else if (
      String(recipe.playbook_type || "") === "weekly_bulletin_download" ||
      String(recipe.site_type || "") === "sequential_bulletin_number"
    ) {
      recipeFlow = "direct_download";
    } else if (hasHtml) recipeFlow = "html_capture";
    else if (hasImage) recipeFlow = "image_capture";
    else if (hasClick && hasDownload) recipeFlow = "click_then_pdf";
    else if (hasDownload && !hasClick) recipeFlow = "direct_download";
    else if (hasClick && clickCount >= 2) recipeFlow = "click_chain";
    else if (hasClick) recipeFlow = "click_chain";

    const usesPdfPattern = steps.some((s) => String(s.url_pattern || "").includes("pdf"));

    return {
      recipe_flow: recipeFlow,
      step_count: steps.length,
      click_count: clickCount,
      uses_pdf_pattern: usesPdfPattern,
      pattern_key: `${actions.join(">") || "empty"}`,
    };
  };

  const combinedPatternKey = (pageFp, recipeFp) => {
    const page = pageFp?.page_type || "unknown";
    const flow = recipeFp?.recipe_flow || "mixed";
    return `${page}+${flow}`;
  };

  const findSimilar = (pageFingerprint, library = {}) => {
    const parishes = library.parishes && typeof library.parishes === "object" ? library.parishes : {};
    const patterns = library.patterns && typeof library.patterns === "object" ? library.patterns : {};
    const pageType = pageFingerprint?.page_type || "unknown";
    const matches = [];

    Object.entries(parishes).forEach(([parishKey, entry]) => {
      if (!entry || typeof entry !== "object") return;
      let score = 0;
      if (entry.page_type === pageType) score += 50;
      if (entry.recipe_flow && pageFingerprint._hint_flow && entry.recipe_flow === pageFingerprint._hint_flow) {
        score += 20;
      }
      if (score > 0) {
        matches.push({
          parish_key: parishKey,
          display_name: entry.display_name || parishKey,
          page_type: entry.page_type,
          recipe_flow: entry.recipe_flow,
          score,
          combined_key: entry.combined_key || "",
          operator_notes: Array.isArray(entry.operator_notes) ? entry.operator_notes : [],
          do_not: Array.isArray(entry.do_not) ? entry.do_not : [],
        });
      }
    });

    Object.entries(patterns).forEach(([key, entry]) => {
      if (!entry || typeof entry !== "object") return;
      if (entry.page_type !== pageType) return;
      const examples = Array.isArray(entry.example_parishes) ? entry.example_parishes : [];
      matches.push({
        parish_key: examples[0] || key,
        display_name: entry.label || key,
        page_type: entry.page_type,
        recipe_flow: entry.recipe_flow,
        score: 40 + Math.min(10, Number(entry.success_count) || 0),
        combined_key: key,
        is_pattern: true,
        advice: entry.advice || "",
        operator_notes: Array.isArray(entry.operator_notes) ? entry.operator_notes : [],
        do_not: Array.isArray(entry.do_not) ? entry.do_not : [],
        examples,
      });
    });

    matches.sort((a, b) => b.score - a.score);

    const seen = new Set();
    const unique = [];
    matches.forEach((m) => {
      const id = m.combined_key || m.parish_key;
      if (seen.has(id)) return;
      seen.add(id);
      unique.push(m);
    });
    return unique.slice(0, 5);
  };

  const buildHintText = (pageFingerprint, matches = []) => {
    const pageType = pageFingerprint?.page_type || "unknown";
    const archetype = ARCHETYPE_ADVICE[pageType] || ARCHETYPE_ADVICE.unknown;
    const lines = [
      `This looks like: ${archetype.label}`,
      archetype.steps,
    ];

    const parishMatches = matches.filter((m) => !m.is_pattern && m.display_name);
    const patternMatch = matches.find((m) => m.is_pattern && m.advice);

    if (patternMatch?.advice) {
      lines.push(`Learned tip: ${patternMatch.advice}`);
    } else if (patternMatch?.examples?.length) {
      lines.push(`Similar parishes already solved: ${patternMatch.examples.slice(0, 4).join(", ")}`);
    } else if (parishMatches.length > 0) {
      const names = parishMatches.slice(0, 4).map((m) => m.display_name).join(", ");
      lines.push(`Similar parishes already solved: ${names}`);
    }

    const mem = globalThis.ph_site_memory;
    const liveMemory = mem?.getForPageType?.(
      pageType === "oneweb_docx" ? "oneweb_docx" : ""
    );
    const notesBlock = mem?.formatHintBlock?.(
      patternMatch?.operator_notes?.length ? patternMatch : liveMemory
    );
    if (notesBlock) lines.push(notesBlock);

    const predicted = String(pageFingerprint?.predicted_url || "").trim();
    if (predicted) {
      lines.push(`This week's bulletin URL may be: ${predicted}`);
    }

    const topFlow = matches.find((m) => m.recipe_flow);
    if (topFlow?.recipe_flow && RECIPE_FLOW_ADVICE[topFlow.recipe_flow]) {
      lines.push(RECIPE_FLOW_ADVICE[topFlow.recipe_flow]);
    }

    return lines.join("\n");
  };

  const buildPatternEntry = (parishKey, displayName, pageFp, recipeFp, startUrl = "") => {
    const combined = combinedPatternKey(pageFp, recipeFp);
    const archetype = ARCHETYPE_ADVICE[pageFp.page_type] || ARCHETYPE_ADVICE.unknown;
    let host = "";
    try {
      host = new URL(startUrl).hostname.toLowerCase();
    } catch (_e) {
      host = "";
    }
    return {
      parish: {
        page_type: pageFp.page_type,
        recipe_flow: recipeFp.recipe_flow,
        combined_key: combined,
        display_name: displayName || parishKey,
        start_url_host: host,
        updated: new Date().toISOString().slice(0, 10),
        step_count: recipeFp.step_count,
      },
      pattern: {
        key: combined,
        page_type: pageFp.page_type,
        recipe_flow: recipeFp.recipe_flow,
        label: archetype.label,
        advice: archetype.steps,
        example_parish: parishKey,
      },
    };
  };

  const globalApi = {
    fingerprintFromPage,
    fingerprintFromRecipe,
    combinedPatternKey,
    findSimilar,
    buildHintText,
    buildPatternEntry,
    predictWixSlugUrl,
    ARCHETYPE_ADVICE,
  };

  if (typeof globalThis !== "undefined") {
    globalThis.PhPatternLibrary = globalApi;
  }
})();
