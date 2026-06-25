const manifest = chrome.runtime.getManifest();
const versionEl = document.getElementById("ext-version");
if (versionEl) versionEl.textContent = `v${manifest.version}`;

const statusEl = document.getElementById("status");
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

function setStatusText(text) {
  statusEl.textContent = text;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function formatDispatchError(result) {
  if (!result) return "Could not communicate with page. Try refreshing.";
  if (result.reason === "unsupported_url") {
    return "This tab cannot be scripted. Open a normal http/https page.";
  }
  if (result.reason === "inject_failed") {
    return "Page script bridge failed to load. Refresh the page and try again.";
  }
  if (result.reason === "receiver_unavailable") {
    const detail = String(result.error || "").trim();
    if (detail) {
      return `${detail} Refresh the tab, or click the toolbar icon again, then retry.`;
    }
    return "Page bridge not responding. Refresh the tab, or click the toolbar icon again, then retry.";
  }
  if (result.reason === "tab_not_found") {
    return "Could not access active tab.";
  }
  return `Could not communicate with page. ${result.error || "Try refreshing."}`;
}

async function tabsSend(tabId, message) {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

async function injectFiles(tabId, files) {
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

async function ensureTabBridge(tabId) {
  let ping = await tabsSend(tabId, { type: "ph_ping" });
  if (!ping?.ok) {
    const bridgeInject = await injectFiles(tabId, TRAINER_BRIDGE_FILES);
    if (!bridgeInject.ok) {
      return { ok: false, reason: "inject_failed", error: bridgeInject.error || "Could not inject page bridge." };
    }
    for (let attempt = 0; attempt < 40; attempt++) {
      ping = await tabsSend(tabId, { type: "ph_ping" });
      if (ping?.ok) break;
      await sleep(100);
    }
  }
  if (!ping?.ok) {
    return { ok: false, reason: "receiver_unavailable", error: "Page bridge did not start on this tab." };
  }

  let ready = await tabsSend(tabId, { type: "ph_bridge_ready" });
  if (!ready?.ok) {
    const heavyInject = await injectFiles(tabId, TRAINER_HEAVY_FILES);
    if (!heavyInject.ok) {
      return { ok: false, reason: "inject_failed", error: heavyInject.error || "Could not inject trainer scripts." };
    }
    for (let attempt = 0; attempt < 80; attempt++) {
      ready = await tabsSend(tabId, { type: "ph_bridge_ready" });
      if (ready?.ok) break;
      await sleep(150);
    }
  }

  return { ok: true, partial: !ready?.ok };
}

async function dispatchToActiveTab(message) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) {
    return { ok: false, reason: "tab_not_found" };
  }
  if (!/^https?:\/\//i.test(tab.url || "")) {
    return { ok: false, reason: "unsupported_url" };
  }

  const bridge = await ensureTabBridge(tab.id);
  if (!bridge.ok) {
    return bridge;
  }

  const direct = await tabsSend(tab.id, message);
  if (direct?.ok) {
    return direct;
  }

  return await new Promise((resolve) => {
    chrome.runtime.sendMessage(
      {
        type: "dispatch_to_tab",
        tabId: tab.id,
        payload: message,
        allowInject: true,
      },
      (result) => {
        if (chrome.runtime.lastError) {
          resolve({
            ok: false,
            reason: "runtime_error",
            error: chrome.runtime.lastError.message,
          });
          return;
        }
        resolve(result || { ok: false, reason: "dispatch_error", error: direct?.error || "no_explicit_ok_from_page" });
      }
    );
  });
}

async function sendToActiveTab(message) {
  setStatusText("Connecting to page…");
  let result = await dispatchToActiveTab(message);
  if (!result?.ok && result.reason === "receiver_unavailable") {
    await sleep(800);
    result = await dispatchToActiveTab(message);
  }
  if (!result?.ok) {
    if (result.reason === "runtime_error") {
      setStatusText(`Could not communicate with extension background: ${result.error}`);
      return;
    }
    setStatusText(formatDispatchError(result));
    return;
  }

  if (message.type === "show_toolbar") {
    setStatusText(result.full === false ? "Toolbar loading on page…" : "Toolbar shown.");
  }
}

document.getElementById("open-operator").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("sidepanel.html") });
  setStatusText("Opened operator console.");
});

