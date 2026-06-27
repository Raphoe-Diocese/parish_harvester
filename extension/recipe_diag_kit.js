/**
 * Parish Trainer — recipe & extension diagnosis kit.
 * Surfaces problems the user may not notice (silent failures, bad recipes, drift).
 */
(() => {
  if (globalThis.ph_recipe_diag) {
    return;
  }

  const REQUIRED_MODULES = [
    { key: "ph_playbook", label: "Playbook (plain-English steps)" },
    { key: "ph_site_memory", label: "Site memory (parish archetypes)" },
    { key: "PhPatternLibrary", label: "Pattern library" },
    { key: "PhHtmlFingerprint", label: "HTML fingerprint scanner" },
  ];

  const TERMINAL_ACTIONS = new Set([
    "download",
    "image",
    "image_stack",
    "print_to_pdf",
    "html",
    "crop_screenshot",
  ]);

  const BAD_DOWNLOAD_RE =
    /privacy|gdpr|gift.?aid|dataentry|financial|safeguarding|standingorder|donation|downandconnor/i;

  const _hostname = (url) => {
    try {
      return new URL(String(url || "")).hostname.toLowerCase();
    } catch (_e) {
      return "";
    }
  };

  const _issue = (id, severity, title, detail = "", fix = "") => ({
    id,
    severity,
    title,
    detail,
    fix,
  });

  const _storageGet = (keys) =>
    new Promise((resolve) => {
      if (!chrome?.storage?.local) {
        resolve({});
        return;
      }
      chrome.storage.local.get(keys, (r) => resolve(r || {}));
    });

  const _pageContext = () => {
    try {
      if (typeof globalThis.__phDiagExport === "function") {
        return globalThis.__phDiagExport() || {};
      }
    } catch (err) {
      return { export_error: String(err) };
    }
    return {};
  };

  const _analyzeSteps = (steps, pageCtx = {}) => {
    const issues = [];
    const list = Array.isArray(steps) ? steps : [];
    const actions = list.map((s) => String(s?.action || "").trim().toLowerCase());
    const pageType = String(pageCtx.page_type?.type || pageCtx.page_type || "").trim();

    if (list.length === 0) {
      issues.push(
        _issue(
          "no_steps",
          "info",
          "No recipe steps recorded yet",
          "Training has not captured any steps on this page.",
          "Use Step 1 to point at the bulletin link, confirm, then save the PDF/download."
        )
      );
      return issues;
    }

    const clickCount = actions.filter((a) => a === "click").length;
    const hasTerminal = actions.some((a) => TERMINAL_ACTIONS.has(a));

    if (clickCount > 0 && !hasTerminal) {
      issues.push(
        _issue(
          "click_only",
          "error",
          "Recipe stops at click — missing save/download step",
          `${clickCount} click step(s) but no download, print_to_pdf, or image capture.`,
          "Open the bulletin, then tap Save this PDF / download capture before Send & test."
        )
      );
    }

    for (let i = 1; i < list.length; i += 1) {
      const prev = list[i - 1];
      const cur = list[i];
      if (
        String(prev?.action || "").toLowerCase() === "click" &&
        String(cur?.action || "").toLowerCase() === "click" &&
        String(prev?.text || "").trim() &&
        String(prev?.text || "").trim() === String(cur?.text || "").trim()
      ) {
        issues.push(
          _issue(
            "duplicate_click",
            "warn",
            "Duplicate click steps for the same link",
            `Steps ${i} and ${i + 1} both click "${String(cur.text || "").slice(0, 50)}".`,
            "Tap Undo Last Step once, or clear and re-record from Step 1."
          )
        );
        break;
      }
    }

    for (const step of list) {
      const action = String(step?.action || "").toLowerCase();
      const selector = String(step?.selector || "");
      const url = String(step?.url || step?.href || step?.captured_url || "");
      const text = String(step?.text || "");

      if (action === "download" && url && BAD_DOWNLOAD_RE.test(url)) {
        issues.push(
          _issue(
            "bad_download_url",
            "error",
            "Download step points at admin/GDPR PDF — not the bulletin",
            url.slice(0, 100),
            "Re-record using the parish weekly bulletin row only (cloud ↓ or bulletin link)."
          )
        );
      }

      if (action === "click" && /\d{4}[-_]\d{2}[-_]\d{2}|june|january|february|march|april|may|july|august|september|october|november|december/i.test(selector)) {
        issues.push(
          _issue(
            "dated_selector",
            "warn",
            "Click selector may include a dated filename",
            selector.slice(0, 80),
            "Re-pick the link using newest-dated strategy — avoid pinning June-2026-style filenames."
          )
        );
      }

      if (action === "print_to_pdf" && /mdocs|weekly.bulletin|mod_downloadlink/i.test(`${pageType} ${url} ${selector}`)) {
        issues.push(
          _issue(
            "print_on_download_site",
            "error",
            "Save page as PDF on a real-file download site",
            "mDocs / Joomla Dropfiles sites serve PDF or DOCX files — not HTML bulletins.",
            "Use Download capture after clicking the bulletin row, not Save page as PDF."
          )
        );
      }
    }

    if (pageType === "weekly_bulletin_download" && !actions.includes("download")) {
      issues.push(
        _issue(
          "weekly_needs_download",
          "warn",
          "Weekly bulletin list site — usually needs a download step",
          "Page looks like Joomla Dropfiles / sequential weekly bulletins.",
          "Click the cloud ↓ on this Sunday's row, then capture the file download."
        )
      );
    }

    if (pageType === "mdocs_bulletin_list" && actions.includes("print_to_pdf")) {
      issues.push(
        _issue(
          "mdocs_print_to_pdf",
          "error",
          "mDocs site must not use Save page as PDF",
          "Portstewart-style mDocs tables have real PDF downloads.",
          "Record Download on the newest mDocs row instead."
        )
      );
    }

    if (
      (pageType === "pdfemb" || pageCtx.html_fingerprint_id === "wordpress_pdfemb") &&
      actions.includes("print_to_pdf")
    ) {
      issues.push(
        _issue(
          "pdfemb_print_to_pdf",
          "error",
          "PDF Embedder page — do not Save page as PDF",
          "Bulletin is a real PDF file linked in the page HTML.",
          "Use Save this PDF / download on the newest a.pdfemb-viewer link."
        )
      );
    }

    if (pageType === "pdfemb" && clickCount > 0 && !actions.includes("download")) {
      issues.push(
        _issue(
          "pdfemb_needs_download_step",
          "warn",
          "PDF Embedder — clicks recorded but no download step",
          "After picking the bulletin link, tap Save this PDF.",
          "Harvester reads a.pdfemb-viewer hrefs — recipe must end with download."
        )
      );
    }

    const startUrl = String(pageCtx.standalone_start_url || pageCtx.page_url || "");
    const startHost = _hostname(startUrl);
    const pageHost = _hostname(pageCtx.page_url || window.location.href);
    if (startHost && pageHost && startHost !== pageHost) {
      issues.push(
        _issue(
          "host_mismatch",
          "warn",
          "Recording start host differs from current page",
          `Start: ${startHost} · Now: ${pageHost}`,
          "Confirm you are training the correct parish site, or tap Wrong parish?"
        )
      );
    }

    if (/portstewartparish\.website/i.test(startUrl) && startUrl.startsWith("https://")) {
      issues.push(
        _issue(
          "portstewart_https",
          "warn",
          "Portstewart recipe uses HTTPS — certificate is expired",
          startUrl,
          "Use http://portstewartparish.website (trainer auto-fixes on push)."
        )
      );
    }

    return issues;
  };

  const _checkExtensionStack = () => {
    const issues = [];
    for (const mod of REQUIRED_MODULES) {
      if (!globalThis[mod.key]) {
        issues.push(
          _issue(
            `missing_${mod.key}`,
            "error",
            `Module not loaded: ${mod.label}`,
            `${mod.key} is undefined — heavy trainer scripts may not have run.`,
            "Reload the extension, close this tab, open a fresh tab, then Show floating toolbar."
          )
        );
      }
    }
    if (!globalThis.__phContentDispatch && globalThis.__phBridgeInstalled) {
      issues.push(
        _issue(
          "dispatch_missing",
          "error",
          "Content bridge ready but trainer dispatch missing",
          "bridge_boot is up but content.js did not register handlers.",
          "Wait 5s and Retry full toolbar, or reload the extension."
        )
      );
    }
    return issues;
  };

  const _checkToolbar = async () => {
    const issues = [];
    const base =
      typeof globalThis.ph_toolbar_diag?.collect === "function"
        ? await globalThis.ph_toolbar_diag.collect()
        : {};

    if (!base.toolbar_present) {
      issues.push(
        _issue(
          "toolbar_missing",
          "error",
          "Floating toolbar not in the page DOM",
          "Mount or toolbar element is absent.",
          "Extension popup → Show floating toolbar. If stub only, wait or Retry full toolbar."
        )
      );
    } else if (base.toolbar_mode === "stub") {
      issues.push(
        _issue(
          "toolbar_stub",
          "warn",
          "Toolbar stuck in stub mode",
          "Full recipe UI did not replace the loading stub.",
          globalThis.__phLastToolbarError
            ? `Last error: ${globalThis.__phLastToolbarError}`
            : "Open Diagnostics → Retry full toolbar."
        )
      );
    } else if (base.toolbar_mode === "minimal") {
      issues.push(
        _issue(
          "toolbar_minimal",
          "warn",
          "Simplified minimal trainer is active",
          "Full UI failed; basic Step 1/2 buttons only.",
          globalThis.__phLastToolbarError
            ? `Cause: ${globalThis.__phLastToolbarError}`
            : "Copy diagnostics for AI — full UI threw during init."
        )
      );
    }

    if (base.toolbar_present && !base.toolbar_on_screen) {
      issues.push(
        _issue(
          "toolbar_offscreen",
          "warn",
          "Toolbar exists but is not visible on screen",
          `display=${base.toolbar_display} rect=${base.toolbar_rect}`,
          "Drag it into view or click Show floating toolbar again."
        )
      );
    }

    if (base.last_error) {
      issues.push(
        _issue(
          "last_runtime_error",
          "error",
          "Last trainer error recorded",
          base.last_error,
          "Fix the error above, then reload extension + fresh tab."
        )
      );
    }

    if (!base.gh_pat) {
      issues.push(
        _issue(
          "no_github_pat",
          "warn",
          "GitHub PAT not configured",
          "Send & test and recipe push will fail.",
          "Extension popup → Settings → add Personal Access Token."
        )
      );
    }

    return { issues, facts: base };
  };

  const _checkRecordingSession = async (pageHost) => {
    const issues = [];
    const stored = await _storageGet(["ph_recording_sessions", "ph_recording_session"]);
    const map =
      stored.ph_recording_sessions && typeof stored.ph_recording_sessions === "object"
        ? stored.ph_recording_sessions
        : {};
    const legacy = stored.ph_recording_session;
    const session = pageHost ? map[pageHost] : null;

    if (legacy?.active && !session?.active) {
      issues.push(
        _issue(
          "legacy_session_active",
          "warn",
          "Old recording session key still marked active",
          "ph_recording_session vs ph_recording_sessions mismatch.",
          "Harmless but may block auto-restore on new tabs — re-open toolbar after navigation."
        )
      );
    }

    if (session?.active) {
      const stepCount = Array.isArray(session.steps) ? session.steps.length : 0;
      if (stepCount === 0) {
        issues.push(
          _issue(
            "empty_session",
            "info",
            "Recording session active with 0 saved steps",
            `Host: ${pageHost}`,
            "Continue training or clear session from a fresh start."
          )
        );
      }
    }

    return issues;
  };

  const _fetchGithubContext = async (pageUrl, parishKey) => {
    if (!chrome?.runtime?.sendMessage) return null;
    try {
      return await new Promise((resolve) => {
        // Without this timeout a hung background fetch leaves the whole
        // diagnosis stuck on "Running diagnostics…" forever.
        const timer = setTimeout(
          () => resolve({ ok: false, error: "GitHub lookup timed out (10s)" }),
          10000
        );
        chrome.runtime.sendMessage(
          { type: "ph_recipe_diag_github", url: pageUrl, parish_key: parishKey || "" },
          (res) => {
            clearTimeout(timer);
            if (chrome.runtime?.lastError) {
              resolve({ ok: false, error: chrome.runtime.lastError.message });
              return;
            }
            resolve(res || { ok: false });
          }
        );
      });
    } catch (err) {
      return { ok: false, error: String(err) };
    }
  };

  const _analyzeGithub = (gh, pageCtx) => {
    const issues = [];
    if (!gh?.ok) {
      if (gh?.error) {
        issues.push(
          _issue("github_fetch_failed", "warn", "Could not load GitHub harvest data", gh.error, "Check PAT and repo settings.")
        );
      }
      return issues;
    }

    const key = String(gh.parish_key || "").trim();
    if (key && gh.consecutive_failures >= 3) {
      issues.push(
        _issue(
          "harvest_fail_streak",
          "error",
          `${gh.consecutive_failures} consecutive harvest failures on GitHub`,
          `Parish: ${key}`,
          "Retrain recipe on the live site, then Send & test."
        )
      );
    } else if (key && gh.consecutive_failures >= 1) {
      issues.push(
        _issue(
          "harvest_recent_fail",
          "warn",
          `Last harvest failed (${gh.consecutive_failures} streak)`,
          gh.last_failure_reason || "See Bulletins/report.json on GitHub.",
          "Open Problems tab or retrain if bulletin layout changed."
        )
      );
    }

    if (gh.recipe) {
      const recipe = gh.recipe;
      const ghSteps = Array.isArray(recipe.steps) ? recipe.steps : [];
      issues.push(..._analyzeSteps(ghSteps, { ...pageCtx, page_url: recipe.start_url || pageCtx.page_url }));

      const recHost = _hostname(recipe.start_url || "");
      const pageHost = _hostname(pageCtx.page_url || "");
      if (recHost && pageHost && recHost === pageHost && pageCtx.page_url) {
        const norm = (u) => String(u || "").replace(/\/+$/, "");
        if (norm(recipe.start_url) !== norm(pageCtx.page_url) && !norm(pageCtx.page_url).includes("/newsletter")) {
          issues.push(
            _issue(
              "start_url_drift",
              "warn",
              "GitHub recipe start_url differs from this page",
              `Recipe: ${recipe.start_url}\nNow: ${pageCtx.page_url}`,
              "Update start_url if the bulletin moved, or train on the recipe start page."
            )
          );
        }
      }

      if (!gh.recipe_found && key) {
        issues.push(
          _issue(
            "no_github_recipe",
            "warn",
            "No recipe file on GitHub for this parish yet",
            `Expected parishes/recipes/.../${key}.json`,
            "Complete training and Send & test to create the recipe."
          )
        );
      }
    } else if (gh.parish_key && !gh.recipe_found) {
      issues.push(
        _issue(
          "no_github_recipe",
          "info",
          "Parish recognised but no GitHub recipe yet",
          gh.parish_key,
          "Record steps and push when the bulletin flow works."
        )
      );
    }

    return issues;
  };

  const _dedupeIssues = (issues) => {
    const seen = new Set();
    const out = [];
    for (const item of issues) {
      const key = `${item.id}:${item.title}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(item);
    }
    return out;
  };

  const _scanHtmlFingerprint = (pageCtx) => {
    const scan = pageCtx.html_fingerprint_scan;
    if (scan && scan.best) return scan;
    try {
      if (globalThis.PhHtmlFingerprint?.scanPage) {
        return globalThis.PhHtmlFingerprint.scanPage(document);
      }
    } catch (_e) {
      return null;
    }
    return null;
  };

  const _pageArchetype = (pageCtx, htmlScan) => {
    const lib = globalThis.PhPatternLibrary;
    const detected = pageCtx.page_type && typeof pageCtx.page_type === "object"
      ? pageCtx.page_type
      : { type: String(pageCtx.page_type || "unknown") };
    if (lib?.fingerprintFromPage) {
      return lib.fingerprintFromPage(detected);
    }
    const best = htmlScan?.best;
    return {
      page_type: best?.pageType || detected.type || "unknown",
      pattern_key: best?.id || pageCtx.html_fingerprint_id || "",
    };
  };

  const _expectedTerminalForArchetype = (archetype) => {
    const key = String(archetype || "").toLowerCase();
    if (key === "wp_pdfemb_list" || key === "pdf_link_list" || key === "wp_block_file_bulletin") {
      return { prefer: ["download"], avoid: ["print_to_pdf", "html"] };
    }
    if (key === "weekly_bulletin_download" || key === "mdocs_download_list") {
      return { prefer: ["download"], avoid: ["print_to_pdf"] };
    }
    if (key === "wix_html" || key === "wix_date_grid") {
      return { prefer: ["print_to_pdf", "html"], avoid: [] };
    }
    if (key === "iframe_viewer" || key === "wix_pdf_viewer") {
      return { prefer: ["download", "print_to_pdf"], avoid: [] };
    }
    if (key === "direct_pdf") {
      return { prefer: ["download"], avoid: ["print_to_pdf"] };
    }
    return { prefer: ["download", "print_to_pdf", "image"], avoid: [] };
  };

  const _analyzePageRecipeMismatch = (pageCtx, steps) => {
    const issues = [];
    const list = Array.isArray(steps) ? steps : [];
    const actions = list.map((s) => String(s?.action || "").trim().toLowerCase());
    const lastAction = actions.length ? actions[actions.length - 1] : "";
    const htmlScan = _scanHtmlFingerprint(pageCtx);
    const archetype = _pageArchetype(pageCtx, htmlScan);
    const archetypeKey = String(archetype.page_type || archetype.pattern_key || "").trim();
    const detectType = String(pageCtx.page_type?.type || pageCtx.page_type || "").trim();
    const fpId = String(htmlScan?.best?.id || pageCtx.html_fingerprint_id || "").trim();
    const fpLabel = String(htmlScan?.best?.label || "").trim();
    const pdfembInDom = Boolean(
      document.querySelector?.('a.pdfemb-viewer[href*=".pdf"], a[class*="pdfemb"][href*=".pdf"]')
    );

    if (fpId === "wordpress_pdfemb" && detectType === "iframe_maybe") {
      issues.push(
        _issue(
          "embed_not_iframe",
          "error",
          "PDF Embedder page misread as iframe",
          `HTML fingerprint: ${fpLabel || "WordPress PDF Embedder"} but detectPageType says ${detectType}.`,
          "Use Follow a link → pick newest bulletin → Save this PDF. Do NOT use frame/viewer flow."
        )
      );
    }

    if (pdfembInDom && !["pdfemb", "wp_pdfemb_list"].includes(detectType) && !["pdfemb", "wp_pdfemb_list"].includes(archetypeKey)) {
      issues.push(
        _issue(
          "pdfemb_links_on_page",
          "error",
          "Page has PDF Embedder links — not a mystery iframe",
          "Found a.pdfemb-viewer[href] in page HTML (direct PDF URLs).",
          "Tap Pick newest bulletin or Follow a link on the top dated PDF, then Save this PDF."
        )
      );
    }

    if (fpId && detectType && detectType !== "unknown") {
      const lib = globalThis.PhPatternLibrary;
      const mapped = lib?.fingerprintFromPage?.({ type: detectType });
      const mappedType = mapped?.page_type || "";
      if (mappedType && archetypeKey && mappedType !== archetypeKey && fpId !== "wordpress_pdfemb") {
        issues.push(
          _issue(
            "page_type_mismatch",
            "warn",
            "Page type detectors disagree",
            `detectPageType=${detectType} · fingerprint=${archetypeKey} · html_id=${fpId}`,
            "Trust the HTML fingerprint advice in the toolbar Pattern hint."
          )
        );
      }
    }

    const expected = _expectedTerminalForArchetype(archetypeKey || fpId);
    if (lastAction && expected.avoid.includes(lastAction)) {
      issues.push(
        _issue(
          "wrong_terminal_for_layout",
          "error",
          `Wrong finish step for ${archetypeKey || fpLabel || "this layout"}`,
          `Recipe ends with "${lastAction}" but this site type needs: ${expected.prefer.join(" or ")}.`,
          htmlScan?.best?.advice || pageCtx.page_type?.advice || "Re-record using the green primary button for this page type."
        )
      );
    }

    if (
      (archetypeKey === "wp_pdfemb_list" || fpId === "wordpress_pdfemb") &&
      list.length === 1 &&
      actions[0] === "goto"
    ) {
      issues.push(
        _issue(
          "pdfemb_needs_download",
          "warn",
          "PDF Embedder page — goto-only recipe will fail harvest",
          "Harvester needs a download step (or goto+download with url_pattern).",
          "Add download step with *.pdf — or push after Pick newest bulletin + Save PDF."
        )
      );
    }

    if (pageCtx.last_auto_terminal?.added) {
      issues.push(
        _issue(
          "auto_terminal_added",
          "warn",
          "Download step was added automatically before push",
          `Extension added "${pageCtx.last_auto_terminal.action || "download"}" — you may not have tapped Save PDF yourself.`,
          "Confirm the auto-added step is correct, or re-record manually so you learn the flow."
        )
      );
    }

    return { issues, htmlScan, archetype };
  };

  const _analyzeSessionDrift = (pageCtx) => {
    const issues = [];
    const uiCount = Number(pageCtx.session_ui_steps) || 0;
    const recipeCount = Array.isArray(pageCtx.recipe_steps)
      ? pageCtx.recipe_steps.length
      : Number(pageCtx.recipe_steps_local) || 0;
    if (uiCount > recipeCount + 1) {
      issues.push(
        _issue(
          "session_steps_drift",
          "error",
          "Toolbar shows more clicks than the recipe will push",
          `Session UI: ${uiCount} step(s) · Recipe file: ${recipeCount} step(s).`,
          "Some clicks did not become recipe steps — tap Save PDF / confirm Step 2 before Send & test."
        )
      );
    }
    const uiSteps = Array.isArray(pageCtx.session_steps_detail) ? pageCtx.session_steps_detail : [];
    const recipeSteps = Array.isArray(pageCtx.recipe_steps_detail)
      ? pageCtx.recipe_steps_detail
      : Array.isArray(pageCtx.recipe_steps)
        ? pageCtx.recipe_steps
        : [];
    const uiClicks = uiSteps.filter((s) => String(s?.action || "").toLowerCase() === "click").length;
    const recipeClicks = recipeSteps.filter((s) => String(s?.action || "").toLowerCase() === "click").length;
    if (uiClicks > 0 && recipeClicks === 0 && recipeSteps.length > 0) {
      issues.push(
        _issue(
          "clicks_not_in_recipe",
          "error",
          "You clicked links but recipe has no click steps",
          `${uiClicks} UI click(s) — recipe has ${recipeSteps.length} step(s) with no click.`,
          "After Step 1 confirm, ensure Step 2 Save PDF runs — clicks alone do not harvest."
        )
      );
    }
    return issues;
  };

  const _getPatternHints = async (pageCtx, parishKey) => {
    const hints = [];
    const lib = globalThis.PhPatternLibrary;
    if (!lib) return hints;

    const detected = pageCtx.page_type && typeof pageCtx.page_type === "object"
      ? pageCtx.page_type
      : { type: String(pageCtx.page_type || "unknown") };
    const pageFp = lib.fingerprintFromPage?.(detected);
    if (pageFp?.page_type && lib.ARCHETYPE_ADVICE?.[pageFp.page_type]) {
      const adv = lib.ARCHETYPE_ADVICE[pageFp.page_type];
      hints.push({ kind: "archetype", label: adv.label, steps: adv.steps });
    }

    try {
      const stored = await _storageGet(["ph_site_patterns_cache"]);
      let library = stored.ph_site_patterns_cache;
      if (!library && chrome?.runtime?.sendMessage) {
        library = await new Promise((resolve) => {
          const timer = setTimeout(() => resolve(null), 8000);
          chrome.runtime.sendMessage({ type: "fetch_site_patterns" }, (res) => {
            clearTimeout(timer);
            resolve(res?.ok ? res.library : null);
          });
        });
      }
      if (library && lib.findSimilar && pageFp) {
        const similar = lib.findSimilar(library, pageFp, parishKey);
        if (similar?.length) {
          for (const match of similar.slice(0, 2)) {
            hints.push({
              kind: "similar_parish",
              parish: match.parish_key || match.key,
              pattern: match.pattern_key || "",
              flow: match.recipe_flow || "",
            });
          }
        }
      }
    } catch (_e) {
      // non-fatal
    }

    const mem = globalThis.ph_site_memory;
    if (mem?.getForPageType && mem?.formatHintBlock) {
      try {
        const block = mem.formatHintBlock(mem.getForPageType(detected.type, null, detected));
        if (block) hints.push({ kind: "site_memory", text: block.slice(0, 400) });
      } catch (_e) {
        // non-fatal
      }
    }

    return hints;
  };

  const buildDiagnosisPayload = async (report) => {
    const r = report || (await runFullDiagnosis());
    return {
      collected_at: r.collected_at,
      extension_version: r.extension_version,
      parish_key: r.parish_key,
      page_url: r.page_url,
      page_type: r.page_type,
      page_archetype: r.page_archetype,
      page_summary: r.page_summary,
      html_fingerprint: r.html_fingerprint,
      recipe_steps_local: r.recipe_steps_local,
      session_ui_steps: r.session_ui_steps,
      issues: r.issues,
      counts: r.counts,
      pattern_hints: r.pattern_hints,
      github: r.github,
    };
  };

  const saveDiagnosisToGithub = async (report) => {
    const payload = await buildDiagnosisPayload(report);
    const key = String(payload.parish_key || "").trim().toLowerCase();
    if (!key) return { ok: false, error: "No parish_key — open a parish page first." };
    return new Promise((resolve) => {
      chrome.runtime.sendMessage(
        { type: "ph_save_diagnosis", parish_key: key, diagnosis: payload, source: "manual_diag" },
        (res) => {
          if (chrome.runtime?.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message });
            return;
          }
          resolve(res || { ok: false, error: "No response" });
        }
      );
    });
  };

  const _inferSiteIntake = (pageCtx, mismatch) => {
    const fp = mismatch.htmlScan?.best;
    const pageType = String(pageCtx.page_type?.type || pageCtx.page_type || "").toLowerCase();
    const capture = String(fp?.captureMethod || fp?.pageType || "").toLowerCase();
    let bulletin_format = "unknown";
    if (capture.includes("image_stack") || pageType.includes("image_stack")) bulletin_format = "image_stack";
    else if (capture.includes("image") || pageType.includes("image")) bulletin_format = "image";
    else if (capture.includes("html") || pageType.includes("html")) bulletin_format = "html";
    else if (capture.includes("docx") || pageType.includes("docx") || pageType.includes("dropfiles")) {
      bulletin_format = "word";
    } else if (capture.includes("drive") || pageType.includes("drive")) bulletin_format = "google_drive";
    else if (pageType.includes("facebook")) bulletin_format = "facebook";
    else if (capture.includes("pdf") || pageType.includes("pdf")) bulletin_format = "pdf_download";

    const terminal_map = {
      pdf_download: "download",
      word: "download",
      html: "print_to_pdf",
      image: "image",
      image_stack: "image_stack",
      google_drive: "download",
    };

    return {
      bulletin_format,
      suggested_terminal_step: terminal_map[bulletin_format] || fp?.captureMethod || "",
      page_type: pageType,
      fingerprint_id: fp?.id || "",
      best_download_url: fp?.bestDownloadUrl || "",
      operator_confirm: {
        bulletin_format: null,
        notes: "",
      },
    };
  };

  const runFullDiagnosis = async () => {
    const pageCtx = _pageContext();
    const pageHost = _hostname(pageCtx.page_url || window.location.href);
    const parishKey = String(pageCtx.parish_key || "").trim();

    const toolbar = await _checkToolbar();
    const mismatch = _analyzePageRecipeMismatch(pageCtx, pageCtx.recipe_steps || []);
    let issues = [
      ..._checkExtensionStack(),
      ...toolbar.issues,
      ...(await _checkRecordingSession(pageHost)),
      ..._analyzeSteps(pageCtx.recipe_steps || [], pageCtx),
      ..._analyzeSessionDrift(pageCtx),
      ...mismatch.issues,
    ];

    const pattern_hints = await _getPatternHints(pageCtx, parishKey || "");

    const gh = await _fetchGithubContext(pageCtx.page_url || window.location.href, parishKey);
    if (gh) {
      issues.push(..._analyzeGithub(gh, pageCtx));
    }

    issues = _dedupeIssues(issues);

    const counts = { error: 0, warn: 0, info: 0, ok: 0 };
    for (const i of issues) {
      if (counts[i.severity] != null) counts[i.severity] += 1;
    }

    return {
      collected_at: new Date().toISOString(),
      extension_version: (() => {
        try {
          return chrome.runtime.getManifest().version;
        } catch (_e) {
          return "unknown";
        }
      })(),
      page_url: pageCtx.page_url || window.location.href,
      page_host: pageHost,
      parish_key: parishKey || gh?.parish_key || "",
      page_type: pageCtx.page_type?.type || pageCtx.page_type || "",
      page_summary: pageCtx.page_type?.summary || "",
      page_archetype: mismatch.archetype?.page_type || "",
      site_intake: _inferSiteIntake(pageCtx, mismatch),
      html_fingerprint: mismatch.htmlScan?.best
        ? {
            id: mismatch.htmlScan.best.id,
            label: mismatch.htmlScan.best.label,
            score: mismatch.htmlScan.best.score,
            pageType: mismatch.htmlScan.best.pageType,
            captureMethod: mismatch.htmlScan.best.captureMethod,
            bestDownloadUrl: mismatch.htmlScan.best.bestDownloadUrl || "",
            advice: mismatch.htmlScan.best.advice || "",
            doNot: mismatch.htmlScan.best.doNot || "",
            downloadUrlCount: Array.isArray(mismatch.htmlScan.allDownloadUrls)
              ? mismatch.htmlScan.allDownloadUrls.length
              : 0,
          }
        : null,
      recipe_steps_local: Array.isArray(pageCtx.recipe_steps) ? pageCtx.recipe_steps.length : 0,
      session_ui_steps: pageCtx.session_ui_steps ?? 0,
      recipe_steps_detail: pageCtx.recipe_steps_detail || pageCtx.recipe_steps || [],
      issues,
      counts,
      pattern_hints,
      github: gh || null,
      toolbar: toolbar.facts || {},
    };
  };

  const _icon = (severity) => {
    if (severity === "error") return "🔴";
    if (severity === "warn") return "🟡";
    if (severity === "info") return "🔵";
    return "🟢";
  };

  const formatReport = (report) => {
    const r = report || {};
    const lines = [
      "Parish Trainer — full diagnosis kit",
      "=================================",
      `Time: ${r.collected_at || "n/a"}`,
      `Extension: ${r.extension_version || "n/a"}`,
      `Page: ${r.page_url || "n/a"}`,
      `Parish key: ${r.parish_key || "(not detected)"}`,
      `Page type: ${r.page_type || "unknown"}${r.page_summary ? ` — ${r.page_summary}` : ""}`,
      r.page_archetype ? `Archetype: ${r.page_archetype}` : null,
      `Local recipe steps: ${r.recipe_steps_local ?? "n/a"} · Session UI steps: ${r.session_ui_steps ?? "n/a"}`,
      "",
    ];

    if (r.html_fingerprint) {
      const hf = r.html_fingerprint;
      lines.push(
        "--- HTML fingerprint (backend page scan) ---",
        `Match: ${hf.label || hf.id || "none"} (score ${hf.score ?? "?"})`,
        hf.captureMethod ? `Capture method: ${hf.captureMethod}` : null,
        hf.bestDownloadUrl ? `Best PDF URL: ${hf.bestDownloadUrl}` : null,
        hf.downloadUrlCount != null ? `PDF URLs found in HTML: ${hf.downloadUrlCount}` : null,
        hf.advice ? `Advice: ${hf.advice}` : null,
        hf.doNot ? `Do NOT: ${hf.doNot}` : null,
        ""
      );
    }

    if (Array.isArray(r.pattern_hints) && r.pattern_hints.length) {
      lines.push("--- Pattern hints (learned from repo) ---");
      for (const h of r.pattern_hints) {
        if (h.kind === "archetype") lines.push(`• ${h.label}: ${h.steps}`);
        else if (h.kind === "similar_parish") {
          lines.push(`• Similar parish: ${h.parish} (${h.pattern || h.flow})`);
        } else if (h.kind === "site_memory" && h.text) {
          lines.push(`• ${h.text.split("\n")[0]}`);
        }
      }
      lines.push("");
    }

    if (r.toolbar) {
      const t = r.toolbar;
      lines.push(
        "--- Extension / toolbar ---",
        `Bridge: ${t.bridge_installed ? "yes" : "no"} · Content: ${t.content_installed ? "yes" : "no"} · Dispatch: ${t.content_dispatch ? "yes" : "no"}`,
        `Toolbar: ${t.toolbar_mode || "missing"} · On screen: ${t.toolbar_on_screen ? "yes" : "no"}`,
        t.last_error ? `Last error: ${t.last_error}` : null,
        ""
      );
    }

    if (r.github?.ok) {
      lines.push(
        "--- GitHub harvest ---",
        `Recipe on GitHub: ${r.github.recipe_found ? "yes" : "no"}`,
        r.github.consecutive_failures != null
          ? `Consecutive failures: ${r.github.consecutive_failures}`
          : null,
        r.github.last_harvest_status ? `Last harvest: ${r.github.last_harvest_status}` : null,
        r.github.last_failure_reason ? `Failure reason: ${r.github.last_failure_reason}` : null,
        ""
      );
    }

    const issueList = Array.isArray(r.issues) ? r.issues : [];
    if (issueList.length === 0) {
      lines.push("✅ No issues detected — extension and recording look healthy.");
    } else {
      lines.push(`Issues found: ${r.counts?.error || 0} error(s), ${r.counts?.warn || 0} warning(s)`);
      lines.push("");
      for (const item of issueList) {
        lines.push(`${_icon(item.severity)} ${item.title}`);
        if (item.detail) lines.push(`   ${item.detail}`);
        if (item.fix) lines.push(`   → Fix: ${item.fix}`);
        lines.push("");
      }
    }

    lines.push("Paste this block to your AI assistant or Franky.");
    lines.push(`Save to repo: parishes/training_diagnosis/${r.parish_key || "PARISH_KEY"}.json`);
    return lines.filter((x) => x != null).join("\n");
  };

  globalThis.ph_recipe_diag = {
    runFullDiagnosis,
    formatReport,
    analyzeSteps: _analyzeSteps,
    buildDiagnosisPayload,
    saveDiagnosisToGithub,
  };
})();
