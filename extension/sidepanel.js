const statusEl = document.getElementById("status");

function setStatus(text, type) {
  statusEl.textContent = text;
  statusEl.className = type || "ok";
  statusEl.dataset.status =
    type === "err"
      ? "error"
      : (type === "warn" ? "warning" : (String(text || "").startsWith("⏳") ? "pending" : "success"));
}

const _spPanels = {
  trainer: {
    tab: document.getElementById("tab-trainer"),
    panel: document.getElementById("panel-trainer"),
  },
  problems: {
    tab: document.getElementById("tab-problems"),
    panel: document.getElementById("panel-problems"),
  },
};

const PROBLEMS_FIX_VISITED_KEY = "ph_problems_fix_visited";
const PROBLEMS_RECIPE_RETRAINED_KEY = "ph_recipe_retrained";
const PROBLEMS_UI_KEY = "ph_problems_ui";
const PH_LAST_DISPATCH_KEY = "ph_last_parish_dispatch";
const PROBLEMS_DEFAULT_DIOCESE = "Raphoe Diocese";

async function _problemsBeginFixNowSession(startUrl, parishKey) {
  const navStartedAt = Date.now();
  let hostname = "";
  try {
    hostname = new URL(startUrl).hostname.toLowerCase();
  } catch (_e) {
    return { navStartedAt, hostname: "" };
  }

  const stored = await chrome.storage.local.get(["ph_recording_sessions"]);
  const sessions =
    stored.ph_recording_sessions && typeof stored.ph_recording_sessions === "object"
      ? { ...stored.ph_recording_sessions }
      : {};
  sessions[hostname] = {
    active: true,
    hostname,
    startUrl,
    steps: [],
    updatedAt: navStartedAt,
    fixNow: true,
    parish_key: parishKey,
  };
  await chrome.storage.local.set({
    ph_recording_sessions: sessions,
    ph_recording_session: { active: false, steps: [], updatedAt: navStartedAt },
  });
  return { navStartedAt, hostname };
}

function _scheduleFixNowToolbar(tabId, parishKey, navStartedAt, startUrl) {
  if (!tabId) return;
  chrome.runtime.sendMessage({
    type: "schedule_fix_now_toolbar",
    tabId,
    parish_key: parishKey,
    nav_started_at: navStartedAt,
    url: startUrl,
  });
}

async function _problemsRepoUrls() {
  const cfg = await chrome.storage.local.get(["gh_repo"]);
  const repo = phResolveGhRepo(cfg?.gh_repo);
  const base = `https://raw.githubusercontent.com/${repo}/main`;
  return {
    reportUrl: `${base}/Bulletins/report.json`,
    statusUrl: `${base}/parishes/parish_status.json`,
    failuresUrl: `${base}/parishes/consecutive_failures.json`,
    repo,
  };
}

window._spSetStatus = setStatus;

function _spShowPanel(name) {
  for (const [key, refs] of Object.entries(_spPanels)) {
    const active = key === name;
    refs.tab.classList.toggle("active", active);
    refs.panel.classList.toggle("active", active);
  }
  if (name === "problems") {
    void loadProblemsDashboard();
  }
  void _updateDriveTrainerWarning();
}

const _spStorageGet = (keys) => new Promise((resolve) => {
  chrome.storage.local.get(keys, (result) => resolve(result || {}));
});

const _spStorageSet = (payload) => new Promise((resolve) => {
  chrome.storage.local.set(payload, () => resolve(!chrome.runtime?.lastError));
});

const _clearElement = (el) => {
  if (el) el.replaceChildren();
};

async function withActiveTab(callback) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    setStatus("No active tab.", "err");
    return;
  }
  callback(tab);
}

function _dispatchErrorText(result) {
  if (!result) return "Could not communicate with page. Try refreshing.";
  if (result.reason === "unsupported_url") {
    return "This tab cannot be scripted. Open a normal http/https page.";
  }
  if (result.reason === "inject_failed") {
    return "Page script bridge failed to load. Refresh the page and try again.";
  }
  if (result.reason === "receiver_unavailable") {
    return "Page bridge not responding. Refresh the tab and try again.";
  }
  return result.error || "Could not communicate with page.";
}

async function sendToActiveTab(message, successText) {
  console.log("[PH-SAVE]", { action: message?.type || "unknown", request: message, phase: "request" });
  await withActiveTab((tab) => {
    if (!/^https?:\/\//i.test(tab.url || "")) {
      setStatus("This tab is not scriptable. Open a normal http/https page.", "err");
      return;
    }
    chrome.runtime.sendMessage({
      type: "dispatch_to_tab",
      tabId: tab.id,
      payload: message,
      allowInject: true,
    }, (result) => {
      console.log("[PH-SAVE]", { action: message?.type || "unknown", request: message, response: result || null });
      if (chrome.runtime.lastError) {
        setStatus(`Could not communicate with extension background: ${chrome.runtime.lastError.message}`, "err");
        return;
      }
      if (!result?.ok) {
        setStatus(`❌ ${result?.reason || _dispatchErrorText(result)}`, "err");
        return;
      }
      setStatus(result?.reason ? `✅ ${result.reason}` : successText, "ok");
    });
  });
}

// ── Guided Mode wizard ────────────────────────────────────────────────────

document.getElementById("wizard-pdf").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_file" }, "✅ Bulletin PDF URL recorded.");
});

document.getElementById("wizard-image").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_crop" },
    "🖼️ Draw a rectangle around the bulletin image…"
  );
});

document.getElementById("wizard-link").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_pick_link" },
    "🎯 Hover over a link and click to select it…"
  );
});

document.getElementById("wizard-pick-image").addEventListener("click", () => {
  void sendToActiveTab(
    { type: "start_pick_image" },
    "🖼️ Hover over an image and click to select it…"
  );
});

// ── Advanced / fallback buttons ───────────────────────────────────────────

document.getElementById("mark-element").addEventListener("click", () => {
  void sendToActiveTab({ type: "mark_element" }, "✅ Element marked.");
});

document.getElementById("crop-btn").addEventListener("click", async () => {
  await sendToActiveTab(
    { type: "start_crop" },
    "Click and drag to select the bulletin area…"
  );
});

// ── GitHub Settings ────────────────────────────────────────────────────────

// Load saved settings on open
chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => {
  const patInput  = document.getElementById("gh-pat");
  const repoInput = document.getElementById("gh-repo");
  if (patInput  && r.gh_pat)  patInput.value  = r.gh_pat;
  if (repoInput) repoInput.value = phResolveGhRepo(r.gh_repo);
});

document.getElementById("gh-save").addEventListener("click", () => {
  const pat  = (document.getElementById("gh-pat").value  || "").trim();
  const repo = phResolveGhRepo((document.getElementById("gh-repo").value || "").trim());
  const status = document.getElementById("gh-save-status");
  chrome.storage.local.set({
    gh_pat: pat,
    gh_repo: repo,
  }, () => {
    if (chrome.runtime.lastError) {
      status.textContent = `❌ Save failed: ${chrome.runtime.lastError.message}`;
      status.style.color = "#fca5a5";
      setTimeout(() => { status.textContent = ""; }, 4000);
      return;
    }
    if (!pat) {
      status.textContent = "⚠️ Saved. Add your GitHub PAT to enable recipe push.";
      status.style.color = "#fde68a";
    } else {
      status.textContent = `✅ Settings saved for ${repo}.`;
      status.style.color = "#86efac";
    }
    if (pat && repo) {
      const details = document.getElementById("parish-dir-details");
      if (details?.open) loadParishDirectory();
    }
    setTimeout(() => { status.textContent = ""; }, 3000);
  });
});




// ── Parish Directory ───────────────────────────────────────────────────────
//
// Shows all parishes grouped by diocese with:
//   • Click name  → open the parish bulletin page
//   • ✏️  button  → edit the # page: URL in the evidence file
//   • ☠️  button  → push a dead recipe to GitHub
//   • exclude ☑   → add / remove the parish key from parishes/mega_excludes.json

const PD_EVIDENCE_FILES_FALLBACK = {
  "Derry Diocese":         "parishes/derry_diocese_bulletin_urls.txt",
  "Down & Connor Diocese": "parishes/down_and_connor_bulletin_urls.txt",
  "Raphoe Diocese":        "parishes/raphoe_diocese_bulletin_urls.txt",
};
let PD_EVIDENCE_FILES = { ...PD_EVIDENCE_FILES_FALLBACK };
const DIOCESES_JSON_PATH = "parishes/dioceses.json";
const MEGA_EXCLUDES_PATH = "parishes/mega_excludes.json";
const MANUAL_OVERRIDES_PATH = "parishes/manual_overrides.json";
const LAST_INCLUDED_PATH = "parishes/last_included.json";
const CONSECUTIVE_FAILURES_PATH = "parishes/consecutive_failures.json";
const STALE_BULLETINS_PATH = "parishes/stale_bulletins.json";
const CURRENT_BULLETINS_PATH_PREFIX = "Bulletins/current";
const _pdParishDetailsCache = {}; // key -> details payload

