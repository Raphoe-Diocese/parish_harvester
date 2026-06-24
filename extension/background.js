const SCRIPTABLE_PROTOCOLS = new Set(["http:", "https:"]);
const PROBLEMS_RECIPE_RETRAINED_KEY = "ph_recipe_retrained";
const PH_LAST_DISPATCH_KEY = "ph_last_parish_dispatch";

try {
  importScripts("github_defaults.js", "trainer_inject.js");
} catch (_importErr) {
  // Fallback when loaded in a context without importScripts.
  globalThis.PH_DEFAULT_GH_REPO = "Raphoe-Diocese/parish_harvester";
  globalThis.phResolveGhRepo = (storedRepo) => {
    const value = String(storedRepo || "").trim();
    return value || globalThis.PH_DEFAULT_GH_REPO;
  };
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(["gh_repo"], (data) => {
    if (chrome.runtime.lastError) return;
    if (!String(data?.gh_repo || "").trim()) {
      chrome.storage.local.set({ gh_repo: phResolveGhRepo("") });
    }
  });
  void _warmOpenTabs();
});

chrome.runtime.onStartup.addListener(() => {
  void _warmOpenTabs();
});

async function _warmOpenTabs() {
  let tabs = [];
  try {
    tabs = await chrome.tabs.query({});
  } catch (_err) {
    return;
  }
  for (const tab of tabs) {
    if (!tab?.id || !_tabUrlIsScriptable(tab.url || "")) continue;
    try {
      const ping = await _sendMessageToTab(tab.id, { type: "ph_ping" });
      if (ping.ok) continue;
      await _injectTrainerFiles(tab.id, TRAINER_BRIDGE_FILES);
    } catch (_err) {
      // Non-fatal — popup/click will inject on demand.
    }
  }
}

function _tabUrlIsScriptable(url) {
  if (!url || typeof url !== "string") return false;
  try {
    return SCRIPTABLE_PROTOCOLS.has(new URL(url).protocol);
  } catch (_err) {
    return false;
  }
}

async function _sendMessageToTab(tabId, message) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, message);
    if (response && typeof response === "object" && response.ok === true) {
      return response;
    }
    return { ok: false, error: "no_explicit_ok_from_page" };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function _waitForTabReceiver(tabId, options = {}) {
  const maxAttempts = Number(options.maxAttempts || 30);
  const delayMs = Number(options.delayMs || 200);
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const pong = await _sendMessageToTab(tabId, { type: "ph_ping" });
    if (pong.ok) {
      return true;
    }
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return false;
}

async function _waitForTabBridgeReady(tabId, options = {}) {
  const maxAttempts = Number(options.maxAttempts || 60);
  const delayMs = Number(options.delayMs || 200);
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const ready = await _sendMessageToTab(tabId, { type: "ph_bridge_ready" });
    if (ready.ok) {
      return true;
    }
    if (attempt < maxAttempts - 1) {
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
  return false;
}

const TRAINER_BRIDGE_FILES = globalThis.PH_TRAINER_BRIDGE_FILES || ["bridge_boot.js"];
const TRAINER_HEAVY_FILES = globalThis.PH_TRAINER_HEAVY_FILES || [
  "pattern_library.js",
  "html_fingerprint.js",
  "site_memory.js",
  "parish_pickers.js",
  "copilot.js",
  "toolbar_playbook.js",
  "click-chain.js",
  "isolated.js",
  "content.js",
];

async function _injectTrainerFiles(tabId, files) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      files,
      world: "ISOLATED",
    });
    return { ok: true };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function _injectTrainerScripts(tabId) {
  const ping = await _sendMessageToTab(tabId, { type: "ph_ping" });
  if (ping.ok) {
    const ready = await _waitForTabBridgeReady(tabId, { maxAttempts: 8, delayMs: 150 });
    if (ready) {
      return { ok: true, skipped: true };
    }
    const heavy = await _injectTrainerFiles(tabId, TRAINER_HEAVY_FILES);
    if (heavy.ok) {
      return heavy;
    }
    return heavy;
  }

  const full = await _injectTrainerFiles(tabId, [...TRAINER_BRIDGE_FILES, ...TRAINER_HEAVY_FILES]);
  if (full.ok) {
    return full;
  }

  const bridgeOnly = await _injectTrainerFiles(tabId, TRAINER_BRIDGE_FILES);
  if (!bridgeOnly.ok) {
    return full;
  }
  return await _injectTrainerFiles(tabId, TRAINER_HEAVY_FILES);
}