const showToolbarBtn = document.getElementById("show-toolbar");
if (showToolbarBtn) {
  showToolbarBtn.addEventListener("click", () => {
    void sendToActiveTab({ type: "show_toolbar" });
  });
}

// ── GitHub Settings ────────────────────────────────────────────────────────

chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => {
  const patInput  = document.getElementById("gh-pat");
  const repoInput = document.getElementById("gh-repo");
  if (patInput  && r.gh_pat)  patInput.value  = r.gh_pat;
  if (repoInput) repoInput.value = phResolveGhRepo(r.gh_repo);
});

document.getElementById("gh-save").addEventListener("click", () => {
  const pat  = (document.getElementById("gh-pat").value  || "").trim();
  const repo = phResolveGhRepo((document.getElementById("gh-repo").value || "").trim());
  const ghStatusEl = document.getElementById("gh-save-status");
  chrome.storage.local.set({
    gh_pat: pat,
    gh_repo: repo,
  }, () => {
    if (chrome.runtime.lastError) {
      ghStatusEl.textContent = `❌ Save failed: ${chrome.runtime.lastError.message}`;
      ghStatusEl.style.color = "#fca5a5";
      setTimeout(() => { ghStatusEl.textContent = ""; }, 4000);
      return;
    }
    if (!pat) {
      ghStatusEl.textContent = "⚠️ Saved. Add your GitHub PAT to enable recipe push.";
      ghStatusEl.style.color = "#fde68a";
    } else {
      ghStatusEl.textContent = `✅ Settings saved for ${repo}.`;
      ghStatusEl.style.color = "#86efac";
    }
    setTimeout(() => { ghStatusEl.textContent = ""; }, 3000);
  });
});

const diagBtn = document.getElementById("run-diag");
const diagSaveBtn = document.getElementById("save-diag-github");
const diagSaveStatusEl = document.getElementById("diag-save-status");
const diagResultsEl = document.getElementById("diag-results");
const diagCopyBtn = document.getElementById("diag-copy");

let _diagTextLines = [];
let _lastDiagReport = null;
const _diagCopyButtonLabel = "📋 Copy diagnostic info (paste to AI)";

function _addDiagRow(icon, text) {
  if (!diagResultsEl) return null;
  const row = document.createElement("div");
  row.style.cssText = "display:flex;align-items:baseline;gap:4px;";
  const iconEl = document.createElement("span");
  iconEl.textContent = icon + " ";
  const textEl = document.createElement("span");
  textEl.textContent = text;
  row.append(iconEl, textEl);
  diagResultsEl.appendChild(row);
  return row;
}

function _clipLinesTo4000Chars(lines) {
  const safeLines = [];
  let used = 0;
  let truncated = false;
  for (const line of lines) {
    const next = String(line || "");
    const delta = next.length + 1;
    if (used + delta > 4000) {
      truncated = true;
      break;
    }
    safeLines.push(next);
    used += delta;
  }
  if (truncated && safeLines.length > 0) {
    safeLines.push("... (output truncated)");
  }
  return safeLines;
}

async function _fetchGitHubUserLogin(pat) {
  if (!pat) return "";
  try {
    const patRes = await fetch("https://api.github.com/user", {
      headers: { Authorization: `token ${pat}`, "User-Agent": "ParishHarvester" },
    });
    if (!patRes.ok) return "";
    const patData = await patRes.json();
    return String(patData?.login || "");
  } catch (_e) {
    return "";
  }
}