// Replicate Python's _url_to_key logic
function _pdUrlToKey(url, headerName = "") {
  try {
    const parsed = new URL(url);
    let hostname = parsed.hostname.toLowerCase().replace(/^www\d*\./, "");
    if (/\bi\d+\.wp\.com\b/.test(hostname)) {
      const parts = parsed.pathname.replace(/^\//, "").split("/");
      if (parts.length > 0) {
        const real = parts[0].toLowerCase().replace(/^www\d*\./, "");
        const segs = real.split(".");
        if (segs.length >= 2) return segs[0];
      }
    }
    if (hostname === "filesafe.space" || hostname.endsWith(".filesafe.space") || hostname === "google.com" || hostname.endsWith(".google.com")) {
      if (headerName) return headerName.toLowerCase().split("(")[0].trim().replace(/[^a-z0-9]/g, "");
      return hostname.split(".")[0].replace(/[^a-z0-9]/g, "");
    }
    return hostname.split(".")[0] || hostname;
  } catch (_e) {
    return "";
  }
}

function _pdParseEvidence(text, dioceseName) {
  const parishes = [];
  let cur = null;

  for (const rawLine of text.split("\n")) {
    const line = rawLine.trim();
    const nameMatch = line.match(/^#\s*---\s*(.+?)\s*---\s*$/);
    if (nameMatch) {
      if (cur) parishes.push(cur);
      cur = { name: nameMatch[1], diocese: dioceseName, pageUrl: null, keyOverride: null, bulletinUrls: [], disabled: false, key: null };
      continue;
    }
    if (!cur) continue;
    const pageMatch = line.match(/^#\s*page:\s*(.+)$/i);
    if (pageMatch) { cur.pageUrl = pageMatch[1].trim(); continue; }
    const keyMatch = line.match(/^#\s*key:\s*(.+)$/i);
    if (keyMatch) { cur.keyOverride = keyMatch[1].trim(); continue; }
    if (/^#\s*DISABLED/i.test(line)) { cur.disabled = true; }
    if (line.startsWith("#") || !line) continue;
    cur.bulletinUrls.push(line);
  }
  if (cur) parishes.push(cur);

  for (const p of parishes) {
    const firstUrl = p.bulletinUrls[0] || p.pageUrl || "";
    p.key = p.keyOverride || (firstUrl ? _pdUrlToKey(firstUrl, p.name) : "");
  }
  return parishes;
}

// Update the # page: URL for a named parish in an evidence file text blob
function _pdUpdatePageUrl(fileText, parishName, newUrl) {
  const lines = fileText.split("\n");
  const escaped = parishName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headerRe = new RegExp(`^#\\s*---\\s*${escaped}\\s*---`, "i");
  let inSection = false;
  let replaced  = false;
  let headerIdx = -1;

  for (let i = 0; i < lines.length; i++) {
    if (headerRe.test(lines[i].trim())) {
      inSection = true; headerIdx = i; continue;
    }
    if (inSection) {
      if (/^#\s*---/.test(lines[i].trim())) {
        if (!replaced && headerIdx >= 0) { lines.splice(headerIdx + 1, 0, `# page: ${newUrl}`); replaced = true; }
        break;
      }
      if (/^#\s*page:/i.test(lines[i].trim())) {
        lines[i] = `# page: ${newUrl}`; replaced = true; break;
      }
    }
  }
  if (!replaced && headerIdx >= 0) lines.splice(headerIdx + 1, 0, `# page: ${newUrl}`);
  return lines.join("\n");
}

// Update the primary bulletin URL line (first https URL in parish section)
function _pdUpdatePrimaryBulletinUrl(fileText, parishName, newUrl) {
  const lines = fileText.split("\n");
  const escaped = parishName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headerRe = new RegExp(`^#\\s*---\\s*${escaped}\\s*---`, "i");
  let inSection = false;
  let replaced = false;
  let headerIdx = -1;

  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (headerRe.test(trimmed)) {
      inSection = true;
      headerIdx = i;
      continue;
    }
    if (inSection) {
      if (/^#\s*---/.test(trimmed)) break;
      if (trimmed.startsWith("#") || !trimmed) continue;
      if (/^https?:\/\//i.test(trimmed)) {
        lines[i] = newUrl;
        replaced = true;
        break;
      }
    }
  }
  if (!replaced && headerIdx >= 0) {
    lines.splice(headerIdx + 1, 0, newUrl);
  }
  return lines.join("\n");
}

let _pdHarvestReport = null;
let _pdParishStatusDoc = null;
let _problemsAllRows = [];
let _problemsAutoRefreshTimer = null;
const PROBLEMS_AUTO_REFRESH_MS = 20 * 60 * 1000;

async function _pdLoadParishStatusDoc(force = false) {
  if (_pdParishStatusDoc && !force) return _pdParishStatusDoc;
  try {
    const cfg = await _pdGetGithubConfig();
    if (!cfg) return null;
    const status = await _problemsFetchParishStatus(cfg.ghRepo, cfg.ghPat);
    if (status?.schema_version >= 1) {
      _pdParishStatusDoc = status;
      try {
        await chrome.storage.local.set({
          ph_parish_status_cache: {
            fetched_at: Date.now(),
            target_date: status.target_date || "",
            actionable_count: Array.isArray(status.actionable_keys) ? status.actionable_keys.length : 0,
            summary: status.summary || {},
          },
        });
      } catch (_e) {
        // storage optional
      }
      return _pdParishStatusDoc;
    }
  } catch (_e) {
    // fall through
  }
  return null;
}

async function _pdLoadHarvestReport() {
  if (_pdHarvestReport) return _pdHarvestReport;
  try {
    const cfg = await _pdGetGithubConfig();
    if (!cfg) return null;
    const report = await _problemsFetchLiveReport(cfg.ghRepo, cfg.ghPat);
    if (report) {
      _pdHarvestReport = report;
      return _pdHarvestReport;
    }
    const resp = await fetch(
      `https://raw.githubusercontent.com/${cfg.ghRepo}/main/Bulletins/report.json?t=${Date.now()}`,
      { cache: "no-store" }
    );
    if (!resp.ok) return null;
    _pdHarvestReport = await resp.json();
    return _pdHarvestReport;
  } catch (_e) {
    return null;
  }
}

function _pdHarvestStatusForKey(parishKey) {
  if (!parishKey) return "";
  const key = String(parishKey).trim().toLowerCase();
  const statusItem = _pdParishStatusDoc?.parishes?.[key];
  if (statusItem) {
    const outcome = String(statusItem.outcome || "");
    const url = String(statusItem.url || "").trim();
    const when = formatUkDate(String(statusItem.last_tested_at || _pdParishStatusDoc?.target_date || "").slice(0, 10));
    if (outcome === "ok") {
      return url
        ? `✅ Last harvest (${when || "—"}): OK — ${url}`
        : `✅ Last harvest (${when || "—"}): OK`;
    }
    if (outcome === "stale") {
      return `⚠️ Stale (${when || "—"}): ${String(statusItem.error || "bulletin too old").slice(0, 80)}`;
    }
    if (outcome && outcome !== "ok") {
      return `❌ Last harvest: ${String(statusItem.error || statusItem.category || outcome).slice(0, 80)}`;
    }
  }
  if (!_pdHarvestReport) return "";
  const downloaded = (_pdHarvestReport.downloaded || []).find((r) => r.parish === key);
  if (downloaded) {
    const url = String(downloaded.url || "").trim();
    return url
      ? `✅ Last harvest (${formatUkDate(_pdHarvestReport.target_date) || "—"}): OK — ${url}`
      : `✅ Last harvest (${formatUkDate(_pdHarvestReport.target_date) || "—"}): OK`;
  }
  const failed = (_pdHarvestReport.failed || []).find((r) => r.parish === key);
  if (failed) {
    return `❌ Last harvest: ${String(failed.reason || failed.error || "failed").slice(0, 80)}`;
  }
  return "";
}


function _pdDecodeGithubContent(data) {
  return decodeURIComponent(
    atob(String(data?.content || "").replace(/\n/g, ""))
      .split("")
      .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
      .join("")
  );
}

async function _pdGhFetch(path) {
  const cfg = await _pdGetGithubConfig();
  if (!cfg) throw new Error("GitHub PAT or repo not configured.");

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 25000);
  try {
    const apiUrl = `https://api.github.com/repos/${cfg.ghRepo}/contents/${path}`;
    const resp = await fetch(apiUrl, {
      signal: controller.signal,
      headers: {
        Authorization: `token ${cfg.ghPat}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    });
    if (resp.status === 404) throw new Error(`File not found: ${path}`);
    if (!resp.ok) throw new Error(`GitHub ${resp.status}: ${resp.statusText}`);
    const data = await resp.json();
    return { content: _pdDecodeGithubContent(data), sha: data.sha };
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error(`Timed out loading ${path} from GitHub.`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

function _pdGhPush(path, content, commitMsg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "push_github_file", path, content, commitMessage: commitMsg }, (res) => {
      if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
      resolve(res);
    });
  });
}

function _pdGhDelete(path, sha, commitMsg) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage({ type: "delete_github_file", path, sha, commitMessage: commitMsg }, (res) => {
      if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
      resolve(res);
    });
  });
}

function _pdExtractParishBlock(fileText, parishName) {
  const lines = fileText.split("\n");
  const escaped = parishName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headerRe = new RegExp(`^#\\s*---\\s*${escaped}\\s*---`, "i");
  let start = -1;
  let end = lines.length;
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (headerRe.test(trimmed)) {
      start = i;
      continue;
    }
    if (start >= 0 && /^#\s*---/.test(trimmed)) {
      end = i;
      break;
    }
  }
  if (start < 0) return null;
  const block = lines.slice(start, end).join("\n").trim();
  const remainder = [...lines.slice(0, start), ...lines.slice(end)].join("\n").replace(/\n{3,}/g, "\n\n");
  return { block, remainder };
}

async function _pdMoveParish(parish, targetDioceseName) {
  const sourceInfo = _pdDioceseTexts[parish.diocese];
  const targetInfo = _pdDioceseTexts[targetDioceseName];
  if (!sourceInfo || !targetInfo) throw new Error("Evidence files not loaded.");
  if (parish.diocese === targetDioceseName) throw new Error("Parish is already in that diocese.");
  const extracted = _pdExtractParishBlock(sourceInfo.text, parish.name);
  if (!extracted?.block) throw new Error(`Could not find ${parish.name} in source file.`);
  const srcRes = await _pdGhPush(
    sourceInfo.path,
    extracted.remainder,
    `evidence: move ${parish.name} out of ${parish.diocese} [from extension]`
  );
  if (!srcRes?.ok) throw new Error(srcRes?.error || "Source save failed.");
  sourceInfo.text = extracted.remainder;
  const targetText = `${targetInfo.text.trim()}\n\n${extracted.block}\n`;
  const tgtRes = await _pdGhPush(
    targetInfo.path,
    targetText,
    `evidence: move ${parish.name} into ${targetDioceseName} [from extension]`
  );
  if (!tgtRes?.ok) throw new Error(tgtRes?.error || "Target save failed.");
  targetInfo.text = targetText;
  const slug = _pdDioceseSlug(targetDioceseName);
  const oldSlug = _pdDioceseSlug(parish.diocese);
  const recipePath = `parishes/recipes/${oldSlug}/${parish.key}.json`;
  const newRecipePath = `parishes/recipes/${slug}/${parish.key}.json`;
  try {
    const { content, sha } = await _pdGhFetch(recipePath);
    const parsed = JSON.parse(content);
    parsed.diocese = slug;
    await _pdGhPush(newRecipePath, JSON.stringify(parsed, null, 2), `chore: move recipe ${parish.key} to ${slug} [from extension]`);
    await _pdGhDelete(recipePath, sha, `chore: remove old recipe path for ${parish.key} [from extension]`);
  } catch (_e) {
    // recipe may not exist yet
  }
  parish.diocese = targetDioceseName;
  delete _pdParishDetailsCache[parish.key];
  return { ok: true };
}

async function _pdDisableParish(parish) {
  const info = _pdDioceseTexts[parish.diocese];
  if (!info) throw new Error("Evidence file not loaded.");
  const lines = info.text.split("\n");
  const escaped = parish.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const headerRe = new RegExp(`^#\\s*---\\s*${escaped}\\s*---`, "i");
  let inserted = false;
  for (let i = 0; i < lines.length; i++) {
    if (headerRe.test(lines[i].trim())) {
      if (!lines[i + 1]?.includes("DISABLED")) {
        lines.splice(i + 1, 0, "# DISABLED — removed from harvest via extension");
        inserted = true;
      }
      break;
    }
  }
  if (!inserted) throw new Error("Parish section not found.");
  const updated = lines.join("\n");
  const res = await _pdGhPush(info.path, updated, `evidence: disable ${parish.name} [from extension]`);
  if (!res?.ok) throw new Error(res?.error || "Save failed.");
  info.text = updated;
  parish.disabled = true;
  return { ok: true };
}

// ── Harvest workflow dispatch ──────────────────────────────────────────────

async function _pdDispatchHarvest(parishKey, dioceseName) {
  const cfg = await _pdGetGithubConfig();
  if (!cfg) return { ok: false, error: "GitHub not configured." };
  const key = String(parishKey || "").trim().toLowerCase();
  let dioceseInput = "all";
  if (key) {
    const display = dioceseName || _pdDioceseForKey(key);
    const slug = _pdDioceseSlug(display);
    const mod = globalThis.phGithubRecipePush;
    dioceseInput = mod?.harvestWorkflowDiocese
      ? mod.harvestWorkflowDiocese(slug)
      : slug === "derry"
        ? "derry_diocese"
        : slug === "raphoe"
          ? "raphoe_diocese"
          : slug || "all";
  }
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${cfg.ghRepo}/actions/workflows/harvest.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `token ${cfg.ghPat}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({
          ref: "main",
          inputs: {
            diocese: dioceseInput,
            target_parish: key,
            run_tests: "false",
          },
        }),
      }
    );
    if (resp.status === 204) return { ok: true };
    if (resp.status === 403) return { ok: false, error: "PAT missing 'workflow' scope." };
    return { ok: false, error: `Dispatch failed (${resp.status}).` };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function _pdDispatchFullHarvest() {
  return _pdDispatchHarvest("");
}

// ── Mega-excludes helpers ─────────────────────────────────────────────────

let _pdExcludes = null; // cached array of parish keys

async function _pdLoadExcludes() {
  if (_pdExcludes !== null) return _pdExcludes;
  try {
    const { content } = await _pdGhFetch(MEGA_EXCLUDES_PATH);
    _pdExcludes = JSON.parse(content);
  } catch (_e) {
    _pdExcludes = [];
  }
  return _pdExcludes;
}

async function _pdSaveExcludes(excludes) {
  _pdExcludes = excludes;
  const content = JSON.stringify(excludes.sort(), null, 2);
  return _pdGhPush(MEGA_EXCLUDES_PATH, content, "excludes: update Collated Bulletin exclude list [from extension]");
}

// ── Manual bulletin overrides ───────────────────────────────────────────────

let _pdOverrides = null; // key -> {url,type,updated_at,source}

function _pdInferOverrideType(url) {
  const lower = (url || "").toLowerCase();
  if (lower.endsWith(".docx")) return "docx";
  if (lower.match(/\.(jpg|jpeg|png|webp)(\?|$)/)) return "image";
  if (lower.endsWith(".pdf") || lower.includes(".pdf?")) return "download";
  return "html";
}

async function _pdLoadOverrides() {
  if (_pdOverrides !== null) return _pdOverrides;
  try {
    const { content } = await _pdGhFetch(MANUAL_OVERRIDES_PATH);
    const parsed = JSON.parse(content);
    _pdOverrides = parsed && typeof parsed === "object" ? parsed : {};
  } catch (_e) {
    _pdOverrides = {};
  }
  return _pdOverrides;
}

async function _pdSaveOverrides(overrides) {
  _pdOverrides = overrides;
  const content = JSON.stringify(overrides, null, 2);
  return _pdGhPush(
    MANUAL_OVERRIDES_PATH,
    content,
    "overrides: update manual bulletin URL overrides [from extension]"
  );
}

function _pdGetOverride(parishKey) {
  if (!_pdOverrides || !parishKey) return null;
  const raw = _pdOverrides[parishKey];
  if (!raw || typeof raw !== "object") return null;
  if (typeof raw.url !== "string" || !/^https?:\/\//i.test(raw.url)) return null;
  return raw;
}

// ── Last-included timestamps ───────────────────────────────────────────────

let _pdLastIncluded = null; // key -> ISO string

async function _pdLoadLastIncluded() {
  if (_pdLastIncluded !== null) return _pdLastIncluded;
  try {
    const { content } = await _pdGhFetch(LAST_INCLUDED_PATH);
    const parsed = JSON.parse(content);
    _pdLastIncluded = (parsed && typeof parsed === "object") ? parsed : {};
  } catch (_e) {
    _pdLastIncluded = {};
  }
  return _pdLastIncluded;
}

function _pdDioceseSlug(dioceseName) {
  const info = _pdDioceseTexts[dioceseName];
  if (info?.path) {
    const m = info.path.match(/^parishes\/(.+)_bulletin_urls\.txt$/);
    if (m) {
      let slug = m[1];
      if (slug.endsWith("_diocese")) slug = slug.slice(0, -"_diocese".length);
      return slug;
    }
  }
  return String(dioceseName || "")
    .replace(/\s*&\s*/g, "_and_")
    .replace(/[^a-zA-Z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .toLowerCase()
    .replace(/_diocese$/i, "");
}

async function _pdLoadDioceseConfig() {
  try {
    const { content } = await _pdGhFetch(DIOCESES_JSON_PATH);
    const parsed = JSON.parse(content);
    if (Array.isArray(parsed?.dioceses) && parsed.dioceses.length > 0) {
      const map = {};
      for (const d of parsed.dioceses) {
        if (d.display_name && d.evidence_file) map[d.display_name] = d.evidence_file;
      }
      if (Object.keys(map).length > 0) PD_EVIDENCE_FILES = map;
    }
  } catch (_e) {
    PD_EVIDENCE_FILES = { ...PD_EVIDENCE_FILES_FALLBACK };
  }
}

async function _pdEnsureDioceseInfo(dioceseDisplayName) {
  let info = _pdDioceseTexts[dioceseDisplayName];
  if (info?.text != null) return info;
  const path = PD_EVIDENCE_FILES[dioceseDisplayName];
  if (!path) throw new Error(`Unknown diocese: ${dioceseDisplayName}`);
  try {
    const { content } = await _pdGhFetch(path);
    info = { text: content, path };
  } catch (_e) {
    info = { text: "", path };
  }
  _pdDioceseTexts[dioceseDisplayName] = info;
  return info;
}

async function _pdAddParish(dioceseDisplayName, name, url) {
  const trimmedUrl = String(url || "").trim();
  if (!trimmedUrl) throw new Error("Bulletin URL is required.");
  let trimmedName = String(name || "").trim();
  const fromUrl = globalThis.phOfficialParishName?.officialDisplayNameFromUrl?.(trimmedUrl) || "";
  if (fromUrl) trimmedName = fromUrl;
  if (!trimmedName) throw new Error("Parish name is required (or use a parish website URL).");
  const info = await _pdEnsureDioceseInfo(dioceseDisplayName);
  if (_pdExtractParishBlock(info.text, trimmedName) != null) {
    throw new Error(`Parish "${trimmedName}" already exists in ${dioceseDisplayName}.`);
  }
  const newText = info.text.trimEnd() + "\n\n# --- " + trimmedName + " ---\n" + trimmedUrl + "\n";
  const res = await _pdGhPush(info.path, newText, `evidence: add ${trimmedName} to ${dioceseDisplayName} [from extension]`);
  if (!res?.ok) throw new Error(res?.error || "Save failed.");
  info.text = newText;
  const newParish = _pdParseEvidence(newText, dioceseDisplayName).find((p) => p.name === trimmedName);
  if (newParish) _pdAllParishes.push(newParish);
}

async function _pdDeleteParish(parish) {
  const info = await _pdEnsureDioceseInfo(parish.diocese);
  const extracted = _pdExtractParishBlock(info.text, parish.name);
  if (!extracted) throw new Error(`Could not find ${parish.name} in evidence file.`);
  const res = await _pdGhPush(
    info.path,
    extracted.remainder,
    `evidence: remove ${parish.name} from ${parish.diocese} [from extension]`
  );
  if (!res?.ok) throw new Error(res?.error || "Save failed.");
  info.text = extracted.remainder;
  _pdAllParishes = _pdAllParishes.filter((p) => !(p.diocese === parish.diocese && p.name === parish.name));
  delete _pdParishDetailsCache[parish.key];
}

async function _pdCreateDiocese(displayName) {
  const trimmed = String(displayName || "").trim();
  if (!trimmed) throw new Error("Diocese name is required.");
  if (PD_EVIDENCE_FILES[trimmed]) throw new Error(`Diocese "${trimmed}" already exists.`);
  const key = _pdDioceseSlug(trimmed);
  if (!key) throw new Error("Could not derive diocese key from name.");
  const evidence_file = `parishes/${key}_diocese_bulletin_urls.txt`;
  const headline = trimmed.toUpperCase() + " BIG BULLETIN";
  const pdf_filename = `${key}_mega_bulletin.pdf`;

  let configData;
  try {
    const { content } = await _pdGhFetch(DIOCESES_JSON_PATH);
    configData = JSON.parse(content);
  } catch (_e) {
    configData = { dioceses: [] };
  }
  if (!Array.isArray(configData.dioceses)) configData.dioceses = [];
  if (configData.dioceses.some((d) => d.key === key || d.display_name === trimmed)) {
    throw new Error(`Diocese key "${key}" already exists in dioceses.json.`);
  }
  configData.dioceses.push({
    key,
    display_name: trimmed,
    headline,
    evidence_file,
    pdf_filename,
  });
  const configRes = await _pdGhPush(
    DIOCESES_JSON_PATH,
    JSON.stringify(configData, null, 2) + "\n",
    `evidence: add diocese ${trimmed} [from extension]`
  );
  if (!configRes?.ok) throw new Error(configRes?.error || "Failed to save dioceses.json.");

  const evidenceRes = await _pdGhPush(
    evidence_file,
    `# ${trimmed} bulletin URLs\n`,
    `evidence: create ${trimmed} [from extension]`
  );
  if (!evidenceRes?.ok) throw new Error(evidenceRes?.error || "Failed to create evidence file.");

  PD_EVIDENCE_FILES[trimmed] = evidence_file;
  _pdDioceseTexts[trimmed] = { text: `# ${trimmed} bulletin URLs\n`, path: evidence_file };
}

async function _pdGetGithubConfig() {
  try {
    const cfg = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
    const ghPat = String(cfg?.gh_pat || "").trim();
    const ghRepo = phResolveGhRepo(cfg?.gh_repo);
    if (!ghPat) return null;
    return { ghPat, ghRepo };
  } catch (_e) {
    return null;
  }
}

function _pdFormatTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "—";
  return formatUkDate(d.toISOString().slice(0, 10));
}

function formatUkDate(isoDate) {
  const value = String(isoDate || "").trim();
  if (!value) return "—";
  const match = value.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[3]}/${match[2]}/${match[1]}`;
  const d = new Date(value);
  if (!Number.isNaN(d.getTime())) {
    const dd = String(d.getUTCDate()).padStart(2, "0");
    const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
    const yyyy = d.getUTCFullYear();
    return `${dd}/${mm}/${yyyy}`;
  }
  return value;
}

async function _pdFetchLatestCommitTime(path) {
  const cfg = await _pdGetGithubConfig();
  if (!cfg) return "";
  const endpoint = `https://api.github.com/repos/${cfg.ghRepo}/commits?path=${encodeURIComponent(path)}&per_page=1`;
  try {
    const resp = await fetch(endpoint, {
      headers: {
        Authorization: `token ${cfg.ghPat}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
    });
    if (!resp.ok) return "";
    const data = await resp.json();
    const first = Array.isArray(data) ? data[0] : null;
    return first?.commit?.committer?.date || first?.commit?.author?.date || "";
  } catch (_e) {
    return "";
  }
}

async function _pdLoadRecipeForParish(parish) {
  const key = parish.key;
  if (!key) return { recipe: null, path: "" };
  const slug = _pdDioceseSlug(parish.diocese);
  const candidates = [
    slug ? `parishes/recipes/${slug}/${key}.json` : "",
    `parishes/recipes/${key}.json`,
    `parishes/recipes/unknown/${key}.json`,
  ].filter(Boolean);
  for (const path of candidates) {
    try {
      const { content } = await _pdGhFetch(path);
      return { recipe: JSON.parse(content), path };
    } catch (_e) {
      // try next
    }
  }
  return { recipe: null, path: "" };
}

function _pdRecipeTerminalUrl(recipe) {
  const steps = Array.isArray(recipe?.steps) ? recipe.steps : [];
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i] || {};
    const action = String(step.action || "");
    if (!["download", "image", "html"].includes(action)) continue;
    const url = String(step.captured_url || step.url || "").trim();
    if (/^https?:\/\//i.test(url)) return { url, action };
  }
  return { url: "", action: "" };
}

function _pdConfirmedChangesList(parish, override, recipe, recipePath) {
  const updates = [];
  if (override?.updated_at) {
    updates.push(`Manual override updated ${_pdFormatTime(override.updated_at)}`);
  } else if (override?.url) {
    updates.push("Manual override URL saved");
  }
  if (recipe?.recorded_date) {
    updates.push(`Recipe updated ${formatUkDate(recipe.recorded_date)}`);
  }
  if (recipePath) {
    updates.push(`Recipe file: ${recipePath}`);
  }
  return updates;
}

async function _pdBuildParishDetails(parish) {
  const cached = _pdParishDetailsCache[parish.key];
  if (cached) return cached;
  const override = _pdGetOverride(parish.key);
  const { recipe, path: recipePath } = await _pdLoadRecipeForParish(parish);
  const terminal = _pdRecipeTerminalUrl(recipe);
  await _pdLoadParishStatusDoc();
  await _pdLoadHarvestReport();
  const statusUrl = String(_pdParishStatusDoc?.parishes?.[parish.key]?.url || "").trim();
  const currentUrl = (override?.url || statusUrl || terminal.url || parish.bulletinUrls[0] || parish.pageUrl || "").trim();
  const changes = _pdConfirmedChangesList(parish, override, recipe, recipePath);
  const lastUpdatedRepoIso = await _pdFetchLatestCommitTime(recipePath || _pdDioceseTexts[parish.diocese]?.path || "");
  const lastIncludedIso = (_pdLastIncluded && _pdLastIncluded[parish.key]) || "";
  const harvestStatus = _pdHarvestStatusForKey(parish.key);
  const details = {
    parish,
    currentUrl,
    terminalAction: terminal.action,
    changes,
    lastUpdatedRepoIso,
    lastIncludedIso,
    harvestStatus,
  };
  _pdParishDetailsCache[parish.key] = details;
  return details;
}

function _pdRenderSubfolder(container, details) {
  _clearElement(container);

  const rowUrl = document.createElement("div");
  rowUrl.className = "pd-subfolder-row";
  const rowUrlLabel = document.createElement("span");
  rowUrlLabel.className = "pd-subfolder-label";
  rowUrlLabel.textContent = "Current bulletin URL:";
  rowUrl.appendChild(rowUrlLabel);
  rowUrl.appendChild(document.createTextNode(" "));
  if (details.currentUrl) {
    const link = document.createElement("a");
    link.className = "pd-subfolder-url";
    link.href = details.currentUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = details.currentUrl;
    rowUrl.appendChild(link);
  } else {
    const none = document.createElement("span");
    none.className = "pd-subfolder-empty";
    none.textContent = "Not available";
    rowUrl.appendChild(none);
  }
  container.appendChild(rowUrl);

  if (details.harvestStatus) {
    const rowHarvest = document.createElement("div");
    rowHarvest.className = "pd-subfolder-row";
    rowHarvest.style.color = details.harvestStatus.startsWith("✅") ? "#86efac" : "#fca5a5";
    rowHarvest.textContent = details.harvestStatus;
    container.appendChild(rowHarvest);
  }

  const rowChanges = document.createElement("div");
  rowChanges.className = "pd-subfolder-row";
  const rowChangesLabel = document.createElement("span");
  rowChangesLabel.className = "pd-subfolder-label";
  rowChangesLabel.textContent = "Confirmed changes:";
  rowChanges.appendChild(rowChangesLabel);
  rowChanges.appendChild(document.createTextNode(" "));
  if (details.changes.length > 0) {
    const list = document.createElement("ul");
    list.className = "pd-subfolder-list";
    details.changes.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      list.appendChild(li);
    });
    rowChanges.appendChild(list);
  } else {
    const none = document.createElement("span");
    none.className = "pd-subfolder-empty";
    none.textContent = "No user-confirmed changes recorded";
    rowChanges.appendChild(none);
  }
  container.appendChild(rowChanges);

  const rowRepo = document.createElement("div");
  rowRepo.className = "pd-subfolder-row";
  const rowRepoLabel = document.createElement("span");
  rowRepoLabel.className = "pd-subfolder-label";
  rowRepoLabel.textContent = "Last updated in harvester repo:";
  const rowRepoTime = document.createElement("span");
  rowRepoTime.className = "pd-subfolder-time";
  rowRepoTime.textContent = _pdFormatTime(details.lastUpdatedRepoIso);
  rowRepo.appendChild(rowRepoLabel);
  rowRepo.appendChild(document.createTextNode(" "));
  rowRepo.appendChild(rowRepoTime);
  container.appendChild(rowRepo);

  const rowMega = document.createElement("div");
  rowMega.className = "pd-subfolder-row";
  const rowMegaLabel = document.createElement("span");
  rowMegaLabel.className = "pd-subfolder-label";
  rowMegaLabel.textContent = "Last included in Collated Bulletin:";
  const rowMegaTime = document.createElement("span");
  rowMegaTime.className = "pd-subfolder-time";
  rowMegaTime.textContent = _pdFormatTime(details.lastIncludedIso);
  rowMega.appendChild(rowMegaLabel);
  rowMega.appendChild(document.createTextNode(" "));
  rowMega.appendChild(rowMegaTime);
  container.appendChild(rowMega);

  if (details.parish) {
    const saveRow = document.createElement("div");
    saveRow.className = "pd-subfolder-row";
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "green";
    saveBtn.style.cssText = "width:auto;font-size:9px;padding:3px 8px;margin-top:4px;";
    saveBtn.textContent = "✏️ Edit URL → push to GitHub";
    saveBtn.addEventListener("click", () => {
      const wrap = document.querySelector(`[data-key="${details.parish.key}"]`);
      if (wrap) _pdShowEditRow(wrap, details.parish);
    });
    saveRow.appendChild(saveBtn);
    container.appendChild(saveRow);
  }
}

// ── Consecutive failures ────────────────────────────────────────────────────

let _pdConsecutiveFailures = {}; // key -> number
let _pdShowBrokenOnly = false;

function _pdFailureCount(parishKey) {
  return Number(_pdConsecutiveFailures[parishKey] || 0);
}

function _pdIsBroken(parishKey) {
  const key = String(parishKey || "").trim().toLowerCase();
  const item = _pdParishStatusDoc?.parishes?.[key];
  if (item && typeof item.actionable === "boolean") return item.actionable === true;
  return _pdFailureCount(parishKey) >= 2;
}

async function _pdLoadConsecutiveFailures() {
  try {
    const { content } = await _pdGhFetch(CONSECUTIVE_FAILURES_PATH);
    const parsed = JSON.parse(content);
    if (!parsed || typeof parsed !== "object") return {};
    const normalized = {};
    for (const [key, value] of Object.entries(parsed)) {
      const n = Number(value);
      normalized[key] = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
    }
    return normalized;
  } catch (_e) {
    return {};
  }
}

async function _pdLoadStaleBulletins() {
  try {
    const { content } = await _pdGhFetch(STALE_BULLETINS_PATH);
    const parsed = JSON.parse(content);
    const stale = Array.isArray(parsed?.stale) ? parsed.stale : [];
    const unknown_date = Array.isArray(parsed?.unknown_date) ? parsed.unknown_date : [];
    return { stale, unknown_date };
  } catch (_e) {
    return { stale: [], unknown_date: [] };
  }
}

// ── Recipe status cache ────────────────────────────────────────────────────
const _pdRecipeCache = {}; // key → "ok" | "dead" | "none"

function _pdRecipeIsInactive(data) {
  if (!data || typeof data !== "object") return false;
  const status = String(data.status || "").toLowerCase();
  return Boolean(data.skip) || status === "dead_url" || status === "inactive";
}

async function _pdLoadRecipe(key) {
  if (!key) return null;
  const candidates = [
    `parishes/recipes/derry/${key}.json`,
    `parishes/recipes/down_and_connor/${key}.json`,
    `parishes/recipes/raphoe/${key}.json`,
    `parishes/recipes/${key}.json`,
    `parishes/recipes/unknown/${key}.json`,
  ];
  for (const path of candidates) {
    try {
      const { content } = await _pdGhFetch(path);
      return JSON.parse(content);
    } catch (_e) {
      // try next path
    }
  }
  return null;
}

async function _problemsResolveFixUrl(row) {
  const parish = String(row?.parish || "").trim();
  const recipe = await _pdLoadRecipe(parish);
  const recipeStart = String(recipe?.start_url || "").trim();
  if (/drive\.usercontent\.google\.com\/download/i.test(recipeStart)) {
    const idMatch = recipeStart.match(/[?&]id=([^&#]+)/i);
    if (idMatch?.[1]) {
      return `https://drive.google.com/file/d/${idMatch[1]}/view`;
    }
  }
  if (/^https?:\/\/drive\.google\.com\/file\/d\//i.test(recipeStart)) return recipeStart;
  if (/^https?:\/\//i.test(recipeStart) && !/drive\.usercontent\.google\.com/i.test(recipeStart)) {
    return recipeStart;
  }
  const match = _pdAllParishes.find((p) => p.key === parish);
  const pageUrl = String(match?.pageUrl || match?.bulletinUrls?.[0] || "").trim();
  if (/^https?:\/\/drive\.google\.com\/file\/d\//i.test(pageUrl)) return pageUrl;
  if (/^https?:\/\//i.test(pageUrl) && !/drive\.usercontent\.google\.com/i.test(pageUrl)) {
    return pageUrl;
  }
  const failedUrl = String(row?.url || row?.start_url || "").trim();
  if (/^https?:\/\/drive\.google\.com\/file\/d\//i.test(failedUrl)) return failedUrl;
  if (/^https?:\/\//i.test(failedUrl) && !/drive\.usercontent\.google\.com/i.test(failedUrl)) {
    return failedUrl;
  }
  return "";
}

async function _pdCheckRecipe(key) {
  if (_pdRecipeCache[key]) return _pdRecipeCache[key];
  const candidates = [
    `parishes/recipes/derry/${key}.json`,
    `parishes/recipes/down_and_connor/${key}.json`,
    `parishes/recipes/raphoe/${key}.json`,
    `parishes/recipes/${key}.json`,
    `parishes/recipes/unknown/${key}.json`,
  ];
  for (const path of candidates) {
    try {
      const { content } = await _pdGhFetch(path);
      const data = JSON.parse(content);
      _pdRecipeCache[key] = _pdRecipeIsInactive(data) ? "dead" : "ok";
      return _pdRecipeCache[key];
    } catch (_e) {
      // try next path
    }
  }
  _pdRecipeCache[key] = "none";
  return "none";
}

async function _pdEnsureParishesLoaded() {
  if (_pdAllParishes.length > 0 && Object.keys(_pdDioceseTexts).length > 0) return;
  await _pdLoadDioceseConfig();
  const evidenceResults = await Promise.all(
    Object.entries(PD_EVIDENCE_FILES).map(([diocese, path]) =>
      _pdGhFetch(path)
        .then(({ content }) => ({ diocese, path, content }))
        .catch(() => ({ diocese, path, content: "" }))
    )
  );
  _pdAllParishes = [];
  _pdDioceseTexts = {};
  for (const r of evidenceResults) {
    _pdDioceseTexts[r.diocese] = { text: r.content || "", path: r.path };
    if (r.content) _pdAllParishes.push(..._pdParseEvidence(r.content, r.diocese));
  }
}

function _pdDioceseForKey(parishKey) {
  const match = _pdAllParishes.find((p) => p.key === parishKey);
  return match?.diocese || "";
}

function _problemsFormatLastSeen(item, report) {
  const tested = String(item?.last_tested_at || report?.last_patched_at || report?.generated_at || "").trim();
  if (tested) {
    const d = tested.slice(0, 10);
    if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return formatUkDate(d);
  }
  return formatUkDate(String(report?.target_date || ""));
}

function _problemsBulletinDateFromStatus(item) {
  const fromDiag = item?.diagnosis && typeof item.diagnosis === "object"
    ? item.diagnosis.bulletin_date
    : "";
  if (fromDiag) return formatUkDate(fromDiag);
  const err = String(item?.error || item?.reason || "");
  const match = err.match(/bulletin date\s+(\d{4}-\d{2}-\d{2})/i);
  return match ? formatUkDate(match[1]) : "";
}

function _problemsPlainStatus(row) {
  const outcome = String(row?.outcome || "").toLowerCase();
  const category = String(row?.category || "").toLowerCase();
  if (outcome === "stale" || category.includes("too old")) return "too old";
  if (outcome === "html_only" || category.includes("html only")) return "html only";
  if (category === "no_pdf" || category.includes("no pdf") || category.includes("no_pdf")) return "no PDF";
  if (category.includes("blocked") || category.includes("blocking")) return "blocked";
  if (outcome === "failed") return "failed";
  return "failed";
}

function _problemsStatusClass(label) {
  const key = String(label || "").toLowerCase().replace(/\s+/g, "-");
  if (key === "too-old") return "too-old";
  if (key === "html-only") return "html-only";
  if (key === "no-pdf") return "no-pdf";
  if (key === "blocked") return "blocked";
  return "failed";
}

function _isGoogleDriveUrl(url) {
  try {
    const host = new URL(String(url || "")).hostname.toLowerCase();
    return host.includes("drive.google") || host.includes("docs.google");
  } catch (_e) {
    return /drive\.google|docs\.google/i.test(String(url || ""));
  }
}

async function _updateDriveTrainerWarning() {
  const banner = document.getElementById("drive-trainer-warning");
  if (!banner) return;
  let url = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    url = String(tab?.url || "");
  } catch (_e) {
    url = "";
  }
  banner.style.display = _isGoogleDriveUrl(url) ? "block" : "none";
}

async function _problemsLoadUiPrefs() {
  const data = await _spStorageGet([PROBLEMS_UI_KEY]);
  const prefs = data[PROBLEMS_UI_KEY];
  return prefs && typeof prefs === "object" ? prefs : {};
}

async function _problemsSaveUiPrefs() {
  const prefs = {
    diocese: String(document.getElementById("problems-filter-diocese")?.value || ""),
    category: String(document.getElementById("problems-filter-category")?.value || ""),
    sort: String(document.getElementById("problems-sort")?.value || "queue"),
  };
  await _spStorageSet({ [PROBLEMS_UI_KEY]: prefs });
}

async function _problemsFetchParishStatus(repo, ghPat) {
  const mod = globalThis.phGithubRecipePush;
  if (mod?.fetchParishStatusJson && ghPat) {
    try {
      const status = await mod.fetchParishStatusJson({ gh_pat: ghPat, gh_repo: repo });
      if (status && status.schema_version >= 1) return status;
    } catch (_e) {
      // Fall through to raw CDN.
    }
  }
  try {
    const resp = await fetch(
      `https://raw.githubusercontent.com/${repo}/main/parishes/parish_status.json?t=${Date.now()}`,
      { cache: "no-store" }
    );
    if (!resp.ok) return null;
    return resp.json();
  } catch (_e) {
    return null;
  }
}

function _problemsRowsFromStatus(status, retrainedMap) {
  const targetDate = String(status?.target_date || "");
  const defaultLastSeen = formatUkDate(targetDate);
  const rows = [];
  for (const key of status?.actionable_keys || []) {
    const item = status?.parishes?.[key];
    if (!item || item.actionable === false) continue;
    const parishMeta = _pdAllParishes.find((p) => p.key === key);
    if (parishMeta?.disabled) continue;
    const retrainedPending = _problemsIsRetrainedPending(key, targetDate, retrainedMap);
    const errorText = String(item.error || item.reason || "");
    const diagnosis = item.diagnosis && typeof item.diagnosis === "object" ? item.diagnosis : null;
    rows.push({
      parish: key,
      display_name: String(item.display_name || key),
      diocese: String(item.diocese || _pdDioceseForKey(key) || ""),
      start_url: String(item.url || ""),
      url: String(item.url || ""),
      error_text: errorText,
      diagnosis,
      outcome: String(item.outcome || ""),
      bulletin_date: _problemsBulletinDateFromStatus(item),
      advice: _problemsFailureAdvice(errorText, diagnosis),
      category: retrainedPending
        ? `retrained — ${item.category || _problemsCategory(errorText, { retrainedPending, diagnosis })}`
        : (item.category || _problemsCategory(errorText, { retrainedPending, diagnosis })),
      last_seen: _problemsFormatLastSeen(item, status) || defaultLastSeen,
      consecutive_failures: Number(item.consecutive_failures || 0),
      retrainedPending,
    });
  }
  return rows;
}

async function _problemsFilterActionableRows(report, consecutiveFailures, retrainedMap) {
  const targetDate = String(report?.target_date || "");
  const defaultLastSeen = formatUkDate(targetDate);
  const downloadedKeys = new Set(
    (Array.isArray(report?.downloaded) ? report.downloaded : [])
      .map((item) => String(item?.parish || "").trim())
      .filter(Boolean)
  );
  const failed = Array.isArray(report?.failed) ? report.failed : [];
  const staleRejected = Array.isArray(report?.stale_rejected) ? report.stale_rejected : [];
  const htmlLinks = Array.isArray(report?.html_links) ? report.html_links : [];
  const problemItems = [
    ...failed.filter((item) => !/Stale bulletin rejected/i.test(String(item?.error || ""))),
    ...staleRejected,
    ...failed.filter((item) => /Stale bulletin rejected/i.test(String(item?.error || ""))),
  ];
  const recipeStatuses = await Promise.all(
    [...problemItems, ...htmlLinks].map((item) => _pdCheckRecipe(String(item?.parish || "").trim()))
  );

  let hiddenDead = 0;
  let hiddenFixed = 0;
  const rows = [];
  const seen = new Set();

  const pushRow = (item, statusIdx, defaults = {}) => {
    const parish = String(item?.parish || "").trim();
    if (!parish || seen.has(parish)) return;
    if (downloadedKeys.has(parish)) {
      hiddenFixed += 1;
      return;
    }
    if (recipeStatuses[statusIdx] === "dead") {
      hiddenDead += 1;
      return;
    }
    const parishMeta = _pdAllParishes.find((p) => p.key === parish);
    if (parishMeta?.disabled) {
      hiddenDead += 1;
      return;
    }
    seen.add(parish);
    const retrainedPending = _problemsIsRetrainedPending(parish, targetDate, retrainedMap);
    const errorText = String(item?.error || item?.reason || defaults.error_text || "");
    const diagnosis = item?.diagnosis && typeof item.diagnosis === "object" ? item.diagnosis : null;
    rows.push({
      parish,
      display_name: String(item?.display_name || item?.parish || ""),
      diocese: _pdDioceseForKey(parish),
      start_url: String(item?.start_url || item?.url || ""),
      url: String(item?.url || ""),
      error_text: errorText,
      diagnosis,
      outcome: String(defaults.outcome || item?.outcome || ""),
      bulletin_date: _problemsBulletinDateFromStatus(item),
      advice: _problemsFailureAdvice(errorText, diagnosis),
      category: defaults.category || _problemsCategory(errorText, { retrainedPending, diagnosis }),
      last_seen: _problemsFormatLastSeen(item, report) || defaultLastSeen,
      consecutive_failures: Number(consecutiveFailures[parish] || 0),
      retrainedPending,
    });
  };

  problemItems.forEach((item, idx) => {
    const isStale = /Stale bulletin rejected/i.test(String(item?.error || ""));
    pushRow(item, idx, { outcome: isStale ? "stale" : "failed" });
  });

  htmlLinks.forEach((item, offset) => {
    const parish = String(item?.parish || "").trim();
    if (!parish || seen.has(parish)) return;
    const statusIdx = problemItems.length + offset;
    if (downloadedKeys.has(parish)) {
      hiddenFixed += 1;
      return;
    }
    if (recipeStatuses[statusIdx] === "dead") {
      hiddenDead += 1;
      return;
    }
    const parishMeta = _pdAllParishes.find((p) => p.key === parish);
    if (parishMeta?.disabled) {
      hiddenDead += 1;
      return;
    }
    seen.add(parish);
    rows.push({
      parish,
      display_name: String(item?.display_name || item?.parish || ""),
      diocese: _pdDioceseForKey(parish),
      start_url: String(item?.start_url || item?.url || ""),
      url: String(item?.url || ""),
      outcome: "html_only",
      bulletin_date: _problemsBulletinDateFromStatus(item),
      error_text: String(item?.error || item?.reason || ""),
      category: "no_pdf",
      last_seen: _problemsFormatLastSeen(item, report) || defaultLastSeen,
      consecutive_failures: Number(consecutiveFailures[parish] || 0),
      retrainedPending: false,
    });
  });

  return { rows, hiddenDead, hiddenFixed, lastSeen: defaultLastSeen };
}

// ── Rendering ─────────────────────────────────────────────────────────────

let _pdAllParishes  = [];
let _pdDioceseTexts = {}; // dioceseName → { text, path }

function _pdStatusDot(parish) {
  if (parish.disabled) return "⚫";
  if (_pdGetOverride(parish.key)) return "📌";
  const rs = _pdRecipeCache[parish.key];
  if (rs === "dead") return "🔴";
  if (rs === "ok")   return "🟢";
  if (rs === "none") return "🟡";
  return "⬜";
}

function _problemsFailureAdvice(errorText, diagnosis) {
  const text = String(errorText || "");
  const diag = diagnosis && typeof diagnosis === "object" ? diagnosis : {};
  if (/Stale bulletin rejected/i.test(text)) {
    const date = diag.bulletin_date || text.match(/bulletin date ([^,)]+)/i)?.[1];
    return date
      ? `Your recipe worked — harvest downloaded a ${date} bulletin but this week needs a newer one. Open this Sunday's newsletter and end with print_to_pdf.`
      : "Your recipe worked but the bulletin was too old for this harvest week.";
  }
  if (/Recipe for .* is outdated/i.test(text)) {
    return "Harvest ran your recipe on GitHub but a click selector broke (menu or link moved). Re-record from the parish news page.";
  }
  if (/admin\/non-bulletin|not a weekly bulletin/i.test(text)) {
    if (/mdocs|portstewartparish/i.test(`${text} ${diag.playbook_type || ""} ${diag.site_type || ""}`)) {
      return "Wrong PDF captured — on mDocs sites click Download on the newest bulletin row, then Push (real PDF download, not Save page as PDF).";
    }
    return diag.step_count === 0
      ? "No recipe on GitHub — harvest guessed and grabbed a sidebar/admin PDF. Train with print_to_pdf on the news page."
      : "Harvest grabbed the wrong file. For HTML bulletins use print_to_pdf; for PDF list sites use Download on the newest row.";
  }
  if (/Recipe replay failed/i.test(text)) {
    return "Recipe on GitHub failed during replay. Tap Check result for the exact error.";
  }
  if (diag.failure_stage === "recipe_blocked" || /needs_retraining|marked for manual/i.test(text)) {
    return "Recipe has skip/retraining flags — harvest never runs it. Push again from the trainer (that clears the flags).";
  }
  if (diag.legacy_fallbacks_blocked) {
    return "Trained recipe failed and harvest will not fall back to old URL guessing — fix the recipe steps.";
  }
  if (diag.step_count === 0) {
    return "GitHub has no recipe steps for this parish — harvest uses legacy scraping which often picks the wrong file.";
  }
  return "";
}

function _problemsCategory(errorText, options = {}) {
  const text = String(errorText || "");
  const diagnosis = options.diagnosis && typeof options.diagnosis === "object"
    ? options.diagnosis
    : null;
  let base;
  if (/Stale bulletin rejected/i.test(text)) {
    base = "bulletin too old (recipe worked)";
  } else if (/Recipe for .* is outdated/i.test(text)) {
    base = "recipe outdated";
  } else if (/admin\/non-bulletin|not a weekly bulletin/i.test(text)) {
    base = diagnosis?.step_count === 0 ? "no recipe — wrong scrape" : "wrong file scraped";
  } else if (/Recipe replay failed/i.test(text)) {
    base = "recipe replay failed";
  } else if (/needs_retraining|marked for manual|recipe_blocked/i.test(text)) {
    base = "recipe blocked";
  } else if (diagnosis?.step_count === 0) {
    base = "no recipe on GitHub";
  } else if (/getaddrinfo|Name or service not known|ENOTFOUND|Could not resolve host/i.test(text)) {
    base = "dns";
  } else if (/SSL|certificate/i.test(text)) {
    base = "ssl";
  } else if (/timeout|Timeout|TimeoutError/i.test(text)) {
    base = "timeout";
  } else if (/Recipe download step did not find|Recipe finished without downloading/i.test(text)) {
    base = "recipe_drift";
  } else if (/no PDF|html_link/i.test(text)) {
    base = "no_pdf";
  } else {
    base = "other";
  }
  if (options.retrainedPending) return `retrained — ${base}`;
  return base;
}

async function _problemsGetRetrainedMap() {
  const data = await _spStorageGet([PROBLEMS_RECIPE_RETRAINED_KEY]);
  const map = data[PROBLEMS_RECIPE_RETRAINED_KEY];
  return (map && typeof map === "object") ? map : {};
}

function _problemsIsRetrainedPending(parishKey, reportTargetDate, retrainedMap) {
  const pushed = String(retrainedMap?.[parishKey] || "").trim();
  const target = String(reportTargetDate || "").trim();
  if (!pushed || !target) return false;
  return pushed >= target;
}

async function _problemsMarkFixVisited(parishKey, fixBtn) {
  const key = String(parishKey || "").trim();
  if (!key) return;
  const data = await _spStorageGet([PROBLEMS_FIX_VISITED_KEY]);
  const visited = (data[PROBLEMS_FIX_VISITED_KEY] && typeof data[PROBLEMS_FIX_VISITED_KEY] === "object")
    ? { ...data[PROBLEMS_FIX_VISITED_KEY] }
    : {};
  visited[key] = Date.now();
  await _spStorageSet({ [PROBLEMS_FIX_VISITED_KEY]: visited });
  if (fixBtn) fixBtn.classList.add("visited");
}

async function _problemsGetVisitedMap() {
  const data = await _spStorageGet([PROBLEMS_FIX_VISITED_KEY]);
  const visited = data[PROBLEMS_FIX_VISITED_KEY];
  return (visited && typeof visited === "object") ? visited : {};
}

function _problemsGithubLinks(repo) {
  const base = `https://github.com/${repo}`;
  return {
    actions: `${base}/actions/workflows/harvest.yml`,
    report: `${base}/blob/main/Bulletins/report.json`,
    status: `${base}/blob/main/parishes/parish_status.json`,
    dashboard: `${base}/blob/main/Bulletins/dashboard.html`,
    megaDerry: `https://raw.githubusercontent.com/${repo}/main/docs/mega_pdf/derry_mega_bulletin.pdf`,
    megaDac: `https://raw.githubusercontent.com/${repo}/main/docs/mega_pdf/down_and_connor_mega_bulletin.pdf`,
  };
}

function _problemsMegaPdfForParish(repo, parishKey) {
  const links = _problemsGithubLinks(repo);
  const match = _pdAllParishes.find((p) => p.key === parishKey);
  const diocese = String(match?.diocese || "").toLowerCase();
  if (diocese.includes("down") || diocese.includes("connor")) return links.megaDac;
  return links.megaDerry;
}

async function _problemsFindLatestWorkflowRun(ghPat, ghRepo, afterMs) {
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${ghRepo}/actions/workflows/harvest.yml/runs?per_page=20&event=workflow_dispatch`,
      {
        headers: {
          Authorization: `token ${ghPat}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
      }
    );
    if (!resp.ok) return null;
    const data = await resp.json();
    const runs = Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
    const cutoff = afterMs - 120_000;
    const recent = runs.filter((run) => new Date(run.created_at).getTime() >= cutoff);
    return recent[0] || runs[0] || null;
  } catch (_e) {
    return null;
  }
}

async function _problemsFetchLiveReport(repo, ghPat) {
  const mod = globalThis.phGithubRecipePush;
  if (mod?.fetchReportJson && ghPat) {
    try {
      const report = await mod.fetchReportJson({ gh_pat: ghPat, gh_repo: repo });
      if (report && typeof report === "object") return report;
    } catch (_e) {
      // Fall through to raw CDN.
    }
  }
  try {
    const resp = await fetch(
      `https://raw.githubusercontent.com/${repo}/main/Bulletins/report.json?t=${Date.now()}`,
      { cache: "no-store" }
    );
    if (!resp.ok) return null;
    return resp.json();
  } catch (_e) {
    return null;
  }
}

function _problemsParishHarvestStatus(report, parishKey) {
  const mod = globalThis.phGithubRecipePush;
  if (mod?.parishHarvestStatus) {
    return mod.parishHarvestStatus(report, parishKey);
  }
  const key = String(parishKey || "").trim().toLowerCase();
  const find = (rows) => (rows || []).find(
    (row) => String(row?.parish || "").trim().toLowerCase() === key
  );
  const downloaded = find(report?.downloaded);
  if (downloaded) return { status: "ok", item: downloaded };
  const stale = find(report?.stale_rejected);
  if (stale) return { status: "stale", item: stale };
  const failed = find(report?.failed);
  if (failed) {
    if (/Stale bulletin rejected/i.test(String(failed.error || ""))) {
      return { status: "stale", item: failed };
    }
    return { status: "failed", item: failed };
  }
  return { status: "unknown", item: null };
}

async function _problemsClearRetrained(parishKey) {
  const data = await _spStorageGet([PROBLEMS_RECIPE_RETRAINED_KEY]);
  const retrained = (data[PROBLEMS_RECIPE_RETRAINED_KEY] && typeof data[PROBLEMS_RECIPE_RETRAINED_KEY] === "object")
    ? { ...data[PROBLEMS_RECIPE_RETRAINED_KEY] }
    : {};
  delete retrained[parishKey];
  await _spStorageSet({ [PROBLEMS_RECIPE_RETRAINED_KEY]: retrained });
}

function _problemsParishBulletinPdf(repo, parishKey) {
  return `https://raw.githubusercontent.com/${repo}/main/Bulletins/current/${parishKey}.pdf`;
}

function _problemsShowVerifyResult(payload) {
  const box = document.getElementById("problems-verify-result");
  if (!box) return;
  const links = _problemsGithubLinks(payload.repo);
  const parishPdf = _problemsParishBulletinPdf(payload.repo, payload.parishKey);
  const runLink = payload.runUrl || links.actions;
  const lines = [];
  if (payload.ok === true) {
    box.className = "ok";
    lines.push(`✅ <strong>${payload.displayName}</strong> — single-parish test passed.`);
    if (payload.item?.url) {
      lines.push(
        `<strong>Open bulletin (proof):</strong> <a href="${payload.item.url}" target="_blank" rel="noopener noreferrer">${payload.item.url}</a>`
      );
    }
    lines.push(
      `Saved copy: <a href="${parishPdf}" target="_blank" rel="noopener noreferrer">Bulletins/current/${payload.parishKey}.pdf</a>`
    );
  } else if (payload.stale === true) {
    box.className = "warn";
    const reason = String(payload.item?.error || payload.item?.reason || "Bulletin too old").slice(0, 220);
    lines.push(`🕐 <strong>${payload.displayName}</strong> — recipe worked, bulletin too old for this week.`);
    lines.push(`Recorded on GitHub: ${reason}`);
    const advice = _problemsFailureAdvice(reason, payload.item?.diagnosis);
    if (advice) lines.push(`<strong>What this means:</strong> ${advice}`);
  } else if (payload.ok === false) {
    box.className = "err";
    const reason = String(payload.item?.error || payload.item?.reason || "still failed").slice(0, 220);
    lines.push(`❌ <strong>${payload.displayName}</strong> still failed: ${reason}`);
    const advice = _problemsFailureAdvice(
      payload.item?.error || payload.item?.reason || "",
      payload.item?.diagnosis
    );
    if (advice) lines.push(`<strong>What this means:</strong> ${advice}`);
    const diag = payload.item?.diagnosis;
    if (diag && typeof diag === "object") {
      const budget = diag.total_timeout_s ? `${diag.total_timeout_s}s total budget` : "";
      const nav = diag.navigation_timeout_ms ? `${diag.navigation_timeout_ms}ms per step` : "";
      const stage = diag.failure_stage ? `stage: ${diag.failure_stage}` : "";
      const steps = diag.step_count != null ? `${diag.step_count} recipe steps` : "";
      const recorded = diag.recipe_recorded_date ? `recipe dated ${diag.recipe_recorded_date}` : "";
      const navWait = diag.navigation_wait_until ? `nav: ${diag.navigation_wait_until}` : "";
      const hint = [budget, nav, stage, steps, recorded, navWait].filter(Boolean).join(" · ");
      if (hint) lines.push(`Diagnosis: ${hint}`);
      if (diag.slow_site_note) lines.push(`Slow site: ${diag.slow_site_note}`);
    }
    if (payload.item?.url) {
      lines.push(
        `Last URL tried: <a href="${payload.item.url}" target="_blank" rel="noopener noreferrer">${payload.item.url}</a>`
      );
    }
  } else {
    box.className = "warn";
    lines.push(`⏳ <strong>${payload.displayName}</strong> — ${payload.message || "Harvest still running."}`);
  }
  lines.push(
    `<a href="${runLink}" target="_blank" rel="noopener noreferrer">GitHub Actions run</a> · ` +
    `<a href="${links.status}" target="_blank" rel="noopener noreferrer">parish_status.json</a> · ` +
    `<a href="${links.report}" target="_blank" rel="noopener noreferrer">report.json</a> · ` +
    `<a href="${links.dashboard}" target="_blank" rel="noopener noreferrer">dashboard</a>`
  );
  box.innerHTML = lines.join("<br>");
  box.style.display = "block";
}

async function _problemsGetLastDispatch(parishKey) {
  const data = await _spStorageGet([PH_LAST_DISPATCH_KEY]);
  const map = data[PH_LAST_DISPATCH_KEY];
  if (!map || typeof map !== "object") return null;
  return map[String(parishKey || "").trim().toLowerCase()] || null;
}

async function _problemsPollHarvestResult({
  parishKey,
  displayName,
  ghPat,
  ghRepo,
  dispatchStarted,
  verifyBtn,
}) {
  const links = _problemsGithubLinks(ghRepo);
  let runUrl = links.actions;
  const started = Number(dispatchStarted) || Date.now();
  _problemsShowVerifyResult({
    ok: null,
    displayName,
    parishKey,
    repo: ghRepo,
    runUrl,
    message: "Checking GitHub now — slow sites can take 2–5 minutes…",
  });
  setStatus(`⏳ Testing ${displayName} on GitHub…`, "warn");

  const pushMod = globalThis.phGithubRecipePush;
  const maxAttempts = 55;

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (attempt > 0) {
      const delay = attempt < 8 ? 3000 : attempt < 20 ? 8000 : 12000;
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    if (verifyBtn) verifyBtn.textContent = `⏳ ${Math.round((Date.now() - started) / 1000)}s…`;

    const run = await _problemsFindLatestWorkflowRun(ghPat, ghRepo, started);
    if (run?.html_url) runUrl = run.html_url;
    const workflowDone = run && run.status === "completed";
    const workflowRunning = run && (run.status === "in_progress" || run.status === "queued" || run.status === "pending");
    const workflowFailed = workflowDone && run.conclusion === "failure";
    const workflowSucceeded = workflowDone && run.conclusion === "success";

    const report = await _problemsFetchLiveReport(ghRepo, ghPat);
    const statusDoc = pushMod?.fetchParishStatusJson
      ? await pushMod.fetchParishStatusJson({ gh_pat: ghPat, gh_repo: ghRepo })
      : null;
    let parishStatus = statusDoc && pushMod?.parishStatusFromDoc
      ? pushMod.parishStatusFromDoc(statusDoc, parishKey)
      : null;
    const testedAt = parishStatus?.item?.last_tested_at || statusDoc?.last_patched_at || "";
    const testedMs = testedAt ? new Date(testedAt).getTime() : 0;
    const freshStatus = Number.isFinite(testedMs) && testedMs >= started - 120_000;
    if (!freshStatus || !parishStatus) {
      parishStatus = report ? _problemsParishHarvestStatus(report, parishKey) : { status: "unknown", item: null };
    }

    let pdfExists = false;
    if (pushMod?.parishPdfExists) {
      try {
        pdfExists = await pushMod.parishPdfExists({
          gh_pat: ghPat,
          gh_repo: ghRepo,
          parish_key: parishKey,
        });
      } catch (_e) {
        pdfExists = false;
      }
    }

    if (parishStatus.status === "ok" || (pdfExists && workflowSucceeded)) {
      await _problemsClearRetrained(parishKey);
      _pdHarvestReport = null;
      const item = parishStatus.item || {
        parish: parishKey,
        url: _problemsParishBulletinPdf(ghRepo, parishKey),
      };
      _problemsShowVerifyResult({
        ok: true,
        displayName,
        parishKey,
        repo: ghRepo,
        runUrl,
        item,
      });
      setStatus(`✅ ${displayName} verified — bulletin link below.`, "ok");
      if (verifyBtn) verifyBtn.textContent = "✅ Done";
      void loadProblemsDashboard();
      return;
    }

    if (workflowDone && parishStatus.status === "stale") {
      _problemsShowVerifyResult({
        stale: true,
        displayName,
        parishKey,
        repo: ghRepo,
        runUrl,
        item: parishStatus.item,
      });
      setStatus(`🕐 ${displayName} — recipe OK, bulletin too old (recorded on GitHub).`, "warn");
      if (verifyBtn) {
        verifyBtn.disabled = false;
        verifyBtn.textContent = "▶ Test again";
      }
      void loadProblemsDashboard();
      return;
    }

    if (workflowRunning) {
      const runStatus = run.status === "queued" || run.status === "pending"
        ? "queued (another harvest may be ahead — please wait)"
        : "running on GitHub";
      _problemsShowVerifyResult({
        ok: null,
        displayName,
        parishKey,
        repo: ghRepo,
        runUrl,
        message: `${runStatus} — ${Math.round((Date.now() - started) / 1000)}s elapsed. Result appears here when done.`,
      });
      continue;
    }

    if (workflowFailed) {
      if (parishStatus.status === "failed" || parishStatus.status === "stale") {
        _problemsShowVerifyResult({
          ok: parishStatus.status === "failed" ? false : undefined,
          stale: parishStatus.status === "stale",
          displayName,
          parishKey,
          repo: ghRepo,
          runUrl,
          item: parishStatus.item,
        });
      } else {
        _problemsShowVerifyResult({
          ok: false,
          displayName,
          parishKey,
          repo: ghRepo,
          runUrl,
          message: "GitHub Actions run failed — open the run link below for the error log.",
        });
      }
      setStatus(`❌ ${displayName} still failing — see links below.`, "err");
      if (verifyBtn) {
        verifyBtn.disabled = false;
        verifyBtn.textContent = "▶ Test again";
      }
      void loadProblemsDashboard();
      return;
    }

    if (workflowDone && parishStatus.status === "failed") {
      _problemsShowVerifyResult({
        ok: false,
        displayName,
        parishKey,
        repo: ghRepo,
        runUrl,
        item: parishStatus.item,
      });
      setStatus(`❌ ${displayName} still failing — see links below.`, "err");
      if (verifyBtn) {
        verifyBtn.disabled = false;
        verifyBtn.textContent = "▶ Test again";
      }
      void loadProblemsDashboard();
      return;
    }

    if (workflowDone && parishStatus.status === "unknown") {
      _problemsShowVerifyResult({
        ok: null,
        displayName,
        parishKey,
        repo: ghRepo,
        runUrl,
        message: pdfExists
          ? "PDF found on GitHub — refreshing report…"
          : "GitHub finished but report not updated yet — still checking…",
      });
    }
  }

  _problemsShowVerifyResult({
    ok: null,
    displayName,
    parishKey,
    repo: ghRepo,
    runUrl,
    message: "Timed out waiting — open the Actions run link below to see progress.",
  });
  setStatus(`⚠️ Still waiting for ${displayName} — open Actions link below.`, "warn");
  if (verifyBtn) {
    verifyBtn.disabled = false;
    verifyBtn.textContent = "▶ Test again";
  }
}

async function _problemsWatchParishHarvest(parishKey, displayName, dispatchAt) {
  const cfg = await _pdGetGithubConfig();
  if (!cfg || !parishKey) return;
  const stored = await _problemsGetLastDispatch(parishKey);
  const dispatchStarted =
    Number(dispatchAt) ||
    Number(stored?.at) ||
    Date.now() - 30_000;
  await _problemsPollHarvestResult({
    parishKey,
    displayName: displayName || stored?.displayName || parishKey,
    ghPat: cfg.ghPat,
    ghRepo: cfg.ghRepo,
    dispatchStarted,
    verifyBtn: null,
  });
}

async function _problemsVerifyHarvest(row, verifyBtn, { forceDispatch = false } = {}) {
  const cfg = await _pdGetGithubConfig();
  if (!cfg) {
    setStatus("❌ GitHub PAT not set — open ⚙️ Settings in the popup.", "err");
    return;
  }
  const parishKey = row.parish;
  const displayName = row.display_name || parishKey;
  const lastDispatch = await _problemsGetLastDispatch(parishKey);
  const recentDispatch =
    lastDispatch?.at && Date.now() - lastDispatch.at < 45 * 60 * 1000;

  if (verifyBtn) {
    verifyBtn.disabled = true;
    verifyBtn.textContent = "⏳ Checking…";
  }

  if (!forceDispatch && recentDispatch) {
    setStatus(`⏳ Checking GitHub result for ${displayName}…`, "warn");
    await _problemsPollHarvestResult({
      parishKey,
      displayName,
      ghPat: cfg.ghPat,
      ghRepo: cfg.ghRepo,
      dispatchStarted: lastDispatch.at,
      verifyBtn,
    });
    return;
  }

  setStatus(`⏳ Starting new test for ${displayName}…`, "warn");
  const dispatchStarted = Date.now();
  const dispatch = await _pdDispatchHarvest(parishKey, _pdDioceseForKey(parishKey));
  if (!dispatch.ok) {
    setStatus(`❌ Harvest trigger failed: ${dispatch.error}`, "err");
    if (verifyBtn) {
      verifyBtn.disabled = false;
      verifyBtn.textContent = "▶ Test again";
    }
    return;
  }

  const dispatchMap = (await _spStorageGet([PH_LAST_DISPATCH_KEY]))[PH_LAST_DISPATCH_KEY] || {};
  dispatchMap[parishKey] = { at: dispatchStarted, displayName };
  await _spStorageSet({ [PH_LAST_DISPATCH_KEY]: dispatchMap });

  await _problemsPollHarvestResult({
    parishKey,
    displayName,
    ghPat: cfg.ghPat,
    ghRepo: cfg.ghRepo,
    dispatchStarted,
    verifyBtn,
  });
}

function _problemsPopulateFilters(rows, prefs = {}) {
  const dioceseSel = document.getElementById("problems-filter-diocese");
  const categorySel = document.getElementById("problems-filter-category");
  const sortSel = document.getElementById("problems-sort");
  if (!dioceseSel || !categorySel) return;
  const dioceses = [...new Set(rows.map((r) => r.diocese).filter(Boolean))].sort((a, b) => {
    if (a === PROBLEMS_DEFAULT_DIOCESE) return -1;
    if (b === PROBLEMS_DEFAULT_DIOCESE) return 1;
    return a.localeCompare(b);
  });
  const categories = [...new Set(rows.map((r) => r.category).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const hasSavedDiocese = Object.prototype.hasOwnProperty.call(prefs, "diocese");
  const keepDiocese = hasSavedDiocese ? String(prefs.diocese) : dioceseSel.value;
  const keepCategory = prefs.category != null ? String(prefs.category) : categorySel.value;
  dioceseSel.innerHTML = '<option value="">All dioceses</option>';
  for (const d of dioceses) {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    dioceseSel.appendChild(opt);
  }
  categorySel.innerHTML = '<option value="">All reasons</option>';
  for (const c of categories) {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    categorySel.appendChild(opt);
  }
  const preferredDiocese = hasSavedDiocese
    ? keepDiocese
    : (keepDiocese || (dioceses.includes(PROBLEMS_DEFAULT_DIOCESE) ? PROBLEMS_DEFAULT_DIOCESE : ""));
  if ([...dioceseSel.options].some((o) => o.value === preferredDiocese)) dioceseSel.value = preferredDiocese;
  if ([...categorySel.options].some((o) => o.value === keepCategory)) categorySel.value = keepCategory;
  if (sortSel) {
    const keepSort = prefs.sort === "az" ? "az" : "queue";
    sortSel.value = keepSort;
  }
}

function _problemsFilteredRows() {
  const diocese = String(document.getElementById("problems-filter-diocese")?.value || "");
  const category = String(document.getElementById("problems-filter-category")?.value || "");
  const sortMode = String(document.getElementById("problems-sort")?.value || "queue");
  let rows = _problemsAllRows.slice();
  if (diocese) rows = rows.filter((r) => r.diocese === diocese);
  if (category) rows = rows.filter((r) => r.category === category);
  if (sortMode === "az") {
    rows.sort((a, b) =>
      String(a.display_name || a.parish).localeCompare(String(b.display_name || b.parish), undefined, { sensitivity: "base" })
    );
    return rows;
  }
  // Work queue: fewer failures first within same reason, then by name.
  rows.sort((a, b) => {
    const ca = String(a.category || "");
    const cb = String(b.category || "");
    if (ca !== cb) return ca.localeCompare(cb);
    const fa = Number(a.consecutive_failures || 0);
    const fb = Number(b.consecutive_failures || 0);
    if (fa !== fb) return fa - fb;
    return String(a.display_name || a.parish).localeCompare(String(b.display_name || b.parish));
  });
  return rows;
}

function _problemsShortUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  try {
    const u = new URL(raw);
    const path = u.pathname.split("/").filter(Boolean).slice(-2).join("/") || u.hostname;
    return path.length > 42 ? `${path.slice(0, 40)}…` : path;
  } catch (_e) {
    return raw.length > 42 ? `${raw.slice(0, 40)}…` : raw;
  }
}

async function _problemsOpenSite(row, openBtn) {
  const startUrl = await _problemsResolveFixUrl(row);
  if (!/^https?:\/\//i.test(startUrl)) {
    setStatus("❌ No valid start URL for this parish.", "err");
    return "";
  }
  void _problemsMarkFixVisited(row.parish, openBtn);
  const { navStartedAt } = await _problemsBeginFixNowSession(startUrl, row.parish);
  setStatus(
    `✅ Opened ${row.display_name || row.parish} — on that page record the bulletin, then tap Send & test.`,
    "ok"
  );
  const match = _pdAllParishes.find((p) => p.key === row.parish);
  if (match) {
    chrome.storage.local.set({
      ph_training_parish: {
        key: match.key,
        name: match.name,
        diocese: match.diocese,
        hostname: (() => {
          try { return new URL(startUrl).hostname.toLowerCase(); } catch (_e) { return ""; }
        })(),
      },
    });
  }
  chrome.tabs.create({ url: startUrl, active: true }, (tab) => {
    const tabId = tab?.id;
    if (!tabId) return;
    _scheduleFixNowToolbar(tabId, row.parish, navStartedAt, startUrl);
  });
  return startUrl;
}

async function _problemsSendAndTest(row) {
  const startUrl = await _problemsResolveFixUrl(row);
  let tab = null;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (_e) {
    tab = null;
  }
  const tabUrl = String(tab?.url || "");
  let sameHost = false;
  try {
    sameHost = Boolean(startUrl) && new URL(tabUrl).hostname === new URL(startUrl).hostname;
  } catch (_e) {
    sameHost = false;
  }
  if (tab?.id && sameHost && /^https?:\/\//i.test(tabUrl)) {
    chrome.runtime.sendMessage({
      type: "dispatch_to_tab",
      tabId: tab.id,
      payload: { type: "ph_send_and_test" },
      allowInject: true,
    }, (result) => {
      if (chrome.runtime.lastError || !result?.ok) {
        setStatus(
          "Open the parish page, record the bulletin, then tap Send & test on the green toolbar.",
          "warn"
        );
        return;
      }
      setStatus(result?.reason || "Send & test started on this page. Wait for the GitHub result.", "ok");
    });
    return;
  }
  setStatus(
    "Open site first. Record the bulletin on that page, then tap Send & test.",
    "warn"
  );
}

async function _problemsRenderRows(rows) {
  const list = document.getElementById("problems-cards");
  const empty = document.getElementById("problems-empty");
  if (!list || !empty) return;
  _clearElement(list);
  if (!rows.length) {
    empty.textContent = _problemsAllRows.length
      ? "No parishes match these filters."
      : "No current problem parishes.";
    return;
  }
  empty.textContent = "";
  const visitedMap = await _problemsGetVisitedMap();
  const ghCfg = await _pdGetGithubConfig();
  const ghRepo = ghCfg?.ghRepo || "Raphoe-Diocese/parish_harvester";
  for (const row of rows) {
    const card = document.createElement("article");
    card.className = "problems-card";

    const head = document.createElement("div");
    head.className = "problems-card-head";
    const titleWrap = document.createElement("div");
    const nameEl = document.createElement("div");
    nameEl.className = "problems-card-name";
    nameEl.textContent = row.display_name || row.parish || "Unknown";
    const dioceseEl = document.createElement("div");
    dioceseEl.className = "problems-card-diocese";
    dioceseEl.textContent = row.diocese || "—";
    titleWrap.appendChild(nameEl);
    titleWrap.appendChild(dioceseEl);
    const statusLabel = _problemsPlainStatus(row);
    const statusEl = document.createElement("span");
    statusEl.className = `problems-status ${_problemsStatusClass(statusLabel)}`;
    statusEl.textContent = statusLabel;
    if (row.retrainedPending) statusEl.classList.add("problems-retrained");
    head.appendChild(titleWrap);
    head.appendChild(statusEl);
    card.appendChild(head);

    const meta = document.createElement("div");
    meta.className = "problems-card-meta";
    const bulletinDate = row.bulletin_date || "—";
    const lastTest = row.last_seen || "—";
    meta.textContent = `Last bulletin: ${bulletinDate} · Last test: ${lastTest}`;
    if (Number(row.consecutive_failures || 0) > 0) {
      meta.textContent += ` · ${row.consecutive_failures} failed weeks`;
    }
    card.appendChild(meta);

    const diagnosisText = String(row.error_text || "").replace(/\s+/g, " ").trim();
    if (diagnosisText) {
      const errorEl = document.createElement("div");
      errorEl.className = "problems-card-error";
      errorEl.textContent = diagnosisText.length > 220 ? `${diagnosisText.slice(0, 217)}…` : diagnosisText;
      card.appendChild(errorEl);
    }

    const actions = document.createElement("div");
    actions.className = "problems-card-actions";

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "problems-fix-btn problems-open-btn";
    openBtn.textContent = "Open site";
    if (visitedMap[row.parish]) openBtn.classList.add("visited");
    openBtn.addEventListener("click", () => {
      void _problemsOpenSite(row, openBtn);
    });
    actions.appendChild(openBtn);

    const sendBtn = document.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "problems-send-btn";
    sendBtn.textContent = "Send & test";
    sendBtn.title = "Push the recorded recipe from the open parish page and run one-parish test";
    sendBtn.addEventListener("click", () => {
      void _problemsSendAndTest(row);
    });
    actions.appendChild(sendBtn);

    const testBtn = document.createElement("button");
    testBtn.type = "button";
    testBtn.className = "problems-verify-btn";
    testBtn.textContent = row.retrainedPending ? "▶ Check result" : "▶ Test parish";
    testBtn.title = row.retrainedPending
      ? "Check the result from your last Send & test (single-parish harvest, not Collated Bulletin PDF)"
      : "Run a single-parish harvest test on GitHub — no recipe push needed";
    testBtn.addEventListener("click", () => {
      void _problemsVerifyHarvest(row, testBtn, { forceDispatch: !row.retrainedPending });
    });
    actions.appendChild(testBtn);

    const recipeSlug = _pdDioceseSlug(row.diocese || "");
    if (recipeSlug && row.parish) {
      const ghLink = document.createElement("a");
      ghLink.className = "problems-github-link";
      ghLink.href = `https://github.com/${ghRepo}/blob/main/parishes/recipes/${recipeSlug}/${row.parish}.json`;
      ghLink.target = "_blank";
      ghLink.rel = "noopener noreferrer";
      ghLink.textContent = "GitHub";
      ghLink.title = "Open recipe JSON on GitHub";
      actions.appendChild(ghLink);
    }

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "problems-remove-btn";
    removeBtn.textContent = "🗑 Remove";
    removeBtn.title = "Disable parish in harvest (marks DISABLED in evidence file on GitHub)";
    removeBtn.addEventListener("click", () => {
      void (async () => {
        await _pdEnsureParishesLoaded();
        const match = _pdAllParishes.find((p) => p.key === row.parish);
        if (!match) {
          setStatus("❌ Parish not found in directory — check GitHub PAT, then Refresh.", "err");
          return;
        }
        if (!confirm(`Remove ${match.name} from the harvest?\n\nThis marks the parish DISABLED in the evidence file on GitHub.`)) {
          return;
        }
        removeBtn.disabled = true;
        try {
          await _pdDisableParish(match);
          setStatus(`✅ ${match.name} disabled — refreshing Problems list…`, "ok");
          void loadProblemsDashboard();
        } catch (err) {
          setStatus(`❌ ${err.message}`, "err");
        } finally {
          removeBtn.disabled = false;
        }
      })();
    });
    actions.appendChild(removeBtn);
    card.appendChild(actions);
    list.appendChild(card);
  }
}

async function loadProblemsDashboard() {
  const warning = document.getElementById("problems-warning");
  const empty = document.getElementById("problems-empty");
  const hint = document.getElementById("problems-hint");
  if (warning) warning.style.display = "none";
  if (empty) empty.textContent = "Loading…";
  for (const key of Object.keys(_pdRecipeCache)) delete _pdRecipeCache[key];
  for (const key of Object.keys(_pdParishDetailsCache)) delete _pdParishDetailsCache[key];
  _pdHarvestReport = null;
  _pdParishStatusDoc = null;
  try {
    await _pdEnsureParishesLoaded();
    const urls = await _problemsRepoUrls();
    const cfg = await _pdGetGithubConfig();
    const retrainedMap = await _problemsGetRetrainedMap();
    const parishStatus = await _pdLoadParishStatusDoc(true);

    let rows = [];
    let lastSeen = formatUkDate(String(parishStatus?.target_date || ""));
    let hiddenDead = 0;
    let hiddenFixed = 0;
    let statusSource = "parish_status.json";

    if (parishStatus?.schema_version >= 1 && Array.isArray(parishStatus.actionable_keys)) {
      rows = _problemsRowsFromStatus(parishStatus, retrainedMap);
      lastSeen = formatUkDate(String(parishStatus.target_date || "")) || lastSeen;
    } else {
      statusSource = "report.json (legacy)";
      let report = cfg ? await _problemsFetchLiveReport(urls.repo, cfg.ghPat) : null;
      const failuresResp = await fetch(urls.failuresUrl, { cache: "no-store" });
      if (!report) {
        const reportResp = await fetch(urls.reportUrl, { cache: "no-store" });
        if (!reportResp.ok || !failuresResp.ok) {
          throw new Error("Could not fetch live report data");
        }
        report = await reportResp.json();
      } else if (!failuresResp.ok) {
        throw new Error("Could not fetch live report data");
      }
      const consecutive = await failuresResp.json();
      const consecutiveFailures = (consecutive && typeof consecutive === "object") ? consecutive : {};
      const legacy = await _problemsFilterActionableRows(report, consecutiveFailures, retrainedMap);
      rows = legacy.rows;
      hiddenDead = legacy.hiddenDead;
      hiddenFixed = legacy.hiddenFixed;
      lastSeen = legacy.lastSeen;
    }

    _problemsAllRows = rows;
    const uiPrefs = await _problemsLoadUiPrefs();
    _problemsPopulateFilters(rows, uiPrefs);
    const visible = _problemsFilteredRows();

    if (hint) {
      const parts = [
        `${visible.length}${visible.length !== rows.length ? `/${rows.length}` : ""} need action`,
        `week ${lastSeen || "unknown"}`,
        `source ${statusSource}`,
        `repo ${urls.repo}`,
      ];
      if (hiddenDead) parts.push(`${hiddenDead} dead/disabled (hidden)`);
      if (hiddenFixed) parts.push(`${hiddenFixed} already OK (hidden)`);
      parts.push("fixed parishes leave this list after harvest + Refresh");
      hint.textContent = parts.join(" · ") + ".";
    }
    await _problemsRenderRows(visible);
  } catch (_e) {
    if (warning) warning.style.display = "block";
    _problemsAllRows = [];
    await _problemsRenderRows([]);
  } finally {
    if (empty && !empty.textContent) {
      empty.textContent = "";
    }
  }
}

const _PD_DOT_TITLES = { "🟢": "Recipe trained", "🟡": "Needs training", "🔴": "Dead website", "⚫": "Disabled", "📌": "Manual override URL set", "⬜": "Checking…" };

function _pdShowAddParishDialog(dioceseDisplayName, anchorEl) {
  const existing = document.querySelector(".pd-add-parish-row");
  if (existing) { existing.remove(); return; }
  const row = document.createElement("div");
  row.className = "pd-edit-row pd-add-parish-row";
  const label = document.createElement("div");
  label.style.cssText = "font-size:9px;color:#93c5fd;";
  label.textContent = `Add parish to ${dioceseDisplayName}:`;
  row.appendChild(label);
  const nameInp = document.createElement("input");
  nameInp.type = "text";
  nameInp.placeholder = "Parish name";
  nameInp.style.cssText = "width:100%;margin-bottom:4px;";
  row.appendChild(nameInp);
  const urlInp = document.createElement("input");
  urlInp.type = "url";
  urlInp.placeholder = "https://parish.com/bulletin.pdf";
  urlInp.style.cssText = "width:100%;";
  row.appendChild(urlInp);
  const btnRow = document.createElement("div");
  btnRow.className = "pd-edit-btns";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "green";
  saveBtn.textContent = "Save";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => row.remove());
  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    try {
      await _pdAddParish(dioceseDisplayName, nameInp.value, urlInp.value);
      setStatus(`✅ Added ${nameInp.value.trim()} to ${dioceseDisplayName}.`, "ok");
      row.remove();
      _pdRenderAll(document.getElementById("pd-search")?.value || "", _pdExcludes || []);
    } catch (err) {
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      saveBtn.disabled = false;
    }
  });
  btnRow.appendChild(saveBtn);
  btnRow.appendChild(cancelBtn);
  row.appendChild(btnRow);
  anchorEl.appendChild(row);
  nameInp.focus();
}

function _pdShowNewDioceseDialog() {
  const existing = document.querySelector(".pd-new-diocese-row");
  if (existing) { existing.remove(); return; }
  const container = document.getElementById("parish-dir-content");
  const row = document.createElement("div");
  row.className = "pd-edit-row pd-new-diocese-row";
  row.style.marginBottom = "8px";
  const label = document.createElement("div");
  label.style.cssText = "font-size:9px;color:#93c5fd;";
  label.textContent = "New diocese display name (e.g. Clogher Diocese):";
  row.appendChild(label);
  const inp = document.createElement("input");
  inp.type = "text";
  inp.placeholder = "Clogher Diocese";
  inp.style.cssText = "width:100%;";
  row.appendChild(inp);
  const btnRow = document.createElement("div");
  btnRow.className = "pd-edit-btns";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "green";
  saveBtn.textContent = "Create + push to GitHub";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => row.remove());
  saveBtn.addEventListener("click", async () => {
    saveBtn.disabled = true;
    try {
      await _pdCreateDiocese(inp.value);
      setStatus(
        "✅ New diocese saved. Harvesting will pick it up automatically. Its public webpage + Collated Bulletin PDF + OCR will appear once a harvest run produces its Collated Bulletin.",
        "ok"
      );
      row.remove();
      _pdRenderAll(document.getElementById("pd-search")?.value || "", _pdExcludes || []);
    } catch (err) {
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      saveBtn.disabled = false;
    }
  });
  btnRow.appendChild(saveBtn);
  btnRow.appendChild(cancelBtn);
  row.appendChild(btnRow);
  if (container?.firstChild) container.insertBefore(row, container.firstChild.nextSibling);
  else if (container) container.appendChild(row);
  inp.focus();
}

function _pdRenderAll(searchTerm, excludes) {
  const container = document.getElementById("parish-dir-content");
  _clearElement(container);
  const lc = (searchTerm || "").toLowerCase();

  const toolbarRow = document.createElement("div");
  toolbarRow.style.cssText = "margin-bottom:8px;";
  const newDioceseBtn = document.createElement("button");
  newDioceseBtn.type = "button";
  newDioceseBtn.className = "pd-btn green";
  newDioceseBtn.textContent = "➕ New diocese";
  newDioceseBtn.addEventListener("click", () => _pdShowNewDioceseDialog());
  toolbarRow.appendChild(newDioceseBtn);
  container.appendChild(toolbarRow);

  const byDiocese = {};
  for (const p of _pdAllParishes) {
    if (lc && !p.name.toLowerCase().includes(lc) && !(p.key || "").includes(lc)) continue;
    if (_pdShowBrokenOnly && !_pdIsBroken(p.key)) continue;
    if (!byDiocese[p.diocese]) byDiocese[p.diocese] = [];
    byDiocese[p.diocese].push(p);
  }

  const allDioceses = Object.keys(PD_EVIDENCE_FILES);
  let renderedAny = false;
  for (const diocese of allDioceses) {
    const parishes = byDiocese[diocese] || [];
    if (lc && parishes.length === 0) continue;
    if (_pdShowBrokenOnly && parishes.length === 0) continue;
    renderedAny = true;

    const dioceseEl = document.createElement("div");
    dioceseEl.className = "pd-diocese";
    const accordion = document.createElement("details");
    accordion.className = "pd-diocese-accordion";
    accordion.open = !!lc || parishes.length > 0;
    const title = document.createElement("summary");
    title.className = "pd-diocese-title";
    title.textContent = `${diocese} (${parishes.length})`;
    accordion.appendChild(title);
    const content = document.createElement("div");
    content.className = "pd-diocese-content";
    for (const parish of parishes) content.appendChild(_pdBuildRow(parish, excludes));

    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "pd-btn";
    addBtn.textContent = "➕ Add parish";
    addBtn.style.cssText = "margin-top:6px;font-size:10px;";
    addBtn.addEventListener("click", () => _pdShowAddParishDialog(diocese, content));
    content.appendChild(addBtn);

    accordion.appendChild(content);
    dioceseEl.appendChild(accordion);
    container.appendChild(dioceseEl);
  }

  if (!renderedAny) {
    let emptyMessage = "No parishes loaded.";
    if (lc) emptyMessage = "No matching parishes.";
    else if (_pdShowBrokenOnly) emptyMessage = "No broken parishes found.";
    else if (allDioceses.length === 0) emptyMessage = "No dioceses configured.";
    const emptyEl = document.createElement("div");
    emptyEl.textContent = emptyMessage;
    emptyEl.style.color = "#6b7280";
    emptyEl.style.fontSize = "10px";
    container.appendChild(emptyEl);
  }
}

function _pdUpdateBrokenInboxUi() {
  const banner = document.getElementById("pd-broken-banner");
  const text = document.getElementById("pd-broken-text");
  const toggleBtn = document.getElementById("pd-broken-toggle");
  if (!banner || !text || !toggleBtn) return;

  const brokenCount = _pdAllParishes.filter((p) => _pdIsBroken(p.key)).length;
  if (brokenCount > 0) {
    banner.style.display = "flex";
    text.textContent = `⚠️ ${brokenCount} Parish${brokenCount === 1 ? "" : "es"} ${brokenCount === 1 ? "needs" : "need"} attention`;
    toggleBtn.textContent = _pdShowBrokenOnly ? "Show All" : "Show Broken Only";
  } else {
    banner.style.display = "none";
    _pdShowBrokenOnly = false;
    toggleBtn.textContent = "Show Broken Only";
  }
}

function _pdUpdateStaleBannerUi(staleBulletins) {
  const banner = document.getElementById("stale-banner");
  const text = document.getElementById("stale-banner-text");
  const list = document.getElementById("stale-list");
  const toggleBtn = document.getElementById("stale-banner-toggle");
  if (!banner || !text || !list || !toggleBtn) return;

  const stale = Array.isArray(staleBulletins?.stale) ? staleBulletins.stale : [];
  const unknown = Array.isArray(staleBulletins?.unknown_date) ? staleBulletins.unknown_date : [];
  list.style.display = "none";
  toggleBtn.textContent = "Show";

  if (stale.length > 0) {
    banner.style.display = "block";
    banner.style.background = "#450a0a";
    banner.style.borderColor = "#7f1d1d";
    banner.style.color = "#fecaca";
    text.textContent = `⚠️ ${stale.length} bulletin(s) are stale — click Show to review`;
    toggleBtn.style.background = "#991b1b";

    _clearElement(list);
    const formatDaysOld = (days) => `${days} day${days === 1 ? "" : "s"}`;
    for (const item of stale) {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;align-items:center;gap:6px;padding:3px 0;border-bottom:1px solid rgba(127,29,29,0.5);";

      const label = document.createElement("div");
      const daysOld = Number(item?.days_old);
      label.textContent = `${item?.display_name || item?.key || "Unknown"}${Number.isFinite(daysOld) ? ` — ${formatDaysOld(daysOld)}` : ""}`;
      label.style.cssText = "font-size:10px;line-height:1.3;flex:1;";
      row.appendChild(label);

      const fixBtn = document.createElement("button");
      fixBtn.type = "button";
      fixBtn.className = "pd-btn";
      fixBtn.textContent = "Fix";
      fixBtn.style.background = "#991b1b";
      fixBtn.style.color = "#fee2e2";
      fixBtn.addEventListener("click", () => {
        if (item?.url) chrome.tabs.create({ url: item.url });
      });
      row.appendChild(fixBtn);
      list.appendChild(row);
    }
    return;
  }

  if (unknown.length > 0) {
    banner.style.display = "block";
    banner.style.background = "#0f172a";
    banner.style.borderColor = "#334155";
    banner.style.color = "#bfdbfe";
    text.textContent = `ℹ️ ${unknown.length} bulletins: date not in URL (informational — use Open to retrain if needed)`;
    toggleBtn.style.background = "#1d4ed8";
    _clearElement(list);
    for (const item of unknown) {
      const row = document.createElement("div");
      row.style.cssText =
        "display:flex;align-items:center;gap:6px;padding:3px 0;font-size:10px;line-height:1.3;border-bottom:1px solid rgba(51,65,85,0.7);";

      const label = document.createElement("div");
      label.textContent = item?.display_name || item?.key || "Unknown";
      label.style.cssText = "flex:1;";
      row.appendChild(label);

      if (item?.url) {
        const openLink = document.createElement("a");
        openLink.href = item.url;
        openLink.target = "_blank";
        openLink.rel = "noopener noreferrer";
        openLink.className = "stale-open-link";
        openLink.textContent = "Open";
        openLink.addEventListener("click", (e) => {
          e.preventDefault();
          chrome.tabs.create({ url: item.url });
        });
        row.appendChild(openLink);
      }
      list.appendChild(row);
    }
    return;
  }

  banner.style.display = "none";
  _clearElement(list);
  list.style.display = "none";
  toggleBtn.textContent = "Show";
}

function _pdBuildRow(parish, excludes) {
  const wrap = document.createElement("div");
  wrap.dataset.key = parish.key;

  const row = document.createElement("div");
  row.className = "pd-row";

  const dot = document.createElement("span");
  dot.className = "pd-status";
  dot.textContent = _pdStatusDot(parish);
  dot.title = _PD_DOT_TITLES[dot.textContent] || "";
  row.appendChild(dot);

  const nameEl = document.createElement("span");
  nameEl.className = "pd-name" + (parish.disabled ? " disabled" : "");
  nameEl.textContent = parish.name;
  nameEl.title = parish.pageUrl || parish.bulletinUrls[0] || parish.key;
  if (parish.pageUrl || parish.bulletinUrls[0]) {
    nameEl.addEventListener("click", () => {
      chrome.storage.local.set({
        ph_training_parish: {
          key: parish.key,
          name: parish.name,
          diocese: parish.diocese,
          hostname: (() => {
            const u = parish.pageUrl || parish.bulletinUrls[0] || "";
            try { return new URL(u).hostname.toLowerCase(); } catch (_e) { return ""; }
          })(),
        },
      });
      chrome.tabs.create({ url: parish.pageUrl || parish.bulletinUrls[0] });
    });
  }
  row.appendChild(nameEl);

  const editBtn = document.createElement("button");
  editBtn.className = "pd-btn";
  editBtn.textContent = "✏️";
  editBtn.title = "Edit bulletin URL → Save pushes to GitHub repo";
  editBtn.addEventListener("click", () => _pdShowEditRow(wrap, parish));
  row.appendChild(editBtn);

  const overrideBtn = document.createElement("button");
  overrideBtn.className = "pd-btn";
  overrideBtn.textContent = "📌";
  overrideBtn.title = "Quick override: save active tab URL (does not edit evidence file)";
  overrideBtn.addEventListener("click", () => _pdSetOverrideFromActiveTab(parish, dot, clearOverrideBtn));
  row.appendChild(overrideBtn);

  const clearOverrideBtn = document.createElement("button");
  clearOverrideBtn.className = "pd-btn";
  clearOverrideBtn.textContent = "🧹";
  clearOverrideBtn.title = "Clear quick override (📌) only — not evidence file";
  clearOverrideBtn.disabled = !_pdGetOverride(parish.key);
  clearOverrideBtn.style.opacity = clearOverrideBtn.disabled ? "0.4" : "1";
  clearOverrideBtn.addEventListener("click", () => _pdClearOverride(parish, dot, clearOverrideBtn));
  row.appendChild(clearOverrideBtn);

  const detailsBtn = document.createElement("button");
  detailsBtn.className = "pd-btn pd-subfolder-toggle";
  detailsBtn.textContent = "📁";
  detailsBtn.title = "Show parish details";
  row.appendChild(detailsBtn);

  const moveBtn = document.createElement("button");
  moveBtn.className = "pd-btn";
  moveBtn.textContent = "↔";
  moveBtn.title = "Move parish to another diocese (updates GitHub evidence + recipe)";
  moveBtn.addEventListener("click", () => _pdShowMoveDialog(parish, dot));
  row.appendChild(moveBtn);

  const removeBtn = document.createElement("button");
  removeBtn.className = "pd-btn red";
  removeBtn.textContent = "⛔";
  removeBtn.title = "Disable parish in harvest (marks DISABLED in evidence file)";
  removeBtn.addEventListener("click", async () => {
    if (!confirm(`Disable ${parish.name} in the harvester repo?`)) return;
    removeBtn.disabled = true;
    try {
      await _pdDisableParish(parish);
      dot.textContent = "⚫";
      nameEl.classList.add("disabled");
      setStatus(`✅ ${parish.name} disabled in evidence file.`, "ok");
    } catch (err) {
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      removeBtn.disabled = false;
    }
  });
  row.appendChild(removeBtn);

  const deleteBtn = document.createElement("button");
  deleteBtn.className = "pd-btn red";
  deleteBtn.textContent = "🗑";
  deleteBtn.title = "Delete parish from evidence file (removes entry entirely)";
  deleteBtn.addEventListener("click", async () => {
    if (!confirm(`Delete ${parish.name} from ${parish.diocese}? This removes the parish block from the evidence file.`)) return;
    deleteBtn.disabled = true;
    try {
      await _pdDeleteParish(parish);
      setStatus(`✅ ${parish.name} deleted from evidence file.`, "ok");
      _pdRenderAll(document.getElementById("pd-search")?.value || "", _pdExcludes || []);
    } catch (err) {
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      deleteBtn.disabled = false;
    }
  });
  row.appendChild(deleteBtn);

  if (!parish.disabled) {
    const deadBtn = document.createElement("button");
    deadBtn.className = "pd-btn red";
    deadBtn.textContent = "☠";
    deadBtn.title = "Mark as dead website";
    deadBtn.addEventListener("click", () => _pdMarkDead(parish, dot, deadBtn));
    row.appendChild(deadBtn);
  }

  const excl = document.createElement("input");
  excl.type = "checkbox";
  excl.className = "pd-excl";
  excl.title = "Exclude from Collated Bulletin this week";
  excl.checked = excludes.includes(parish.key);
  excl.addEventListener("change", async () => {
    excl.disabled = true;
    try {
      const current = await _pdLoadExcludes();
      const updated = excl.checked
        ? [...new Set([...current, parish.key])]
        : current.filter((k) => k !== parish.key);
      const res = await _pdSaveExcludes(updated);
      if (!res?.ok) { excl.checked = !excl.checked; setStatus(`❌ ${res?.error || "Save failed."}`, "err"); }
      else setStatus(`✅ ${parish.name} ${excl.checked ? "excluded from" : "included in"} Collated Bulletin.`, "ok");
    } catch (err) {
      excl.checked = !excl.checked; setStatus(`❌ ${err.message}`, "err");
    } finally {
      excl.disabled = false;
    }
  });
  row.appendChild(excl);

  const exclLabel = document.createElement("span");
  exclLabel.className = "pd-excl-label";
  exclLabel.textContent = "skip";
  row.appendChild(exclLabel);

  wrap.appendChild(row);
  const detailsWrap = document.createElement("div");
  detailsWrap.className = "pd-subfolder";
  detailsWrap.style.display = "none";
  wrap.appendChild(detailsWrap);
  detailsBtn.addEventListener("click", async () => {
    const opening = detailsWrap.style.display === "none";
    if (!opening) {
      detailsWrap.style.display = "none";
      detailsBtn.title = "Show parish details";
      return;
    }
    detailsWrap.style.display = "block";
    detailsBtn.title = "Hide parish details";
    _clearElement(detailsWrap);
    const loadingEl = document.createElement("div");
    loadingEl.className = "pd-subfolder-loading";
    loadingEl.textContent = "⏳ Loading parish details…";
    detailsWrap.appendChild(loadingEl);
    try {
      const details = await _pdBuildParishDetails(parish);
      _pdRenderSubfolder(detailsWrap, details);
    } catch (_e) {
      _clearElement(detailsWrap);
      const errorEl = document.createElement("div");
      errorEl.className = "pd-subfolder-error";
      errorEl.textContent = "Could not load parish details.";
      detailsWrap.appendChild(errorEl);
    }
  });
  return wrap;
}

function _pdShowMoveDialog(parish, dot) {
  const existing = document.querySelector(".pd-move-row");
  if (existing) { existing.remove(); return; }
  const row = document.createElement("div");
  row.className = "pd-edit-row pd-move-row";
  const label = document.createElement("div");
  label.style.cssText = "font-size:9px;color:#93c5fd;";
  label.textContent = `Move ${parish.name} to diocese:`;
  row.appendChild(label);
  const sel = document.createElement("select");
  sel.style.cssText = "width:100%;border:1px solid #374151;border-radius:4px;padding:4px;background:#1e293b;color:#f9fafb;font-size:10px;";
  for (const name of Object.keys(_pdDioceseTexts)) {
    if (name === parish.diocese) continue;
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  }
  row.appendChild(sel);
  const btnRow = document.createElement("div");
  btnRow.className = "pd-edit-btns";
  const goBtn = document.createElement("button");
  goBtn.type = "button";
  goBtn.className = "green";
  goBtn.textContent = "Move + push to GitHub";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  cancelBtn.addEventListener("click", () => row.remove());
  goBtn.addEventListener("click", async () => {
    goBtn.disabled = true;
    try {
      await _pdMoveParish(parish, sel.value);
      setStatus(`✅ Moved ${parish.name} to ${sel.value}. Refresh directory.`, "ok");
      row.remove();
      void loadParishDirectory();
    } catch (err) {
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      goBtn.disabled = false;
    }
  });
  btnRow.appendChild(goBtn);
  btnRow.appendChild(cancelBtn);
  row.appendChild(btnRow);
  const wrap = document.querySelector(`[data-key="${parish.key}"]`);
  if (wrap) wrap.appendChild(row);
}

function _pdShowEditRow(wrap, parish) {
  const existing = wrap.querySelector(".pd-edit-row");
  if (existing) { existing.remove(); return; }

  const info = _pdDioceseTexts[parish.diocese];
  const editRow = document.createElement("div");
  editRow.className = "pd-edit-row";

  const label = document.createElement("div");
  label.style.cssText = "font-size:9px;color:#93c5fd;";
  label.textContent = "Primary bulletin URL (updates evidence file — used by Sunday harvest):";
  editRow.appendChild(label);

  const hint = document.createElement("div");
  hint.style.cssText = "font-size:8px;color:#9ca3af;margin-bottom:4px;line-height:1.35;";
  hint.textContent =
    "Paste the real PDF or listing URL here. For a direct PDF (e.g. parishpress.net/.../bulletin.pdf), this replaces the old Facebook/link line. Use 📌 pin on active tab for a one-off override without editing evidence.";
  editRow.appendChild(hint);

  const inp = document.createElement("input");
  inp.type = "url";
  inp.value =
    parish.bulletinUrls[0] ||
    parish.pageUrl ||
    "";
  inp.placeholder = "https://parish.com/bulletin.pdf";
  editRow.appendChild(inp);

  const btnRow = document.createElement("div");
  btnRow.className = "pd-edit-btns";

  const inlineStatus = document.createElement("div");
  inlineStatus.style.cssText = "font-size:9px;margin-top:3px;min-height:12px;";
  const setInlineStatus = (msg, type) => {
    inlineStatus.textContent = msg;
    inlineStatus.style.color = type === "err" ? "#fca5a5" : "#86efac";
  };

  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.className = "green";
  saveBtn.textContent = "💾 Save";
  saveBtn.addEventListener("click", async () => {
    const newUrl = inp.value.trim();
    if (!newUrl) { setInlineStatus("❌ URL is required.", "err"); setStatus("❌ URL is required.", "err"); return; }
    if (!info)   { setInlineStatus("❌ Evidence file not loaded.", "err"); setStatus("❌ Evidence file not loaded.", "err"); return; }
    saveBtn.disabled = true; saveBtn.textContent = "⏳ Saving…";
    setInlineStatus("Saving…", "ok");
    try {
      let updated = _pdUpdatePrimaryBulletinUrl(info.text, parish.name, newUrl);
      updated = _pdUpdatePageUrl(updated, parish.name, newUrl);
      const res = await _pdGhPush(info.path, updated, `evidence: update bulletin URL for ${parish.name} [from extension]`);
      if (res?.ok) {
        info.text = updated;
        if (parish.bulletinUrls.length > 0) parish.bulletinUrls[0] = newUrl;
        else parish.bulletinUrls.push(newUrl);
        parish.pageUrl = newUrl;
        delete _pdParishDetailsCache[parish.key];
        setInlineStatus("✅ Saved. Triggering harvest rebuild…", "ok");
        setStatus(`✅ Saved page URL for ${parish.name}. Triggering harvest…`, "ok");
        editRow.remove();
        _pdDispatchHarvest(parish.key, parish.diocese).then((d) => {
          if (d?.ok) {
            setStatus(`✅ Saved page URL for ${parish.name} and triggered harvest rebuild.`, "ok");
          } else {
            setStatus(
              `⚠️ Recipe saved OK. Harvest trigger failed — check GitHub token has workflow scope. (${d?.error || "unknown"})`,
              "warn"
            );
          }
        });
      } else {
        const errMsg = res?.error || "Save failed.";
        setInlineStatus(`❌ ${errMsg}`, "err");
        setStatus(`❌ ${errMsg}`, "err");
      }
    } catch (err) {
      setInlineStatus(`❌ ${err.message}`, "err");
      setStatus(`❌ ${err.message}`, "err");
    } finally {
      saveBtn.disabled = false; saveBtn.textContent = "💾 Save";
    }
  });
  btnRow.appendChild(saveBtn);

  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.style.cssText = "background:#374151;color:#d1d5db;";
  cancelBtn.textContent = "✕ Cancel";
  cancelBtn.addEventListener("click", () => editRow.remove());
  btnRow.appendChild(cancelBtn);

  editRow.appendChild(btnRow);
  editRow.appendChild(inlineStatus);
  wrap.appendChild(editRow);
  inp.focus();
}

async function _pdSetOverrideFromActiveTab(parish, dotEl, clearBtn) {
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (err) {
    setStatus(`❌ Could not read active tab: ${err.message}`, "err");
    return;
  }
  const url = (tab?.url || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    setStatus("❌ Active tab URL must be http/https.", "err");
    return;
  }
  const type = _pdInferOverrideType(url);
  const overrides = await _pdLoadOverrides();
  overrides[parish.key] = {
    url,
    type,
    updated_at: new Date().toISOString(),
    source: "extension-sidepanel",
  };
  const res = await _pdSaveOverrides(overrides);
  if (!res?.ok) {
    setStatus(`❌ ${res?.error || "Failed to save override."}`, "err");
    return;
  }
  dotEl.textContent = "📌";
  dotEl.title = _PD_DOT_TITLES["📌"];
  clearBtn.disabled = false;
  clearBtn.style.opacity = "1";
  delete _pdParishDetailsCache[parish.key];
  setStatus(`✅ Saved manual override for ${parish.name}.`, "ok");
}

async function _pdClearOverride(parish, dotEl, clearBtn) {
  const overrides = await _pdLoadOverrides();
  if (!overrides[parish.key]) {
    setStatus(`ℹ️ ${parish.name} has no override set.`, "info");
    return;
  }
  delete overrides[parish.key];
  const res = await _pdSaveOverrides(overrides);
  if (!res?.ok) {
    setStatus(`❌ ${res?.error || "Failed to clear override."}`, "err");
    return;
  }
  dotEl.textContent = _pdStatusDot(parish);
  dotEl.title = _PD_DOT_TITLES[dotEl.textContent] || "";
  clearBtn.disabled = true;
  clearBtn.style.opacity = "0.4";
  delete _pdParishDetailsCache[parish.key];
  setStatus(`✅ Cleared override for ${parish.name}.`, "ok");
}

async function _pdMarkDead(parish, dotEl, btnEl) {
  if (!confirm(`Mark "${parish.name}" as a dead website?\nThis pushes a dead recipe to GitHub.`)) return;
  btnEl.disabled = true;
  setStatus(`⏳ Marking ${parish.name} as dead…`, "ok");
  try {
    const recipe = {
      parish_key: parish.key,
      display_name: parish.name,
      diocese: parish.diocese,
      start_url: parish.pageUrl || parish.bulletinUrls[0] || "",
      status: "dead_url",
      skip: true,
      dead_reason: "Marked dead from browser extension.",
      reason: "Marked dead from browser extension.",
      steps: [],
    };
    const res = await new Promise((resolve, reject) => {
      chrome.runtime.sendMessage({ type: "push_recipe", parish_key: parish.key, recipe }, (r) => {
        if (chrome.runtime.lastError) { reject(new Error(chrome.runtime.lastError.message)); return; }
        resolve(r);
      });
    });
    if (res?.ok) {
      _pdRecipeCache[parish.key] = "dead";
      dotEl.textContent = "🔴";
      dotEl.title = "Dead website";
      setStatus(`✅ ${parish.name} marked as dead.`, "ok");
      if (_spPanels.problems.panel.classList.contains("active")) {
        void loadProblemsDashboard();
      }
    } else {
      setStatus(`❌ ${res?.error || "Failed."}`, "err");
    }
  } catch (err) {
    setStatus(`❌ ${err.message}`, "err");
  } finally {
    btnEl.disabled = false;
  }
}

// ── Auto-detect active tab's parish ──────────────────────────────────────
// After evidence is loaded, match the active tab URL against known parishes
// and store the result in chrome.storage so the toolbar push form auto-fills.

async function _pdAutoDetectFromActiveTab() {
  if (_pdAllParishes.length === 0) return;
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  } catch (_e) { return; }
  if (!tab?.url || !/^https?:\/\//i.test(tab.url)) return;

  const tabKey = _pdUrlToKey(tab.url);
  if (!tabKey) return;

  const match = _pdAllParishes.find((p) => {
    if (p.key === tabKey) return true;
    const allUrls = [p.pageUrl, ...p.bulletinUrls].filter(Boolean);
    return allUrls.some((u) => _pdUrlToKey(u) === tabKey);
  });

  if (match) {
    try {
      await chrome.storage.local.set({
        ph_training_parish: {
          key: match.key,
          name: match.name,
          diocese: match.diocese,
          hostname: (() => {
            try { return new URL(tab.url).hostname.toLowerCase(); } catch (_e) { return ""; }
          })(),
        },
      });
      setStatus(`✅ Active tab auto-detected as: ${match.name}`, "ok");
    } catch (_e) {
      // Storage write failure is non-fatal.
    }
  }
}

// ── Main load ─────────────────────────────────────────────────────────────

async function loadParishDirectory() {
  const loadingEl = document.getElementById("parish-dir-loading");
  const errorEl   = document.getElementById("parish-dir-error");
  const container = document.getElementById("parish-dir-content");
  if (!loadingEl || !errorEl || !container) return;

  loadingEl.style.display = "block";
  errorEl.style.display   = "none";
  errorEl.textContent = "";
  _clearElement(container);
  _pdAllParishes = []; _pdDioceseTexts = {}; _pdExcludes = null; _pdOverrides = null; _pdLastIncluded = null;
  Object.keys(_pdParishDetailsCache).forEach((k) => delete _pdParishDetailsCache[k]);
  _pdConsecutiveFailures = {};
  _pdShowBrokenOnly = false;
  _pdUpdateBrokenInboxUi();
  _pdUpdateStaleBannerUi({ stale: [], unknown_date: [] });

  try {
    await _pdLoadDioceseConfig();
    const [excludes, _overrides, consecutiveFailures, staleBulletins, _lastIncluded, ...evidenceResults] = await Promise.all([
      _pdLoadExcludes(),
      _pdLoadOverrides(),
      _pdLoadConsecutiveFailures(),
      _pdLoadStaleBulletins(),
      _pdLoadLastIncluded(),
      ...Object.entries(PD_EVIDENCE_FILES).map(([diocese, path]) =>
        _pdGhFetch(path)
          .then(({ content }) => ({ diocese, path, content }))
          .catch((e) => ({ diocese, path, error: e.message }))
      ),
    ]);

    for (const r of evidenceResults) {
      if (r.error) {
        console.warn(`Parish Directory: ${r.diocese}: ${r.error}`);
        _pdDioceseTexts[r.diocese] = { text: "", path: r.path };
        continue;
      }
      _pdDioceseTexts[r.diocese] = { text: r.content, path: r.path };
      _pdAllParishes.push(..._pdParseEvidence(r.content, r.diocese));
    }
    _pdConsecutiveFailures = consecutiveFailures || {};
    _pdHarvestReport = null;
    _pdParishStatusDoc = null;
    await _pdLoadParishStatusDoc(true);
    await _pdLoadHarvestReport();

    if (Object.keys(PD_EVIDENCE_FILES).length === 0 || Object.keys(_pdDioceseTexts).length === 0) {
      loadingEl.style.display = "none";
      const failed = evidenceResults.filter((r) => r.error).map((r) => `${r.diocese}: ${r.error}`);
      errorEl.textContent = failed.length
        ? `⚠️ No dioceses loaded. ${failed.join(" | ")}`
        : "⚠️ No dioceses configured — check GitHub settings.";
      errorEl.style.display = "block";
      return;
    }

    loadingEl.style.display = "none";
    _pdUpdateBrokenInboxUi();
    _pdUpdateStaleBannerUi(staleBulletins);
    _pdRenderAll("", excludes);

    // Asynchronously load recipe status and refresh dots
    (async () => {
      await Promise.all(_pdAllParishes.map((p) => p.key ? _pdCheckRecipe(p.key) : Promise.resolve()));
      const c = document.getElementById("parish-dir-content");
      for (const p of _pdAllParishes) {
        if (!p.key) continue;
        const el = c.querySelector(`[data-key="${CSS.escape(p.key)}"] .pd-status`);
        if (el) { el.textContent = _pdStatusDot(p); el.title = _PD_DOT_TITLES[el.textContent] || ""; }
      }
    })();

    // Auto-detect parish from the currently active tab and persist as
    // ph_training_parish so the toolbar push form can auto-fill without manual entry.
    _pdAutoDetectFromActiveTab();

  } catch (err) {
    loadingEl.style.display = "none";
    errorEl.textContent = `❌ ${err.message}`;
    errorEl.style.display = "block";
  }
}

const _pdDetailsEl = document.getElementById("parish-dir-details");
if (_pdDetailsEl) {
  _pdDetailsEl.addEventListener("toggle", function () {
    if (this.open) loadParishDirectory();
  });
  if (_pdDetailsEl.open) loadParishDirectory();
}
document.getElementById("pd-refresh").addEventListener("click", () => {
  Object.keys(_pdRecipeCache).forEach((k) => delete _pdRecipeCache[k]);
  Object.keys(_pdParishDetailsCache).forEach((k) => delete _pdParishDetailsCache[k]);
  _pdHarvestReport = null;
  _pdParishStatusDoc = null;
  _pdExcludes = null;
  _pdOverrides = null;
  _pdConsecutiveFailures = {};
  _pdShowBrokenOnly = false;
  loadParishDirectory();
  void loadProblemsDashboard();
});
document.getElementById("pd-search").addEventListener("input", function () {
  if (_pdAllParishes.length > 0) _pdRenderAll(this.value, _pdExcludes || []);
});
document.getElementById("pd-broken-toggle").addEventListener("click", function () {
  if (_pdAllParishes.length === 0) return;
  _pdShowBrokenOnly = !_pdShowBrokenOnly;
  _pdUpdateBrokenInboxUi();
  _pdRenderAll(document.getElementById("pd-search").value || "", _pdExcludes || []);
});
document.getElementById("stale-banner-toggle").addEventListener("click", function () {
  const list = document.getElementById("stale-list");
  if (!list) return;
  const isOpen = list.style.display !== "none";
  list.style.display = isOpen ? "none" : "block";
  this.textContent = isOpen ? "Show" : "Hide";
});

_spPanels.trainer.tab.addEventListener("click", () => _spShowPanel("trainer"));
_spPanels.problems.tab.addEventListener("click", () => _spShowPanel("problems"));
const problemsHowtoToggle = document.getElementById("problems-howto-toggle");
const problemsHowto = document.getElementById("problems-howto");
if (problemsHowtoToggle && problemsHowto) {
  problemsHowtoToggle.addEventListener("click", () => {
    const open = problemsHowto.style.display !== "none";
    problemsHowto.style.display = open ? "none" : "block";
    problemsHowtoToggle.textContent = open ? "Show how-to ▸" : "Hide how-to ▾";
  });
}
for (const id of ["problems-filter-diocese", "problems-filter-category", "problems-sort"]) {
  const el = document.getElementById(id);
  if (!el) continue;
  el.addEventListener("change", () => {
    void _problemsSaveUiPrefs();
    void _problemsRenderRows(_problemsFilteredRows());
  });
}
const problemsRefreshBtn = document.getElementById("problems-refresh-btn");
if (problemsRefreshBtn) {
  problemsRefreshBtn.addEventListener("click", () => {
    problemsRefreshBtn.disabled = true;
    problemsRefreshBtn.textContent = "↻ …";
    void loadProblemsDashboard().finally(() => {
      problemsRefreshBtn.disabled = false;
      problemsRefreshBtn.textContent = "↻ Refresh";
    });
  });
}
if (!_problemsAutoRefreshTimer) {
  _problemsAutoRefreshTimer = setInterval(() => {
    void loadProblemsDashboard();
  }, PROBLEMS_AUTO_REFRESH_MS);
}
const problemsFullHarvestBtn = document.getElementById("problems-full-harvest-btn");
if (problemsFullHarvestBtn) {
  problemsFullHarvestBtn.addEventListener("click", () => {
    void (async () => {
      problemsFullHarvestBtn.disabled = true;
      problemsFullHarvestBtn.textContent = "⏳ …";
      setStatus("⏳ Starting full harvest on GitHub (all parishes)…", "warn");
      const result = await _pdDispatchFullHarvest();
      if (!result.ok) {
        setStatus(`❌ Full harvest failed to start: ${result.error}`, "err");
        problemsFullHarvestBtn.disabled = false;
        problemsFullHarvestBtn.textContent = "▶ Full harvest";
        return;
      }
      setStatus(
        "✅ Full harvest started (30–60 min). Open GitHub Actions → Harvest Parish Bulletins to watch progress, then tap Refresh here.",
        "ok"
      );
      problemsFullHarvestBtn.disabled = false;
      problemsFullHarvestBtn.textContent = "▶ Full harvest";
    })();
  });
}
_spShowPanel("problems");
void loadProblemsDashboard();
void _updateDriveTrainerWarning();
if (chrome.tabs?.onActivated) {
  chrome.tabs.onActivated.addListener(() => {
    void _updateDriveTrainerWarning();
  });
}
if (chrome.tabs?.onUpdated) {
  chrome.tabs.onUpdated.addListener((_tabId, change) => {
    if (change.url || change.status === "complete") void _updateDriveTrainerWarning();
  });
}

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[PROBLEMS_RECIPE_RETRAINED_KEY]) {
    void loadProblemsDashboard();
  }
});