async function sendToTab(tabId, message, options = {}) {
  const { allowInject = true } = options;
  if (!tabId) {
    return { ok: false, reason: "no_tab_id", error: "No tab ID supplied." };
  }

  let tab;
  try {
    tab = await chrome.tabs.get(tabId);
  } catch (err) {
    return { ok: false, reason: "tab_not_found", error: String(err) };
  }

  if (!_tabUrlIsScriptable(tab?.url || "")) {
    return {
      ok: false,
      reason: "unsupported_url",
      error: "Active tab is not a regular http/https page.",
      tabUrl: tab?.url || "",
    };
  }

  const firstAttempt = await _sendMessageToTab(tabId, message);
  if (firstAttempt.ok) {
    return firstAttempt;
  }

  if (!allowInject) {
    return {
      ok: false,
      reason: "receiver_unavailable",
      error: firstAttempt.error || "Could not reach page receiver.",
      tabUrl: tab?.url || "",
    };
  }

  // Content scripts may still be parsing on slow pages — wait before re-injecting.
  if (await _waitForTabReceiver(tabId, { maxAttempts: 15, delayMs: 200 })) {
    if (await _waitForTabBridgeReady(tabId, { maxAttempts: 45, delayMs: 200 })) {
      const warmAttempt = await _sendMessageToTab(tabId, message);
      if (warmAttempt.ok) {
        return warmAttempt;
      }
    }
  }

  const injected = await _injectTrainerScripts(tabId);
  if (!injected.ok) {
    return {
      ok: false,
      reason: "inject_failed",
      error: injected.error || "Failed to inject extension scripts.",
      tabUrl: tab?.url || "",
    };
  }

  if (!(await _waitForTabReceiver(tabId, { maxAttempts: 30, delayMs: 200 }))) {
    return {
      ok: false,
      reason: "receiver_unavailable",
      error: "Content script bridge did not become ready after injection.",
      tabUrl: tab?.url || "",
    };
  }

  if (!(await _waitForTabBridgeReady(tabId, { maxAttempts: 60, delayMs: 200 }))) {
    return {
      ok: false,
      reason: "receiver_unavailable",
      error: "Parish Trainer loaded but the floating toolbar is not ready yet. Refresh the tab and try again.",
      tabUrl: tab?.url || "",
    };
  }

  const secondAttempt = await _sendMessageToTab(tabId, message);
  if (secondAttempt.ok) {
    return secondAttempt;
  }

  return {
    ok: false,
    reason: "receiver_unavailable",
    error: secondAttempt.error || "Content script did not receive message.",
    tabUrl: tab?.url || "",
  };
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: "mark-bulletin-image",
      title: "Mark as Bulletin Image",
      contexts: ["image"],
    });
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "mark-bulletin-image" && tab?.id) {
    void sendToTab(tab.id, {
      type: "mark_image",
      url: info.srcUrl,
    });
  }
});

