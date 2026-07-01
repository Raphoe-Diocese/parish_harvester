const SCRIPTABLE_PROTOCOLS = new Set(["http:", "https:"]);
const PROBLEMS_RECIPE_RETRAINED_KEY = "ph_recipe_retrained";
const PH_LAST_DISPATCH_KEY = "ph_last_parish_dispatch";

try {
  importScripts("github_defaults.js", "github_recipe_push.js", "trainer_inject.js", "parish_dead_sites.js");
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

const TRAINER_BRIDGE_FILES = globalThis.PH_TRAINER_BRIDGE_FILES || ["bridge_boot.js", "toolbar_diag.js"];
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
  if (changeInfo.status !== "complete" && changeInfo.status !== "loading") return;
  if (!_tabUrlIsScriptable(tab?.url || "")) return;
  (async () => {
    try {
      const fixKey = `ph_fix_now_tab_${tabId}`;
      const fixStored = await chrome.storage.session.get(fixKey);
      const fixNow = fixStored[fixKey];
      if (fixNow) {
        await sendToTab(
          tabId,
          {
            type: "ph_show_toolbar",
            reason: "fix_now",
            parish_key: fixNow.parish_key || "",
            nav_started_at: fixNow.nav_started_at,
          },
          { allowInject: true }
        );
      }

      if (changeInfo.status !== "complete") return;

      const ping = await _sendMessageToTab(tabId, { type: "ph_ping" });
      if (!ping.ok) {
        await _injectTrainerFiles(tabId, TRAINER_BRIDGE_FILES);
      }
      const { ph_recording_session: legacySession, ph_recording_sessions: sessionsMap } =
        await chrome.storage.local.get(["ph_recording_session", "ph_recording_sessions"]);
      let sessionActive = Boolean(legacySession?.active);
      if (!sessionActive && sessionsMap && typeof sessionsMap === "object") {
        const host = (() => {
          try {
            return new URL(tab.url || "").hostname.toLowerCase();
          } catch (_e) {
            return "";
          }
        })();
        if (host && sessionsMap[host]?.active) {
          sessionActive = true;
        }
      }
      if (!sessionActive) return;
      const pageUrl = String(tab.url || "");
      if (
        /et_fb=1/i.test(pageUrl) ||
        /\/wp-admin/i.test(pageUrl) ||
        (/parishpress\.net/i.test(pageUrl) && !/wp-content\/uploads\/parish-bulletins/i.test(pageUrl))
      ) {
        return;
      }
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

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "ph_save_diagnosis") return false;
  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured." });
        return;
      }
      const parishKey = String(message.parish_key || message.diagnosis?.parish_key || "").trim().toLowerCase();
      if (!parishKey) {
        sendResponse({ ok: false, error: "No parish_key provided." });
        return;
      }
      const result = await _upsertTrainingDiagnosis(
        gh_pat,
        gh_repo,
        parishKey,
        message.diagnosis,
        message.source || "manual_diag"
      );
      sendResponse(result);
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "ph_recipe_diag_github") return false;
  (async () => {
    try {
      const url = String(message.url || "").trim();
      let parishKey = String(message.parish_key || "").trim().toLowerCase();
      const stored = await chrome.storage.local.get(["gh_repo", "ph_hostname_map"]);
      const ghRepo = String(stored.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
      const rawBase = `https://raw.githubusercontent.com/${ghRepo}/main`;

      if (!parishKey && url) {
        try {
          const host = new URL(url).hostname.toLowerCase();
          const map =
            stored.ph_hostname_map && typeof stored.ph_hostname_map === "object"
              ? stored.ph_hostname_map
              : {};
          const parish = map[host];
          parishKey = String(
            parish?.parish_key || parish?.key || host.replace(/^www\d*\./, "").split(".")[0] || ""
          )
            .trim()
            .toLowerCase()
            .replace(/\s+/g, "_");
        } catch (_e) {
          parishKey = "";
        }
      }

      let consecutive_failures = 0;
      let last_failure_reason = "";
      let last_harvest_status = "";
      let recipe = null;
      let recipe_found = false;

      try {
        const failResp = await fetch(`${rawBase}/parishes/consecutive_failures.json`);
        if (failResp.ok) {
          const fails = await failResp.json();
          if (parishKey && fails && typeof fails === "object") {
            consecutive_failures = Number(fails[parishKey] || 0);
          }
        }
      } catch (_e) {
        // non-fatal
      }

      try {
        const reportResp = await fetch(`${rawBase}/Bulletins/report.json`);
        if (reportResp.ok) {
          const report = await reportResp.json();
          const downloaded = (report.downloaded || []).find((r) => r.parish === parishKey);
          const failed = (report.failed || []).find((r) => r.parish === parishKey);
          if (downloaded) {
            last_harvest_status = `downloaded (${report.target_date || "recent"})`;
          } else if (failed) {
            last_harvest_status = "failed";
            last_failure_reason = String(failed.reason || failed.error || "").slice(0, 220);
          }
        }
      } catch (_e) {
        // non-fatal
      }

      if (parishKey) {
        for (const dio of ["derry", "down_and_connor", "raphoe", "unknown"]) {
          try {
            const recipeResp = await fetch(
              `${rawBase}/parishes/recipes/${dio}/${parishKey}.json`
            );
            if (recipeResp.ok) {
              recipe = await recipeResp.json();
              recipe_found = true;
              break;
            }
          } catch (_e) {
            // try next diocese
          }
        }
      }

      sendResponse({
        ok: true,
        parish_key: parishKey,
        consecutive_failures,
        last_harvest_status,
        last_failure_reason,
        recipe_found,
        recipe,
      });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

const SITE_PATTERNS_PATH = "parishes/site_patterns.json";
const HOST_PROFILES_PATH = "parishes/host_profiles.json";
const TRAINING_DIAGNOSIS_DIR = "parishes/training_diagnosis";

async function _upsertTrainingDiagnosis(gh_pat, gh_repo, parishKey, diagnosis, source = "extension") {
  const key = String(parishKey || "").trim().toLowerCase();
  if (!key || !diagnosis || typeof diagnosis !== "object") {
    return { ok: false, skipped: true };
  }
  const filePath = `${TRAINING_DIAGNOSIS_DIR}/${key}.json`;
  const loaded = await _fetchGithubJsonFile(gh_pat, gh_repo, filePath);
  if (!loaded.ok && loaded.error) return loaded;

  const prior = loaded.data && typeof loaded.data === "object" ? loaded.data : {};
  const history = Array.isArray(prior.history) ? prior.history.slice(-4) : [];
  if (prior.collected_at) {
    history.push({
      collected_at: prior.collected_at,
      issue_count: Array.isArray(prior.issues) ? prior.issues.length : 0,
      source: prior.source || "extension",
    });
  }

  const payload = {
    parish_key: key,
    collected_at: diagnosis.collected_at || new Date().toISOString(),
    extension_version: diagnosis.extension_version || "",
    source,
    page_url: diagnosis.page_url || "",
    page_type: diagnosis.page_type || "",
    page_archetype: diagnosis.page_archetype || "",
    html_fingerprint: diagnosis.html_fingerprint || null,
    recipe_steps_local: diagnosis.recipe_steps_local ?? 0,
    session_ui_steps: diagnosis.session_ui_steps ?? 0,
    issues: Array.isArray(diagnosis.issues) ? diagnosis.issues : [],
    counts: diagnosis.counts || {},
    pattern_hints: diagnosis.pattern_hints || [],
    site_intake: diagnosis.site_intake || null,
    github: diagnosis.github
      ? {
          recipe_found: Boolean(diagnosis.github.recipe_found),
          consecutive_failures: diagnosis.github.consecutive_failures ?? 0,
          last_failure_reason: diagnosis.github.last_failure_reason || "",
        }
      : null,
    history,
  };

  return _putGithubJsonFile(
    gh_pat,
    gh_repo,
    filePath,
    payload,
    loaded.sha,
    `chore: training diagnosis for ${key} [${source}]`
  );
}

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

function _recipeLooksLikeMdocs(recipe) {
  if (!recipe || typeof recipe !== "object") return false;
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
    out.timeout_ms = Math.max(Number(out.timeout_ms) || 0, 300000);
    out.total_timeout_s = Math.max(Number(out.total_timeout_s) || 0, 900);
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

function _harvestWorkflowDiocese(value) {
  const slug = _canonicalDioceseSlug(value);
  if (!slug) return "all";
  if (slug === "derry") return "derry_diocese";
  if (slug === "raphoe") return "raphoe_diocese";
  if (slug === "down_and_connor") return "down_and_connor";
  return slug;
}

const _RECIPE_DIOCESE_FOLDERS = ["derry", "down_and_connor", "raphoe", "unknown"];

async function _fetchGithubJson(url, headers, timeoutMs = 45000, init = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...init, headers, signal: controller.signal });
    return resp;
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error(`GitHub request timed out after ${Math.round(timeoutMs / 1000)}s — check your connection and PAT.`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/** Find an existing recipe file across diocese folders (fixes wrong-folder pushes). */
async function _locateRecipeOnGithub(gh_pat, gh_repo, key, preferredDiocese) {
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const preferred = _canonicalDioceseSlug(preferredDiocese) || "";

  const tryPath = async (dio, timeoutMs = 10000) => {
    const filePath = `parishes/recipes/${dio}/${key}.json`;
    const apiBase = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
    const getResp = await _fetchGithubJson(apiBase, headers, timeoutMs);
    if (getResp.status === 404) return null;
    if (!getResp.ok) {
      throw new Error(`GitHub ${getResp.status} reading ${filePath}`);
    }
    const existing = await getResp.json();
    let existingRecipe = null;
    try {
      existingRecipe = JSON.parse(_decodeGithubFileContent(existing.content) || "{}");
    } catch (_parseErr) {
      existingRecipe = null;
    }
    return {
      filePath,
      apiBase,
      diocese: dio,
      existingSha: existing.sha || null,
      existingRecipe,
    };
  };

  if (preferred) {
    try {
      const hit = await tryPath(preferred, 12000);
      if (hit) return hit;
    } catch (err) {
      console.warn(`Parish Trainer: preferred recipe path failed (${preferred}):`, err);
    }
  }

  const others = _RECIPE_DIOCESE_FOLDERS.filter((d) => d !== preferred);
  const probes = await Promise.all(
    others.map((dio) => tryPath(dio, 8000).catch((err) => {
      console.warn(`Parish Trainer: locate recipe failed for ${dio}:`, err);
      return null;
    }))
  );
  const found = probes.find(Boolean);
  if (found) return found;

  const dio = preferred || "unknown";
  const filePath = `parishes/recipes/${dio}/${key}.json`;
  return {
    filePath,
    apiBase: `https://api.github.com/repos/${gh_repo}/contents/${filePath}`,
    diocese: dio,
    existingSha: null,
    existingRecipe: null,
  };
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "sanitize_recipe") return false;
  try {
    const recipe = _normalizeRecipeTerminalSteps(_sanitizeRecipeOnPush(message.recipe || {}));
    sendResponse({ ok: true, recipe });
  } catch (err) {
    sendResponse({ ok: false, error: String(err), recipe: message.recipe || {} });
  }
  return false;
});

async function _pushRecipeFollowupWork(message, gh_pat, gh_repo) {
  const key = String(message.parish_key || "").trim().toLowerCase().replace(/\s+/g, "_");
  if (!key) return;
  const normalizedRecipe = message.recipe && typeof message.recipe === "object" ? message.recipe : {};
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const filePath = message.filePath || "";
  const savedDiocese = _canonicalDioceseSlug(normalizedRecipe.diocese) || "unknown";

  if (savedDiocese && savedDiocese !== "unknown" && filePath) {
    for (const strayDio of _RECIPE_DIOCESE_FOLDERS) {
      if (strayDio === savedDiocese) continue;
      const strayPath = `parishes/recipes/${strayDio}/${key}.json`;
      if (strayPath === filePath) continue;
      try {
        const strayApi = `https://api.github.com/repos/${gh_repo}/contents/${strayPath}`;
        const strayGet = await _fetchGithubJson(strayApi, headers, 15000);
        if (!strayGet.ok) continue;
        const strayData = await strayGet.json();
        await _fetchGithubJson(strayApi, headers, 15000, {
          method: "DELETE",
          body: JSON.stringify({
            message: `chore: remove duplicate recipe for ${key} from ${strayDio} (belongs in ${savedDiocese})`,
            sha: strayData.sha,
          }),
        });
      } catch (_strayErr) {
        // Non-fatal.
      }
    }
  }

  if (message.diagnosis_snapshot && typeof message.diagnosis_snapshot === "object") {
    try {
      await _upsertTrainingDiagnosis(
        gh_pat,
        gh_repo,
        key,
        message.diagnosis_snapshot,
        message.diagnosis_source || "push_recipe"
      );
    } catch (_diagErr) {
      // Non-fatal.
    }
  }
  if (message.site_pattern) {
    try {
      await _upsertSitePattern(
        gh_pat,
        gh_repo,
        key,
        normalizedRecipe.display_name || key,
        normalizedRecipe,
        message.site_pattern
      );
    } catch (_patternErr) {
      // Non-fatal.
    }
  }
  try {
    await _upsertHostProfile(gh_pat, gh_repo, normalizedRecipe);
  } catch (_hostErr) {
    // Non-fatal.
  }

  try {
    const stored = await chrome.storage.local.get([PROBLEMS_RECIPE_RETRAINED_KEY]);
    const retrained = (stored?.[PROBLEMS_RECIPE_RETRAINED_KEY] && typeof stored[PROBLEMS_RECIPE_RETRAINED_KEY] === "object")
      ? stored[PROBLEMS_RECIPE_RETRAINED_KEY]
      : {};
    if (normalizedRecipe.skip || ["dead_url", "inactive"].includes(String(normalizedRecipe.status || "").toLowerCase())) {
      delete retrained[key];
    } else {
      retrained[key] = normalizedRecipe.recorded_date || new Date().toISOString().slice(0, 10);
    }
    await chrome.storage.local.set({ [PROBLEMS_RECIPE_RETRAINED_KEY]: retrained });
    if (message.dispatchOk) {
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
        dispatch_at: message.dispatchOk ? Date.now() : 0,
      });
    } catch (_broadcastErr) {
      // Side panel may be closed.
    }
  } catch (_storeErr) {
    console.warn("Parish Trainer: could not store recipe retrained marker", _storeErr);
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "push_recipe_followup_work") return false;
  (async () => {
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      if (!gh_pat) {
        sendResponse({ ok: false, error: "No PAT" });
        return;
      }
      await _pushRecipeFollowupWork(message, gh_pat, phResolveGhRepo(storedGhRepo));
      sendResponse({ ok: true });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true;
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "push_recipe" && message?.type !== "new_parish") return false;

  (async () => {
    let responded = false;
    const reply = (payload) => {
      if (responded) return;
      responded = true;
      try {
        sendResponse(payload);
      } catch (_replyErr) {
        console.warn("Parish Trainer: sendResponse failed (channel closed?)", _replyErr);
      }
    };
    try {
      const { gh_pat, gh_repo: storedGhRepo } = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
      const gh_repo = phResolveGhRepo(storedGhRepo);
      if (!gh_pat) {
        reply({ ok: false, error: "GitHub PAT not configured. Open the extension popup → ⚙️ Settings and enter your PAT." });
        return;
      }

      // ── new_parish: create a minimal stub recipe file ────────────────────
      if (message.type === "new_parish") {
        const parish_key = String(message.parish_key || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
        const parish_name = String(message.parish_name || "").trim();
        const diocese = _canonicalDioceseSlug(String(message.diocese || "").trim()) || "unknown";
        const start_url = String(message.start_url || "").trim();

        if (!parish_key) { reply({ ok: false, error: "No parish_key provided." }); return; }
        if (!diocese || diocese === "unknown") { reply({ ok: false, error: "No diocese provided." }); return; }

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
          reply({ ok: false, error: `Recipe already exists at ${filePath}. Use the Push Recipe button to update it.` });
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
          reply({ ok: false, error: await _githubApiError(putResp) });
          return;
        }

        const result = await putResp.json();
        const htmlUrl = result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}`;
        reply({ ok: true, url: htmlUrl, filePath });
        return;
      }

      // ── push_recipe: existing handler ────────────────────────────────────
      const key = (message.parish_key || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_");
      if (!key) {
        reply({ ok: false, error: "No parish_key provided." });
        return;
      }

      // Locate existing recipe across diocese folders (user may have picked wrong diocese).
      const recipeDioceseRaw = ((message.recipe || {}).diocese || "").trim();
      const located = globalThis.phGithubRecipePush
        ? await globalThis.phGithubRecipePush.locateRecipe(gh_pat, gh_repo, key, recipeDioceseRaw)
        : await _locateRecipeOnGithub(gh_pat, gh_repo, key, recipeDioceseRaw);
      const filePath = located.filePath;
      const apiBase = located.apiBase;
      const existingSha = located.existingSha;
      const existingRecipe = located.existingRecipe;
      const headers = {
        Authorization: `token ${gh_pat}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      };

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
      const markAsDead = Boolean(message.mark_dead) ||
        ["dead_url", "inactive"].includes(String(incoming.status || "").toLowerCase()) ||
        incoming.skip === true;
      const deadStatus = ["dead_url", "inactive"].includes(String(incoming.status || "").toLowerCase())
        ? String(incoming.status).toLowerCase()
        : "dead_url";
      const deadReason = String(incoming.dead_reason || incoming.reason || "Marked inactive").trim();
      // Retrain push must clear harvest-blocking flags left on the old recipe.
      delete normalizedRecipe.skip;
      delete normalizedRecipe.status;
      delete normalizedRecipe.reason;
      delete normalizedRecipe.dead_reason;
      delete normalizedRecipe.needs_retraining;
      delete normalizedRecipe.placeholder;
      delete normalizedRecipe.auto_generated;
      delete normalizedRecipe.retraining_reason;
      if (markAsDead) {
        normalizedRecipe.status = deadStatus;
        normalizedRecipe.skip = true;
        normalizedRecipe.dead_reason = deadReason || "Marked inactive";
        normalizedRecipe.reason = normalizedRecipe.dead_reason;
      }

      // Set recorded_date to today.
      normalizedRecipe.recorded_date = new Date().toISOString().slice(0, 10);
      normalizedRecipe.parish_key = key;
      if (located.diocese) {
        normalizedRecipe.diocese = located.diocese;
      }
      const recipeDiocese = (normalizedRecipe.diocese || "").trim();

      const recipeJson = JSON.stringify(normalizedRecipe, null, 2);
      const encoded    = btoa(unescape(encodeURIComponent(recipeJson)));

      const body = {
        message: `chore: update recipe for ${key} [${recipeDiocese || "unknown diocese"}]`,
        content: encoded,
        branch: "main",
        ...(existingSha ? { sha: existingSha } : {}),
      };

      let putResp = await _fetchGithubJson(
        apiBase,
        headers,
        30000,
        { method: "PUT", body: JSON.stringify(body) }
      );
      if (putResp.status === 422 && !body.sha) {
        try {
          const refetch = await _fetchGithubJson(apiBase, headers, 15000);
          if (refetch.ok) {
            const refData = await refetch.json();
            if (refData?.sha) {
              body.sha = refData.sha;
              putResp = await _fetchGithubJson(
                apiBase,
                headers,
                30000,
                { method: "PUT", body: JSON.stringify(body) }
              );
            }
          }
        } catch (_retryErr) {
          // fall through
        }
      }
      if (!putResp.ok) {
        reply({ ok: false, error: await _githubApiError(putResp) });
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

      // Reply immediately after GitHub save — harvest dispatch / diagnosis can take 30s+.
      const tabId = sender?.tab?.id;
      reply({
        ok: true,
        url: htmlUrl,
        filePath,
        updated: !!existingSha,
        dispatchOk: false,
        dispatchPending: !markAsDead && !message.mark_dead,
        stepsPushed: Array.isArray(normalizedRecipe.steps) ? normalizedRecipe.steps.length : 0,
        stepsPreservedFromOld,
      });

      // Best-effort: remove duplicate recipe copies in wrong diocese folders (after UI unblocks).
      const savedDiocese = _canonicalDioceseSlug(normalizedRecipe.diocese || located.diocese) || located.diocese;
      if (savedDiocese && savedDiocese !== "unknown") {
        void (async () => {
          for (const strayDio of _RECIPE_DIOCESE_FOLDERS) {
            if (strayDio === savedDiocese) continue;
            const strayPath = `parishes/recipes/${strayDio}/${key}.json`;
            if (strayPath === filePath) continue;
            try {
              const strayApi = `https://api.github.com/repos/${gh_repo}/contents/${strayPath}`;
              const strayGet = await _fetchGithubJson(strayApi, headers, 15000);
              if (!strayGet.ok) continue;
              const strayData = await strayGet.json();
              await _fetchGithubJson(strayApi, headers, 15000, {
                method: "DELETE",
                body: JSON.stringify({
                  message: `chore: remove duplicate recipe for ${key} from ${strayDio} (belongs in ${savedDiocese})`,
                  sha: strayData.sha,
                }),
              });
            } catch (_strayErr) {
              // Non-fatal.
            }
          }
        })();
      }

      const githubVerify = await _verifyRecipeOnGithub(
        apiBase,
        headers,
        normalizedRecipe.steps
      );

      // Brief pause so GitHub serves the recipe commit before the harvest workflow checks out main.
      await new Promise((resolve) => setTimeout(resolve, markAsDead ? 0 : 2500));

      // After saving the recipe, immediately trigger a workflow_dispatch so
      // the Mega PDF is rebuilt for just this parish right away.
      let dispatchOk = false;
      let dispatchError = "";
      if (!markAsDead && !message.mark_dead) {
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
                  diocese: _harvestWorkflowDiocese(savedDiocese),
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
      }

      let patternLearned = false;
      let patternLearnError = "";
      let hostProfileLearned = false;
      let hostProfileLearnError = "";
      let diagnosisSaved = false;
      let diagnosisSaveError = "";
      if (message.diagnosis_snapshot && typeof message.diagnosis_snapshot === "object") {
        try {
          const diagResult = await _upsertTrainingDiagnosis(
            gh_pat,
            gh_repo,
            key,
            message.diagnosis_snapshot,
            message.diagnosis_source || "push_recipe"
          );
          diagnosisSaved = Boolean(diagResult?.ok);
          if (!diagResult?.ok && !diagResult?.skipped) {
            diagnosisSaveError = diagResult?.error || "Could not save training diagnosis.";
          }
        } catch (diagErr) {
          diagnosisSaveError = String(diagErr);
        }
      }
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

      const followup = {
        type: "push_recipe_followup",
        parish_key: key,
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
        diagnosisSaved,
        diagnosisSaveError,
        stepsPushed: Array.isArray(normalizedRecipe.steps) ? normalizedRecipe.steps.length : 0,
        stepsPreservedFromOld,
        githubVerify,
      };
      if (tabId) {
        try {
          await chrome.tabs.sendMessage(tabId, followup);
        } catch (_tabMsgErr) {
          // Tab may have navigated — non-fatal.
        }
      }

      try {
        const stored = await chrome.storage.local.get([PROBLEMS_RECIPE_RETRAINED_KEY]);
        const retrained = (stored?.[PROBLEMS_RECIPE_RETRAINED_KEY] && typeof stored[PROBLEMS_RECIPE_RETRAINED_KEY] === "object")
          ? stored[PROBLEMS_RECIPE_RETRAINED_KEY]
          : {};
        if (deadStatus === "dead_url" || deadStatus === "inactive" || normalizedRecipe.skip) {
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
      reply({ ok: false, error: `Unexpected error: ${String(err)}. Try reloading the extension.` });
    }
  })();

  return true; // keep message channel open for async response
});

// ── Auto-download PDF detection (Brave / sites that force download) ────────
async function _pushDeadRecipeFile(gh_pat, gh_repo, parishKey, recipe) {
  const key = String(parishKey || "").trim().toLowerCase().replace(/\s+/g, "_");
  const dioceseSubfolder = _canonicalDioceseSlug(String(recipe.diocese || "").trim()) || "unknown";
  const filePath = `parishes/recipes/${dioceseSubfolder}/${key}.json`;
  const apiBase = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
  };

  let existingSha = null;
  try {
    const getResp = await fetch(apiBase, { headers });
    if (getResp.ok) {
      const existing = await getResp.json();
      existingSha = existing.sha || null;
    }
  } catch (_e) { /* new file */ }

  const deadRecipe = {
    ...recipe,
    parish_key: key,
    status: "dead_url",
    skip: true,
    recorded_date: new Date().toISOString().slice(0, 10),
    steps: [],
  };
  const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(deadRecipe, null, 2))));
  const putResp = await fetch(apiBase, {
    method: "PUT",
    headers,
    body: JSON.stringify({
      message: `chore: mark ${key} as dead website [from extension]`,
      content: encoded,
      ...(existingSha ? { sha: existingSha } : {}),
    }),
  });
  if (!putResp.ok) return { ok: false, error: await _githubApiError(putResp) };
  const result = await putResp.json();
  const htmlUrl = result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${filePath}`;
  return { ok: true, url: htmlUrl };
}

  const apiUrl = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const resp = await fetch(apiUrl, { headers });
  if (resp.status === 404) return { ok: true, text: null, sha: null };
  if (!resp.ok) return { ok: false, error: await _githubApiError(resp) };
  const json = await resp.json();
  try {
    const decoded = decodeURIComponent(
      atob(String(json.content || "").replace(/\n/g, ""))
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
    return { ok: true, text: decoded, sha: json.sha || null };
  } catch (err) {
    return { ok: false, error: `Could not decode ${filePath}: ${String(err)}` };
  }
}

async function _putGithubTextFile(gh_pat, gh_repo, filePath, text, sha, commitMessage) {
  const apiUrl = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
  const headers = {
    Authorization: `token ${gh_pat}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const encoded = btoa(unescape(encodeURIComponent(String(text || ""))));
  const body = {
    message: commitMessage,
    content: encoded,
    ...(sha ? { sha } : {}),
  };
  const putResp = await fetch(apiUrl, { method: "PUT", headers, body: JSON.stringify(body) });
  if (!putResp.ok) return { ok: false, error: await _githubApiError(putResp) };
  return { ok: true };
}