async function runDiagnostics() {
  if (!diagResultsEl) return;
  diagResultsEl.replaceChildren();
  _diagTextLines = [];
  if (diagCopyBtn) diagCopyBtn.style.display = "none";

  const versionLine = `Extension version: ${chrome.runtime.getManifest().version}`;
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const activeUrl = String(activeTab?.url || "").trim();
  const activeTabIsHttp = /^https?:\/\//i.test(activeUrl);

  let fullReportText = "";
  if (activeTab?.id && activeTabIsHttp) {
    const bridge = await ensureTabBridge(activeTab.id);
    if (bridge.ok) {
      const diag = await tabsSend(activeTab.id, { type: "ph_run_full_diagnosis" });
      if (diag?.ok && diag.text) {
        fullReportText = String(diag.text);
        _lastDiagReport = diag.report || null;
      }
    }
  }

  if (fullReportText) {
    const dumpLines = _clipLinesTo4000Chars(fullReportText.split("\n"));
    _diagTextLines = dumpLines;
    const preview = dumpLines.slice(0, 12);
    for (const line of preview) {
      if (!line.trim()) continue;
      const icon = line.startsWith("🔴") ? "🔴" : line.startsWith("🟡") ? "🟡" : line.startsWith("🔵") ? "🔵" : "ℹ️";
      _addDiagRow(icon, line.replace(/^[🔴🟡🔵🟢]\s*/, ""));
    }
    if (dumpLines.length > preview.length) {
      _addDiagRow("ℹ️", `… ${dumpLines.length - preview.length} more lines — tap Copy for full report`);
    }
    if (diagCopyBtn) diagCopyBtn.style.display = "";
    return;
  }

  const userAgentLine = `Browser user-agent: ${navigator.userAgent || "n/a"}`;
  const activeTabUrlLine = `Active tab URL: ${activeTabIsHttp ? activeUrl : "n/a — extension tab"}`;
  const activeTabTypeLine = `Active tab is real http(s) page: ${activeTabIsHttp ? "yes" : "no"}`;

  let bridgeLine = "Page bridge ping: n/a";
  if (activeTab?.id && activeTabIsHttp) {
    const bridge = await ensureTabBridge(activeTab.id);
    if (bridge.ok) {
      const ready = await tabsSend(activeTab.id, { type: "ph_bridge_ready" });
      bridgeLine = ready?.ok
        ? "Page bridge ping: ok (full toolbar ready)"
        : "Page bridge ping: ok (stub toolbar only — wait a few seconds)";
    } else {
      bridgeLine = `Page bridge ping: failed (${bridge.error || bridge.reason || "unknown"})`;
    }
  }

  const allLocalStorage = await new Promise((resolve) => chrome.storage.local.get(null, resolve));
  const pat = typeof allLocalStorage.gh_pat === "string" ? allLocalStorage.gh_pat.trim() : "";
  const repo = phResolveGhRepo(allLocalStorage.gh_repo);
  const ghLogin = await _fetchGitHubUserLogin(pat);

  const patLine = `GitHub PAT present: ${pat ? "yes" : "no"}${ghLogin ? ` (authenticated user: ${ghLogin})` : ""}`;
  const repoLine = `GitHub repo configured: ${repo}`;
  const patternLine = "Open a parish website tab and run again for full diagnosis kit.";

  const dumpLines = _clipLinesTo4000Chars([
    "Parish Trainer diagnostic dump (basic — open a parish tab for full kit)",
    "========================================================================",
    versionLine,
    userAgentLine,
    activeTabUrlLine,
    activeTabTypeLine,
    bridgeLine,
    patLine,
    repoLine,
    patternLine,
    "Paste this whole block to your AI assistant.",
  ]);
  _diagTextLines = dumpLines;

  _addDiagRow("ℹ️", versionLine);
  _addDiagRow("📄", activeTabUrlLine);
  _addDiagRow("🔍", activeTabTypeLine);
  _addDiagRow("🌉", bridgeLine);
  _addDiagRow("🔐", patLine);
  _addDiagRow("📦", repoLine);
  _addDiagRow("📚", patternLine);
  _addDiagRow("📋", "Diagnostic text is ready to copy.");

  if (diagCopyBtn) diagCopyBtn.style.display = "";
}

if (diagBtn) {
  diagBtn.addEventListener("click", () => {
    void runDiagnostics();
  });
}

if (diagSaveBtn) {
  diagSaveBtn.addEventListener("click", async () => {
    if (diagSaveStatusEl) diagSaveStatusEl.textContent = "⏳ Saving to GitHub…";
    const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!activeTab?.id || !/^https?:\/\//i.test(activeTab.url || "")) {
      if (diagSaveStatusEl) diagSaveStatusEl.textContent = "Open a parish website tab first.";
      return;
    }
    const bridge = await ensureTabBridge(activeTab.id);
    if (!bridge.ok) {
      if (diagSaveStatusEl) diagSaveStatusEl.textContent = formatDispatchError(bridge);
      return;
    }
  const diag = await tabsSend(activeTab.id, { type: "ph_run_full_diagnosis" });
    if (!diag?.ok) {
      if (diagSaveStatusEl) diagSaveStatusEl.textContent = "Could not run diagnosis on page.";
      return;
    }
    const report = diag.report || null;
    const parishKey = report?.parish_key || "";
    const res = await new Promise((resolve) => {
      chrome.runtime.sendMessage(
        {
          type: "ph_save_diagnosis",
          parish_key: parishKey,
          diagnosis: report,
          source: "popup_manual",
        },
        (r) => resolve(r || { ok: false, error: "No response" })
      );
    });
    if (res?.ok) {
      if (diagSaveStatusEl) {
        diagSaveStatusEl.textContent = `✅ Saved parishes/training_diagnosis/${parishKey || "?"}.json`;
      }
    } else if (diagSaveStatusEl) {
      diagSaveStatusEl.textContent = `❌ ${res?.error || "Save failed"}`;
    }
  });
}