// ── Crop done notification ─────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "problems_refresh") {
    _spShowPanel("problems");
    void loadProblemsDashboard().then(() => {
      if (message.parish_key) {
        void _problemsWatchParishHarvest(
          message.parish_key,
          message.display_name || message.parish_key,
          message.dispatch_at
        );
      }
    });
    return;
  }
  if (message?.type !== "crop_done") return;
  const x = Number(message.x ?? 0);
  const y = Number(message.y ?? 0);
  const width = Number(message.width ?? 0);
  const height = Number(message.height ?? 0);
  const pageX = Number(message.pageX ?? x);
  const pageY = Number(message.pageY ?? y);
  const elementSelector = message.element_selector || "";

  void withActiveTab((tab) => {
    const payload = {
      type: "mark_crop",
      x,
      y,
      width,
      height,
      pageX,
      pageY,
      element_selector: elementSelector,
    };
    console.log("[PH-SAVE]", { action: "mark_crop", request: payload, phase: "request" });
    chrome.runtime.sendMessage({
      type: "dispatch_to_tab",
      tabId: tab.id,
      payload,
      allowInject: true,
    }, (result) => {
      console.log("[PH-SAVE]", { action: "mark_crop", request: payload, response: result || null });
      if (chrome.runtime.lastError) {
        setStatus(`❌ Could not save crop: ${chrome.runtime.lastError.message}`, "err");
        return;
      }
      if (!result?.ok) {
        setStatus(`❌ ${result?.reason || _dispatchErrorText(result)}`, "err");
        return;
      }
      setStatus(`✂️ Crop saved (${Math.round(width)}×${Math.round(height)})`, "ok");
    });
  });
});