async function _resolveParishFromUrl(gh_pat, gh_repo, tabUrl) {
  const deadApi = globalThis.PH_DEAD_SITES;
  if (!deadApi || !tabUrl) return null;
  const evidenceFiles = deadApi.PH_EVIDENCE_FILES || {};
  const allParishes = [];
  for (const [diocese, path] of Object.entries(evidenceFiles)) {
    const loaded = await _fetchGithubTextFile(gh_pat, gh_repo, path);
    if (!loaded.ok || !loaded.text) continue;
    allParishes.push(...deadApi.phParseEvidence(loaded.text, diocese));
  }
  return deadApi.phMatchParishFromUrl(tabUrl, allParishes);
}

const _phStorageGet = (keys) => new Promise((resolve) => {
  chrome.storage.local.get(keys, (result) => resolve(result || {}));
});
const _phStorageSet = (payload) => new Promise((resolve) => {
  chrome.storage.local.set(payload, () => resolve(!chrome.runtime?.lastError));
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const type = message?.type;
  if (
    type !== "mark_parish_dead" &&
    type !== "remove_dead_parish_local" &&
    type !== "list_dead_parishes" &&
    type !== "resolve_parish_from_url"
  ) {
    return false;
  }

  (async () => {
    const deadApi = globalThis.PH_DEAD_SITES;
    if (!deadApi) {
      sendResponse({ ok: false, error: "Dead-site module not loaded." });
      return;
    }

    if (type === "list_dead_parishes") {
      const list = await deadApi.phGetDeadParishes(_phStorageGet);
      sendResponse({ ok: true, parishes: list });
      return;
    }

    if (type === "remove_dead_parish_local") {
      const list = await deadApi.phRemoveDeadParishLocal(_phStorageGet, _phStorageSet, message.parish_key);
      sendResponse({ ok: true, parishes: list });
      return;
    }

    const { gh_pat, gh_repo: storedGhRepo } = await _phStorageGet(["gh_pat", "gh_repo"]);
    const gh_repo = phResolveGhRepo(storedGhRepo);

    if (type === "resolve_parish_from_url") {
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured." });
        return;
      }
      const parish = await _resolveParishFromUrl(gh_pat, gh_repo, String(message.url || "").trim());
      sendResponse({ ok: true, parish });
      return;
    }

    if (type === "mark_parish_dead") {
      if (!gh_pat) {
        sendResponse({ ok: false, error: "GitHub PAT not configured. Open popup → GitHub Settings." });
        return;
      }

      const parishKey = String(message.parish_key || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
      const displayName = String(message.display_name || message.name || parishKey).trim();
      const diocese = String(message.diocese || "").trim();
      const startUrl = String(message.url || message.start_url || "").trim();
      const reason = String(message.reason || "Website gone or unreachable — marked dead from extension.").trim();
      const disableEvidence = message.disable_evidence !== false;

      if (!parishKey) {
        sendResponse({ ok: false, error: "No parish_key provided." });
        return;
      }

      const dioceseSlug = _canonicalDioceseSlug(diocese) || "unknown";
      const recipe = {
        parish_key: parishKey,
        display_name: displayName,
        diocese,
        start_url: startUrl,
        status: "dead_url",
        skip: true,
        dead_reason: reason,
        reason,
        steps: [],
      };

      const pushResult = await _pushDeadRecipeFile(gh_pat, gh_repo, parishKey, recipe);

      if (!pushResult?.ok) {
        sendResponse({ ok: false, error: pushResult?.error || "Failed to push dead recipe." });
        return;
      }

      let evidenceDisabled = false;
      let evidenceWarning = "";
      if (disableEvidence && diocese && displayName) {
        const evidencePath = deadApi.PH_EVIDENCE_FILES[diocese];
        if (evidencePath) {
          const loaded = await _fetchGithubTextFile(gh_pat, gh_repo, evidencePath);
          if (loaded.ok && loaded.text) {
            const disabled = deadApi.phDisableParishInEvidence(loaded.text, displayName);
            if (disabled.ok) {
              const put = await _putGithubTextFile(
                gh_pat,
                gh_repo,
                evidencePath,
                disabled.text,
                loaded.sha,
                `evidence: disable ${displayName} [dead site from extension]`
              );
              evidenceDisabled = Boolean(put.ok);
              if (!put.ok) evidenceWarning = put.error || "Evidence file not updated.";
            } else {
              evidenceWarning = disabled.error || "Could not find parish in evidence file.";
            }
          } else {
            evidenceWarning = loaded.error || "Could not load evidence file.";
          }
        }
      }

      const parishes = await deadApi.phUpsertDeadParish(_phStorageGet, _phStorageSet, {
        key: parishKey,
        name: displayName,
        diocese,
        url: startUrl,
        reason,
        evidence_disabled: evidenceDisabled,
      });

      sendResponse({
        ok: true,
        recipe_url: pushResult.url,
        evidence_disabled: evidenceDisabled,
        evidence_warning: evidenceWarning,
        parishes,
      });
    }
  })();

  return true;
});

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