if (diagCopyBtn) {
  diagCopyBtn.style.display = "none";
  diagCopyBtn.textContent = _diagCopyButtonLabel;
  diagCopyBtn.addEventListener("click", () => {
    const text = _diagTextLines.join("\n");
    navigator.clipboard.writeText(text).then(() => {
      diagCopyBtn.textContent = "✅ Copied!";
      setTimeout(() => { diagCopyBtn.textContent = _diagCopyButtonLabel; }, 2000);
    }).catch((_e) => {
      diagCopyBtn.textContent = "❌ Copy failed";
      setTimeout(() => { diagCopyBtn.textContent = _diagCopyButtonLabel; }, 2000);
    });
  });
}

// ── Dead / broken websites ─────────────────────────────────────────────────

const deadCurrentEl = document.getElementById("dead-current");
const deadReasonEl = document.getElementById("dead-reason");
const deadDisableEvidenceEl = document.getElementById("dead-disable-evidence");
const deadMarkBtn = document.getElementById("dead-mark-btn");
const deadStatusEl = document.getElementById("dead-status");
const deadListEl = document.getElementById("dead-list");

let _currentDeadParish = null;

function _bgMessage(payload) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(payload, (result) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }
      resolve(result || { ok: false, error: "No response from background." });
    });
  });
}

function _setDeadStatus(text, isError = false) {
  if (!deadStatusEl) return;
  deadStatusEl.textContent = text;
  deadStatusEl.style.color = isError ? "#fca5a5" : "#86efac";
}

function _formatDeadDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  } catch (_e) {
    return "";
  }
}

async function _renderDeadList() {
  if (!deadListEl) return;
  const res = await _bgMessage({ type: "list_dead_parishes" });
  const list = res?.ok && Array.isArray(res.parishes) ? res.parishes : [];
  deadListEl.replaceChildren();
  if (!list.length) {
    const empty = document.createElement("span");
    empty.style.cssText = "color:#6b7280;font-size:10px;";
    empty.textContent = "No dead sites remembered yet.";
    deadListEl.appendChild(empty);
    return;
  }
  for (const p of list) {
    const row = document.createElement("div");
    row.className = "dead-row";
    const info = document.createElement("div");
    info.style.flex = "1";
    const title = document.createElement("div");
    title.innerHTML = `<strong style="color:#fca5a5;">${p.name || p.key}</strong> <span style="color:#6b7280;">(${p.key})</span>`;
    const meta = document.createElement("div");
    meta.style.color = "#9ca3af";
    meta.textContent = [
      p.diocese || "",
      p.url || "",
      p.marked_at ? `marked ${_formatDeadDate(p.marked_at)}` : "",
    ].filter(Boolean).join(" · ");
    const note = document.createElement("div");
    note.style.color = "#d1d5db";
    note.textContent = p.reason || "";
    info.append(title, meta, note);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.textContent = "✕";
    removeBtn.title = "Remove from local reminder list (does not re-enable harvest)";
    removeBtn.addEventListener("click", async () => {
      await _bgMessage({ type: "remove_dead_parish_local", parish_key: p.key });
      await _renderDeadList();
      _setDeadStatus(`Removed ${p.name || p.key} from local list.`);
    });

    row.append(info, removeBtn);
    deadListEl.appendChild(row);
  }
}