chrome.action.onClicked.addListener((tab) => {
  if (!tab?.id) {
    return;
  }
  void sendToTab(tab.id, { type: "toggle_toolbar" });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "open_recording_tab") return false;
  (async () => {
    try {
      const url = String(message.url || "").trim();
      if (!url) {
        sendResponse({ ok: false, error: "No URL to open." });
        return;
      }
      const tab = await chrome.tabs.create({ url, active: true });
      sendResponse({ ok: true, tabId: tab.id || null });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete") return;
  if (!_tabUrlIsScriptable(tab?.url || "")) return;
  (async () => {
    try {
      const ping = await _sendMessageToTab(tabId, { type: "ph_ping" });
      if (!ping.ok) {
        await _injectTrainerFiles(tabId, TRAINER_BRIDGE_FILES);
      }
      const { ph_recording_session: session } = await chrome.storage.local.get([
        "ph_recording_session",
      ]);
      if (!session?.active) return;
      await sendToTab(tabId, { type: "restore_recording_session" }, { allowInject: true });
    } catch (_err) {
      // Non-fatal — user can reopen the toolbar from the popup.
    }
  })();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "dispatch_to_tab") return false;
  (async () => {
    const tabId = Number(message.tabId || 0);
    const payload = message.payload || {};
    const allowInject = message.allowInject !== false;
    const result = await sendToTab(tabId, payload, { allowInject });
    sendResponse(result);
  })().catch((err) => {
    sendResponse({
      ok: false,
      reason: "dispatch_error",
      error: String(err),
    });
  });
  return true;
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "lookup_parish_for_url") return false;
  (async () => {
    try {
      const url = String(message.url || "").trim();
      const hostname = (() => {
        try {
          return new URL(url).hostname.toLowerCase();
        } catch (_e) {
          return "";
        }
      })();
      if (!hostname) {
        sendResponse({ ok: false });
        return;
      }
      const { ph_hostname_map } = await chrome.storage.local.get(["ph_hostname_map"]);
      const parish = ph_hostname_map && typeof ph_hostname_map === "object"
        ? ph_hostname_map[hostname]
        : null;
      if (!parish) {
        sendResponse({ ok: false });
        return;
      }
      const parishKey = String(parish.parish_key || parish.key || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_");
      const inferredKey = (() => {
        try {
          const hostSeg = hostname.replace(/^www\d*\./, "").split(".")[0] || "";
          return hostSeg;
        } catch (_e) {
          return "";
        }
      })();
      if (parishKey && inferredKey && parishKey !== inferredKey) {
        const matches =
          parishKey === inferredKey ||
          inferredKey.includes(parishKey) ||
          parishKey.includes(inferredKey);
        if (!matches) {
          sendResponse({ ok: false, reason: "stale_hostname_map" });
          return;
        }
      }
      sendResponse({ ok: true, parish });
    } catch (_e) {
      sendResponse({ ok: false });
    }
  })();
  return true;
});

const SITE_PATTERNS_PATH = "parishes/site_patterns.json";
const HOST_PROFILES_PATH = "parishes/host_profiles.json";

function _isBadBulletinDownloadUrl(url, startUrl) {
  const text = String(url || "").toLowerCase();
  if (!text) return false;
  if (/\b(bulletin|newsletter)\b/i.test(text)) return false;
  if (
    /privacy|gdpr|gift.?aid|dataentry|financial|diocese|prayer|safeguarding|standingorder|donation/i.test(
      text
    )
  ) {
    return true;
  }
  try {
    const dlHost = new URL(url).hostname.toLowerCase();
    const startHost = new URL(String(startUrl || url)).hostname.toLowerCase();
    if (dlHost !== startHost && !/weekly-bulletins|mdocs-file|\.docx/i.test(text)) {
      return true;
    }
  } catch (_e) {
    // ignore invalid URLs
  }
  return false;
}

function _recipeLooksLikeMdocs(recipe = {}) {
  if (String(recipe.site_type || "").includes("mdocs")) return true;
  if (String(recipe.playbook_type || "").includes("mdocs")) return true;
  return (Array.isArray(recipe.steps) ? recipe.steps : []).some((step) => {
    const blob = `${step?.href || ""} ${step?.url || ""} ${step?.selector || ""}`;
    return /mdocs-file|table\.mdocs|mdocs-download/i.test(blob);
  });
}

function _sanitizeRecipeOnPush(recipe) {
  if (!recipe || !Array.isArray(recipe.steps)) return recipe;
  const out = { ...recipe, steps: recipe.steps.map((s) => (s && typeof s === "object" ? { ...s } : s)) };
  const startUrl = String(out.start_url || "").trim();

  if (/portstewartparish\.(website|ie)/i.test(startUrl)) {
    out.start_url = startUrl.replace(/^https:/i, "http:");
    out.navigation_wait_until = out.navigation_wait_until || "commit";
    out.timeout_ms = Math.max(Number(out.timeout_ms) || 0, 180000);
    out.total_timeout_s = Math.max(Number(out.total_timeout_s) || 0, 420);
    out.site_type = out.site_type || "mdocs_bulletin_list";
    out.playbook_type = out.playbook_type || "mdocs_download_list";
    out.steps = out.steps.map((step) => {
      if (!step || typeof step !== "object") return step;
      const next = { ...step };
      if (next.url) next.url = String(next.url).replace(/^https:\/\/portstewartparish/i, "http://portstewartparish");
      return next;
    });
  }

  if (_recipeLooksLikeMdocs(out)) {
    out.steps = out.steps.filter((s) => String(s?.action || "").toLowerCase() !== "print_to_pdf");
    if (!out.steps.some((s) => String(s?.action || "").toLowerCase() === "download")) {
      out.steps.push({ action: "download", use_captured_url: true, url_pattern: "*.pdf" });
    }
    out.site_type = out.site_type || "mdocs_bulletin_list";
    out.playbook_type = out.playbook_type || "mdocs_download_list";
  }

  out.steps = out.steps.map((step) => {
    if (String(step?.action || "").toLowerCase() !== "image_stack") return step;
    const next = { ...step };
    delete next.urls;
    if (!next.count) next.count = 2;
    return next;
  });

  out.steps = out.steps.map((step) => {
    if (String(step?.action || "").toLowerCase() !== "download") return step;
    const next = { ...step };
    const dlUrl = String(next.url || next.captured_url || "").trim();
    if (dlUrl && _isBadBulletinDownloadUrl(dlUrl, startUrl)) {
      delete next.url;
      delete next.captured_url;
      next.use_captured_url = true;
    }
    return next;
  });

  const hasDropfilesClick = out.steps.some((s) =>
    /mod_downloadlink/i.test(String(s?.selector || ""))
  );
  if (hasDropfilesClick) {
    const badDownloads = out.steps.filter((s) => {
      if (String(s?.action || "").toLowerCase() !== "download") return false;
      const dlUrl = String(s.url || s.captured_url || "").trim();
      return dlUrl && _isBadBulletinDownloadUrl(dlUrl, startUrl);
    });
    if (badDownloads.length > 0) {
      out.steps = out.steps.filter((s) => !badDownloads.includes(s));
    }
    out.site_type = out.site_type || "joomla_dropfiles";
  }

  return out;
}

async function _upsertHostProfile(gh_pat, gh_repo, recipe) {
  const startUrl = String(recipe.start_url || "").trim();
  if (!startUrl) return { ok: false, skipped: true };
  let host = "";
  try {
    host = new URL(startUrl).hostname.toLowerCase();
  } catch (_e) {
    return { ok: false, skipped: true };
  }

  const loaded = await _fetchGithubJsonFile(gh_pat, gh_repo, HOST_PROFILES_PATH);
  if (!loaded.ok) return loaded;

  const profile =
    loaded.data && typeof loaded.data === "object"
      ? loaded.data
      : { _comment: "Per-host fetch profiles.", _default: {}, hosts: {} };
  if (!profile.hosts || typeof profile.hosts !== "object") profile.hosts = {};

  const existing = profile.hosts[host] && typeof profile.hosts[host] === "object"
    ? profile.hosts[host]
    : {};
  const next = { ...existing };
  if (recipe.navigation_wait_until) next.navigation_wait_until = recipe.navigation_wait_until;
  if (recipe.total_timeout_s) next.total_timeout_s = Number(recipe.total_timeout_s);
  if (recipe.timeout_ms) next.navigation_timeout_ms = Number(recipe.timeout_ms);
  if (Number(recipe.observed_load_ms) >= 45000) {
    next.wait_after_load_ms = Math.min(Number(recipe.observed_load_ms), 180000);
  }
  if (/portstewartparish\.(website|ie)/i.test(host)) {
    next.ignore_https_errors = true;
    next.prefer_headful = true;
    next.notes =
      "Use HTTP — HTTPS cert expired. mDocs bulletin table can take 3–5 minutes; PDF is first row Download link.";
  }
  if (/derriaghycatholicparish\.com/i.test(host)) {
    next.navigation_wait_until = next.navigation_wait_until || "commit";
    next.prefer_headful = true;
    if (!next.notes) {
      next.notes = "TLS is fast but domcontentloaded can hang — harvest uses commit navigation.";
    }
  }
  const opNotes = Array.isArray(recipe.operator_notes) ? recipe.operator_notes : [];
  if (opNotes.length && !next.notes) {
    next.notes = opNotes.join(" ").slice(0, 280);
  }

  profile.hosts[host] = next;
  return _putGithubJsonFile(
    gh_pat,
    gh_repo,
    HOST_PROFILES_PATH,
    profile,
    loaded.sha,
    `chore: learn host profile for ${host}`
  );
}

async function _fetchGithubJsonFile(gh_pat, gh_repo, filePath) {
  const apiUrl = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const resp = await fetch(apiUrl, { headers });
  if (resp.status === 404) return { ok: true, data: null, sha: null };
  if (!resp.ok) return { ok: false, error: await _githubApiError(resp) };
  const json = await resp.json();
  try {
    const decoded = decodeURIComponent(
      atob(String(json.content || "").replace(/\n/g, ""))
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return { ok: true, data: JSON.parse(decoded), sha: json.sha || null };
  } catch (err) {
    return { ok: false, error: `Could not parse ${filePath}: ${String(err)}` };
  }
}

async function _putGithubJsonFile(gh_pat, gh_repo, filePath, data, sha, commitMessage) {
  const apiUrl = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(data, null, 2))));
  const body = {
    message: commitMessage,
    content: encoded,
    ...(sha ? { sha } : {}),
  };
  const putResp = await fetch(apiUrl, { method: "PUT", headers, body: JSON.stringify(body) });
  if (!putResp.ok) return { ok: false, error: await _githubApiError(putResp) };
  return { ok: true };
}

