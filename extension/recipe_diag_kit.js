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
        chrome.runtime.sendMessage(
          { type: "ph_recipe_diag_github", url: pageUrl, parish_key: parishKey || "" },
          (res) => {
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

  const runFullDiagnosis = async () => {
    const pageCtx = _pageContext();
    const pageHost = _hostname(pageCtx.page_url || window.location.href);
    const parishKey = String(pageCtx.parish_key || "").trim();

    const toolbar = await _checkToolbar();
    let issues = [
      ..._checkExtensionStack(),
      ...toolbar.issues,
      ...(await _checkRecordingSession(pageHost)),
      ..._analyzeSteps(pageCtx.recipe_steps || [], pageCtx),
    ];

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
      recipe_steps_local: Array.isArray(pageCtx.recipe_steps) ? pageCtx.recipe_steps.length : 0,
      issues,
      counts,
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
      `Local recipe steps: ${r.recipe_steps_local ?? "n/a"}`,
      "",
    ];

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
    return lines.filter((x) => x != null).join("\n");
  };

  globalThis.ph_recipe_diag = {
    runFullDiagnosis,
    formatReport,
    analyzeSteps: _analyzeSteps,
  };
})();