async function _detectCurrentParishForDead() {
  if (!deadCurrentEl) return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = String(tab?.url || "").trim();
  if (!/^https?:\/\//i.test(url)) {
    _currentDeadParish = null;
    deadCurrentEl.textContent = "Open a parish website tab to detect it here.";
    if (deadMarkBtn) deadMarkBtn.disabled = true;
    return;
  }

  const stored = await new Promise((resolve) => {
    chrome.storage.local.get(["ph_training_parish", "ph_dead_parishes"], resolve);
  });
  const deadList = Array.isArray(stored?.ph_dead_parishes) ? stored.ph_dead_parishes : [];
  const tabHost = (() => {
    try { return new URL(url).hostname.replace(/^www\./, ""); } catch (_e) { return ""; }
  })();

  let parish = null;
  const training = stored?.ph_training_parish;
  if (training?.key && training?.name) {
    parish = {
      key: training.key,
      name: training.name,
      diocese: training.diocese || "",
      pageUrl: url,
      bulletinUrls: [url],
    };
  }

  if (!parish) {
    const resolved = await _bgMessage({ type: "resolve_parish_from_url", url });
    if (resolved?.ok && resolved.parish) parish = resolved.parish;
  }

  if (!parish && tabHost) {
    const hostKey = tabHost.split(".")[0];
    parish = {
      key: hostKey,
      name: hostKey,
      diocese: "",
      pageUrl: url,
      bulletinUrls: [url],
    };
  }

  _currentDeadParish = parish;
  const alreadyDead = deadList.some((p) => String(p.key).toLowerCase() === String(parish?.key || "").toLowerCase());
  if (parish) {
    deadCurrentEl.innerHTML = alreadyDead
      ? `☠ <strong>${parish.name}</strong> (${parish.key}) — already in your dead list`
      : `Detected: <strong>${parish.name}</strong> (${parish.key})<br><span style="color:#9ca3af;">${url}</span>`;
    if (deadMarkBtn) deadMarkBtn.disabled = alreadyDead;
  } else {
    deadCurrentEl.textContent = `Tab: ${url} — could not match a parish name. You can still mark by hostname if needed.`;
    if (deadMarkBtn) deadMarkBtn.disabled = false;
  }
}

if (deadMarkBtn) {
  deadMarkBtn.addEventListener("click", async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = String(tab?.url || "").trim();
    if (!/^https?:\/\//i.test(url)) {
      _setDeadStatus("Open a parish website tab first.", true);
      return;
    }

    let parish = _currentDeadParish;
    if (!parish?.key) {
      const resolved = await _bgMessage({ type: "resolve_parish_from_url", url });
      parish = resolved?.parish;
    }
    if (!parish?.key) {
      try {
        const host = new URL(url).hostname.replace(/^www\./, "");
        parish = { key: host.split(".")[0], name: host, diocese: "", pageUrl: url };
      } catch (_e) {
        _setDeadStatus("Could not detect parish.", true);
        return;
      }
    }

    const reason = String(deadReasonEl?.value || "").trim() || "Website gone or unreachable.";
    const label = parish.name || parish.key;
    if (!confirm(`Mark "${label}" as a DEAD website?\n\n• Pushes dead recipe to GitHub (harvest skips)\n• ${deadDisableEvidenceEl?.checked ? "Adds DISABLED to evidence file" : "Evidence file unchanged"}\n• Saves to your local reminder list`)) {
      return;
    }

    deadMarkBtn.disabled = true;
    _setDeadStatus("⏳ Marking as dead…");

    const res = await _bgMessage({
      type: "mark_parish_dead",
      parish_key: parish.key,
      display_name: parish.name || parish.key,
      diocese: parish.diocese || "",
      url: parish.pageUrl || parish.bulletinUrls?.[0] || url,
      reason,
      disable_evidence: Boolean(deadDisableEvidenceEl?.checked),
    });

    if (!res?.ok) {
      _setDeadStatus(`❌ ${res?.error || "Failed."}`, true);
      deadMarkBtn.disabled = false;
      return;
    }

    let msg = `✅ ${label} marked dead on GitHub.`;
    if (res.evidence_disabled) msg += " Evidence file updated.";
    else if (res.evidence_warning) msg += ` (${res.evidence_warning})`;
    _setDeadStatus(msg);
    if (deadReasonEl) deadReasonEl.value = "";
    await _renderDeadList();
    await _detectCurrentParishForDead();
    deadMarkBtn.disabled = true;
  });
}

void _renderDeadList();
void _detectCurrentParishForDead();

void sendToActiveTab({ type: "show_toolbar" });