async function _upsertSitePattern(gh_pat, gh_repo, parishKey, displayName, recipe, sitePattern) {
  if (!sitePattern?.page || !sitePattern?.recipe) return { ok: false, skipped: true };
  const loaded = await _fetchGithubJsonFile(gh_pat, gh_repo, SITE_PATTERNS_PATH);
  if (!loaded.ok) return loaded;

  const library = loaded.data && typeof loaded.data === "object"
    ? loaded.data
    : { version: 1, description: "", patterns: {}, parishes: {} };
  if (!library.patterns || typeof library.patterns !== "object") library.patterns = {};
  if (!library.parishes || typeof library.parishes !== "object") library.parishes = {};

  const pageFp = sitePattern.page;
  const recipeFp = sitePattern.recipe;
  const combined = `${pageFp.page_type || "unknown"}+${recipeFp.recipe_flow || "mixed"}`;
  const startUrl = String(recipe.start_url || "").trim();
  const existingPattern = library.patterns[combined];
  const existingParish = library.parishes[parishKey];

  library.parishes[parishKey] = {
    page_type: pageFp.page_type,
    recipe_flow: recipeFp.recipe_flow,
    combined_key: combined,
    display_name: displayName || parishKey,
    start_url_host: (() => {
      try { return new URL(startUrl).hostname.toLowerCase(); } catch (_e) { return ""; }
    })(),
    updated: new Date().toISOString().slice(0, 10),
    step_count: recipeFp.step_count || 0,
    playbook_type: String(recipe.playbook_type || "").trim() || undefined,
    operator_notes: Array.isArray(recipe.operator_notes) ? recipe.operator_notes : undefined,
    do_not: Array.isArray(recipe.do_not) ? recipe.do_not : undefined,
    html_fingerprint: sitePattern.html?.fingerprint_id || existingParish?.html_fingerprint,
    html_markers: sitePattern.html?.html_markers || existingParish?.html_markers,
    bulletin_layout: recipe.bulletin_layout || existingParish?.bulletin_layout,
  };

  const recipeAdvice = Array.isArray(recipe.operator_notes) && recipe.operator_notes.length
    ? recipe.operator_notes.join(" ")
    : "";
  const adviceByType = {
    direct_pdf: "Tap Save this PDF — saves the real https:// address for GitHub. Word/docx in the tab title is normal.",
    wp_pdfemb_list: "Click Follow a link → pick the newest dated bulletin → then Get a PDF.",
    pdf_link_list: "Click Find bulletin → Pick newest, or Follow a link to the latest PDF.",
    iframe_viewer: "Click It's in a frame / viewer and choose the bulletin frame.",
    oneweb_docx: "One.com + Google previews: auto-detect newsletter from HTML. Direct download only — never wait for iframes. See Claudy recipe.",
    wix_pdf_viewer: "Use Find bulletin — Wix often hides the real PDF URL in the viewer.",
    wix_html: "Save page as PDF — harvester prints HTML text bulletins (WordPress/Wix) into the mega PDF each Sunday.",
    mdocs_download_list: "mDocs table — click Download on newest row, then capture PDF. Never Save page as PDF.",
    wp_block_file_bulletin: "Permanent bulletin page — harvest scrapes wp-block-file embed (*bulletin*.pdf pattern).",
    stacked_image_bulletin: "Stack top N bulletin images — never hardcode image URLs in the recipe.",
    parish_messenger_embed: "Follow a link → pick newest View Newsletter (ignore Gift Aid / Data Entry PDFs).",
    image_bulletin: "Click Get an image or Pick an image on this page.",
    html_click_chain: "Click Follow a link to reach the bulletin, then Get a PDF or Mark as HTML.",
  };
  library.patterns[combined] = {
    page_type: pageFp.page_type,
    recipe_flow: recipeFp.recipe_flow,
    label: existingPattern?.label || sitePattern.label || pageFp.page_type,
    advice: recipeAdvice || existingPattern?.advice || adviceByType[pageFp.page_type] || "",
    operator_notes: Array.isArray(recipe.operator_notes) ? recipe.operator_notes : existingPattern?.operator_notes,
    do_not: Array.isArray(recipe.do_not) ? recipe.do_not : existingPattern?.do_not,
    html_fingerprint: sitePattern.html?.fingerprint_id || existingPattern?.html_fingerprint,
    html_markers: sitePattern.html?.html_markers || existingPattern?.html_markers,
    bulletin_layout: recipe.bulletin_layout || existingPattern?.bulletin_layout,
    example_parishes: Array.from(new Set([
      ...(Array.isArray(existingPattern?.example_parishes) ? existingPattern.example_parishes : []),
      parishKey,
    ])).slice(0, 12),
    success_count: (Number(existingPattern?.success_count) || 0) + 1,
  };

  return _putGithubJsonFile(
    gh_pat,
    gh_repo,
    SITE_PATTERNS_PATH,
    library,
    loaded.sha,
    `chore: learn site pattern for ${parishKey} (${combined})`
  );
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "fetch_site_patterns") return false;
  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured." });
        return;
      }
      const loaded = await _fetchGithubJsonFile(gh_pat, gh_repo, SITE_PATTERNS_PATH);
      if (!loaded.ok) {
        sendResponse({ ok: false, error: loaded.error });
        return;
      }
      sendResponse({
        ok: true,
        patterns: loaded.data || { version: 1, patterns: {}, parishes: {} },
      });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

