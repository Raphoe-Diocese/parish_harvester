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
const diagResultsEl = document.getElementById("diag-results");
const diagCopyBtn = document.getElementById("diag-copy");

let _diagTextLines = [];
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
  const userAgentLine = `Browser user-agent: ${navigator.userAgent || "n/a"}`;
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const activeUrl = String(activeTab?.url || "").trim();
  const activeTabIsHttp = /^https?:\/\//i.test(activeUrl);
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
  const patternLine = "Pattern learning: HTML fingerprint scan + parishes/site_patterns.json on GitHub";

  const dumpLines = _clipLinesTo4000Chars([
    "Parish Trainer diagnostic dump",
    "============================",
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

void sendToActiveTab({ type: "show_toolbar" });