// ── GitHub recipe push ────────────────────────────────────────────────────
//
// Handles "push_recipe" messages from content.js / sidepanel.js.
// Reads the stored GitHub PAT and repo from chrome.storage.local, then
// creates or updates the recipe file via the GitHub Contents API.
//
// Required storage keys:
//   gh_pat   — personal access token with repo write scope
//   gh_repo  — owner/repo  (default: Raphoe-Diocese/parish_harvester)
//
// Message shape:
//   { type: "push_recipe", parish_key: string, recipe: object }
//
// Reply shape (sent back via sendResponse):
//   { ok: true,  url: string }   — on success
//   { ok: false, error: string } — on failure

// ── Generic GitHub file fetch ─────────────────────────────────────────────
//
// Message shape: { type: "fetch_github_file", path: string }
// Reply:         { ok: true, content: string } | { ok: false, error: string }

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "fetch_github_file") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured." });
        return;
      }
      const apiUrl = `https://api.github.com/repos/${gh_repo}/contents/${message.path}`;
      const resp = await fetch(apiUrl, {
        headers: {
          Authorization: `token ${gh_pat}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
      });
      if (!resp.ok) {
        sendResponse({ ok: false, error: `GitHub ${resp.status}: ${resp.statusText}` });
        return;
      }
      const data = await resp.json();
      // content is base64-encoded by GitHub API
      const decoded = decodeURIComponent(
        atob(data.content.replace(/\n/g, ""))
          .split("")
          .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
          .join("")
      );
      sendResponse({ ok: true, content: decoded, sha: data.sha });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true;
});

// ── Generic GitHub file push ──────────────────────────────────────────────
//
// Message shape:
//   { type: "push_github_file", path: string, content: string, commitMessage: string }
// Reply: { ok: true, url: string } | { ok: false, error: string }

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "push_github_file") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured." });
        return;
      }

      const filePath = (message.path || "").trim();
      if (!filePath) { sendResponse({ ok: false, error: "No file path provided." }); return; }

      const apiBase = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
      const headers = {
        Authorization: `token ${gh_pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      };

      // Get current SHA (for updates)
      let existingSha = null;
      try {
        const getResp = await fetch(apiBase, { headers });
        if (getResp.ok) { existingSha = (await getResp.json()).sha || null; }
      } catch (_e) { /* new file */ }

      const encoded = btoa(unescape(encodeURIComponent(message.content || "")));
      const body = {
        message: message.commitMessage || `update ${filePath} [from extension]`,
        content: encoded,
        ...(existingSha ? { sha: existingSha } : {}),
      };

      const putResp = await fetch(apiBase, { method: "PUT", headers, body: JSON.stringify(body) });
      if (!putResp.ok) {
        const err = await putResp.json().catch(() => ({}));
        sendResponse({ ok: false, error: `GitHub API error ${putResp.status}: ${err.message || putResp.statusText}` });
        return;
      }

      const result = await putResp.json();
      sendResponse({ ok: true, url: result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}` });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();

  return true;
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "delete_github_file") return false;
  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured." });
        return;
      }
      const filePath = (message.path || "").trim();
      const sha = (message.sha || "").trim();
      if (!filePath || !sha) {
        sendResponse({ ok: false, error: "Path and sha required to delete." });
        return;
      }
      const apiBase = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
      const headers = {
        Authorization: `token ${gh_pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      };
      const delResp = await fetch(apiBase, {
        method: "DELETE",
        headers,
        body: JSON.stringify({
          message: message.commitMessage || `delete ${filePath} [from extension]`,
          sha,
        }),
      });
      if (!delResp.ok) {
        const err = await delResp.json().catch(() => ({}));
        sendResponse({ ok: false, error: `GitHub delete ${delResp.status}: ${err.message || delResp.statusText}` });
        return;
      }
      sendResponse({ ok: true });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

// ── Recipe push ───────────────────────────────────────────────────────────

const _githubApiError = async (resp) => {
  try {
    const body = await resp.json();
    const msg = body.message || resp.statusText;
    if (resp.status === 401) return `GitHub authentication failed — your Personal Access Token may be invalid or expired. Open Settings and re-enter it. (${msg})`;
    if (resp.status === 403) return `GitHub access denied — your PAT may lack 'repo' write scope. Open Settings and check permissions. (${msg})`;
    if (resp.status === 404) return `Repository not found — check the repo name in Settings (expected format: owner/repo). (${msg})`;
    if (resp.status === 409) return `GitHub conflict (${resp.status}): ${msg} — reload the extension and try again.`;
    if (resp.status === 422) return `GitHub validation error: ${msg}`;
    return `GitHub API error ${resp.status}: ${msg}`;
  } catch (_e) {
    return `GitHub API error ${resp.status}: ${resp.statusText}`;
  }
};

function _decodeGithubFileContent(content) {
  if (!content || typeof content !== "string") return null;
  try {
    const decoded = decodeURIComponent(
      atob(content.replace(/\n/g, ""))
        .split("")
        .map((c) => `%${(`00${c.charCodeAt(0).toString(16)}`).slice(-2)}`)
        .join("")
    );
    return JSON.parse(decoded);
  } catch (_e) {
    return null;
  }
}

async function _verifyRecipeOnGithub(apiBase, headers, expectedSteps) {
  try {
    const verifyResp = await fetch(apiBase, { headers });
    if (!verifyResp.ok) {
      return { ok: false, error: `Could not read recipe back (${verifyResp.status})` };
    }
    const verifyData = await verifyResp.json();
    const parsed = _decodeGithubFileContent(verifyData.content);
    if (!parsed || typeof parsed !== "object") {
      return { ok: false, error: "Recipe saved but could not parse GitHub copy" };
    }
    const steps = Array.isArray(parsed.steps) ? parsed.steps : [];
    const last = steps.length ? steps[steps.length - 1] : null;
    const expected = Array.isArray(expectedSteps) ? expectedSteps.length : 0;
    return {
      ok: true,
      stepCount: steps.length,
      lastAction: last && typeof last === "object" ? String(last.action || "").trim() : "",
      recorded_date: String(parsed.recorded_date || "").trim(),
      sha: verifyData.sha || "",
      stepsMatch: steps.length === expected && expected > 0,
      skip: Boolean(parsed.skip),
      needs_retraining: Boolean(parsed.needs_retraining),
    };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

function _looksLikeDatedSelector(selector) {
  const value = String(selector || "");
  if (!value) return false;
  return (
    /\d{1,2}(?:st|nd|rd|th)?[_\s-](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(value) ||
    /\d{1,2}[_-]\d{1,2}[_-]20\d{2}/i.test(value) ||
    /href\*="[^"]*\d{1,2}(?:st|nd|rd|th)?/i.test(value)
  );
}

function _normalizeClickStepsForWeeklyHarvest(recipe) {
  if (!recipe || !Array.isArray(recipe.steps)) return recipe;
  let layout = recipe.bulletin_layout && typeof recipe.bulletin_layout === "object"
    ? { ...recipe.bulletin_layout }
    : null;

  recipe.steps = recipe.steps.map((step) => {
    if (!step || String(step.action || "").toLowerCase() !== "click") return step;
    const next = { ...step };
    // Preserve trainer-recorded selectors — only add generic fallbacks, never rewrite.
    const looksLikePdfList =
      /\[href[^\]]*\.pdf/i.test(String(next.selector || "")) ||
      /\.pdf/i.test(String(next.href || ""));
    if (looksLikePdfList && !next.pick_strategy) {
      next.pick_strategy = "newest_dated";
      next.bulletin_position = next.bulletin_position || "top";
    }
    const fallbacks = new Set(
      Array.isArray(next.fallback_selectors)
        ? next.fallback_selectors.filter((s) => s && String(s).trim())
        : []
    );
    if (looksLikePdfList) {
      fallbacks.add("a[href$='.pdf']");
      fallbacks.add("a[href*='.pdf']");
    }
    if (fallbacks.size) next.fallback_selectors = Array.from(fallbacks);
    if (next.pick_strategy) {
      layout = {
        strategy: next.pick_strategy,
        position: next.bulletin_position || layout?.position || "top",
      };
    }
    return next;
  });

  if (layout) recipe.bulletin_layout = layout;
  return recipe;
}

function _normalizeRecipeTerminalSteps(recipe) {
  if (!recipe || !Array.isArray(recipe.steps)) return recipe;
  const normalized = _normalizeClickStepsForWeeklyHarvest({ ...recipe, steps: [...recipe.steps] });
  const terminalActions = new Set(["download", "image", "image_stack", "html", "print_to_pdf", "crop_screenshot"]);
  let lastTerminalIdx = -1;
  for (let i = 0; i < normalized.steps.length; i += 1) {
    const action = String(normalized.steps[i]?.action || "");
    if (terminalActions.has(action)) lastTerminalIdx = i;
  }
  if (lastTerminalIdx < 0) return normalized;

  const normalizedSteps = normalized.steps.filter((step, idx) => {
    const action = String(step?.action || "");
    if (!terminalActions.has(action)) return true;
    return idx === lastTerminalIdx;
  });
  return { ...normalized, steps: normalizedSteps };
}

function _canonicalDioceseSlug(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "";
  if (raw === "derry" || raw === "derry_diocese" || raw === "derry diocese") return "derry";
  if (
    raw === "down_and_connor" ||
    raw === "down & connor" ||
    raw === "down and connor" ||
    raw === "down_and_connor_diocese" ||
    raw === "down and connor diocese" ||
    raw === "down & connor diocese"
  ) {
    return "down_and_connor";
  }
  if (raw === "raphoe" || raw === "raphoe_diocese" || raw === "raphoe diocese") return "raphoe";
  const normalized = raw.replace(/&/g, "and").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return normalized;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "push_recipe" && message?.type !== "new_parish") return false;

  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured. Open the extension popup → ⚙️ Settings and enter your PAT." });
        return;
      }

      // ── new_parish: create a minimal stub recipe file ────────────────────
      if (message.type === "new_parish") {
        const parish_key = String(message.parish_key || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
        const parish_name = String(message.parish_name || "").trim();
        const diocese = _canonicalDioceseSlug(String(message.diocese || "").trim()) || "unknown";
        const start_url = String(message.start_url || "").trim();

        if (!parish_key) { sendResponse({ ok: false, error: "No parish_key provided." }); return; }
        if (!diocese || diocese === "unknown") { sendResponse({ ok: false, error: "No diocese provided." }); return; }

        const filePath = `parishes/recipes/${diocese}/${parish_key}.json`;
        const apiBase  = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
        const headers  = {
          Authorization: `token ${gh_pat}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        };

        // Refuse to overwrite an existing recipe.
        let existingSha = null;
        try {
          const getResp = await fetch(apiBase, { headers });
          if (getResp.ok) {
            const existing = await getResp.json();
            existingSha = existing.sha || null;
          }
        } catch (_e) {}

        if (existingSha) {
          sendResponse({ ok: false, error: `Recipe already exists at ${filePath}. Use the Push Recipe button to update it.` });
          return;
        }

        const stub = {
          parish_key,
          parish_name: parish_name || parish_key,
          diocese,
          start_url,
          steps: [],
          created_via: "toolbar_new_parish_wizard",
          created_at: new Date().toISOString(),
          recorded_date: new Date().toISOString().slice(0, 10),
        };

        const recipeJson = JSON.stringify(stub, null, 2);
        const encoded    = btoa(unescape(encodeURIComponent(recipeJson)));

        const putResp = await fetch(apiBase, {
          method: "PUT",
          headers,
          body: JSON.stringify({
            message: `chore: add new parish stub ${parish_key} [${diocese}] via toolbar`,
            content: encoded,
          }),
        });

        if (!putResp.ok) {
          sendResponse({ ok: false, error: await _githubApiError(putResp) });
          return;
        }

        const result = await putResp.json();
        const htmlUrl = result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}`;
        sendResponse({ ok: true, url: htmlUrl, filePath });
        return;
      }

      // ── push_recipe: existing handler ────────────────────────────────────
      const key = (message.parish_key || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_");
      if (!key) {
        sendResponse({ ok: false, error: "No parish_key provided." });
        return;
      }

      // Determine diocese subfolder from the recipe being pushed.
      // Falls back to "unknown" if diocese is empty or not provided.
      const recipeDioceseRaw = ((message.recipe || {}).diocese || "").trim();
      const dioceseSubfolder = _canonicalDioceseSlug(recipeDioceseRaw) || "unknown";
      const filePath = `parishes/recipes/${dioceseSubfolder}/${key}.json`;
      const apiBase  = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
      const headers  = {
        Authorization: `token ${gh_pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      };

      // Fetch existing file SHA (needed for updates) and existing recipe.
      let existingSha = null;
      let existingRecipe = null;
      try {
        const getResp = await fetch(apiBase, { headers });
        if (getResp.ok) {
          const existing = await getResp.json();
          existingSha = existing.sha || null;
          try {
            const decoded = decodeURIComponent(
              atob(existing.content.replace(/\n/g, ""))
                .split("")
                .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
                .join("")
            );
            existingRecipe = JSON.parse(decoded);
          } catch (_parseErr) { /* use new recipe as-is */ }
        } else if (getResp.status !== 404) {
          // Non-404 failure fetching the existing file — warn but proceed (treat as new).
          console.warn(`Parish Trainer: could not check existing recipe (${getResp.status})`);
        }
      } catch (_e) { /* file does not exist yet — that's fine */ }

      // Preserve stable fields from the existing recipe when updating.
      const incoming = message.recipe || {};
      const stepsReplaced = Array.isArray(incoming.steps) && incoming.steps.length > 0;
      const recipe = existingRecipe && !stepsReplaced ? {
        ...existingRecipe,
        ...incoming,
        steps: existingRecipe.steps,
        start_url: (incoming.start_url && String(incoming.start_url).trim())
          ? incoming.start_url
          : existingRecipe.start_url,
        display_name: (incoming.display_name && incoming.display_name.trim()) ? incoming.display_name.trim() : existingRecipe.display_name,
        diocese:      (incoming.diocese      && incoming.diocese.trim())      ? incoming.diocese.trim()      : existingRecipe.diocese,
        observed_load_ms: incoming.observed_load_ms ?? existingRecipe.observed_load_ms,
        timeout_ms: incoming.timeout_ms ?? existingRecipe.timeout_ms,
        total_timeout_s: incoming.total_timeout_s ?? existingRecipe.total_timeout_s,
        timeout: incoming.timeout ?? existingRecipe.timeout,
      } : {
        ...(stepsReplaced ? {} : (existingRecipe || {})),
        ...incoming,
        steps: stepsReplaced ? incoming.steps : (existingRecipe?.steps || incoming.steps),
      };
      const normalizedRecipe = _normalizeRecipeTerminalSteps(
        _sanitizeRecipeOnPush(recipe)
      );
      // Retrain push must clear harvest-blocking flags left on the old recipe.
      delete normalizedRecipe.skip;
      delete normalizedRecipe.status;
      delete normalizedRecipe.reason;
      delete normalizedRecipe.dead_reason;
      delete normalizedRecipe.needs_retraining;
      delete normalizedRecipe.placeholder;
      delete normalizedRecipe.auto_generated;
      delete normalizedRecipe.retraining_reason;
      const recipeStatus = String(normalizedRecipe.status || "").toLowerCase();
      if (recipeStatus === "dead_url" || recipeStatus === "inactive" || normalizedRecipe.skip) {
        normalizedRecipe.skip = true;
        if (!normalizedRecipe.reason) {
          normalizedRecipe.reason = normalizedRecipe.dead_reason || "Marked inactive";
        }
      }

      // Set recorded_date to today.
      normalizedRecipe.recorded_date = new Date().toISOString().slice(0, 10);
      normalizedRecipe.parish_key = key;
      const recipeDiocese = (normalizedRecipe.diocese || "").trim();

      const recipeJson = JSON.stringify(normalizedRecipe, null, 2);
      const encoded    = btoa(unescape(encodeURIComponent(recipeJson)));

      const body = {
        message: `chore: update recipe for ${key} [${recipeDiocese || "unknown diocese"}]`,
        content: encoded,
        ...(existingSha ? { sha: existingSha } : {}),
      };

      const putResp = await fetch(apiBase, {
        method: "PUT",
        headers,
        body: JSON.stringify(body),
      });

      if (!putResp.ok) {
        sendResponse({ ok: false, error: await _githubApiError(putResp) });
        return;
      }

      const result = await putResp.json();
      const htmlUrl = result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}`;

      const stepsPreservedFromOld = Boolean(
        existingRecipe
        && Array.isArray(existingRecipe.steps)
        && existingRecipe.steps.length > 0
        && !stepsReplaced
      );
      const githubVerify = await _verifyRecipeOnGithub(
        apiBase,
        headers,
        normalizedRecipe.steps
      );

      // Brief pause so GitHub serves the recipe commit before the harvest workflow checks out main.
      await new Promise((resolve) => setTimeout(resolve, 2500));

      // After saving the recipe, immediately trigger a workflow_dispatch so
      // the Mega PDF is rebuilt for just this parish right away.
      let dispatchOk = false;
      let dispatchError = "";
      try {
        const dispatchResp = await fetch(
          `https://api.github.com/repos/${gh_repo}/actions/workflows/harvest.yml/dispatches`,
          {
            method: "POST",
            headers: {
              Authorization: `token ${gh_pat}`,
              Accept: "application/vnd.github+json",
              "Content-Type": "application/json",
              "X-GitHub-Api-Version": "2022-11-28",
            },
            body: JSON.stringify({
              ref: "main",
              inputs: {
                diocese: "all",
                target_parish: key,
                run_tests: "false",
              },
            }),
          }
        );
        dispatchOk = dispatchResp.status === 204;
        if (!dispatchOk) {
          if (dispatchResp.status === 403) {
            dispatchError = "Your GitHub PAT is missing the 'workflow' scope. Go to github.com/settings/tokens, click your token, tick the 'workflow' checkbox, then regenerate and save it in the extension settings.";
          } else {
            dispatchError = await _githubApiError(dispatchResp);
          }
        }
      } catch (dispatchErr) {
        dispatchError = String(dispatchErr);
      }

      let patternLearned = false;
      let patternLearnError = "";
      let hostProfileLearned = false;
      let hostProfileLearnError = "";
      if (message.site_pattern) {
        try {
          const patternResult = await _upsertSitePattern(
            gh_pat,
            gh_repo,
            key,
            normalizedRecipe.display_name || key,
            normalizedRecipe,
            message.site_pattern
          );
          patternLearned = Boolean(patternResult?.ok);
          if (!patternResult?.ok && !patternResult?.skipped) {
            patternLearnError = patternResult?.error || "Could not save site pattern.";
          }
        } catch (patternErr) {
          patternLearnError = String(patternErr);
        }
      }
      try {
        const hostResult = await _upsertHostProfile(gh_pat, gh_repo, normalizedRecipe);
        hostProfileLearned = Boolean(hostResult?.ok);
        if (!hostResult?.ok && !hostResult?.skipped) {
          hostProfileLearnError = hostResult?.error || "Could not save host profile.";
        }
      } catch (hostErr) {
        hostProfileLearnError = String(hostErr);
      }

      sendResponse({
        ok: true,
        url: htmlUrl,
        filePath,
        updated: !!existingSha,
        dispatchOk,
        dispatchError,
        patternLearned,
        patternLearnError,
        hostProfileLearned,
        hostProfileLearnError,
        stepsPushed: Array.isArray(normalizedRecipe.steps) ? normalizedRecipe.steps.length : 0,
        stepsPreservedFromOld,
        githubVerify,
      });

      try {
        const stored = await chrome.storage.local.get([PROBLEMS_RECIPE_RETRAINED_KEY]);
        const retrained = (stored?.[PROBLEMS_RECIPE_RETRAINED_KEY] && typeof stored[PROBLEMS_RECIPE_RETRAINED_KEY] === "object")
          ? stored[PROBLEMS_RECIPE_RETRAINED_KEY]
          : {};
        if (recipeStatus === "dead_url" || recipeStatus === "inactive" || normalizedRecipe.skip) {
          delete retrained[key];
        } else {
          retrained[key] = normalizedRecipe.recorded_date || new Date().toISOString().slice(0, 10);
        }
        await chrome.storage.local.set({ [PROBLEMS_RECIPE_RETRAINED_KEY]: retrained });
        if (dispatchOk) {
          const dispatchStored = await chrome.storage.local.get([PH_LAST_DISPATCH_KEY]);
          const dispatchMap =
            dispatchStored?.[PH_LAST_DISPATCH_KEY] && typeof dispatchStored[PH_LAST_DISPATCH_KEY] === "object"
              ? { ...dispatchStored[PH_LAST_DISPATCH_KEY] }
              : {};
          dispatchMap[key] = {
            at: Date.now(),
            displayName: normalizedRecipe.display_name || key,
          };
          await chrome.storage.local.set({ [PH_LAST_DISPATCH_KEY]: dispatchMap });
        }
        try {
          chrome.runtime.sendMessage({
            type: "problems_refresh",
            parish_key: key,
            display_name: normalizedRecipe.display_name || key,
            dispatch_at: dispatchOk ? Date.now() : 0,
          });
        } catch (_broadcastErr) {
          // Side panel may be closed — non-fatal.
        }
      } catch (_storeErr) {
        console.warn("Parish Trainer: could not store recipe retrained marker", _storeErr);
      }
    } catch (err) {
      sendResponse({ ok: false, error: `Unexpected error: ${String(err)}. Try reloading the extension.` });
    }
  })();

  return true; // keep message channel open for async response
});

// ── Auto-download PDF detection (Brave / sites that force download) ────────
const _recordingTabIds = new Set();

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type === "recording_tab_active") {
    const tabId = sender?.tab?.id;
    if (tabId) _recordingTabIds.add(tabId);
    return;
  }
  if (message?.type === "recording_tab_inactive") {
    const tabId = sender?.tab?.id;
    if (tabId) _recordingTabIds.delete(tabId);
    return;
  }
});

chrome.downloads.onCreated.addListener((downloadItem) => {
  const tabId = downloadItem.tabId;
  if (!tabId || tabId < 0 || !_recordingTabIds.has(tabId)) return;
  const mime = String(downloadItem.mime || "").toLowerCase();
  const url = String(downloadItem.url || downloadItem.finalUrl || "").trim();
  if (!url) return;
  const looksPdf =
    mime.includes("pdf") ||
    url.toLowerCase().includes(".pdf") ||
    /weekly-bulletins/i.test(url);
  if (!looksPdf) return;
  chrome.tabs.sendMessage(tabId, { type: "auto_download_detected", url }).catch(() => {});
});
