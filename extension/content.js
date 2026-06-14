(() => {
  // ── Session state ────────────────────────────────────────────────────────
  let cropOverlay = null;
  let lastCropSignature = "";
  let toolbar = null;
  const TOOLBAR_ID = "ph-floating-toolbar";
  let toolbarReadyLogged = false;
  let recipeSteps = []; // single source of truth for both UI preview and standalone recipe push
  let pickLinkActive = false;
  let pickLinkHighlightEl = null;
  let pickLinkCancelListeners = [];
  let pickImageActive = false;
  let pickImageHighlightEl = null;
  let pickImageCancelListeners = [];
  let pickedImages = []; // accumulates {url, el} when picking multiple
  let _stepsListEl = null; // set by createToolbar
  let _refreshRecipeCount = null; // callback set by createToolbar

  // ── Standalone recipe accumulator ────────────────────────────────────────
  // When the Playwright training bindings (window.ph_*) are absent, the
  // extension operates in "standalone" mode.  Steps are stored here so the
  // user can later push the recipe directly to GitHub without running train.py.
  let standaloneStartUrl = "";

  const _inStandaloneMode = () => typeof window.ph_mark_download_url !== "function";
  const _currentHostname = () => {
    try {
      return (window.location.hostname || "").toLowerCase();
    } catch (_e) {
      return "";
    }
  };
  const _hostnameFromUrl = (url) => {
    try {
      return new URL(url).hostname.toLowerCase().replace(/^www\d*\./, "");
    } catch (_e) {
      return "";
    }
  };
  // Parish key/name must always come from the tab you are on — never a stale
  // recording startUrl from another parish (Bellaghy bleeding into Ballinascreen).
  const _pageUrlForParishDetection = () => {
    try {
      return window.location.href;
    } catch (_e) {
      return standaloneStartUrl || "";
    }
  };
  const _hostsMatch = (urlA, urlB) => {
    const a = _hostnameFromUrl(urlA);
    const b = _hostnameFromUrl(urlB);
    return Boolean(a && b && a === b);
  };
  let _refreshParishPushForm = null;
  const _storageGet = (keys) =>
    new Promise((resolve) => {
      if (typeof chrome === "undefined" || !chrome.storage) {
        resolve({});
        return;
      }
      try {
        chrome.storage.local.get(keys, (r) => {
          if (chrome.runtime?.lastError) resolve({});
          else resolve(r || {});
        });
      } catch (_e) {
        resolve({});
      }
    });
  const _storageSet = (data) =>
    new Promise((resolve) => {
      if (typeof chrome === "undefined" || !chrome.storage) {
        resolve(false);
        return;
      }
      try {
        chrome.storage.local.set(data, () => resolve(!chrome.runtime?.lastError));
      } catch (_e) {
        resolve(false);
      }
    });

  const RECORDING_SESSIONS_KEY = "ph_recording_sessions";
  const LEGACY_RECORDING_SESSION_KEY = "ph_recording_session";
  const PARISH_DETECT_DEBUG_KEY = "ph_parish_detect_debug";

  const _serializeRecipeSteps = () =>
    recipeSteps.map((entry) => ({
      type: entry.type || "",
      label: entry.label || "",
      recipeStep: entry.recipeStep || null,
    }));

  const _getRecordingSessionsMap = async () => {
    const data = await _storageGet([RECORDING_SESSIONS_KEY, LEGACY_RECORDING_SESSION_KEY]);
    const map =
      data[RECORDING_SESSIONS_KEY] && typeof data[RECORDING_SESSIONS_KEY] === "object"
        ? { ...data[RECORDING_SESSIONS_KEY] }
        : {};
    const legacy = data[LEGACY_RECORDING_SESSION_KEY];
    if (legacy?.active && legacy.startUrl) {
      const legacyHost = _hostnameFromUrl(legacy.startUrl);
      if (legacyHost && !map[legacyHost]) {
        map[legacyHost] = {
          active: true,
          hostname: legacyHost,
          startUrl: legacy.startUrl,
          steps: Array.isArray(legacy.steps) ? legacy.steps : [],
          updatedAt: legacy.updatedAt || Date.now(),
        };
      }
    }
    return map;
  };

  const _getRecordingSessionForCurrentHost = async () => {
    const host = _hostnameFromUrl(_pageUrlForParishDetection());
    if (!host) return null;
    const map = await _getRecordingSessionsMap();
    return map[host] || null;
  };

  const _persistRecordingSession = async (extra = {}) => {
    if (!_inStandaloneMode()) return;
    const host = _hostnameFromUrl(_pageUrlForParishDetection());
    if (!host) return;
    const map = await _getRecordingSessionsMap();
    const prev = map[host] || {};
    const startUrl =
      standaloneStartUrl && _hostsMatch(standaloneStartUrl, _pageUrlForParishDetection())
        ? standaloneStartUrl
        : prev.startUrl && _hostsMatch(prev.startUrl, _pageUrlForParishDetection())
          ? prev.startUrl
          : _pageUrlForParishDetection();
    standaloneStartUrl = startUrl;
    map[host] = {
      active: true,
      hostname: host,
      startUrl,
      steps: _serializeRecipeSteps(),
      updatedAt: Date.now(),
      ...extra,
    };
    await _storageSet({
      [RECORDING_SESSIONS_KEY]: map,
      [LEGACY_RECORDING_SESSION_KEY]: { active: false, steps: [], updatedAt: Date.now() },
    });
  };

  const _clearRecordingSession = async () => {
    const host = _hostnameFromUrl(_pageUrlForParishDetection());
    const map = await _getRecordingSessionsMap();
    if (host) delete map[host];
    await _storageSet({
      [RECORDING_SESSIONS_KEY]: map,
      [LEGACY_RECORDING_SESSION_KEY]: { active: false, steps: [], updatedAt: Date.now() },
    });
  };

  const _linkOpensNewTab = (el) => {
    if (!(el instanceof Element)) return false;
    const anchor = el.closest("a") || (el.tagName === "A" ? el : null);
    if (!anchor) return false;
    const target = String(anchor.getAttribute("target") || "").toLowerCase();
    return target === "_blank" || target === "_new";
  };

  const _navigateRecordingToUrl = async (absUrl, selectedEl, showStatus) => {
    if (!absUrl) return false;
    await _persistRecordingSession({ pendingUrl: absUrl });
    if (
      _linkOpensNewTab(selectedEl) &&
      typeof chrome !== "undefined" &&
      chrome.runtime?.sendMessage
    ) {
      try {
        const resp = await new Promise((resolve) => {
          chrome.runtime.sendMessage({ type: "open_recording_tab", url: absUrl }, (res) => {
            if (chrome.runtime?.lastError) {
              resolve({ ok: false, error: chrome.runtime.lastError.message });
              return;
            }
            resolve(res || { ok: false });
          });
        });
        if (resp?.ok) {
          if (showStatus) showStatus("✅ Step saved — extension continues in the new tab.", "ok");
          return true;
        }
      } catch (_e) {
        // Fall through to same-tab navigation.
      }
    }
    if (showStatus) showStatus("✅ Step saved — opening link…", "info");
    window.location.assign(absUrl);
    return true;
  };

  const _restoreRecordingSessionFromStorage = async () => {
    if (!_inStandaloneMode()) return false;
    const pageUrl = _pageUrlForParishDetection();
    const currentHost = _hostnameFromUrl(pageUrl);
    const session = await _getRecordingSessionForCurrentHost();
    if (!session?.active) {
      standaloneStartUrl = pageUrl;
      return false;
    }
    const sessionHost = String(session.hostname || _hostnameFromUrl(session.startUrl || "")).toLowerCase();
    if (sessionHost && currentHost && sessionHost !== currentHost) {
      recipeSteps = [];
      standaloneStartUrl = pageUrl;
      await _clearRecordingSession();
      return false;
    }

    const steps = Array.isArray(session.steps) ? session.steps : [];
    recipeSteps = steps.map((entry) => ({
      type: entry.type || "",
      label: entry.label || "",
      recipeStep: entry.recipeStep || null,
    }));
    standaloneStartUrl =
      session.startUrl && _hostsMatch(session.startUrl, pageUrl) ? session.startUrl : pageUrl;

    _ensureToolbar(true);
    window.dispatchEvent(
      new CustomEvent("ph-recording-continued", {
        detail: { stepCount: _standaloneRecipeSteps().length },
      })
    );
    return true;
  };

  const _writeParishDetectDebug = async (resolved, extra = {}) => {
    const pageUrl = _pageUrlForParishDetection();
    const session = await _getRecordingSessionForCurrentHost();
    const payload = {
      pageUrl,
      hostname: _hostnameFromUrl(pageUrl),
      inferredKey: _inferParishKeyFromUrl(pageUrl),
      resolvedKey: resolved?.key || "",
      resolvedName: resolved?.name || "",
      recordingStartUrl: standaloneStartUrl || "",
      recordingHost: _hostnameFromUrl(standaloneStartUrl || ""),
      sessionSteps: _standaloneRecipeSteps().length,
      sessionHost: session?.hostname || "",
      mismatch:
        Boolean(resolved?.inferredKey && resolved?.key && resolved.inferredKey !== resolved.key) ||
        Boolean(standaloneStartUrl && !_hostsMatch(standaloneStartUrl, pageUrl)),
      ts: Date.now(),
      ...extra,
    };
    await _storageSet({ [PARISH_DETECT_DEBUG_KEY]: payload });
    return payload;
  };

  const _markRecordingActive = async () => {
    if (!_inStandaloneMode()) return;
    await _persistRecordingSession();
  };
  const _clearElement = (el) => {
    if (el) el.replaceChildren();
  };
  const _installTrustedTypesPolicy = () => {
    try {
      if (globalThis.__phTrustedTypesPolicy) return;
      if (window.trustedTypes?.createPolicy) {
        globalThis.__phTrustedTypesPolicy = window.trustedTypes.createPolicy("parish-trainer", {
          createHTML: (value) => String(value || ""),
        });
      }
    } catch (_error) {
      // Trusted Types policy is optional.
    }
  };
  _installTrustedTypesPolicy();

  // ── Safe message bridge ───────────────────────────────────────────────────
  // content.js now runs in the ISOLATED world so chrome.runtime is always
  // available.  _safeSendMessage uses the direct API and falls back to the
  // window.postMessage ↔ isolated.js bridge only if chrome.runtime becomes
  // unavailable (e.g. after an extension reload mid-session).
  // callback(response, errorString) — errorString is non-null on failure.
  const _safeSendMessage = (message, callback) => {
    const TIMEOUT_MS = 15000;

    // ── Direct path ──────────────────────────────────────────────────────
    if (typeof chrome !== "undefined" && chrome?.runtime?.sendMessage) {
      try {
        chrome.runtime.sendMessage(message, (res) => {
          const lastErr = chrome.runtime?.lastError;
          if (lastErr) {
            callback(null, lastErr.message);
          } else {
            callback(res || null, null);
          }
        });
        return;
      } catch (_directErr) {
        // Fall through to bridge
      }
    }

    // ── Bridge path via isolated.js ──────────────────────────────────────
    const reqId = `ph-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    let settled = false;
    let timer = null;

    const onResponse = (event) => {
      if (event.source !== window) return;
      if (event.data?.direction !== "from-isolated-response") return;
      if (event.data?.reqId !== reqId) return;
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      window.removeEventListener("message", onResponse);
      callback(event.data.response || null, event.data.error || null);
    };

    window.addEventListener("message", onResponse);

    timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      window.removeEventListener("message", onResponse);
      callback(null, "Extension bridge timed out. Reload the page and try again. If the problem persists, check that your GitHub PAT is saved in Settings.");
    }, TIMEOUT_MS);

    window.postMessage({ direction: "from-main", reqId, message }, "*");
  };

  // ── Parish key / name inference from URL ─────────────────────────────────
  // Mirrors the _pdUrlToKey() logic used in sidepanel.js so the push form can
  // auto-populate fields without requiring manual entry.
  const _inferParishKeyFromUrl = (url) => {
    if (!url) return "";
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
      if (
        hostname === "filesafe.space" || hostname.endsWith(".filesafe.space") ||
        hostname === "google.com"     || hostname.endsWith(".google.com")
      ) {
        return "";
      }
      return hostname.split(".")[0] || "";
    } catch (_e) {
      return "";
    }
  };

  const _inferDisplayNameFromUrl = (url) => {
    const key = _inferParishKeyFromUrl(url);
    if (!key) return "";
    return key.charAt(0).toUpperCase() + key.slice(1);
  };

  // Resolve parish key/name from the CURRENT page URL — never reuse a stale
  // ph_training_parish from a different website (e.g. bellaghyparish bleeding
  // into threepatrons.org).
  const _resolveParishContextForPage = (pageUrl, storageData = {}) => {
    const hostname = (() => {
      try {
        return new URL(pageUrl || window.location.href).hostname.toLowerCase();
      } catch (_e) {
        return _currentHostname();
      }
    })();
    const inferredKey = _inferParishKeyFromUrl(pageUrl || window.location.href);
    const inferredName = _inferDisplayNameFromUrl(pageUrl || window.location.href);
    const hostnameCtx =
      hostname && storageData.ph_hostname_map && typeof storageData.ph_hostname_map === "object"
        ? storageData.ph_hostname_map[hostname]
        : null;

    let key = inferredKey || "";
    let name = inferredName || "";
    let diocese = "";

    if (hostnameCtx && typeof hostnameCtx === "object") {
      const mappedKey = String(hostnameCtx.parish_key || hostnameCtx.key || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_");
      const mappedName = String(hostnameCtx.display_name || hostnameCtx.name || "").trim();
      const mappedDiocese = String(hostnameCtx.diocese || "").trim();
      if (mappedDiocese) diocese = mappedDiocese;
      if (mappedName) name = mappedName;
      // Only trust cached key when URL gives nothing, or cache agrees with URL.
      if (mappedKey && !inferredKey) {
        key = mappedKey;
      } else if (mappedKey && inferredKey && mappedKey === inferredKey) {
        key = mappedKey;
      }
    }

    return { key, name, diocese, hostname, inferredKey };
  };

  const _parishKeyMatchesPageUrl = (key, pageUrl) => {
    const inferred = _inferParishKeyFromUrl(pageUrl);
    const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, "_");
    const k = norm(key);
    const i = norm(inferred);
    if (!k) return false;
    if (!i) return true;
    if (k === i) return true;
    try {
      const hostSeg = new URL(pageUrl).hostname.toLowerCase().replace(/^www\d*\./, "").split(".")[0] || "";
      if (hostSeg && (k === hostSeg || hostSeg.includes(k) || k.includes(hostSeg))) return true;
    } catch (_e) {
      // ignore
    }
    return false;
  };

  const _purgeStaleHostnameMapEntry = (hostname, pageUrl) => {
    if (!hostname || typeof chrome === "undefined" || !chrome.storage) return;
    try {
      chrome.storage.local.get(["ph_hostname_map"], (r) => {
        if (chrome.runtime?.lastError) return;
        const hostnameMap = (r.ph_hostname_map && typeof r.ph_hostname_map === "object")
          ? { ...r.ph_hostname_map }
          : {};
        const stale = hostnameMap[hostname];
        if (!stale) return;
        const staleKey = String(stale.parish_key || stale.key || "").trim().toLowerCase().replace(/\s+/g, "_");
        if (!staleKey || _parishKeyMatchesPageUrl(staleKey, pageUrl)) return;
        delete hostnameMap[hostname];
        try { chrome.storage.local.set({ ph_hostname_map: hostnameMap }); } catch (_e) {}
      });
    } catch (_e) {
      // ignore
    }
  };

  // Persist per-domain parish context after a successful push.
  const _cacheParishByDomain = (url, key, name, diocese, startUrl = "") => {
    const hostname = (() => { try { return new URL(url).hostname; } catch (_e) { return ""; } })();
    if (!hostname || !key) return;
    if (typeof chrome === "undefined" || !chrome.storage) return;
    try {
      chrome.storage.local.get(["ph_parish_by_domain", "ph_hostname_map"], (r) => {
        if (chrome.runtime?.lastError) return;
        const cache = (r.ph_parish_by_domain && typeof r.ph_parish_by_domain === "object")
          ? r.ph_parish_by_domain : {};
        const hostnameMap = (r.ph_hostname_map && typeof r.ph_hostname_map === "object")
          ? r.ph_hostname_map : {};
        const context = {
          hostname,
          key,
          parish_key: key,
          name: name || key,
          display_name: name || key,
          diocese: diocese || "",
          start_url: startUrl || url,
          ts: Date.now(),
        };
        cache[hostname] = context;
        hostnameMap[hostname] = context;
        try { chrome.storage.local.set({ ph_parish_by_domain: cache, ph_hostname_map: hostnameMap }); } catch (_e) {}
      });
    } catch (_e) {}
  };

  const _standaloneRecipeSteps = () =>
    recipeSteps
      .filter((entry) => entry && entry.recipeStep && typeof entry.recipeStep.action === "string")
      .map((entry) => entry.recipeStep);

  const standaloneAddStep = (step, uiType = "", uiLabel = "") => {
    if (!_inStandaloneMode()) return;
    // Replace an existing download/image/html step if one already exists
    const terminal = ["download", "image", "print_to_pdf", "crop_screenshot"];
    if (terminal.includes(step.action)) {
      const idx = recipeSteps.findIndex((entry) =>
        terminal.includes(String(entry?.recipeStep?.action || ""))
      );
      if (idx >= 0) {
        recipeSteps.splice(idx, 1);
      }
    }
    recipeSteps.push({
      type: uiType || step.action || "step",
      label: uiLabel || _recipeStepToUiLabel(step),
      recipeStep: step,
    });
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    if (!standaloneStartUrl) {
      standaloneStartUrl = window.location.href;
    }
    void _persistRecordingSession();
  };

  const standaloneUndo = (actionType) => {
    if (!_inStandaloneMode()) return;
    for (let i = recipeSteps.length - 1; i >= 0; i--) {
      if (recipeSteps[i]?.recipeStep?.action === actionType) {
        recipeSteps.splice(i, 1);
        break;
      }
    }
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    void _persistRecordingSession();
  };

  const buildStandaloneRecipe = (parishKey, displayName, diocese) => {
    const steps = [];
    const pageUrl = _pageUrlForParishDetection();
    const startUrl =
      standaloneStartUrl && _hostsMatch(standaloneStartUrl, pageUrl) ? standaloneStartUrl : pageUrl;
    if (startUrl) {
      const gotoStep = { action: "goto", url: startUrl };
      if (/(?:\d{1,2})[_-](?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[_-](?:\d{4})/i.test(startUrl)) {
        gotoStep.use_target_url = true;
      }
      steps.push(gotoStep);
    }
    steps.push(..._standaloneRecipeSteps());
    return {
      version: 1,
      parish_key: parishKey,
      display_name: displayName,
      diocese: diocese || "",
      start_url: startUrl,
      steps,
    };
  };

  const clearStandaloneRecipe = () => {
    recipeSteps = recipeSteps.filter((entry) => !entry?.recipeStep);
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    standaloneStartUrl = _pageUrlForParishDetection();
    void _clearRecordingSession();
  };

  const _recipeStepToUiLabel = (step) => {
    const action = String(step?.action || "").trim().toLowerCase();
    if (action === "goto") return `Open start page: ${String(step.url || "").slice(-60)}`;
    if (action === "click") {
      const text = String(step.text || "").trim();
      return text ? `Click link: "${text}"` : `Click: ${String(step.selector || "element")}`;
    }
    if (action === "download") {
      const url = String(step.url || step.captured_url || step.url_pattern || "").trim();
      return url ? `Download PDF: …${url.slice(-50)}` : "Download bulletin PDF";
    }
    if (action === "html" || action === "print_to_pdf") return "Save page as PDF (included in mega bulletin)";
    if (action === "image") return `Capture image: …${String(step.url || "").slice(-40)}`;
    return `${action || "step"}: ${JSON.stringify(step).slice(0, 80)}`;
  };

  const _importStandaloneRecipe = (recipe, { showLoadedMessage = true } = {}) => {
    if (!_inStandaloneMode() || !recipe || !Array.isArray(recipe.steps)) return 0;
    const startUrl = String(recipe.start_url || "").trim();
    if (startUrl) standaloneStartUrl = startUrl;
    recipeSteps = recipeSteps.filter((entry) => !entry?.recipeStep);
    let imported = 0;
    for (const step of recipe.steps) {
      if (!step || typeof step !== "object") continue;
      const action = String(step.action || "").trim().toLowerCase();
      if (!action || action === "goto") continue;
      recipeSteps.push({
        type: action,
        label: _recipeStepToUiLabel(step),
        recipeStep: step,
      });
      imported += 1;
    }
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    if (showLoadedMessage && imported > 0) {
      // Caller should show status when toolbar is ready.
    }
    void _persistRecordingSession();
    return imported;
  };

  const _contactsCache = { loaded: false, byKey: {}, byHost: {} };
  const _indexContactsFile = (data) => {
    if (!data || typeof data !== "object") return;
    Object.entries(data).forEach(([key, entry]) => {
      if (!entry || typeof entry !== "object") return;
      const displayName = String(entry.display_name || entry.name || "").trim();
      if (!displayName) return;
      _contactsCache.byKey[String(key).trim().toLowerCase()] = displayName;
      const website = String(entry.website || "").trim();
      if (website) {
        try {
          const host = new URL(website).hostname.toLowerCase().replace(/^www\d*\./, "");
          if (host) _contactsCache.byHost[host] = displayName;
        } catch (_e) {
          // ignore bad website URLs in contacts file
        }
      }
    });
  };

  const _lookupDisplayNameFromContacts = async (parishKey, hostname = "") => {
    const key = String(parishKey || "").trim().toLowerCase();
    const host = String(hostname || "").toLowerCase().replace(/^www\d*\./, "");
    if (!key && !host) return "";
    if (!_contactsCache.loaded) {
      const settings = await _storageGet(["gh_repo"]);
      const ghRepo = String(settings.gh_repo || "").trim();
      if (!ghRepo) return "";
      const files = [
        "parishes/derry_diocese_contacts.json",
        "parishes/down_and_connor_contacts.json",
        "parishes/raphoe_diocese_contacts.json",
      ];
      for (const filePath of files) {
        try {
          const resp = await fetch(`https://raw.githubusercontent.com/${ghRepo}/main/${filePath}`);
          if (!resp.ok) continue;
          _indexContactsFile(JSON.parse(await resp.text()));
        } catch (_e) {
          // try next contacts file
        }
      }
      _contactsCache.loaded = true;
    }
    if (key && _contactsCache.byKey[key]) return _contactsCache.byKey[key];
    if (host && _contactsCache.byHost[host]) return _contactsCache.byHost[host];
    return "";
  };

  const _getToolbarNode = () => {
    if (toolbar && toolbar.isConnected) {
      return toolbar;
    }
    const found = document.getElementById(TOOLBAR_ID);
    if (found) {
      toolbar = found;
      return toolbar;
    }
    toolbar = null;
    return null;
  };

  const _cleanupDuplicateToolbars = () => {
    const all = Array.from(document.querySelectorAll(`#${TOOLBAR_ID}`));
    if (all.length <= 1) return;
    const keep = all[0];
    for (let i = 1; i < all.length; i++) {
      all[i].remove();
    }
    toolbar = keep;
  };

  const _ensureToolbar = (visible = true) => {
    _cleanupDuplicateToolbars();
    let node = _getToolbarNode();
    if (!node) {
      node = createToolbar();
      document.documentElement.appendChild(node);
      toolbar = node;
    }
    if (visible) {
      node.dataset.phHidden = "false";
      node.style.display = "flex";
      _notifyRecordingTabActive();
      if (!toolbarReadyLogged) {
        console.log("✅ Parish Trainer toolbar ready");
        toolbarReadyLogged = true;
      }
    }
    return node;
  };

  // ── Helpers ───────────────────────────────────────────────────────────────

  const cropSignature = (payload) =>
    `${payload.x},${payload.y},${payload.width},${payload.height},${payload.pageX},${payload.pageY},${payload.element_selector || ""}`;

  const cssPath = (el) => {
    if (!el || el.nodeType !== Node.ELEMENT_NODE) return "";
    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let selector = current.tagName.toLowerCase();
      if (current.id) {
        selector += "#" + current.id;
        parts.unshift(selector);
        break;
      }
      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter(
          (c) => c.tagName === current.tagName
        );
        if (siblings.length > 1) {
          selector += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }
      parts.unshift(selector);
      current = current.parentElement;
    }
    return parts.join(" > ");
  };

  const nearestElementSelector = (x, y) => {
    const candidates = document.elementsFromPoint(x, y);
    for (const el of candidates) {
      if (!(el instanceof Element)) continue;
      const img = el.closest("img");
      if (img) return cssPath(img);
      const container = el.closest("figure,article,section,main,div");
      if (container) return cssPath(container);
      return cssPath(el);
    }
    return "";
  };

  // Include nearby card/heading text — many parish sites put the date above "Read More".
  const _getEnrichedLinkLabel = (el) => {
    if (!el) return "";
    const direct = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
    let node = el.parentElement;
    for (let depth = 0; depth < 6 && node; depth++) {
      const block = (node.innerText || node.textContent || "").trim().replace(/\s+/g, " ");
      if (
        /\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+20\d{2}\b/i.test(
          block
        )
      ) {
        const dateLine =
          block
            .split("\n")
            .map((line) => line.trim())
            .find((line) =>
              /\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(
                line
              )
            ) || block.split("\n")[0];
        return `${dateLine} | ${direct}`.slice(0, 200);
      }
      node = node.parentElement;
    }
    return direct;
  };

  const buildStableLinkSelector = (el) => {
    if (!el) return "";
    const tag = el.tagName.toLowerCase();
    const text = (el.innerText || el.textContent || "")
      .trim()
      .replace(/\s+/g, " ")
      .slice(0, 80);
    const role = el.getAttribute("role") || "";
    // Escape backslashes first, then double-quotes, for a valid Playwright selector
    const escapeForSelector = (s) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    if (text && text.length >= 3 && text.length <= 60) {
      return `${tag}:has-text("${escapeForSelector(text)}")`;
    }
    if (role) {
      return `[role="${role}"]:has-text("${escapeForSelector(text)}")`;
    }
    return cssPath(el);
  };

  // ── URL date extraction and candidate scoring ──────────────────────────────

  // Month abbreviation (first 3 letters, lowercase) → month number
  const _MONTH_ABBR_MAP = {
    jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
    jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
  };

  /**
   * Extract the best date from a URL / filename string.
   * Returns {year, month, day} or null.
   * month and/or day may be 0 when not found (partial date).
   * Handles: ISO (2026-04-26), WP path (/2026/04/26/), ordinal slug
   * (26th-April-2026), ISO-nodash (20260426), DDMMYYYY (26042026),
   * year-month path (/2026/04/), and bare year (2026).
   */
  const extractDateFromUrl = (text) => {
    let s;
    try { s = decodeURIComponent(text).toLowerCase(); } catch (_e) { s = text.toLowerCase(); }

    // ISO: 2026-04-26
    let m = s.match(/\b(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])\b/);
    if (m) return { year: +m[1], month: +m[2], day: +m[3] };

    // WP path: /2026/04/26/
    m = s.match(/\/(20\d{2})\/(0[1-9]|1[0-2])\/([0-2]\d|3[01])\//);
    if (m) return { year: +m[1], month: +m[2], day: +m[3] };

    // Ordinal / plain slug: 26th-april-2026, 3rd-may-2026, 26-april-2026, 26_april_2026
    m = s.match(/\b(\d{1,2})(?:st|nd|rd|th)?[-_]([a-z]{3,9})[-_](20\d{2})\b/);
    if (m) {
      const mo = _MONTH_ABBR_MAP[m[2].slice(0, 3)];
      if (mo) return { year: +m[3], month: mo, day: +m[1] };
    }

    // Ordinal with spaces: 24th may 2026, sunday 24th may 2026
    m = s.match(/\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\s+(20\d{2})\b/);
    if (m) {
      const mo = _MONTH_ABBR_MAP[m[2].slice(0, 3)];
      if (mo) return { year: +m[3], month: mo, day: +m[1] };
    }

    // DDMMYY in PDF filenames: pdf/240526.pdf → 24 May 2026
    m = s.match(/(?:^|\/)(\d{2})(\d{2})(\d{2})\.pdf\b/);
    if (m) {
      const day = +m[1];
      const month = +m[2];
      const year = 2000 + +m[3];
      if (month >= 1 && month <= 12 && day >= 1 && day <= 31) {
        return { year, month, day };
      }
    }

    // ISO nodash: 20260426 (8 consecutive digits)
    m = s.match(/(?<!\d)(20\d{2})(0[1-9]|1[0-2])([0-2]\d|3[01])(?!\d)/);
    if (m) return { year: +m[1], month: +m[2], day: +m[3] };

    // DDMMYYYY: 26042026 (last resort — inherently ambiguous, restrict to 2020-2039 to reduce false positives)
    m = s.match(/(?<!\d)([0-2]\d|3[01])(0[1-9]|1[0-2])(20[2-3]\d)(?!\d)/);
    if (m) return { year: +m[3], month: +m[2], day: +m[1] };

    // WP year/month path: /2026/04/ (partial — no day)
    m = s.match(/\/(20\d{2})\/(0[1-9]|1[0-2])\//);
    if (m) return { year: +m[1], month: +m[2], day: 0 };

    // Month + year without day: May 2026, may 2026 - ardstraw parish messenger labels
    m = s.match(
      /\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(20\d{2})\b/
    );
    if (m) {
      const mo = _MONTH_ABBR_MAP[m[1].slice(0, 3)];
      if (mo) return { year: +m[2], month: mo, day: 0 };
    }

    // Bare year only (fallback — match any 20xx year)
    m = s.match(/\b(20\d{2})\b/);
    if (m) return { year: +m[1], month: 0, day: 0 };

    return null;
  };

  // Admin / non-bulletin PDFs (Gift Aid forms, data entry, etc.) — never treat as weekly bulletin.
  const _isNonBulletinPdf = (url, label) => {
    const text = `${url || ""} ${label || ""}`.toLowerCase();
    return (
      /dataentry|giftaid|standingorder|donation|prayer|safeguarding|privacy|sitemap|application|registration|volunteer|finances|parishdraw/i.test(
        text
      ) && !/\b(bulletin|newsletter|view newsletter)\b/i.test(text)
    );
  };

  const _filterBulletinCandidates = (elements) =>
    Array.from(elements || []).filter((el) => {
      if (!(el instanceof Element)) return false;
      const href = el.getAttribute("href") || "";
      const label = _getEnrichedLinkLabel(el);
      if (_isNonBulletinPdf(href, label)) return false;
      return true;
    });

  // Approximate date scores for named liturgical events (used when no numeric date found).
  const _NAMED_BULLETIN_SCORES = {
    "easter sunday": { month: 4, day: 15 },
    "palm sunday": { month: 4, day: 8 },
    "good friday": { month: 4, day: 14 },
    "ash wednesday": { month: 3, day: 5 },
    "pentecost": { month: 5, day: 19 },
    "corpus christi": { month: 6, day: 15 },
    "christmas": { month: 12, day: 25 },
  };

  /**
   * Score a URL+label candidate for bulletin date ranking.
   * Higher total = better candidate (newer date, better keywords, pdf preferred).
   * Returns {dateScore, tieBreaker, hasDate, hasFullDate, total}.
   * NOTE: domIdx is accepted for API compatibility but is NOT included in tieBreaker —
   * callers should store domIdx separately and use the date-first sort helper below.
   */
  const scoreUrlCandidateStr = (url, label, domIdx) => {
    let decoded;
    try { decoded = decodeURIComponent((url || "") + " " + (label || "")).toLowerCase(); }
    catch (_e) { decoded = ((url || "") + " " + (label || "")).toLowerCase(); }
    let d = extractDateFromUrl(decoded);
    const keywordBonus = /\b(bulletin|newsletter|notice)\b/.test(decoded) ? 5 : 0;
    const pdfBonus = /\.pdf(\?|$)/.test(decoded) ? 3 : 0;
    const docxBonus = /\.docx(\?|$)/.test(decoded) ? 1 : 0;
    const uploadsBonus = decoded.includes("/uploads/") || decoded.includes("/wp-content/") ? 2 : 0;
    // If no numeric date found, check for named liturgical events
    if (!d) {
      for (const [name, approx] of Object.entries(_NAMED_BULLETIN_SCORES)) {
        if (decoded.includes(name)) {
          const approxYear = new Date().getFullYear();
          const dateScore = approxYear * 10000 + approx.month * 100 + approx.day;
          const tieBreaker = keywordBonus + pdfBonus + docxBonus + uploadsBonus;
          return {
            dateScore,
            tieBreaker,
            hasDate: true,
            hasFullDate: false,
            total: dateScore * 100 + tieBreaker,
          };
        }
      }
    }
    const dateScore = d ? d.year * 10000 + d.month * 100 + d.day : 0;
    const hasFullDate = d !== null && d.month > 0 && d.day > 0;
    const hasDate = d !== null && d.year > 0;
    // tieBreaker does NOT include domIdx — position is handled by the sort comparator
    let tieBreaker = keywordBonus + pdfBonus + docxBonus + uploadsBonus;
    const phrase = window.ph_copilot?.scorePhrase?.(url, label);
    if (phrase) {
      tieBreaker += phrase.bonus - phrase.penalty;
    }
    return { dateScore, tieBreaker, hasDate, hasFullDate, total: dateScore * 100 + tieBreaker };
  };

  /**
   * Comparator for scored bulletin candidates.
   * When dates are available, date always wins (newest first).
   * Falls back to inverted domIdx (later on page = better) only when no dates exist.
   */
  const _bulletinDateSortFn = (a, b) => {
    if (a.hasFullDate && b.hasFullDate) return b.dateScore - a.dateScore;
    if (a.hasFullDate) return -1;
    if (b.hasFullDate) return 1;
    if (a.hasDate && b.hasDate) return b.dateScore - a.dateScore;
    if (a.hasDate) return -1;
    if (b.hasDate) return 1;
    // Neither has a date — later on page wins (many pages list newest at the bottom)
    return (b.domIdx || 0) - (a.domIdx || 0);
  };

  /**
   * Return a human-readable date string from a URL+label pair, or null if no date found.
   */
  const getDisplayDate = (url, label) => {
    let decoded;
    try { decoded = decodeURIComponent((url || "") + " " + (label || "")).toLowerCase(); }
    catch (_e) { decoded = ((url || "") + " " + (label || "")).toLowerCase(); }
    const d = extractDateFromUrl(decoded);
    if (!d || !d.year) return null;
    const months = ["","Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    if (d.month > 0 && d.day > 0) return `${d.day} ${months[d.month]} ${d.year}`;
    if (d.month > 0) return `${months[d.month]} ${d.year}`;
    return `${d.year}`;
  };

  // Returns true if the URL looks like a downloadable document.
  const _looksLikeBulletinDownloadUrl = (url, text = "") => {
    if (!url) return false;
    const combined = `${url} ${text}`.toLowerCase();
    if (isDocumentUrl(url)) return true;
    if (/\/files\/\d+\/weekly-bulletins\//i.test(url)) return true;
    if (/\/weekly-bulletins\//i.test(url)) return true;
    if (
      /\/wp-content\/uploads\//i.test(url) &&
      /bulletin|newsletter|\d{4}/i.test(combined)
    ) {
      return true;
    }
    return false;
  };

  const isDocumentUrl = (url) => {
    if (!url) return false;
    // Check Google Drive / Docs patterns on the full URL (including query string)
    // before stripping query parameters, since these patterns often live in the query.
    const lowerFull = url.toLowerCase();
    if (
      lowerFull.includes("drive.google.com/file") ||
      lowerFull.includes("docs.google.com/viewer") ||
      lowerFull.includes("docs.google.com/gview") ||
      lowerFull.includes("drive.google.com/uc?") ||
      lowerFull.includes("drive.google.com/open?") ||
      lowerFull.includes("1drv.ms/") ||
      lowerFull.includes("onedrive.live.com/") ||
      lowerFull.includes("sharepoint.com/") ||
      lowerFull.includes("officeapps.live.com/")
    )
      return true;
    // Check file extensions on the path (before the query string)
    const lowerPath = lowerFull.split("?")[0];
    const docExts = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".odt", ".ods"];
    if (docExts.some((ext) => lowerPath.endsWith(ext))) return true;
    return false;
  };

  const IMAGE_CONTENT_AREA_SELECTOR = ".entry-content, article, main, [role='main']";
  const IMAGE_CONTENT_CLASS_HINT_RE = /(entry-content|post-content|article|main)/i;
  const MIN_CONTENT_IMAGE_WIDTH = 200;

  const getImageWidth = (img) => {
    const widthAttr = Number(img.getAttribute("width") || 0);
    if (Number.isFinite(widthAttr) && widthAttr > 0) return widthAttr;
    const renderWidth = Number(img.width || 0);
    if (Number.isFinite(renderWidth) && renderWidth > 0) return renderWidth;
    const rectWidth = Number(img.getBoundingClientRect?.().width || 0);
    return Number.isFinite(rectWidth) ? rectWidth : 0;
  };

  const isLargeImage = (img, threshold = 400) => {
    const width = getImageWidth(img);
    const naturalWidth = Number(img.naturalWidth || 0);
    return width > threshold || naturalWidth > threshold;
  };

  const isInClassHintedContentArea = (img) => {
    let node = img;
    while (node && node instanceof Element) {
      const className = node.getAttribute("class") || "";
      if (IMAGE_CONTENT_CLASS_HINT_RE.test(className)) return true;
      node = node.parentElement;
    }
    return false;
  };

  const hasPickableImageInContentAreas = (minWidth = MIN_CONTENT_IMAGE_WIDTH) =>
    Array.from(document.querySelectorAll(`${IMAGE_CONTENT_AREA_SELECTOR} img`)).some(
      (img) => {
        const rawWidthAttr = (img.getAttribute("width") || "").trim();
        if (/^\d+$/.test(rawWidthAttr) && Number(rawWidthAttr) < minWidth) return false;
        return true;
      }
    );

  // Detect what kind of bulletin page we are on and give plain-language guidance.
  const WIX_SLUG_DATE_RE = /(\d{1,2})(?:st|nd|rd|th)?[_-](jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[_-](\d{4})/i;
  const _isWixSite = () => {
    try {
      const html = document.documentElement?.innerHTML || "";
      return Boolean(
        document.querySelector("#SITE_CONTAINER") ||
        document.querySelector('meta[name="generator"][content*="Wix" i]') ||
        /static\.wixstatic\.com/i.test(html) ||
        globalThis.wixBiSession
      );
    } catch (_e) {
      return false;
    }
  };
  const _hasWixDateSlug = (text) => WIX_SLUG_DATE_RE.test(String(text || ""));
  const _nextSundayDate = () => {
    const d = new Date();
    const day = d.getDay();
    if (day !== 0) d.setDate(d.getDate() + (7 - day));
    return d;
  };

  const detectPageType = () => {
    const url = window.location.href.toLowerCase();

    // 1. Current page IS a PDF
    if (url.endsWith(".pdf") || url.includes(".pdf?") || url.includes("/pdf/")) {
      return {
        emoji: "📄",
        summary: "This page IS a PDF document.",
        advice: "Tap the green 📄 Save this PDF button, then Push Recipe below.",
        type: "direct_pdf",
      };
    }

    // 1b. Parish Services / Parish Messenger embed (dmaparish, ardstraw, culdaff, etc.)
    const parishMessengerScript = document.querySelector(
      'script[src*="theparishmessenger.com"]'
    );
    if (parishMessengerScript) {
      const widgetLinks = _filterBulletinCandidates(
        document.querySelectorAll('a[href*=".pdf"], a[href*="View"], a[href*="newsletter"]')
      );
      return {
        emoji: "📰",
        summary: "Parish Messenger widget — bulletin links load after the script runs.",
        advice:
          'Click Follow a link → pick the newest "View Newsletter" or dated row (e.g. May 2026). Ignore Gift Aid / Data Entry PDFs in the menu.',
        type: "parish_messenger",
        links: widgetLinks.length > 0 ? widgetLinks : undefined,
      };
    }

    // 2. WordPress PDF Embedder plugin — check original <a> tags AND viewer elements
    const pdfembEls = Array.from(
      document.querySelectorAll(
        'a.pdfemb-viewer, a[class*="pdfemb"], [id^="pdfemb-embed-"], [class*="pdfemb-embed"]'
      )
    );
    // Filter to those that have a usable href or contain a child PDF iframe/embed
    const pdfembLinks = pdfembEls.filter((el) => {
      const href =
        el.getAttribute("href") ||
        el.getAttribute("data-url") ||
        el.getAttribute("data-pdfurl") ||
        "";
      if (href.length > 0) return true;
      // For viewer wrapper divs, look for a nested iframe/embed with a PDF src
      const inner =
        el.querySelector && el.querySelector("iframe[src], embed[src]");
      return (
        inner && (inner.getAttribute("src") || "").toLowerCase().includes(".pdf")
      );
    });
    if (pdfembEls.length > 0 || pdfembLinks.length > 0) {
      const count = Math.max(pdfembEls.length, pdfembLinks.length);
      // Collect anchor elements only (need href for "Pick newest" feature)
      const anchors = pdfembEls.filter(
        (el) =>
          el.tagName === "A" &&
          (el.getAttribute("href") ||
            el.getAttribute("data-url") ||
            el.getAttribute("data-pdfurl"))
      );
      return {
        emoji: "🔗",
        summary: `PDF listing page — found ${count} PDF Embedder link(s) (WordPress plugin).`,
        advice:
          'Use "No — I need to click a link" or "Pick newest bulletin" below to record the right bulletin link.',
        type: "pdfemb",
        links: anchors,
      };
    }

    // 3. iframes with PDF or viewer content
    const iframes = Array.from(document.querySelectorAll("iframe[src]"));

    // 3a. Wix PDF viewer detection — must run BEFORE generic pdfIframes check
    const wixViewerIframes = iframes.filter((f) => {
      const src = f.getAttribute("src") || "";
      try {
        const hostname = new URL(src, window.location.href).hostname.toLowerCase();
        return (
          hostname === "wixlabs-pdf-dev.appspot.com" ||
          hostname.startsWith("wixlabs-pdf")
        );
      } catch (_e) {
        return false;
      }
    });

    if (wixViewerIframes.length > 0) {
      // Try to extract the real PDF URL from the Wix viewer src
      let extractedPdfUrl = null;
      for (const frame of wixViewerIframes) {
        try {
          const wixUrl = new URL(frame.getAttribute("src") || "", window.location.href);
          const pdfParam =
            wixUrl.searchParams.get("url") ||
            wixUrl.searchParams.get("PDF_URL") ||
            wixUrl.searchParams.get("pdf") ||
            wixUrl.searchParams.get("file");
          if (pdfParam) {
            extractedPdfUrl = decodeURIComponent(pdfParam);
            break;
          }
        } catch (_e) {}
      }
      return {
        emoji: "📄",
        summary: extractedPdfUrl
          ? `Wix PDF viewer detected — found the PDF URL automatically.`
          : `Wix PDF viewer detected (${wixViewerIframes.length} viewer(s)).`,
        advice: extractedPdfUrl
          ? `Click "It's in a frame / viewer" to record the extracted PDF URL directly.`
          : `💡 Click the ↓ download icon at the TOP of the viewer. When a new tab opens with the PDF, come back and click 📄 Get a PDF.`,
        type: "wix_viewer",
        wixPdfUrl: extractedPdfUrl,
      };
    }

    const pdfIframes = iframes.filter((f) => {
      const src = (f.getAttribute("src") || "").toLowerCase();
      return (
        src.endsWith(".pdf") ||
        src.includes(".pdf?") ||
        src.includes("docs.google.com/viewer") ||
        src.includes("docs.google.com/gview") ||
        src.includes("drive.google.com/file")
      );
    });
    if (pdfIframes.length > 0) {
      return {
        emoji: "🖼️",
        summary: `This page embeds ${pdfIframes.length} PDF frame(s).`,
        advice: "Click \"It's embedded in a frame\" to choose the correct frame.",
        type: "iframe",
      };
    }
    const maybeDocIframes = iframes.filter((f) => {
      const src = (f.getAttribute("src") || "").toLowerCase();
      return (
        src.includes("pdf") ||
        src.includes("doc") ||
        src.includes("bulletin") ||
        src.includes("newsletter") ||
        src.includes("viewer") ||
        src.includes("drive.google") ||
        src.includes("dropbox") ||
        src.includes("filesafe") ||
        src.includes("amazonaws") ||
        src.includes("blob.core")
      );
    });
    if (maybeDocIframes.length > 0) {
      return {
        emoji: "🖼️",
        summary: `Found ${maybeDocIframes.length} frame(s) — may contain a PDF viewer.`,
        advice:
          "Click \"It's embedded in a frame\" to inspect the frames. Background PDF detection now runs automatically as fallback.",
        type: "iframe_maybe",
      };
    }

    // 4. <embed> or <object> with PDF content
    const pdfEmbeds = Array.from(
      document.querySelectorAll("embed[src],object[data]")
    ).filter((el) => {
      const src = (
        el.getAttribute("src") ||
        el.getAttribute("data") ||
        ""
      ).toLowerCase();
      return (
        src.includes(".pdf") || el.getAttribute("type") === "application/pdf"
      );
    });
    if (pdfEmbeds.length > 0) {
      return {
        emoji: "📎",
        summary: `Found ${pdfEmbeds.length} embedded PDF object(s).`,
        advice:
          'If the bulletin is showing here, use "Yes, it\'s a PDF". If not, background PDF detection runs automatically.',
        type: "embed",
      };
    }

    // 5. Generic PDF / document links
    const pdfLinks = _filterBulletinCandidates(
      Array.from(document.querySelectorAll("a[href]")).filter((a) => {
        const href = (a.getAttribute("href") || "").toLowerCase();
        return (
          href.includes(".pdf") ||
          href.includes(".docx") ||
          href.includes("/wp-content/uploads/")
        );
      })
    );
    if (pdfLinks.length > 0) {
      const bulletinLinks = pdfLinks.filter((a) => {
        const text = (
          (a.innerText || a.textContent || "") +
          " " +
          (a.getAttribute("href") || "")
        ).toLowerCase();
        return /bulletin|newsletter|notice|\b\d{1,2}(st|nd|rd|th)?.{0,8}(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i.test(
          text
        );
      });
      return {
        emoji: "🔗",
        summary: `Found ${pdfLinks.length} PDF link(s)${
          bulletinLinks.length > 0
            ? ` (${bulletinLinks.length} look like weekly bulletins)`
            : ""
        }.`,
        advice:
          "Click \"No — I need to click a link\" to select the correct bulletin.",
        type: "pdf_links",
        links: bulletinLinks.length > 0 ? bulletinLinks : pdfLinks,
        bulletinLinks,
      };
    }

    // 6. Pickable images in content areas (common on WordPress bulletin pages)
    if (hasPickableImageInContentAreas(MIN_CONTENT_IMAGE_WIDTH)) {
      return {
        emoji: "🖼️",
        summary: "Found large content image(s) that may be the bulletin.",
        advice: 'Use "Pick an image on this page" to select the bulletin image.',
        type: "image",
      };
    }

    // 6. Image bulletins
    const bulletinImages = Array.from(document.querySelectorAll("img")).filter(
      (img) => {
        const srcAttr = img.getAttribute("src") || "";
        const srcAlt = (
          srcAttr +
          " " +
          (img.getAttribute("alt") || "")
        ).toLowerCase();
        const src = srcAttr.toLowerCase();
        const inContentArea =
          img.closest(IMAGE_CONTENT_AREA_SELECTOR) || isInClassHintedContentArea(img);
        return (
          srcAlt.includes("bulletin") ||
          srcAlt.includes("newsletter") ||
          srcAlt.includes("notice") ||
          src.includes("/uploads/") ||
          src.includes("/wp-content/") ||
          isLargeImage(img, 400) ||
          Boolean(inContentArea)
        );
      }
    );
    if (bulletinImages.length > 0) {
      return {
        emoji: "🖼️",
        summary: `Found ${bulletinImages.length} possible image bulletin(s).`,
        advice: "Click \"Yes, it's an image\" to crop or mark the image bulletin.",
        type: "image",
      };
    }

    const allLinks = document.querySelectorAll("a[href],button");

    // Wix HTML bulletin — text newsletter on page (no PDF file)
    if (_isWixSite()) {
      const path = window.location.pathname || "";
      if (_hasWixDateSlug(path)) {
        const predicted = globalThis.PhPatternLibrary?.predictWixSlugUrl
          ? globalThis.PhPatternLibrary.predictWixSlugUrl(window.location.href, _nextSundayDate())
          : "";
        return {
          emoji: "📰",
          summary: "Wix HTML bulletin — the newsletter text is on this page (not a PDF file).",
          advice: 'Click "Save page as PDF" — Sunday harvest prints this into the mega bulletin.',
          type: "wix_html",
          predictedUrl: predicted,
        };
      }
      const dateLinks = Array.from(document.querySelectorAll("a[href]")).filter((a) =>
        _hasWixDateSlug(a.getAttribute("href") || "")
      );
      if (dateLinks.length >= 4) {
        return {
          emoji: "📅",
          summary: `Wix bulletin calendar — ${dateLinks.length} dated links on this page.`,
          advice: "Follow a link → pick this week's Sunday, then Save page as PDF.",
          type: "wix_date_grid",
          links: dateLinks,
        };
      }
    }

    if (allLinks.length > 0) {
      return {
        emoji: "📋",
        summary: "HTML page — no PDF or document links detected.",
        advice:
          'Background PDF detection now runs automatically. If still nothing appears, use "No — I need to click a link".',
        type: "html",
      };
    }
    return {
      emoji: "❓",
      summary: "Page type not automatically detected.",
      advice:
        "Navigate to the parish bulletin page first, then try again.",
      type: "unknown",
    };
  };

  // ── Deep Detect: monitor network requests for document URLs ──────────────

  const startDeepDetect = (onDetected, showStatus, durationMs = 10000) => {
    const detectedUrls = new Map();
    const origXHR = window.XMLHttpRequest;
    const origFetch = window.fetch;

    const trackUrl = (rawUrl) => {
      if (!rawUrl) return;
      try {
        const abs = new URL(String(rawUrl), window.location.href).href;
        if (isDocumentUrl(abs) && !detectedUrls.has(abs)) {
          detectedUrls.set(abs, true);
        }
      } catch (_e) {
        // ignore unparseable URLs
      }
    };

    // Patch XMLHttpRequest
    function PatchedXHR() {
      const xhr = new origXHR();
      const origOpen = xhr.open.bind(xhr);
      xhr.open = function (method, url, ...rest) {
        trackUrl(url);
        return origOpen(method, url, ...rest);
      };
      return xhr;
    }
    Object.setPrototypeOf(PatchedXHR, origXHR);
    PatchedXHR.prototype = origXHR.prototype;
    window.XMLHttpRequest = PatchedXHR;

    // Patch fetch
    window.fetch = function (input, ...rest) {
      const url =
        typeof input === "string"
          ? input
          : input instanceof Request
          ? input.url
          : "";
      trackUrl(url);
      return origFetch.call(this, input, ...rest);
    };

    // Scan already-loaded resources via Performance API
    try {
      (window.performance.getEntriesByType("resource") || []).forEach((e) =>
        trackUrl(e.name)
      );
    } catch (_e) {}

    // Watch new resource loads via PerformanceObserver
    let observer = null;
    try {
      observer = new PerformanceObserver((list) =>
        list.getEntries().forEach((e) => trackUrl(e.name))
      );
      observer.observe({ entryTypes: ["resource"] });
    } catch (_e) {}

    if (showStatus) {
      showStatus(
        "🔍 Deep Detect active — interact with the page for 10 s…",
        "info"
      );
    }

    setTimeout(() => {
      window.XMLHttpRequest = origXHR;
      window.fetch = origFetch;
      if (observer) observer.disconnect();
      onDetected(Array.from(detectedUrls.keys()));
    }, durationMs);
  };

  // ── Session step tracking ─────────────────────────────────────────────────

  const addSessionStep = (type, label) => {
    recipeSteps.push({ type, label, recipeStep: null });
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
  };

  const undoSessionStep = () => {
    if (recipeSteps.length === 0) return null;
    const removed = recipeSteps.pop();
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    if (typeof window.ph_undo_step === "function") {
      try {
        window.ph_undo_step({ step_type: removed?.type || "" });
      } catch (_e) {
        // ph_undo_step may not be available in all training sessions
      }
    }
    void _persistRecordingSession();
    return removed;
  };

  const _renderSessionSteps = () => {
    if (!_stepsListEl) return;
    _clearElement(_stepsListEl);
    if (recipeSteps.length === 0) {
      const empty = document.createElement("div");
      empty.style.cssText = "opacity:0.55;font-size:10px;padding:2px 0;";
      empty.textContent = "No steps recorded yet.";
      _stepsListEl.appendChild(empty);
      return;
    }
    recipeSteps.forEach((step, i) => {
      const item = document.createElement("div");
      item.style.cssText = [
        "display:flex",
        "align-items:flex-start",
        "gap:4px",
        "padding:3px 0",
        "border-bottom:1px solid #374151",
        "font-size:10px",
      ].join(";");
      const num = document.createElement("span");
      num.style.cssText = "color:#6b7280;min-width:14px;flex-shrink:0;";
      num.textContent = `${i + 1}.`;
      const txt = document.createElement("span");
      txt.style.cssText = "flex:1;word-break:break-all;line-height:1.35;";
      txt.textContent = step.label;
      item.appendChild(num);
      item.appendChild(txt);
      _stepsListEl.appendChild(item);
    });
  };

  // ── Pick Link Mode ────────────────────────────────────────────────────────

  const stopPickLinkMode = () => {
    if (!pickLinkActive) return;
    pickLinkActive = false;
    if (pickLinkHighlightEl && pickLinkHighlightEl.parentNode) {
      pickLinkHighlightEl.parentNode.removeChild(pickLinkHighlightEl);
    }
    pickLinkHighlightEl = null;
    pickLinkCancelListeners.forEach(({ el, type, fn }) =>
      el.removeEventListener(type, fn, true)
    );
    pickLinkCancelListeners = [];
    document.body.style.cursor = "";
  };

  const startPickLinkMode = (onPick, showStatus) => {
    if (pickLinkActive) stopPickLinkMode();
    pickLinkActive = true;
    document.body.style.cursor = "crosshair";
    if (showStatus) {
      showStatus(
        "🎯 Hover a link and click it. The page will NOT move yet — confirm, then use \"Record & open link\". Escape to cancel.",
        "info"
      );
    }

    const highlight = document.createElement("div");
    Object.assign(highlight.style, {
      position: "fixed",
      pointerEvents: "none",
      border: "2px solid #f59e0b",
      background: "rgba(245,158,11,0.12)",
      borderRadius: "4px",
      zIndex: "2147483645",
      display: "none",
      boxSizing: "border-box",
    });
    document.documentElement.appendChild(highlight);
    pickLinkHighlightEl = highlight;

    const CANDIDATE_SELECTOR = 'a,button,[role="button"],[role="link"],input[type="submit"],input[type="button"]';

    const onMouseMove = (e) => {
      if (!pickLinkActive) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el && el.closest("#ph-floating-toolbar")) {
        highlight.style.display = "none";
        return;
      }
      const candidate = el ? el.closest(CANDIDATE_SELECTOR) : null;
      if (candidate) {
        const r = candidate.getBoundingClientRect();
        Object.assign(highlight.style, {
          display: "block",
          left: `${r.left - 2}px`,
          top: `${r.top - 2}px`,
          width: `${r.width + 4}px`,
          height: `${r.height + 4}px`,
        });
      } else {
        highlight.style.display = "none";
      }
    };

    const onClick = (e) => {
      if (!pickLinkActive) return;
      if (
        e.target instanceof Element &&
        e.target.closest("#ph-floating-toolbar")
      )
        return;
      const el = e.target instanceof Element
        ? e.target.closest(CANDIDATE_SELECTOR) || e.target
        : null;
      if (el && el.closest && el.closest("#ph-floating-toolbar")) return;
      if (!el) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      stopPickLinkMode();
      onPick(el);
    };

    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        stopPickLinkMode();
        if (showStatus) showStatus("❌ Link selection cancelled.", "info");
      }
    };

    setTimeout(() => {
      if (!pickLinkActive) return;
      document.addEventListener("mousemove", onMouseMove, true);
      document.addEventListener("click", onClick, true);
      document.addEventListener("keydown", onKeyDown, true);
      pickLinkCancelListeners = [
        { el: document, type: "mousemove", fn: onMouseMove },
        { el: document, type: "click", fn: onClick },
        { el: document, type: "keydown", fn: onKeyDown },
      ];
    }, 0);
  };

  // ── Pick Image Mode ───────────────────────────────────────────────────────

  const stopPickImageMode = () => {
    if (!pickImageActive) return;
    pickImageActive = false;
    if (pickImageHighlightEl && pickImageHighlightEl.parentNode) {
      pickImageHighlightEl.parentNode.removeChild(pickImageHighlightEl);
    }
    pickImageHighlightEl = null;
    pickImageCancelListeners.forEach(({ el, type, fn }) =>
      el.removeEventListener(type, fn, true)
    );
    pickImageCancelListeners = [];
    document.body.style.cursor = "";
  };

  const startPickImageMode = (onPick, showStatus) => {
    if (pickImageActive) stopPickImageMode();
    pickImageActive = true;
    document.body.style.cursor = "crosshair";
    if (showStatus) {
      showStatus(
        "🖼️ Hover over an image and click to select it. Press Escape to cancel.",
        "info"
      );
    }

    const highlight = document.createElement("div");
    Object.assign(highlight.style, {
      position: "fixed",
      pointerEvents: "none",
      border: "3px solid #f59e0b",
      background: "rgba(245,158,11,0.15)",
      borderRadius: "4px",
      zIndex: "2147483645",
      display: "none",
      boxSizing: "border-box",
    });
    document.documentElement.appendChild(highlight);
    pickImageHighlightEl = highlight;

    const IMAGE_SELECTOR = "img";

    const onMouseMove = (e) => {
      if (!pickImageActive) return;
      const el = document.elementFromPoint(e.clientX, e.clientY);
      if (el && el.closest("#ph-floating-toolbar")) {
        highlight.style.display = "none";
        return;
      }
      const candidate = el
        ? el.closest(IMAGE_SELECTOR) || (el.tagName === "IMG" ? el : null)
        : null;
      if (candidate) {
        const r = candidate.getBoundingClientRect();
        Object.assign(highlight.style, {
          display: "block",
          left: `${r.left - 3}px`,
          top: `${r.top - 3}px`,
          width: `${r.width + 6}px`,
          height: `${r.height + 6}px`,
        });
      } else {
        highlight.style.display = "none";
      }
    };

    const onClick = (e) => {
      if (!pickImageActive) return;
      if (e.target instanceof Element && e.target.closest("#ph-floating-toolbar"))
        return;
      const el =
        e.target instanceof Element
          ? e.target.closest(IMAGE_SELECTOR) ||
            (e.target.tagName === "IMG" ? e.target : null)
          : null;
      if (!el) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      stopPickImageMode();
      onPick(el);
    };

    const onKeyDown = (e) => {
      if (e.key === "Escape") {
        stopPickImageMode();
        if (showStatus) showStatus("❌ Image selection cancelled.", "info");
      }
    };

    document.addEventListener("mousemove", onMouseMove, true);
    document.addEventListener("click", onClick, true);
    document.addEventListener("keydown", onKeyDown, true);
    pickImageCancelListeners = [
      { el: document, type: "mousemove", fn: onMouseMove },
      { el: document, type: "click", fn: onClick },
      { el: document, type: "keydown", fn: onKeyDown },
    ];
  };

  // ── Safety-checked mark download URL ─────────────────────────────────────

  const _standaloneAddClickAndDownload = (clickStep, downloadUrl, clickLabel, showStatus) => {
    standaloneAddStep(clickStep, "click", clickLabel);
    standaloneAddStep(
      { action: "download", url: downloadUrl },
      "mark_file",
      `📄 Download: ${downloadUrl.slice(-50)}`
    );
    void _persistRecordingSession();
    if (showStatus) {
      showStatus(
        "✅ Click + download steps saved. Brave may auto-download the PDF — you can push the recipe now.",
        "ok"
      );
    }
    if (typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
      try {
        chrome.runtime.sendMessage({ type: "recording_tab_active" });
      } catch (_e) {}
    }
  };

  const _notifyRecordingTabActive = () => {
    if (typeof chrome !== "undefined" && chrome.runtime?.sendMessage) {
      try {
        chrome.runtime.sendMessage({ type: "recording_tab_active" });
      } catch (_e) {}
    }
  };

  const _pathLooksLikeNewsletterPage = () => {
    try {
      return /\/(news|newsletter|bulletin|parishnews|nuacht)/i.test(
        new URL(_pageUrlForParishDetection()).pathname || ""
      );
    } catch (_e) {
      return false;
    }
  };

  const markDownloadUrlSafe = (url, showStatus, forceConfirm) => {
    if (!url) {
      if (showStatus) showStatus("❌ No URL to mark.", "error");
      return;
    }
    if (!isDocumentUrl(url) && !_looksLikeBulletinDownloadUrl(url) && !forceConfirm) {
      const preview = url.length > 60 ? url.slice(0, 57) + "…" : url;
      if (showStatus) {
        showStatus(
          `⚠️ "${preview}" doesn't look like a PDF/document. See "Mark Anyway" button below.`,
          "warn"
        );
      }
      window.dispatchEvent(
        new CustomEvent("ph-confirm-mark-download", { detail: { url } })
      );
      return;
    }
    if (window.ph_mark_download_url) {
      try {
        const request = { url };
        const result = window.ph_mark_download_url(request);
        const response = result === false
          ? { ok: false, reason: "Page rejected the file URL save." }
          : { ok: true };
        _logSaveCycle("mark_file", request, response);
        if (result === false) {
          if (showStatus) showStatus(`❌ ${response.reason}`, "error");
          return;
        }
        addSessionStep("mark_file", `📄 File: ${url.slice(-50)}`);
        if (showStatus) showStatus("✅ Bulletin file URL recorded.");
      } catch (_e) {
        _logSaveCycle("mark_file", { url }, { ok: false, reason: "Could not communicate with page. Try refreshing." });
        if (showStatus)
          showStatus(
            "❌ Could not communicate with page. Try refreshing.",
            "error"
          );
      }
    } else {
      // Standalone mode: accumulate step locally for later GitHub push
      standaloneAddStep(
        { action: "download", url },
        "mark_file",
        `📄 File: ${url.slice(-50)}`
      );
      if (showStatus) showStatus("✅ File URL saved (standalone). Use ⬆ Push Recipe to save to GitHub.");
    }
  };

  // ── Iframe picker panel ───────────────────────────────────────────────────

  const buildIframePickerPanel = (showStatus) => {
    const iframes = Array.from(document.querySelectorAll("iframe[src]"));
    if (iframes.length === 0) {
      if (showStatus)
        showStatus(
          "ℹ️ No iframes on this page. Try \"Pick Bulletin Link\" for PDF links.",
          "info"
        );
      return null;
    }

    const panel = document.createElement("div");
    panel.style.cssText = [
      "background:#0f172a",
      "border-radius:4px",
      "padding:6px",
      "font-size:10px",
    ].join(";");

    const heading = document.createElement("div");
    heading.style.cssText = "font-weight:600;margin-bottom:6px;color:#93c5fd;";
    heading.textContent = `Found ${iframes.length} iframe(s) — click to select the bulletin:`;
    panel.appendChild(heading);

    // Score and sort iframes by date (bulletins/resolved URLs newest first)
    const _iframeScores = iframes.map((frame, idx) => {
      const _src = frame.getAttribute("src") || "";
      const _lower = _src.toLowerCase();
      let _resolved = _src;
      if (_lower.includes("docs.google.com/viewer") || _lower.includes("docs.google.com/gview")) {
        try {
          const _p = new URL(_src, window.location.href).searchParams.get("url");
          if (_p) _resolved = decodeURIComponent(_p);
        } catch (_e2) {}
      }
      return { frame, domIdx: idx, ...scoreUrlCandidateStr(_resolved, "", idx) };
    });
    _iframeScores.sort(_bulletinDateSortFn);
    const _sortedFrames = _iframeScores.map((i) => i.frame);

    _sortedFrames.forEach((frame, idx) => {
      const src = frame.getAttribute("src") || "";
      const lowerSrc = src.toLowerCase();
      let resolvedUrl = src;
      let isBulletin = false;
      let isWixViewer = false;

      // Unwrap Google Docs viewer URL
      if (
        lowerSrc.includes("docs.google.com/viewer") ||
        lowerSrc.includes("docs.google.com/gview")
      ) {
        try {
          const urlParam = new URL(src, window.location.href).searchParams.get("url");
          if (urlParam) {
            resolvedUrl = decodeURIComponent(urlParam);
            isBulletin = true;
          }
        } catch (_e) {
          // keep original src
        }
      } else if ((() => {
          try {
            const hostname = new URL(src, window.location.href).hostname.toLowerCase();
            return hostname === "wixlabs-pdf-dev.appspot.com" || hostname.startsWith("wixlabs-pdf");
          } catch (_e) { return false; }
        })()) {
        // Unwrap Wix PDF viewer URL
        try {
          const wixUrl = new URL(src, window.location.href);
          const pdfParam =
            wixUrl.searchParams.get("url") ||
            wixUrl.searchParams.get("PDF_URL") ||
            wixUrl.searchParams.get("pdf") ||
            wixUrl.searchParams.get("file");
          if (pdfParam) {
            resolvedUrl = decodeURIComponent(pdfParam);
            isBulletin = true;
          } else {
            // Can't extract URL — mark as Wix viewer so we show special instruction
            isWixViewer = true;
          }
        } catch (_e) {
          isWixViewer = true;
        }
      } else if (
        lowerSrc.endsWith(".pdf") ||
        lowerSrc.includes(".pdf?") ||
        lowerSrc.includes("drive.google.com/file")
      ) {
        isBulletin = true;
      }

      let hostname = "";
      try {
        hostname = new URL(src, window.location.href).hostname;
      } catch (_e) {
        hostname = src.slice(0, 30);
      }
      const preview = src.length > 50 ? src.slice(0, 47) + "…" : src;

      const row = document.createElement("div");
      row.style.cssText = [
        "display:flex",
        "align-items:flex-start",
        "gap:5px",
        "padding:5px",
        "border-radius:4px",
        "cursor:pointer",
        "border:1px solid " + (isBulletin ? "#16a34a" : "#374151"),
        "background:" + (isBulletin ? "rgba(22,163,74,0.08)" : "transparent"),
        "margin-bottom:4px",
      ].join(";");

      const badge = document.createElement("span");
      badge.style.cssText =
        "background:#374151;border-radius:3px;padding:1px 4px;font-size:9px;white-space:nowrap;flex-shrink:0;";
      badge.textContent = `#${idx + 1}`;

      const info = document.createElement("div");
      info.style.cssText = "flex:1;word-break:break-all;line-height:1.3;";
      const mainText = document.createElement("div");
      if (isBulletin && resolvedUrl !== src) {
        const filename = resolvedUrl.replace(/\/+$/, '').split('/').pop().split('?')[0];
        const truncated = resolvedUrl.length > 55 ? resolvedUrl.slice(0, 55) + "…" : resolvedUrl;
        mainText.textContent = `✅ ${filename}`;
        info.appendChild(mainText);
        const sub = document.createElement("span");
        sub.style.cssText = "display:block;color:#9ca3af;font-size:9px;";
        sub.textContent = truncated;
        info.appendChild(sub);
      } else {
        mainText.textContent = `${isBulletin ? "✅ " : ""}${hostname} — ${preview}`;
        info.appendChild(mainText);
      }
      if (isWixViewer) {
        const wixNote = document.createElement("div");
        wixNote.style.cssText = "color:#93c5fd;font-size:9px;margin-top:2px;line-height:1.4;";
        wixNote.textContent = "💡 Wix PDF viewer — click the ↓ download icon at the TOP of the viewer. When a new tab opens with the PDF, come back and click 📄 Get a PDF.";
        info.appendChild(wixNote);
      } else if (!isBulletin) {
        const warn = document.createElement("div");
        warn.style.cssText = "color:#f59e0b;font-size:9px;margin-top:2px;";
        warn.textContent = "⚠️ Not clearly a document — confirm before using";
        info.appendChild(warn);
      }

      row.appendChild(badge);
      row.appendChild(info);

      row.addEventListener("mouseenter", () => {
        row.style.background = isBulletin
          ? "rgba(22,163,74,0.2)"
          : "rgba(255,255,255,0.05)";
      });
      row.addEventListener("mouseleave", () => {
        row.style.background = isBulletin ? "rgba(22,163,74,0.08)" : "transparent";
      });

      row.addEventListener("click", () => {
        markDownloadUrlSafe(resolvedUrl, showStatus, isBulletin);
        if (isDocumentUrl(resolvedUrl)) {
          if (panel.parentNode) panel.parentNode.removeChild(panel);
        }
      });

      panel.appendChild(row);
    });

    return panel;
  };

  // ── Crop overlay ──────────────────────────────────────────────────────────

  let cropSectionIndicator = null;

  const emitCrop = (payload) => {
    lastCropSignature = cropSignature(payload);
    if (window.ph_mark_crop) {
      window.ph_mark_crop(payload);
    } else {
      console.warn("Parish Trainer: ph_mark_crop binding is unavailable.");
    }
    addSessionStep("crop", "✂️ Crop recorded");
    window.postMessage(
      { direction: "from-main", message: { type: "crop_done", ...payload } },
      "*"
    );
  };

  const removeCropOverlay = () => {
    if (cropOverlay && cropOverlay.parentNode) {
      cropOverlay.parentNode.removeChild(cropOverlay);
    }
    cropOverlay = null;
  };

  const removeSectionIndicator = () => {
    if (cropSectionIndicator && cropSectionIndicator.parentNode) {
      cropSectionIndicator.parentNode.removeChild(cropSectionIndicator);
    }
    cropSectionIndicator = null;
  };

  const showSectionIndicator = (count) => {
    removeSectionIndicator();
    cropSectionIndicator = document.createElement("div");
    Object.assign(cropSectionIndicator.style, {
      position: "fixed",
      top: "12px",
      right: "12px",
      zIndex: "2147483646",
      background: "rgba(37,99,235,0.92)",
      color: "#fff",
      borderRadius: "8px",
      padding: "10px 16px",
      fontSize: "14px",
      fontFamily: "system-ui, -apple-system, sans-serif",
      boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      userSelect: "none",
      lineHeight: "1.4",
    });
    cropSectionIndicator.textContent = `${count} section${
      count !== 1 ? "s" : ""
    } saved — draw the next section`;
    document.documentElement.appendChild(cropSectionIndicator);
  };

  const startCrop = () => {
    removeCropOverlay();

    const sections = [];
    const HANDLE_SIZE = 12;
    const MIN_CROP_SIZE = 5;

    const beginDrawing = () => {
      const overlay = document.createElement("div");
      Object.assign(overlay.style, {
        position: "fixed",
        top: "0",
        left: "0",
        width: "100%",
        height: "100%",
        zIndex: "2147483647",
        cursor: "crosshair",
        background: "rgba(37,99,235,0.02)",
        userSelect: "none",
      });

      const rect = document.createElement("div");
      Object.assign(rect.style, {
        position: "fixed",
        border: "2px dashed #3b82f6",
        background: "rgba(59,130,246,0.15)",
        pointerEvents: "none",
        display: "none",
        boxSizing: "border-box",
      });
      overlay.appendChild(rect);

      // Scroll hint shown while the overlay is active
      const scrollHint = document.createElement("div");
      Object.assign(scrollHint.style, {
        position: "fixed",
        bottom: "14px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: "2147483647",
        background: "rgba(30,41,59,0.92)",
        color: "#93c5fd",
        borderRadius: "6px",
        padding: "5px 14px",
        fontSize: "11px",
        fontFamily: "system-ui, -apple-system, sans-serif",
        pointerEvents: "none",
        whiteSpace: "nowrap",
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      });
      scrollHint.textContent =
        "🖱 Scroll with mouse wheel · drag near top/bottom edge to auto-scroll · Add More for multi-section";
      overlay.appendChild(scrollHint);

      let startX = 0;
      let startY = 0;
      let scrollYAtDragStart = 0;
      let lastMouseClientX = 0;
      let lastMouseClientY = 0;
      let autoScrollRAF = null;
      let dragging = false;
      let editMode = false;
      let cropBox = { left: 0, top: 0, width: 0, height: 0 };
      const handles = [];
      let optionsBar = null;

      const syncRect = () => {
        const { left, top, width, height } = cropBox;
        rect.style.display = "block";
        rect.style.left = `${left}px`;
        rect.style.top = `${top}px`;
        rect.style.width = `${width}px`;
        rect.style.height = `${height}px`;
      };

      const handlePositions = [
        { xFrac: 0,   yFrac: 0   },
        { xFrac: 0.5, yFrac: 0   },
        { xFrac: 1,   yFrac: 0   },
        { xFrac: 1,   yFrac: 0.5 },
        { xFrac: 1,   yFrac: 1   },
        { xFrac: 0.5, yFrac: 1   },
        { xFrac: 0,   yFrac: 1   },
        { xFrac: 0,   yFrac: 0.5 },
      ];

      const syncHandles = () => {
        const { left, top, width, height } = cropBox;
        handles.forEach((h, i) => {
          const p = handlePositions[i];
          h.el.style.left = `${left + p.xFrac * width - HANDLE_SIZE / 2}px`;
          h.el.style.top  = `${top  + p.yFrac * height - HANDLE_SIZE / 2}px`;
        });
      };

      const syncOptionsBar = () => {
        if (!optionsBar) return;
        const { left, top, width, height } = cropBox;
        const barH = 52;
        const barW = optionsBar.offsetWidth || 300;
        const viewH = window.innerHeight;
        const viewW = window.innerWidth;
        const barTop =
          top + height + barH + 8 <= viewH
            ? top + height + 6
            : top - barH - 6;
        const barLeft = Math.min(
          Math.max(left + width / 2 - barW / 2, 6),
          viewW - barW - 6
        );
        optionsBar.style.left = `${barLeft}px`;
        optionsBar.style.top  = `${Math.max(4, barTop)}px`;
      };

      const makeCursor = (xDir, yDir) => {
        if (xDir === 0)  return yDir < 0 ? "n-resize"  : "s-resize";
        if (yDir === 0)  return xDir < 0 ? "w-resize"  : "e-resize";
        if (xDir < 0)    return yDir < 0 ? "nw-resize" : "sw-resize";
        return yDir < 0 ? "ne-resize" : "se-resize";
      };

      const createHandle = (xDir, yDir) => {
        const el = document.createElement("div");
        Object.assign(el.style, {
          position: "fixed",
          width: `${HANDLE_SIZE}px`,
          height: `${HANDLE_SIZE}px`,
          background: "#fff",
          border: "2px solid #3b82f6",
          borderRadius: "2px",
          cursor: makeCursor(xDir, yDir),
          zIndex: "2147483647",
          boxSizing: "border-box",
        });

        el.addEventListener("mousedown", (e) => {
          e.stopPropagation();
          e.preventDefault();
          const startRX = e.clientX;
          const startRY = e.clientY;
          const snapBox = { ...cropBox };

          const onMM = (me) => {
            const dx = me.clientX - startRX;
            const dy = me.clientY - startRY;
            let { left, top, width, height } = snapBox;
            if (xDir === -1) { left = snapBox.left + dx; width = snapBox.width - dx; }
            else if (xDir === 1) { width = snapBox.width + dx; }
            if (yDir === -1) { top = snapBox.top + dy; height = snapBox.height - dy; }
            else if (yDir === 1) { height = snapBox.height + dy; }
            if (width < MIN_CROP_SIZE)  {
              width = MIN_CROP_SIZE;
              if (xDir === -1) left = snapBox.left + snapBox.width - MIN_CROP_SIZE;
            }
            if (height < MIN_CROP_SIZE) {
              height = MIN_CROP_SIZE;
              if (yDir === -1) top  = snapBox.top  + snapBox.height - MIN_CROP_SIZE;
            }
            cropBox = { left, top, width, height };
            syncRect();
            syncHandles();
            syncOptionsBar();
          };

          const onMU = () => {
            document.removeEventListener("mousemove", onMM);
            document.removeEventListener("mouseup", onMU);
          };
          document.addEventListener("mousemove", onMM);
          document.addEventListener("mouseup", onMU);
        });
        return el;
      };

      const showEditMode = () => {
        editMode = true;
        overlay.style.cursor = "default";
        overlay.style.background = "transparent";

        const handleDirs = [
          [-1, -1], [0, -1], [1, -1],
          [ 1,  0],
          [ 1,  1], [0,  1], [-1,  1],
          [-1,  0],
        ];
        handleDirs.forEach(([xDir, yDir]) => {
          const el = createHandle(xDir, yDir);
          overlay.appendChild(el);
          handles.push({ el, xDir, yDir });
        });
        syncHandles();

        optionsBar = document.createElement("div");
        Object.assign(optionsBar.style, {
          position: "fixed",
          zIndex: "2147483647",
          background: "#1e293b",
          border: "1px solid #3b82f6",
          borderRadius: "8px",
          padding: "6px 10px",
          display: "flex",
          gap: "8px",
          alignItems: "center",
          boxShadow: "0 4px 16px rgba(0,0,0,0.55)",
          fontFamily: "system-ui, -apple-system, sans-serif",
        });

        const makeBtn = (label, bg, onClick) => {
          const btn = document.createElement("button");
          btn.textContent = label;
          Object.assign(btn.style, {
            border: "none",
            borderRadius: "6px",
            padding: "9px 18px",
            background: bg,
            color: "#fff",
            cursor: "pointer",
            fontSize: "14px",
            fontWeight: "600",
            fontFamily: "inherit",
            whiteSpace: "nowrap",
          });
          btn.addEventListener("mousedown", (e) => e.stopPropagation());
          btn.addEventListener("click", (e) => { e.stopPropagation(); onClick(); });
          return btn;
        };

        const confirmBtn = makeBtn("Confirm", "#16a34a", () => {
          const { left, top, width, height } = cropBox;
          if (width < MIN_CROP_SIZE || height < MIN_CROP_SIZE) return;
          const pageX = left + window.scrollX;
          const pageY = top  + window.scrollY;
          const element_selector = nearestElementSelector(left + width / 2, top + height / 2);
          const lastSection = { x: left, y: top, width, height, pageX, pageY, element_selector };
          removeSectionIndicator();
          removeCropOverlay();
          const allSections = [...sections, lastSection];
          if (allSections.length > 1) {
            emitCrop({ ...lastSection, sections: allSections });
          } else {
            emitCrop(lastSection);
          }
        });

        const addMoreBtn = makeBtn("Add More", "#2563eb", () => {
          const { left, top, width, height } = cropBox;
          if (width < MIN_CROP_SIZE || height < MIN_CROP_SIZE) return;
          const pageX = left + window.scrollX;
          const pageY = top  + window.scrollY;
          const element_selector = nearestElementSelector(left + width / 2, top + height / 2);
          sections.push({ x: left, y: top, width, height, pageX, pageY, element_selector });
          removeCropOverlay();
          showSectionIndicator(sections.length);
          beginDrawing();
        });

        const cancelBtn = makeBtn("Cancel", "#dc2626", () => {
          removeSectionIndicator();
          removeCropOverlay();
        });

        optionsBar.appendChild(confirmBtn);
        optionsBar.appendChild(addMoreBtn);
        optionsBar.appendChild(cancelBtn);
        overlay.appendChild(optionsBar);
        requestAnimationFrame(syncOptionsBar);
      };

      const onMove = (event) => {
        if (!dragging || editMode) return;
        lastMouseClientX = event.clientX;
        lastMouseClientY = event.clientY;
        const scrollDelta = window.scrollY - scrollYAtDragStart;
        const adjustedStartY = startY - scrollDelta;
        cropBox = {
          left:   Math.min(startX, event.clientX),
          top:    Math.min(adjustedStartY, event.clientY),
          width:  Math.abs(event.clientX - startX),
          height: Math.abs(event.clientY - adjustedStartY),
        };
        syncRect();
      };

      const finish = (event) => {
        if (!dragging) return;
        dragging = false;
        if (autoScrollRAF !== null) {
          cancelAnimationFrame(autoScrollRAF);
          autoScrollRAF = null;
        }
        const endX = event.clientX;
        const endY = event.clientY;
        const scrollDelta = window.scrollY - scrollYAtDragStart;
        const adjustedStartY = startY - scrollDelta;
        cropBox = {
          left:   Math.min(startX, endX),
          top:    Math.min(adjustedStartY, endY),
          width:  Math.abs(endX - startX),
          height: Math.abs(endY - adjustedStartY),
        };
        if (cropBox.width < MIN_CROP_SIZE || cropBox.height < MIN_CROP_SIZE) {
          if (sections.length === 0) removeCropOverlay();
          return;
        }
        syncRect();
        showEditMode();
      };

      // ── Auto-scroll while dragging near the top/bottom edge ──────────────
      const AUTOSCROLL_EDGE_PX = 60;
      const AUTOSCROLL_SPEED_PX = 8;

      const autoScrollTick = () => {
        if (!dragging || editMode) {
          autoScrollRAF = null;
          return;
        }
        let scrollDir = 0;
        if (lastMouseClientY < AUTOSCROLL_EDGE_PX) {
          scrollDir = -AUTOSCROLL_SPEED_PX;
        } else if (lastMouseClientY > window.innerHeight - AUTOSCROLL_EDGE_PX) {
          scrollDir = AUTOSCROLL_SPEED_PX;
        }
        if (scrollDir !== 0) {
          window.scrollBy(0, scrollDir);
          const scrollDelta = window.scrollY - scrollYAtDragStart;
          const adjustedStartY = startY - scrollDelta;
          cropBox = {
            left:   Math.min(startX, lastMouseClientX),
            top:    Math.min(adjustedStartY, lastMouseClientY),
            width:  Math.abs(lastMouseClientX - startX),
            height: Math.abs(lastMouseClientY - adjustedStartY),
          };
          syncRect();
        }
        autoScrollRAF = requestAnimationFrame(autoScrollTick);
      };

      overlay.addEventListener("mousedown", (event) => {
        if (editMode) return;
        event.preventDefault();
        startX = event.clientX;
        startY = event.clientY;
        scrollYAtDragStart = window.scrollY;
        lastMouseClientX = event.clientX;
        lastMouseClientY = event.clientY;
        dragging = true;
        rect.style.display = "none";
        autoScrollRAF = requestAnimationFrame(autoScrollTick);
      });

      // Allow mouse-wheel scrolling while the overlay is active.
      overlay.addEventListener("wheel", (event) => {
        event.preventDefault();
        window.scrollBy(0, event.deltaY);
        if (dragging) {
          const scrollDelta = window.scrollY - scrollYAtDragStart;
          const adjustedStartY = startY - scrollDelta;
          cropBox = {
            left:   Math.min(startX, lastMouseClientX),
            top:    Math.min(adjustedStartY, lastMouseClientY),
            width:  Math.abs(lastMouseClientX - startX),
            height: Math.abs(lastMouseClientY - adjustedStartY),
          };
          syncRect();
        }
      }, { passive: false });
      overlay.addEventListener("mousemove", onMove);
      overlay.addEventListener("mouseup", finish);
      overlay.addEventListener("mouseleave", (event) => {
        if (dragging && !editMode) finish(event);
      });

      cropOverlay = overlay;
      document.documentElement.appendChild(overlay);
    };

    beginDrawing();
  };

  // ── Chrome interstitial detection helpers ─────────────────────────────────

  const detectChromeInterstitial = () => {
    return (
      document.getElementById("main-frame-error") !== null ||
      document.getElementById("security-interstitial-content") !== null ||
      (document.body && document.body.id === "t")
    );
  };

  const tryClickChromeInterstitialProceed = () => {
    const btn =
      document.getElementById("proceed-link") ||
      document.getElementById("proceed-button") ||
      document.querySelector("#proceed-link, #proceed-button, .proceed-button, [id*='proceed']");
    if (btn) { try { btn.click(); } catch (_e) {} }
  };

  // ── createToolbar ─────────────────────────────────────────────────────────

  const createToolbar = () => {
    const bar = document.createElement("div");
    bar.id = TOOLBAR_ID;
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", "Parish Trainer");
    bar.style.cssText = [
      "position: fixed",
      "top: 10px",
      "left: 50%",
      "transform: translateX(-50%)",
      "z-index: 2147483646",
      "background: #111827",
      "color: #f9fafb",
      "font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif",
      "font-size: 12px",
      "border-radius: 8px",
      "box-shadow: 0 4px 16px rgba(0,0,0,0.55)",
      "display: flex",
      "flex-direction: column",
      "min-width: 320px",
      "max-width: 420px",
      "user-select: none",
      "pointer-events: auto",
      "overflow: hidden",
      `max-height: calc(${window.innerHeight}px - 40px)`,
    ].join(";");
    window.addEventListener("resize", () => {
      bar.style.maxHeight = `calc(${window.innerHeight}px - 40px)`;
    });

    // ── Header / drag handle ───────────────────────────────────────────────
    const header = document.createElement("div");
    header.style.cssText = [
      "display: flex",
      "align-items: center",
      "justify-content: space-between",
      "padding: 5px 8px",
      "background: #1f2937",
      "border-radius: 8px 8px 0 0",
      "cursor: grab",
      "gap: 8px",
    ].join(";");

    const title = document.createElement("span");
    title.textContent = "⠿ Parish Trainer";
    title.style.cssText = "font-weight:600;font-size:11px;opacity:0.9;white-space:nowrap;";
    header.appendChild(title);

    const versionBadge = document.createElement("span");
    versionBadge.style.cssText = "color:#93c5fd;font-size:10px;white-space:nowrap;";
    try {
      versionBadge.textContent = `v${chrome.runtime.getManifest().version}`;
    } catch (_e) {
      versionBadge.textContent = "";
    }
    header.appendChild(versionBadge);

    const guidedBadge = document.createElement("span");
    guidedBadge.textContent = "Guided ✓";
    guidedBadge.title = "Guided Mode ON — follow the steps below";
    guidedBadge.style.cssText = [
      "background:#16a34a",
      "color:#fff",
      "border-radius:4px",
      "padding:1px 5px",
      "font-size:9px",
      "font-weight:600",
      "white-space:nowrap",
    ].join(";");
    header.appendChild(guidedBadge);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.textContent = "✕";
    closeBtn.title = "Hide toolbar";
    closeBtn.style.cssText = [
      "background: none",
      "border: none",
      "color: #9ca3af",
      "cursor: pointer",
      "font-size: 12px",
      "line-height: 1",
      "padding: 0 2px",
      "margin-left: auto",
    ].join(";");
    closeBtn.addEventListener("click", () => {
      bar.dataset.phHidden = "true";
      bar.style.display = "none";
      stopPickLinkMode();
      stopPickImageMode();
    });
    header.appendChild(closeBtn);

    const dockBtn = document.createElement("button");
    dockBtn.type = "button";
    dockBtn.textContent = "⊡";
    dockBtn.title = "Snap to top-right corner";
    dockBtn.style.cssText = [
      "background: none",
      "border: none",
      "color: #9ca3af",
      "cursor: pointer",
      "font-size: 12px",
      "line-height: 1",
      "padding: 0 2px",
    ].join(";");
    dockBtn.addEventListener("click", () => {
      bar.style.left = window.innerWidth - bar.offsetWidth - 10 + "px";
      bar.style.top = "10px";
      bar.style.transform = "";
    });
    header.appendChild(dockBtn);

    // Interstitial banner (shown when Chrome blocks the page)
    if (detectChromeInterstitial()) {
      const interstitialBanner = document.createElement("div");
      interstitialBanner.id = "ph-interstitial-banner";
      interstitialBanner.style.cssText = [
        "background:#7f1d1d",
        "color:#fca5a5",
        "padding:8px 10px",
        "font-size:11px",
        "line-height:1.5",
        "border-radius:8px 8px 0 0",
      ].join(";");
      const msg = document.createElement("div");
      msg.textContent = "⚠️ Chrome is blocking this page (connection not private).";
      const instruction = document.createElement("div");
      instruction.style.cssText = "margin-top:4px;font-weight:600;";
      instruction.textContent = "👉 Click Advanced → Proceed to [site] (unsafe), then click Continue here.";
      const continueBtn = document.createElement("button");
      continueBtn.type = "button";
      continueBtn.textContent = "Continue here ↩";
      continueBtn.style.cssText = [
        "margin-top:6px","border:none","border-radius:4px",
        "padding:4px 10px","background:#dc2626","color:#fff",
        "cursor:pointer","font-size:10px","font-family:inherit",
      ].join(";");
      continueBtn.addEventListener("click", () => {
        tryClickChromeInterstitialProceed();
        if (interstitialBanner.parentNode) interstitialBanner.parentNode.removeChild(interstitialBanner);
      });
      interstitialBanner.appendChild(msg);
      interstitialBanner.appendChild(instruction);
      interstitialBanner.appendChild(continueBtn);
      bar.appendChild(interstitialBanner);
    }

    bar.appendChild(header);

    // ── Status bar ─────────────────────────────────────────────────────────
    const statusBar = document.createElement("div");
    statusBar.style.cssText = [
      "display: none",
      "padding: 5px 10px",
      "font-size: 10px",
      "text-align: center",
      "line-height: 1.4",
      "word-break: break-word",
      "border-radius: 0 0 8px 8px",
      "transition: opacity 0.3s",
    ].join(";");

    let statusTimer = null;
    const showStatus = (message, type) => {
      clearTimeout(statusTimer);
      // Remove any existing "Mark Anyway" buttons
      const old = statusBar.querySelector(".ph-mark-anyway");
      if (old) statusBar.removeChild(old);
      statusBar.textContent = message;
      statusBar.style.display = "block";
      statusBar.style.opacity = "1";
      statusBar.dataset.status =
        type === "error"
          ? "error"
          : (type === "info" || type === "warn" || String(message || "").startsWith("⏳"))
          ? "pending"
          : "success";
      if (type === "error") {
        statusBar.style.background = "#7f1d1d";
        statusBar.style.color = "#fca5a5";
      } else if (type === "warn") {
        statusBar.style.background = "#78350f";
        statusBar.style.color = "#fde68a";
      } else if (type === "info") {
        statusBar.style.background = "#1e3a5f";
        statusBar.style.color = "#93c5fd";
      } else {
        statusBar.style.background = "#14532d";
        statusBar.style.color = "#86efac";
      }
      // Success banners stay visible longer so the user can read the URL.
      const displayMs = (type === "error") ? 12000 : (type === "info" || type === "warn") ? 6000 : 10000;
      statusTimer = setTimeout(() => {
        statusBar.style.opacity = "0";
        setTimeout(() => { statusBar.style.display = "none"; }, 300);
      }, displayMs);
    };

    // ── Body container ─────────────────────────────────────────────────────
    const body = document.createElement("div");
    body.style.cssText = "padding:8px;display:flex;flex-direction:column;gap:6px;";

    // Helper: small styled button
    const makeSmallBtn = (label, bg, onClick, tooltip) => {
      const btn = document.createElement("button");
      btn.textContent = label;
      if (tooltip) btn.title = tooltip;
      btn.style.cssText = [
        "border: none",
        "border-radius: 6px",
        "padding: 6px 10px",
        "background: " + (bg || "#2563eb"),
        "color: #fff",
        "cursor: pointer",
        "font-size: 11px",
        "text-align: left",
        "white-space: normal",
        "font-family: inherit",
        "line-height: 1.3",
        "width: 100%",
      ].join(";");
      btn.addEventListener("mouseenter", () => { btn.style.filter = "brightness(1.15)"; });
      btn.addEventListener("mouseleave", () => { btn.style.filter = ""; });
      btn.addEventListener("click", onClick);
      return btn;
    };

    // ── GUIDED MODE WIZARD ─────────────────────────────────────────────────
    let clickFirstBtn = null;
    const guidedPanel = document.createElement("div");
    guidedPanel.style.cssText = [
      "background:#1e293b",
      "border:1px solid #2563eb",
      "border-radius:6px",
      "padding:8px",
    ].join(";");

    const wizardQ = document.createElement("div");
    wizardQ.style.cssText = "font-size:11px;font-weight:600;margin-bottom:6px;color:#93c5fd;";
    wizardQ.textContent = "Step 1 — follow a menu link to reach the bulletin";

    const nextStepBanner = document.createElement("div");
    nextStepBanner.style.cssText = [
      "display:none",
      "background:#14532d",
      "border:1px solid #16a34a",
      "color:#bbf7d0",
      "font-size:10px",
      "line-height:1.45",
      "border-radius:6px",
      "padding:6px 8px",
      "margin-bottom:6px",
    ].join(";");

    const compactPageHint = document.createElement("div");
    compactPageHint.style.cssText = "font-size:10px;color:#9ca3af;line-height:1.4;margin-bottom:6px;";

    const wizardBtns = document.createElement("div");
    wizardBtns.style.cssText = "display:flex;flex-direction:column;gap:5px;";

    const moreOptionsSection = document.createElement("details");
    moreOptionsSection.style.cssText = [
      "margin-top:4px",
      "background:#0f172a",
      "border:1px solid #374151",
      "border-radius:6px",
      "padding:4px 6px",
    ].join(";");
    const moreOptionsSummary = document.createElement("summary");
    moreOptionsSummary.textContent = "More options";
    moreOptionsSummary.style.cssText = [
      "cursor:pointer",
      "font-size:10px",
      "color:#9ca3af",
      "font-weight:600",
      "list-style-position:inside",
    ].join(";");
    const moreOptionsBody = document.createElement("div");
    moreOptionsBody.style.cssText = "display:flex;flex-direction:column;gap:5px;margin-top:5px;";
    moreOptionsSection.appendChild(moreOptionsSummary);
    moreOptionsSection.appendChild(moreOptionsBody);

    const advancedHostname = _currentHostname();
    const advancedStorageKey = advancedHostname ? `ph_advanced_open_${advancedHostname}` : "";

    const stuckLink = document.createElement("button");
    stuckLink.type = "button";
    stuckLink.style.cssText = [
      "font-size:9px",
      "color:#6b7280",
      "margin-top:4px",
      "cursor:pointer",
      "text-decoration:underline",
      "background:none",
      "border:none",
      "padding:0",
      "font-family:inherit",
      "display:inline-block",
    ].join(";");
    stuckLink.textContent = "I'm stuck — show all options";
    stuckLink.title = "Open the advanced section with all manual controls";
    stuckLink.addEventListener("click", () => {
      advancedSection.open = true;
      if (advancedStorageKey) void _storageSet({ [advancedStorageKey]: true });
      advancedSection.scrollIntoView({ block: "nearest" });
    });

    let patternHintBanner = null;
    let patternHintWrap = null;
    let parishRecordingLine = null;

    const updateParishRecordingLine = (displayName, parishKey, hostname) => {
      if (!parishRecordingLine) return;
      const name = String(displayName || parishKey || "this parish").trim();
      const host = String(hostname || _currentHostname() || "").trim();
      parishRecordingLine.textContent = host
        ? `📍 Recording recipe for ${name} (${host})`
        : `📍 Recording recipe for ${name}`;
      parishRecordingLine.style.display = "block";
    };

    const resetGuidedPanel = () => {
      const savedPattern = patternHintWrap;
      const savedParish = parishRecordingLine;
      const savedIdentify = identifyResult;
      _clearElement(guidedPanel);
      if (savedPattern) guidedPanel.appendChild(savedPattern);
      if (savedParish) guidedPanel.appendChild(savedParish);
      guidedPanel.appendChild(nextStepBanner);
      guidedPanel.appendChild(wizardQ);
      guidedPanel.appendChild(compactPageHint);
      guidedPanel.appendChild(wizardBtns);
      guidedPanel.appendChild(moreOptionsSection);
      if (savedIdentify) guidedPanel.appendChild(savedIdentify);
      guidedPanel.appendChild(stuckLink);
      _refreshGuidedContext();
    };

    const _pdfTerminalActions = new Set(["download", "image", "print_to_pdf", "crop_screenshot"]);

    const _ensureTerminalPdfStep = () => {
      const recorded = _standaloneRecipeSteps();
      const last = recorded[recorded.length - 1];
      if (last && _pdfTerminalActions.has(String(last.action || "").toLowerCase())) {
        return { ok: true, added: false };
      }
      const pageUrl = window.location.href;
      const pageCtx = detectPageType();
      if (
        pageCtx.type === "direct_pdf" ||
        isDocumentUrl(pageUrl) ||
        /\.pdf(\?|$)/i.test(pageUrl)
      ) {
        standaloneAddStep(
          { action: "download", url: pageUrl },
          "mark_file",
          `📄 Download: ${pageUrl.slice(-50)}`
        );
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "download" };
      }
      if (
        pageCtx.type === "wix_html" ||
        (pageCtx.type === "html" && _pathLooksLikeNewsletterPage())
      ) {
        standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "print_to_pdf" };
      }
      return { ok: false, added: false };
    };

    const _refreshGuidedContext = () => {
      const stepCount = _standaloneRecipeSteps().length;
      const pageCtx = detectPageType();
      compactPageHint.textContent = pageCtx.summary || "";
      compactPageHint.style.display = pageCtx.summary ? "block" : "none";

      const onDirectPdf = pageCtx.type === "direct_pdf";
      if (clickFirstBtn) {
        clickFirstBtn.style.display = onDirectPdf ? "none" : "block";
      }

      if (onDirectPdf) {
        const recorded = _standaloneRecipeSteps();
        const hasTerminal = recorded.some((s) =>
          _pdfTerminalActions.has(String(s?.action || "").toLowerCase())
        );
        nextStepBanner.style.display = "block";
        nextStepBanner.textContent = hasTerminal
          ? "✅ PDF saved — scroll down and tap Push Recipe to GitHub."
          : "👇 Tap the green Save this PDF button, then Push.";
        wizardQ.textContent = "You are on the bulletin PDF";
        if (contextPrimaryBtn) {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent = "📄 Save this PDF";
        }
        if (moreOptionsSection) moreOptionsSection.style.display = "none";
        if (stuckLink) stuckLink.style.display = "none";
      } else if (stepCount > 0) {
        if (contextPrimaryBtn) contextPrimaryBtn.style.background = "#2563eb";
        if (moreOptionsSection) moreOptionsSection.style.display = "";
        if (stuckLink) stuckLink.style.display = "";
        nextStepBanner.style.display = "block";
        nextStepBanner.textContent =
          `✅ ${stepCount} step${stepCount === 1 ? "" : "s"} saved. ` +
          "Use Follow a link again if you need another click, or finish with PDF / frame / image below.";
        wizardQ.textContent = `Step ${stepCount + 1} — what is on this page?`;
      } else {
        if (moreOptionsSection) moreOptionsSection.style.display = "";
        if (stuckLink) stuckLink.style.display = "";
        nextStepBanner.style.display = "none";
        wizardQ.textContent = "Step 1 — follow a menu link to reach the bulletin";
      }

      if (contextPrimaryBtn) {
        const showContext =
          pageCtx.type === "direct_pdf" ||
          pageCtx.type === "iframe" ||
          pageCtx.type === "iframe_maybe" ||
          pageCtx.type === "wix_viewer" ||
          pageCtx.type === "wix_html" ||
          pageCtx.type === "parish_messenger" ||
          (pageCtx.type === "html" && _pathLooksLikeNewsletterPage()) ||
          pageCtx.type === "pdf_links";
        contextPrimaryBtn.style.display = showContext ? "block" : "none";
        if (pageCtx.type === "direct_pdf") {
          contextPrimaryBtn.textContent = "📄 Save this PDF";
        } else if (pageCtx.type === "wix_html" || (pageCtx.type === "html" && _pathLooksLikeNewsletterPage())) {
          contextPrimaryBtn.textContent = "📰 Save page as PDF";
        } else if (pageCtx.type === "parish_messenger") {
          contextPrimaryBtn.textContent = "🔗 Pick View Newsletter link";
        } else if (pageCtx.type === "pdf_links") {
          contextPrimaryBtn.textContent = "🔗 Pick bulletin PDF link";
        } else if (
          pageCtx.type === "iframe" ||
          pageCtx.type === "iframe_maybe" ||
          pageCtx.type === "wix_viewer"
        ) {
          contextPrimaryBtn.textContent = "📐 Bulletin is in a frame";
        }
      }
    };

    // Show a confirmation step after a link is picked
    const showPickConfirmation = (selectedEl) => {
      const selector = buildStableLinkSelector(selectedEl);
      const href = selectedEl.getAttribute("href") || "";
      const text = _getEnrichedLinkLabel(selectedEl).slice(0, 60);
      const clickLabel = `🔗 Click: "${text || selector}"`;
      const clickStep = {
        action: "click",
        selector,
        href,
        text,
      };

      const _recordStandaloneClick = () => {
        if (_inStandaloneMode()) {
          standaloneAddStep(clickStep, "click", clickLabel);
          return true;
        }
        return false;
      };

      showStatus("Link selected — choose Looks right (stay here) or Record & open link.", "info");

      _clearElement(guidedPanel);
      if (patternHintWrap) guidedPanel.appendChild(patternHintWrap);
      if (parishRecordingLine) guidedPanel.appendChild(parishRecordingLine);

      const confirmQ = document.createElement("div");
      confirmQ.style.cssText = "font-weight:600;color:#93c5fd;margin-bottom:6px;font-size:11px;";
      confirmQ.textContent = "Is this the right link?";
      guidedPanel.appendChild(confirmQ);

      const preview = document.createElement("div");
      preview.style.cssText = [
        "background:#0f172a",
        "border-radius:4px",
        "padding:5px",
        "margin-bottom:6px",
        "word-break:break-all",
        "line-height:1.4",
        "font-size:10px",
      ].join(";");

      const makePreviewRow = (label, value) => {
        const row = document.createElement("div");
        const strong = document.createElement("strong");
        strong.textContent = label + ": ";
        const span = document.createElement("span");
        span.textContent = value;
        row.appendChild(strong);
        row.appendChild(span);
        return row;
      };
      preview.appendChild(makePreviewRow("Text", text || "(no text)"));
      preview.appendChild(makePreviewRow("Href", (href || "(none)").slice(0, 70)));
      const selectorRow = document.createElement("div");
      const selectorLabel = document.createElement("strong");
      selectorLabel.textContent = "Selector: ";
      const selectorCode = document.createElement("code");
      selectorCode.style.cssText = "font-size:9px;";
      selectorCode.textContent = selector;
      selectorRow.appendChild(selectorLabel);
      selectorRow.appendChild(selectorCode);
      preview.appendChild(selectorRow);
      guidedPanel.appendChild(preview);

      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;gap:5px;flex-wrap:wrap;";

      const looksRightBtn = makeSmallBtn(
        "👍 Looks right",
        "#16a34a",
        () => {
          if (window.ph_record_click) {
            try {
              window.ph_record_click({
                tag: (selectedEl.tagName || "").toLowerCase(),
                role: (selectedEl.getAttribute("role") || "").toLowerCase(),
                text: (selectedEl.innerText || selectedEl.textContent || "").trim().slice(0, 200),
                href: selectedEl.getAttribute("href") || "",
                css_path: cssPath(selectedEl),
              });
              addSessionStep("click", clickLabel);
            } catch (_e) {
              showStatus("❌ Could not record click.", "error");
              return;
            }
          } else if (_recordStandaloneClick()) {
            // recorded in standalone mode
          } else {
            showStatus("❌ Could not record click.", "error");
            return;
          }
          showStatus(`✅ Click step recorded: "${text || selector}"`);
          resetGuidedPanel();
        },
        "Record this click and stay on this page"
      );

      const recordAndOpenBtn = makeSmallBtn(
        "🔗 Record & open link",
        "#2563eb",
        () => {
          const rawHref = selectedEl.getAttribute("href") || "";
          if (!rawHref) {
            showStatus("❌ This link has no URL to open.", "error");
            resetGuidedPanel();
            return;
          }
          let absUrl = "";
          try {
            absUrl = new URL(rawHref, window.location.href).href;
          } catch (_e) {
            showStatus("❌ Could not open that link.", "error");
            resetGuidedPanel();
            return;
          }

          if (_looksLikeBulletinDownloadUrl(absUrl, text)) {
            stopPickLinkMode();
            if (!_recordStandaloneClick()) {
              showStatus("❌ Could not record click.", "error");
              return;
            }
            standaloneAddStep(
              { action: "download", url: absUrl },
              "mark_file",
              `📄 Download: ${absUrl.slice(-50)}`
            );
            void _persistRecordingSession();
            _notifyRecordingTabActive();
            showStatus(
              "✅ Click + download saved. Brave may auto-download — push recipe now.",
              "ok"
            );
            resetGuidedPanel();
            return;
          }

          if (window.ph_record_click) {
            try {
              window.ph_record_click({
                tag: (selectedEl.tagName || "").toLowerCase(),
                role: (selectedEl.getAttribute("role") || "").toLowerCase(),
                text: (selectedEl.innerText || selectedEl.textContent || "").trim().slice(0, 200),
                href: selectedEl.getAttribute("href") || "",
                css_path: cssPath(selectedEl),
              });
              addSessionStep("click", clickLabel);
            } catch (_e) {
              showStatus("❌ Could not record click.", "error");
              return;
            }
          } else if (!_recordStandaloneClick()) {
            showStatus("❌ Could not record click.", "error");
            return;
          }
          stopPickLinkMode();
          void _navigateRecordingToUrl(absUrl, selectedEl, showStatus);
        },
        "Save this step and go to the linked page (for multi-step recipes)"
      );
      recordAndOpenBtn.style.width = "auto";

      const autoDownloadBtn = makeSmallBtn(
        "📄 Link auto-downloads PDF",
        "#7c3aed",
        () => {
          const rawHref = selectedEl.getAttribute("href") || "";
          if (!rawHref) {
            showStatus("❌ This link has no URL.", "error");
            return;
          }
          try {
            const absUrl = new URL(rawHref, window.location.href).href;
            stopPickLinkMode();
            _standaloneAddClickAndDownload(clickStep, absUrl, clickLabel, showStatus);
            _notifyRecordingTabActive();
            resetGuidedPanel();
          } catch (_e) {
            showStatus("❌ Could not read link URL.", "error");
          }
        },
        "Brave downloads the PDF without opening a page — saves click + download in one go"
      );
      autoDownloadBtn.style.width = "auto";
      autoDownloadBtn.style.display = _looksLikeBulletinDownloadUrl(
        (() => {
          try {
            return new URL(selectedEl.getAttribute("href") || "", window.location.href).href;
          } catch (_e) {
            return "";
          }
        })(),
        text
      )
        ? "block"
        : "none";

      const pickAgainBtn = makeSmallBtn(
        "🔄 Pick again",
        "#374151",
        () => {
          resetGuidedPanel();
          startPickLinkMode(showPickConfirmation, showStatus);
        },
        "Select a different link"
      );
      pickAgainBtn.style.width = "auto";

      btnRow.appendChild(looksRightBtn);
      btnRow.appendChild(recordAndOpenBtn);
      btnRow.appendChild(autoDownloadBtn);
      btnRow.appendChild(pickAgainBtn);
      guidedPanel.appendChild(btnRow);
      guidedPanel.appendChild(stuckLink);

      if (selectedEl instanceof Element) {
        const prevOutline = selectedEl.style.outline;
        selectedEl.style.outline = "3px solid #f59e0b";
        selectedEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => {
          if (selectedEl.style.outline === "3px solid #f59e0b") {
            selectedEl.style.outline = prevOutline;
          }
        }, 3000);
      }
    };

    // Show a "please choose" panel when the top candidate is ambiguous.
    const showPickMultipleChoice = (candidates, hasAnyDate) => {
      _clearElement(guidedPanel);

      const heading = document.createElement("div");
      heading.style.cssText = "font-weight:600;color:#fbbf24;margin-bottom:6px;font-size:11px;";
      heading.textContent = hasAnyDate
        ? "Multiple dated bulletins found — please pick one:"
        : "No dates detected — please pick the correct bulletin:";
      guidedPanel.appendChild(heading);

      if (hasAnyDate) {
        const note = document.createElement("div");
        note.style.cssText = "font-size:9px;color:#6b7280;margin-bottom:4px;";
        note.textContent = "Sorted newest-first. ⭐ = most likely this week's bulletin.";
        guidedPanel.appendChild(note);
      }

      // Warn if the page lists oldest first (newest candidate appeared last on page)
      const looksReversed = candidates.length > 2 &&
        candidates[0].hasFullDate &&
        candidates[0].domIdx > candidates[candidates.length - 1].domIdx;
      if (looksReversed) {
        const reversedNote = document.createElement("div");
        reversedNote.style.cssText = "color:#fbbf24;font-size:9px;margin-bottom:5px;padding:3px 5px;background:#451a03;border-radius:3px;";
        reversedNote.textContent = "⚠️ This page lists oldest first — showing newest at top.";
        guidedPanel.appendChild(reversedNote);
      }

      // Find candidate closest to today to highlight as "this week"
      // Use real Date arithmetic so month boundaries work correctly
      const today = new Date();
      const todayMs = today.getTime();
      const MS_PER_DAY = 86400000;
      const thisWeekCandidate = candidates.find(c => {
        if (!c.hasFullDate) return false;
        const year = Math.floor(c.dateScore / 10000);
        const month = Math.floor((c.dateScore % 10000) / 100);
        const day = c.dateScore % 100;
        const candidateMs = new Date(year, month - 1, day).getTime();
        return Math.abs(todayMs - candidateMs) <= 7 * MS_PER_DAY;
      }) || (candidates.length > 0 && candidates[0].hasFullDate ? candidates[0] : null);

      // Split into dated and undated groups
      const datedCandidates = candidates.filter(c => c.hasDate);
      const undatedCandidates = candidates.filter(c => !c.hasDate);

      const renderCandidate = (candidate, idx, isRecommended) => {
        const { el, url, label } = candidate;
        const row = document.createElement("div");
        row.style.cssText = [
          "display:flex",
          "align-items:center",
          "gap:5px",
          "padding:4px",
          "margin-bottom:4px",
          "background:#0f172a",
          "border-radius:4px",
        ].join(";");

        // Highlight this week's candidate with a green border
        if (candidate === thisWeekCandidate) {
          row.style.border = "1px solid #16a34a";
          row.style.background = "#052e16";
        }

        const info = document.createElement("div");
        info.style.cssText = [
          "flex:1",
          "font-size:9px",
          "word-break:break-all",
          "color:#d1d5db",
          "line-height:1.35",
        ].join(";");

        // Date badge
        const displayDate = getDisplayDate(url, label);
        if (displayDate) {
          const dateBadge = document.createElement("span");
          dateBadge.style.cssText = "color:#fbbf24;font-size:9px;font-weight:600;display:block;margin-bottom:1px;";
          dateBadge.textContent = `📅 ${displayDate}`;
          info.appendChild(dateBadge);
        }

        const textSpan = document.createElement("span");
        textSpan.style.cssText = "white-space:pre-wrap;";
        const shortUrl = (url || "").length > 55 ? (url || "").slice(0, 52) + "…" : (url || "");
        const shortLabel = (label || "").slice(0, 40);
        const prefix = isRecommended ? "⭐ Recommended (newest)\n" : "";
        textSpan.textContent = prefix + (shortLabel ? shortLabel + "\n" + shortUrl : shortUrl);
        info.appendChild(textSpan);

        const pickBtn = document.createElement("button");
        pickBtn.textContent = "Use this";
        pickBtn.style.cssText = [
          "border:none",
          "border-radius:3px",
          "padding:3px 7px",
          "background:#2563eb",
          "color:#fff",
          "cursor:pointer",
          "font-size:9px",
          "font-family:inherit",
          "flex-shrink:0",
        ].join(";");
        pickBtn.addEventListener("click", () => showPickConfirmation(el));
        row.appendChild(info);
        row.appendChild(pickBtn);
        guidedPanel.appendChild(row);
      };

      datedCandidates.forEach((c, idx) => renderCandidate(c, idx, idx === 0 && hasAnyDate));

      if (undatedCandidates.length > 0) {
        const sep = document.createElement("div");
        sep.style.cssText = "color:#6b7280;font-size:9px;margin:4px 0 2px;border-top:1px solid #374151;padding-top:4px;";
        sep.textContent = "⚠️ No date found — review manually:";
        guidedPanel.appendChild(sep);
        undatedCandidates.forEach((c, idx) => renderCandidate(c, idx, false));
      }

      const cancelBtn = document.createElement("button");
      cancelBtn.type = "button";
      cancelBtn.textContent = "↩ Cancel";
      cancelBtn.style.cssText = [
        "border:none",
        "border-radius:3px",
        "padding:3px 8px",
        "background:#374151",
        "color:#d1d5db",
        "cursor:pointer",
        "font-size:9px",
        "font-family:inherit",
        "margin-top:4px",
      ].join(";");
      cancelBtn.addEventListener("click", resetGuidedPanel);
      guidedPanel.appendChild(cancelBtn);
    };

    // Show confirmation after an image is picked
    const showPickImageConfirmation = (imgEl) => {
      const src = imgEl.getAttribute("src") || "";
      const alt = imgEl.getAttribute("alt") || "";
      // Many lazy-load placeholders are tiny data/blob strings; require a longer http URL.
      const MIN_REAL_IMAGE_URL_LENGTH = 50;
      const isRealImageUrl = (value) => {
        const v = String(value || "").trim();
        return (
          v.startsWith("http") &&
          !v.includes("data:image") &&
          v.length > MIN_REAL_IMAGE_URL_LENGTH
        );
      };
      const toSafeImageUrl = (value) => {
        const raw = String(value || "").trim();
        if (!raw || raw.toLowerCase().includes("data:image")) return "";
        try {
          const parsed = new URL(raw, window.location.href);
          if (parsed.protocol === "http:" || parsed.protocol === "https:") {
            return parsed.href;
          }
        } catch (_e) {
          return "";
        }
        return "";
      };
      const imageSourceCandidates = [
        isRealImageUrl(imgEl.src) ? imgEl.src : "",
        imgEl.getAttribute("data-lazy-src") || "",
        imgEl.getAttribute("data-src") || "",
        imgEl.getAttribute("data-original") || "",
        imgEl.getAttribute("data-full-url") || "",
        imgEl.currentSrc || "",
      ];
      const pickedSource =
        imageSourceCandidates.find(
          (candidate) => Boolean(toSafeImageUrl(candidate))
        ) || "";
      const absUrl = (() => {
        if (!pickedSource) return toSafeImageUrl(src);
        return toSafeImageUrl(pickedSource);
      })();

      _clearElement(guidedPanel);

      const heading = document.createElement("div");
      heading.style.cssText =
        "font-weight:600;color:#93c5fd;margin-bottom:6px;font-size:11px;";
      heading.textContent =
        pickedImages.length > 0
          ? `Is this image #${pickedImages.length + 1} correct?`
          : "Is this the right image?";
      guidedPanel.appendChild(heading);

      const preview = document.createElement("div");
      preview.style.cssText = [
        "background:#0f172a",
        "border-radius:4px",
        "padding:5px",
        "margin-bottom:6px",
        "text-align:center",
      ].join(";");

      const thumb = document.createElement("img");
      thumb.src = absUrl;
      thumb.style.cssText =
        "max-width:100%;max-height:80px;border-radius:3px;display:block;margin:0 auto 4px;";
      thumb.alt = alt || "selected image";
      preview.appendChild(thumb);

      const urlText = document.createElement("div");
      urlText.style.cssText = "font-size:9px;color:#9ca3af;word-break:break-all;";
      urlText.textContent =
        absUrl.length > 70 ? absUrl.slice(0, 67) + "…" : absUrl;
      preview.appendChild(urlText);
      if (alt) {
        const altText = document.createElement("div");
        altText.style.cssText = "font-size:9px;color:#6b7280;margin-top:2px;";
        altText.textContent = `Alt: "${alt}"`;
        preview.appendChild(altText);
      }
      guidedPanel.appendChild(preview);

      if (pickedImages.length > 0) {
        const countNote = document.createElement("div");
        countNote.style.cssText = "font-size:9px;color:#fbbf24;margin-bottom:5px;";
        countNote.textContent = `Already picked ${pickedImages.length} image(s). Add this one too?`;
        guidedPanel.appendChild(countNote);
      }

      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;flex-direction:column;gap:4px;";

      const confirmBtn = makeSmallBtn(
        pickedImages.length > 0 ? "✅ Yes — add this image" : "✅ Yes, use this image",
        "#16a34a",
        () => {
          if (!absUrl) {
            showStatus("❌ Could not read this image URL. Try a different image.", "error");
            resetGuidedPanel();
            return;
          }
          pickedImages.push({ url: absUrl, el: imgEl });
          if (window.ph_mark_image) {
            try {
              const request = { url: absUrl };
              const markResult = window.ph_mark_image(request);
              const response = markResult === false
                ? { ok: false, reason: "Page rejected the image save." }
                : { ok: true };
              _logSaveCycle("mark_image", request, response);
              if (markResult === false) {
                showStatus(`❌ ${response.reason}`, "error");
                return;
              }
              addSessionStep("mark_image", `🖼️ Image: ${absUrl.slice(-50)}`);
              showStatus(`✅ Image recorded: ${absUrl.slice(-40)}`);
            } catch (_e) {
              _logSaveCycle("mark_image", { url: absUrl }, { ok: false, reason: "Could not record image. Try refreshing." });
              showStatus("❌ Could not record image. Try refreshing.", "error");
            }
          } else {
            standaloneAddStep(
              { action: "image", url: absUrl },
              "mark_image",
              `🖼️ Image: ${absUrl.slice(-50)}`
            );
            showStatus(`✅ Image noted: ${absUrl.slice(-40)}`);
          }
          pickedImages = [];
          resetGuidedPanel();
        },
        "Record this image as the bulletin"
      );

      const addAnotherBtn = makeSmallBtn(
        "➕ Pick another image too",
        "#2563eb",
        () => {
          if (!absUrl) {
            showStatus("❌ Could not read this image URL. Try a different image.", "error");
            resetGuidedPanel();
            return;
          }
          pickedImages.push({ url: absUrl, el: imgEl });
          showStatus(
            `✅ Image ${pickedImages.length} saved. Now pick the next one.`,
            "info"
          );
          resetGuidedPanel();
          startPickImageMode(showPickImageConfirmation, showStatus);
        },
        "Add another image (e.g. multi-page bulletin)"
      );

      const pickAgainBtn = makeSmallBtn(
        "🔄 Pick a different image",
        "#374151",
        () => {
          resetGuidedPanel();
          startPickImageMode(showPickImageConfirmation, showStatus);
        },
        "Select a different image"
      );

      const cancelBtn = makeSmallBtn("↩ Cancel", "#374151", () => {
        pickedImages = [];
        resetGuidedPanel();
      });
      cancelBtn.style.fontSize = "10px";
      cancelBtn.style.padding = "4px 8px";

      btnRow.appendChild(confirmBtn);
      if (pickedImages.length === 0) btnRow.appendChild(addAnotherBtn);
      btnRow.appendChild(pickAgainBtn);
      btnRow.appendChild(cancelBtn);
      guidedPanel.appendChild(btnRow);

      if (imgEl instanceof Element) {
        const prev = imgEl.style.outline;
        imgEl.style.outline = "3px solid #f59e0b";
        imgEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => {
          if (imgEl.style.outline === "3px solid #f59e0b") imgEl.style.outline = prev;
        }, 3000);
      }
    };

    // Wizard buttons — link-first flow; PDF/frame only when page context needs them
    let contextPrimaryBtn = null;

    clickFirstBtn = makeSmallBtn(
      "🔗 Follow a link (most parishes)",
      "#16a34a",
      () => startPickLinkMode(showPickConfirmation, showStatus),
      "Click through menus/links to reach the bulletin — use Record & open link after each pick"
    );

    contextPrimaryBtn = makeSmallBtn(
      "📐 Bulletin is in a frame",
      "#2563eb",
      () => {
        const pageCtx = detectPageType();
        if (pageCtx.type === "direct_pdf") {
          markDownloadUrlSafe(window.location.href, showStatus, false);
          return;
        }
        if (pageCtx.type === "wix_html") {
          standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
          showStatus("✅ Recorded: page will print into the mega bulletin.", "ok");
          return;
        }
        if (pageCtx.type === "html" && _pathLooksLikeNewsletterPage()) {
          standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
          showStatus("✅ Recorded: this news page will print into the mega bulletin.", "ok");
          return;
        }
        if (pageCtx.type === "pdf_links") {
          startPickLinkMode(showPickConfirmation, showStatus);
          return;
        }
        if (pageCtx.type === "parish_messenger") {
          startPickLinkMode(showPickConfirmation, showStatus);
          return;
        }
        window.dispatchEvent(new CustomEvent("ph-start-pick-iframe"));
      },
      "Finish on this page — PDF, Wix/HTML print, or embedded frame"
    );
    contextPrimaryBtn.style.display = "none";

    const pdfBtn = makeSmallBtn(
      "📄 Get a PDF",
      "#374151",
      () => markDownloadUrlSafe(window.location.href, showStatus, false),
      "Only when you are already looking at the PDF file"
    );
    const savePagePdfBtn = makeSmallBtn(
      "📰 Save page as PDF (Wix/HTML bulletin)",
      "#7c3aed",
      () => {
        standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
        showStatus("✅ Recorded: this page will be printed into the mega bulletin on Sunday.", "ok");
      },
      "The bulletin is a web page (Wix/text) — harvester prints it to PDF, not just a link"
    );
    const imageCropBtn = makeSmallBtn(
      "🖼️ Get an image (newsletter screenshot)",
      "#2563eb",
      () => {
        bar.dataset.phHidden = "true";
        bar.style.display = "none";
        startCrop();
      },
      "The bulletin is an image on screen — draw a rectangle to capture it"
    );
    const pickImageBtn = makeSmallBtn(
      "🖼️ Pick an image on this page",
      "#2563eb",
      () => {
        pickedImages = [];
        startPickImageMode(showPickImageConfirmation, showStatus);
      },
      "Click to hover-select an existing image on the page — no cropping needed"
    );
    const noBulletinBtn = makeSmallBtn(
      "🚫 No bulletin here (skip)",
      "#6b7280",
      () => {
        if (typeof window.ph_mark_download_url === "function") {
          try {
            window.ph_mark_download_url({ url: "no_bulletin", type: "no_bulletin" });
          } catch (_e) {}
        }
        addSessionStep("no_bulletin", "🚫 No bulletin — skipped");
        showStatus("🚫 Marked as no bulletin. You can now close this tab or move on.");
      },
      "Record that this parish has no bulletin and skip it"
    );

    wizardBtns.appendChild(clickFirstBtn);
    wizardBtns.appendChild(contextPrimaryBtn);

    moreOptionsBody.appendChild(pdfBtn);
    moreOptionsBody.appendChild(savePagePdfBtn);
    moreOptionsBody.appendChild(imageCropBtn);
    moreOptionsBody.appendChild(pickImageBtn);
    moreOptionsBody.appendChild(noBulletinBtn);

    parishRecordingLine = document.createElement("div");
    parishRecordingLine.style.cssText = [
      "display:none",
      "font-size:10px",
      "font-weight:600",
      "color:#bbf7d0",
      "margin-bottom:6px",
    ].join(";");
    guidedPanel.appendChild(parishRecordingLine);
    guidedPanel.appendChild(nextStepBanner);
    guidedPanel.appendChild(wizardQ);
    guidedPanel.appendChild(compactPageHint);
    guidedPanel.appendChild(wizardBtns);
    guidedPanel.appendChild(moreOptionsSection);
    guidedPanel.appendChild(stuckLink);
    updateParishRecordingLine("", "", _currentHostname());
    _refreshGuidedContext();

    // guidedPanel is attached to scrollable body after recipe preview (below).

    window.addEventListener("ph-recording-continued", (e) => {
      const count = Number(e?.detail?.stepCount || _standaloneRecipeSteps().length || 0);
      if (count > 0) {
        showStatus(
          `✅ Recording continued — ${count} step${count === 1 ? "" : "s"} saved. Keep going or push when done.`,
          "ok"
        );
      } else {
        showStatus("✅ Recording continued on this page.", "ok");
      }
      _refreshGuidedContext();
      if (_stepsListEl) _renderSessionSteps();
      if (_refreshRecipeCount) _refreshRecipeCount();
    });

    // Listen for messages from the side-panel / isolated world that request
    // pick modes — they need to run inside the createToolbar closure.
    window.addEventListener("ph-start-pick-link", () => {
      startPickLinkMode(showPickConfirmation, showStatus);
    });
    window.addEventListener("ph-start-pick-image-mode", () => {
      pickedImages = [];
      startPickImageMode(showPickImageConfirmation, showStatus);
    });
    window.addEventListener("ph-start-pick-iframe", () => {
      const pickerPanel = buildIframePickerPanel(showStatus);
      if (pickerPanel) {
        _clearElement(guidedPanel);
        const backBtn = makeSmallBtn("← Back", "#374151", resetGuidedPanel);
        backBtn.style.width = "auto";
        backBtn.style.marginBottom = "6px";
        guidedPanel.appendChild(backBtn);
        guidedPanel.appendChild(pickerPanel);
      }
    });
    window.addEventListener("ph-document-detected", (e) => {
      const url = (e.detail && e.detail.url) || "";
      const short = url.length > 50 ? url.slice(0, 47) + "…" : url;
      showStatus(`🔍 Document detected: ${short} — tap Advanced → Get a PDF, or it may auto-save if Brave downloads.`, "info");
      if (_inStandaloneMode() && url && _looksLikeBulletinDownloadUrl(url)) {
        markDownloadUrlSafe(url, showStatus, true);
        resetGuidedPanel();
      }
    });
    window.addEventListener("ph-retraining-hint", () => {
      showStatus("Retraining: follow the steps on this page, then click '⬆ Push Recipe to GitHub'.", "warn");
    });

    // ── IDENTIFY PAGE ──────────────────────────────────────────────────────
    const identifyBtn = document.createElement("button");
    identifyBtn.type = "button";
    identifyBtn.textContent = "🔍 Find bulletin on this page";
    identifyBtn.title = "Scan this page for PDFs, images, and bulletin links — uses learned patterns from similar parishes";
    identifyBtn.style.cssText = [
      "border: none",
      "border-radius: 6px",
      "padding: 5px 8px",
      "background: #374151",
      "color: #d1d5db",
      "cursor: pointer",
      "font-size: 10px",
      "white-space: nowrap",
      "font-family: inherit",
      "width: 100%",
      "text-align: left",
    ].join(";");

    const identifyResult = document.createElement("div");
    identifyResult.style.cssText = [
      "display:none",
      "background:#0f172a",
      "border:1px solid #374151",
      "border-radius:6px",
      "padding:6px 8px",
      "font-size:10px",
      "line-height:1.45",
      "max-height: 160px",
      "overflow-y: auto",
    ].join(";");

    identifyBtn.addEventListener("click", () => {
      if (!identifyResult.isConnected) {
        guidedPanel.insertBefore(identifyResult, stuckLink);
      }
      const result = detectPageType();
      identifyResult.style.display = "block";
      _clearElement(identifyResult);

      const emojiSpan = document.createElement("span");
      emojiSpan.style.cssText = "font-size:15px;";
      emojiSpan.textContent = result.emoji;

      const summaryStrong = document.createElement("strong");
      summaryStrong.style.cssText = "color:#f9fafb;";
      summaryStrong.textContent = result.summary;

      const adviceSpan = document.createElement("span");
      adviceSpan.style.cssText = "color:#9ca3af;display:block;margin-top:2px;";
      adviceSpan.textContent = result.advice;

      identifyResult.appendChild(emojiSpan);
      identifyResult.appendChild(document.createTextNode(" "));
      identifyResult.appendChild(summaryStrong);
      identifyResult.appendChild(adviceSpan);

      // "Pick newest bulletin" shortcut for pdfemb / pdf_links pages
      const pickableLinks = result.links || [];
      if (
        (result.type === "pdfemb" ||
          result.type === "pdf_links" ||
          result.type === "parish_messenger") &&
        pickableLinks.length > 0
      ) {
        const pickNewestBtn = makeSmallBtn(
          `🎯 Pick newest bulletin (${pickableLinks.length} link${
            pickableLinks.length !== 1 ? "s" : ""
          } found)`,
          "#16a34a",
          () => {
            // Score each link — copilot rules prefer current newsletter + skip admin PDFs.
            const scored = pickableLinks.map((el, idx) => {
              const url = el.getAttribute("href") || "";
              const label = _getEnrichedLinkLabel(el);
              const s = scoreUrlCandidateStr(url, label, idx);
              const phrase = window.ph_copilot?.scorePhrase?.(url, label);
              const adminSkip = phrase && phrase.penalty >= 120 && phrase.bonus < 40;
              return { el, url, label, domIdx: idx, ...s, adminSkip };
            });
            const viable = scored.filter((c) => !c.adminSkip);
            const pool = viable.length ? viable : scored;
            pool.sort(_bulletinDateSortFn);

            // Ambiguous: no dates found at all, or top two candidates share the
            // same date score (cannot tell which is newer).
            const hasAnyDate = pool.some((c) => c.hasDate);
            const ambiguous =
              !hasAnyDate ||
              (pool.length > 1 && pool[0].dateScore === pool[1].dateScore);

            if (!ambiguous) {
              showPickConfirmation(pool[0].el);
            } else {
              showPickMultipleChoice(pool.slice(0, 3), hasAnyDate);
            }
          },
          "Automatically selects the most recent bulletin link for you to confirm"
        );
        pickNewestBtn.style.marginTop = "6px";
        identifyResult.appendChild(pickNewestBtn);
      }

      // Deep-detect fallback for pages with no obvious document content
      if (
        result.type === "html" ||
        result.type === "unknown" ||
        result.type === "embed" ||
        result.type === "iframe_maybe"
      ) {
        showStatus("🕵️ Running deep detection fallback for 10 seconds…", "info");
        startDeepDetect(
          (urls) => {
            if (urls.length === 0) {
              if (hasPickableImageInContentAreas(MIN_CONTENT_IMAGE_WIDTH)) {
                showStatus(
                  "Deep Detect: no PDFs found. This looks like an image bulletin — try 'Pick an image on this page' instead.",
                  "info"
                );
              } else {
                showStatus(
                  "Deep Detect: no document URLs detected in 10 s.",
                  "info"
                );
              }
              return;
            }
            _clearElement(identifyResult);
            const heading = document.createElement("div");
            heading.style.cssText =
              "font-weight:600;color:#93c5fd;margin-bottom:5px;font-size:10px;";

            // Sort detected URLs by date score (newest first)
            const scoredUrls = urls.map((url, idx) => ({
              url,
              domIdx: idx,
              ...scoreUrlCandidateStr(url, "", idx),
            }));
            scoredUrls.sort(_bulletinDateSortFn);
            const hasAnyUrlDate = scoredUrls.some((c) => c.hasDate);

            heading.textContent = `🕵️ Detected ${urls.length} document URL(s) — sorted by recency:`;
            identifyResult.appendChild(heading);

            const note = document.createElement("div");
            note.style.cssText = "font-size:9px;margin-bottom:5px;";
            if (hasAnyUrlDate) {
              note.style.color = "#6b7280";
              note.textContent = "⭐ marks the recommended pick (looks like the newest dated bulletin).";
            } else {
              note.style.color = "#fbbf24";
              note.textContent = "⚠️ No dates detected in URLs — please review and pick manually.";
            }
            identifyResult.appendChild(note);

            scoredUrls.forEach(({ url, hasDate }, rankIdx) => {
              const row = document.createElement("div");
              row.style.cssText =
                "display:flex;gap:5px;margin-bottom:3px;align-items:center;";
              if (rankIdx === 0 && hasDate) {
                row.style.cssText +=
                  "background:#052e16;border-radius:3px;padding:2px 3px;";
              }
              const preview = document.createElement("span");
              preview.style.cssText =
                "flex:1;font-size:9px;word-break:break-all;line-height:1.35;white-space:pre-wrap;";
              preview.style.color = (rankIdx === 0 && hasDate) ? "#86efac" : "#d1d5db";
              let labelText = "";
              if (rankIdx === 0 && hasDate) {
                labelText = "⭐ Recommended (newest)\n";
              }
              labelText += url.length > 70 ? url.slice(0, 67) + "…" : url;
              preview.textContent = labelText;
              const useBtn = document.createElement("button");
              useBtn.textContent = "Use";
              useBtn.style.cssText = [
                "border:none",
                "border-radius:3px",
                "padding:2px 6px",
                "background:#16a34a",
                "color:#fff",
                "cursor:pointer",
                "font-size:9px",
                "font-family:inherit",
                "flex-shrink:0",
              ].join(";");
              useBtn.addEventListener("click", () =>
                markDownloadUrlSafe(url, showStatus, isDocumentUrl(url))
              );
              row.appendChild(preview);
              row.appendChild(useBtn);
              identifyResult.appendChild(row);
            });
          },
          showStatus
        );
      }

      // Wix PDF viewer handling
      if (result.type === "wix_viewer") {
        if (result.wixPdfUrl) {
          // We extracted the URL — offer a one-click record button
          const useExtractedBtn = makeSmallBtn(
            "📄 Use extracted PDF URL",
            "#16a34a",
            () => markDownloadUrlSafe(result.wixPdfUrl, showStatus, true),
            "Record the PDF URL extracted from the Wix viewer"
          );
          useExtractedBtn.style.marginTop = "6px";
          identifyResult.appendChild(useExtractedBtn);
        }
        // Always show the iframe picker button for Wix
        const iframeBtn = makeSmallBtn(
          "📐 Open frame picker",
          "#2563eb",
          () => window.dispatchEvent(new CustomEvent("ph-start-pick-iframe")),
          "Open the iframe picker to select the Wix viewer"
        );
        iframeBtn.style.marginTop = "6px";
        identifyResult.appendChild(iframeBtn);
      }
    });

    moreOptionsBody.appendChild(identifyBtn);
    guidedPanel.insertBefore(identifyResult, stuckLink);

    patternHintWrap = document.createElement("details");
    patternHintWrap.style.cssText = [
      "display:none",
      "background:#0c4a6e",
      "border:1px solid #38bdf8",
      "border-radius:6px",
      "padding:4px 6px",
      "margin-bottom:6px",
    ].join(";");
    const patternHintSummary = document.createElement("summary");
    patternHintSummary.textContent = "Pattern hint (similar parishes)";
    patternHintSummary.style.cssText = [
      "cursor:pointer",
      "font-size:10px",
      "color:#e0f2fe",
      "font-weight:600",
      "list-style-position:inside",
    ].join(";");
    patternHintBanner = document.createElement("div");
    patternHintBanner.style.cssText = [
      "color:#e0f2fe",
      "font-size:10px",
      "line-height:1.45",
      "margin-top:4px",
      "white-space:pre-wrap",
    ].join(";");
    patternHintWrap.appendChild(patternHintSummary);
    patternHintWrap.appendChild(patternHintBanner);
    guidedPanel.insertBefore(patternHintWrap, parishRecordingLine);

    const refreshPatternHints = () => {
      const lib = globalThis.PhPatternLibrary;
      if (!lib) return;
      const detected = detectPageType();
      const pageFp = lib.fingerprintFromPage(detected);
      if (detected.predictedUrl) {
        pageFp.predicted_url = detected.predictedUrl;
      } else if (lib.predictWixSlugUrl && _hasWixDateSlug(window.location.href)) {
        pageFp.predicted_url = lib.predictWixSlugUrl(window.location.href, _nextSundayDate());
      }
      _safeSendMessage({ type: "fetch_site_patterns" }, (resp, _err) => {
        if (!resp?.ok) return;
        const matches = lib.findSimilar(pageFp, resp.patterns || {});
        const text = lib.buildHintText(pageFp, matches);
        patternHintWrap.style.display = "block";
        patternHintBanner.textContent = text;
      });
    };
    const recipeSection = document.createElement("div");
    recipeSection.style.cssText = [
      "background:#1e293b",
      "border:1px solid #374151",
      "border-radius:6px",
      "overflow:hidden",
    ].join(";");

    const recipeHeaderEl = document.createElement("div");
    recipeHeaderEl.style.cssText = [
      "display:flex",
      "align-items:center",
      "justify-content:space-between",
      "padding:5px 8px",
      "cursor:pointer",
    ].join(";");

    const recipeTitleEl = document.createElement("span");
    recipeTitleEl.style.cssText = "font-size:10px;font-weight:600;";
    recipeTitleEl.textContent = "📋 Recipe Preview (0 steps)";

    const recipeToggleEl = document.createElement("span");
    recipeToggleEl.style.cssText = "font-size:10px;color:#6b7280;";
    recipeToggleEl.textContent = "▶";

    recipeHeaderEl.appendChild(recipeTitleEl);
    recipeHeaderEl.appendChild(recipeToggleEl);

    const recipeBodyEl = document.createElement("div");
    recipeBodyEl.style.cssText = "padding:6px 8px;display:none;";

    const stepsListEl = document.createElement("div");
    stepsListEl.style.cssText = "margin-bottom:6px;";
    // Wire up the module-level reference so addSessionStep can find it
    _stepsListEl = stepsListEl;
    _renderSessionSteps();

    const undoBtn = document.createElement("button");
    undoBtn.type = "button";
    undoBtn.textContent = "↩ Undo Last Step";
    undoBtn.title = "Remove the last recorded step from this session";
    undoBtn.style.cssText = [
      "border: none",
      "border-radius: 5px",
      "padding: 4px 8px",
      "background: #78350f",
      "color: #fde68a",
      "cursor: pointer",
      "font-size: 10px",
      "font-family: inherit",
    ].join(";");
    undoBtn.addEventListener("click", () => {
      const removed = undoSessionStep();
      if (removed) {
        showStatus(`↩ Undone: ${removed.label}`);
      } else {
        showStatus("ℹ️ Nothing to undo.", "info");
      }
    });

    recipeBodyEl.appendChild(stepsListEl);
    recipeBodyEl.appendChild(undoBtn);
    recipeSection.appendChild(recipeHeaderEl);
    recipeSection.appendChild(recipeBodyEl);

    // Wire up the recipe count refresh callback
    _refreshRecipeCount = () => {
      recipeTitleEl.textContent = `📋 Recipe Preview (${recipeSteps.length} step${
        recipeSteps.length !== 1 ? "s" : ""
      })`;
      _refreshGuidedContext();
      if (_standaloneRecipeSteps().length > 0 && !recipeOpen) {
        recipeOpen = true;
        recipeBodyEl.style.display = "block";
        recipeToggleEl.textContent = "▼";
      }
    };

    let recipeOpen = _standaloneRecipeSteps().length > 0;
    recipeBodyEl.style.display = recipeOpen ? "block" : "none";
    recipeToggleEl.textContent = recipeOpen ? "▼" : "▶";
    recipeHeaderEl.addEventListener("click", () => {
      recipeOpen = !recipeOpen;
      recipeBodyEl.style.display = recipeOpen ? "block" : "none";
      recipeToggleEl.textContent = recipeOpen ? "▼" : "▶";
    });

    body.appendChild(guidedPanel);
    body.appendChild(recipeSection);

    const copilotMount = document.createElement("div");

    // ── ADVANCED SECTION ───────────────────────────────────────────────────
    // These buttons keep their original labels so existing tests still pass.
    const advancedSection = document.createElement("details");
    advancedSection.className = "ph-advanced-section";
    advancedSection.style.cssText = [
      "background:#1e293b",
      "border:1px solid #374151",
      "border-radius:6px",
      "overflow:hidden",
    ].join(";");

    const advancedSummary = document.createElement("summary");
    advancedSummary.textContent = "▾ Advanced";
    advancedSummary.setAttribute("aria-label", "Advanced options");
    advancedSummary.style.cssText = [
      "padding:6px 8px",
      "cursor:pointer",
      "font-size:10px",
      "font-weight:600",
      "color:#9ca3af",
      "list-style-position:inside",
    ].join(";");
    advancedSection.appendChild(advancedSummary);

    const advancedBodyEl = document.createElement("div");
    advancedBodyEl.style.cssText = "padding:6px 8px;border-top:1px solid #374151;";

    advancedSection.open = false;
    if (advancedStorageKey) {
      void _storageGet([advancedStorageKey]).then((saved) => {
        advancedSection.open = saved[advancedStorageKey] === true;
      });
    }
    advancedSection.addEventListener("toggle", () => {
      if (advancedStorageKey) void _storageSet({ [advancedStorageKey]: !!advancedSection.open });
    });

    const row = document.createElement("div");
    row.style.cssText = "display:flex;gap:5px;flex-wrap:wrap;";

    const makeBtn = (label, handler) => {
      const btn = document.createElement("button");
      btn.textContent = label;
      btn.style.cssText = [
        "border: none",
        "border-radius: 6px",
        "padding: 5px 8px",
        "background: #2563eb",
        "color: #fff",
        "cursor: pointer",
        "font-size: 11px",
        "white-space: nowrap",
        "font-family: inherit",
      ].join(";");
      btn.addEventListener("click", handler);
      return btn;
    };

    row.appendChild(
      makeBtn("✨ Mark this element", () => {
        const result = _handleIncomingMessage({ type: "mark_element" });
        if (result?.ok) {
          if (result.reason) showStatus(`✅ ${result.reason}`);
          else showStatus("✅ Element marked.");
        } else {
          showStatus(`❌ ${result?.reason || "Could not mark this element."}`, "error");
        }
      })
    );

    row.appendChild(
      makeBtn("Crop Bulletin Image", () => {
        bar.dataset.phHidden = "true";
        bar.style.display = "none";
        startCrop();
      })
    );

    advancedBodyEl.appendChild(pickImageBtn);
    advancedBodyEl.appendChild(row);
    noBulletinBtn.style.marginTop = "5px";
    advancedBodyEl.appendChild(noBulletinBtn);

    // ── ➕ New Parish wizard ───────────────────────────────────────────────
    // Adds a button (inside the Advanced fold) that opens a lightweight modal
    // so Franky can register a new parish without leaving the page.
    (() => {
      const DIOCESE_CACHE_KEY = "ph_diocese_list_cache";
      const DIOCESE_CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes
      const FALLBACK_DIOCESES = ["derry", "down_and_connor", "raphoe"];

      const _fetchDioceseList = async () => {
        // Try cache first.
        const cached = await _storageGet([DIOCESE_CACHE_KEY]);
        const entry = cached[DIOCESE_CACHE_KEY];
        if (entry && typeof entry === "object" && Array.isArray(entry.list) && Date.now() - entry.ts < DIOCESE_CACHE_TTL_MS) {
          return entry.list;
        }
        // Fetch live from GitHub Contents API.
        try {
          const settings = await _storageGet(["gh_repo", "gh_pat"]);
          const ghRepo = String(settings.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
          const apiUrl = `https://api.github.com/repos/${ghRepo}/contents/parishes/recipes`;
          const headers = { Accept: "application/vnd.github+json" };
          const pat = String(settings.gh_pat || "").trim();
          if (pat) headers.Authorization = `token ${pat}`;
          const resp = await fetch(apiUrl, { headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const items = await resp.json();
          const list = items
            .filter((item) => item.type === "dir")
            .map((item) => item.name)
            .sort();
          if (list.length > 0) {
            await _storageSet({ [DIOCESE_CACHE_KEY]: { list, ts: Date.now() } });
            return list;
          }
        } catch (_e) { /* fall through to hardcoded list */ }
        return FALLBACK_DIOCESES;
      };

      const _toParishKey = (name) =>
        name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");

      const openNewParishModal = async () => {
        // Remove any existing modal.
        const existing = document.getElementById("ph-new-parish-modal");
        if (existing) existing.remove();

        // ── backdrop ──────────────────────────────────────────────────────
        const backdrop = document.createElement("div");
        backdrop.id = "ph-new-parish-modal";
        Object.assign(backdrop.style, {
          position: "fixed",
          inset: "0",
          zIndex: "2147483647",
          background: "rgba(0,0,0,0.65)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: "system-ui,sans-serif",
        });

        // ── panel ─────────────────────────────────────────────────────────
        const panel = document.createElement("div");
        Object.assign(panel.style, {
          background: "#1e293b",
          border: "1px solid #374151",
          borderRadius: "10px",
          padding: "16px",
          width: "min(400px, 92vw)",
          color: "#f9fafb",
          fontSize: "12px",
        });

        const title = document.createElement("div");
        title.style.cssText = "font-size:13px;font-weight:700;color:#86efac;margin-bottom:10px;";
        title.textContent = "➕ Register New Parish";
        panel.appendChild(title);

        // Status message inside modal.
        const modalStatus = document.createElement("div");
        modalStatus.style.cssText = "min-height:18px;margin-bottom:8px;font-size:11px;color:#fde68a;";
        panel.appendChild(modalStatus);
        const setModalStatus = (msg, ok = false) => {
          modalStatus.style.color = ok ? "#86efac" : "#fde68a";
          modalStatus.textContent = msg;
        };

        const makeField = (labelText) => {
          const wrap = document.createElement("div");
          wrap.style.marginBottom = "8px";
          const lbl = document.createElement("label");
          lbl.style.cssText = "display:block;font-size:10px;color:#9ca3af;margin-bottom:3px;";
          lbl.textContent = labelText;
          wrap.appendChild(lbl);
          return wrap;
        };

        const inputStyle = [
          "width:100%",
          "border:1px solid #374151",
          "border-radius:4px",
          "padding:5px 7px",
          "background:#0f172a",
          "color:#f9fafb",
          "font-size:11px",
          "box-sizing:border-box",
          "font-family:inherit",
        ].join(";");

        // ── Diocese dropdown + optional new diocese field ─────────────────
        const dioceseWrap = makeField("Diocese");
        const dioceseSelect = document.createElement("select");
        dioceseSelect.style.cssText = inputStyle + ";cursor:pointer;margin-bottom:6px;";
        const loadingOpt = document.createElement("option");
        loadingOpt.value = "";
        loadingOpt.textContent = "Loading…";
        dioceseSelect.appendChild(loadingOpt);
        dioceseWrap.appendChild(dioceseSelect);

        const newDioceseWrap = document.createElement("div");
        newDioceseWrap.style.display = "none";
        const newDioceseLabel = document.createElement("label");
        newDioceseLabel.style.cssText = "display:block;font-size:10px;color:#93c5fd;margin-bottom:3px;";
        newDioceseLabel.textContent = "New diocese folder name";
        newDioceseWrap.appendChild(newDioceseLabel);
        const newDioceseInput = document.createElement("input");
        newDioceseInput.type = "text";
        newDioceseInput.placeholder = "e.g. donegal, cloyne, killaloe";
        newDioceseInput.style.cssText = inputStyle;
        newDioceseWrap.appendChild(newDioceseInput);
        const newDioceseHint = document.createElement("div");
        newDioceseHint.style.cssText = "font-size:9px;color:#6b7280;margin-top:3px;line-height:1.35;";
        newDioceseHint.textContent =
          "Creates parishes/recipes/your_name/ on GitHub. Use lowercase letters — spaces become underscores.";
        newDioceseWrap.appendChild(newDioceseHint);
        dioceseWrap.appendChild(newDioceseWrap);
        panel.appendChild(dioceseWrap);

        const NEW_DIOCESE_VALUE = "__new_diocese__";
        const _slugifyDioceseInput = (value) =>
          String(value || "")
            .trim()
            .toLowerCase()
            .replace(/&/g, "and")
            .replace(/[^a-z0-9]+/g, "_")
            .replace(/^_+|_+$/g, "");

        dioceseSelect.addEventListener("change", () => {
          const isNew = dioceseSelect.value === NEW_DIOCESE_VALUE;
          newDioceseWrap.style.display = isNew ? "block" : "none";
          if (isNew) setTimeout(() => newDioceseInput.focus(), 30);
        });

        // Populate asynchronously.
        _fetchDioceseList().then((list) => {
          _clearElement(dioceseSelect);
          const placeholder = document.createElement("option");
          placeholder.value = "";
          placeholder.textContent = "— select diocese —";
          dioceseSelect.appendChild(placeholder);
          const seen = new Set();
          for (const d of list) {
            if (!d || d === "unknown" || seen.has(d)) continue;
            seen.add(d);
            const opt = document.createElement("option");
            opt.value = d;
            opt.textContent = d.replace(/_/g, " ");
            dioceseSelect.appendChild(opt);
          }
          const newOpt = document.createElement("option");
          newOpt.value = NEW_DIOCESE_VALUE;
          newOpt.textContent = "➕ Create new diocese…";
          dioceseSelect.appendChild(newOpt);
          const unknownOpt = document.createElement("option");
          unknownOpt.value = "unknown";
          unknownOpt.textContent = "unknown (last resort)";
          dioceseSelect.appendChild(unknownOpt);
        });

        // ── Parish name ───────────────────────────────────────────────────
        const nameWrap = makeField("Parish name");
        const nameInput = document.createElement("input");
        nameInput.type = "text";
        nameInput.placeholder = "e.g. St Patrick's Magherafelt";
        nameInput.style.cssText = inputStyle;
        nameWrap.appendChild(nameInput);
        panel.appendChild(nameWrap);

        // Auto-suggest parish_key below the name field.
        const keyHint = document.createElement("div");
        keyHint.style.cssText = "font-size:9px;color:#6b7280;margin-top:2px;";
        keyHint.textContent = "parish_key: (enter name above)";
        nameWrap.appendChild(keyHint);
        nameInput.addEventListener("input", () => {
          const key = _toParishKey(nameInput.value);
          keyHint.textContent = key ? `parish_key: ${key}` : "parish_key: (enter name above)";
        });

        // ── Start URL ─────────────────────────────────────────────────────
        const urlWrap = makeField("Start URL");
        const urlInput = document.createElement("input");
        urlInput.type = "url";
        urlInput.placeholder = "https://";
        urlInput.style.cssText = inputStyle;
        try { urlInput.value = window.location.href; } catch (_e) {}
        urlWrap.appendChild(urlInput);
        panel.appendChild(urlWrap);

        // ── Buttons ───────────────────────────────────────────────────────
        const btnRow = document.createElement("div");
        btnRow.style.cssText = "display:flex;gap:8px;margin-top:10px;";

        const submitBtn = document.createElement("button");
        submitBtn.type = "button";
        submitBtn.textContent = "➕ Create stub recipe";
        submitBtn.style.cssText = [
          "flex:1",
          "border:none",
          "border-radius:6px",
          "padding:6px 10px",
          "background:#16a34a",
          "color:#fff",
          "cursor:pointer",
          "font-size:11px",
          "font-family:inherit",
        ].join(";");

        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.textContent = "Cancel";
        cancelBtn.style.cssText = [
          "flex:1",
          "border:1px solid #374151",
          "border-radius:6px",
          "padding:6px 10px",
          "background:#374151",
          "color:#d1d5db",
          "cursor:pointer",
          "font-size:11px",
          "font-family:inherit",
        ].join(";");

        cancelBtn.addEventListener("click", () => backdrop.remove());
        backdrop.addEventListener("click", (e) => { if (e.target === backdrop) backdrop.remove(); });

        submitBtn.addEventListener("click", async () => {
          let diocese = dioceseSelect.value.trim();
          if (diocese === NEW_DIOCESE_VALUE) {
            diocese = _slugifyDioceseInput(newDioceseInput.value);
            if (!diocese) {
              setModalStatus("⚠ Enter a name for the new diocese (e.g. donegal).");
              return;
            }
            if (["recipes", "unknown", "main"].includes(diocese)) {
              setModalStatus("⚠ That diocese name is reserved — pick another.");
              return;
            }
          }
          const rawName = nameInput.value.trim();
          const startUrl = urlInput.value.trim();
          const parish_key = _toParishKey(rawName);

          if (!diocese) { setModalStatus("⚠ Please select a diocese or create a new one."); return; }
          if (!rawName) { setModalStatus("⚠ Please enter a parish name."); return; }
          if (!parish_key) { setModalStatus("⚠ Parish key could not be generated — check the name."); return; }
          if (!startUrl || !/^https?:\/\//i.test(startUrl)) {
            setModalStatus("⚠ Please enter a valid https:// start URL."); return;
          }

          submitBtn.disabled = true;
          submitBtn.textContent = "⏳ Creating…";
          setModalStatus("Sending to GitHub…");

          _safeSendMessage(
            {
              type: "new_parish",
              diocese,
              parish_key,
              parish_name: rawName,
              start_url: startUrl,
            },
            (resp, err) => {
              submitBtn.disabled = false;
              submitBtn.textContent = "➕ Create stub recipe";
              if (err || !resp?.ok) {
                setModalStatus(`❌ ${resp?.error || err || "Unknown error"}`);
              } else {
                setModalStatus(`✅ Created! ${resp.filePath || ""}`, true);
                void (async () => {
                  if (dioceseSelect.value === NEW_DIOCESE_VALUE && diocese) {
                    const cached = await _storageGet([DIOCESE_CACHE_KEY]);
                    const entry = cached[DIOCESE_CACHE_KEY];
                    const list = Array.isArray(entry?.list) ? [...entry.list] : [];
                    if (!list.includes(diocese)) {
                      list.push(diocese);
                      list.sort();
                      await _storageSet({ [DIOCESE_CACHE_KEY]: { list, ts: Date.now() } });
                    }
                  }
                })();
                setTimeout(() => backdrop.remove(), 2500);
              }
            }
          );
        });

        btnRow.appendChild(submitBtn);
        btnRow.appendChild(cancelBtn);
        panel.appendChild(btnRow);
        backdrop.appendChild(panel);
        document.body.appendChild(backdrop);
        // Focus name field once diocese list loads.
        setTimeout(() => nameInput.focus(), 50);
      };

      const newParishBtn = makeBtn("➕ New Parish", () => { void openNewParishModal(); });
      row.appendChild(newParishBtn);
    })();
    // ── end New Parish wizard ──────────────────────────────────────────────

    // ── Iframe picker in Advanced ─────────────────────────────────────────
    const iframePickerBtn = makeBtn("📐 It's in a frame / viewer", () => {
      const pickerPanel = buildIframePickerPanel(showStatus);
      if (pickerPanel) {
        _clearElement(guidedPanel);
        const backBtn = makeSmallBtn("← Back", "#374151", resetGuidedPanel);
        backBtn.style.width = "auto";
        backBtn.style.marginBottom = "6px";
        guidedPanel.appendChild(backBtn);
        guidedPanel.appendChild(pickerPanel);
        advancedSection.open = false;
        if (advancedStorageKey) void _storageSet({ [advancedStorageKey]: false });
      }
    });
    advancedBodyEl.appendChild(iframePickerBtn);

    // ── Capture newsletter column (auto) ──────────────────────────────────
    const CONTENT_SELECTORS = [
      "article",
      ".entry-content",
      ".post-content",
      ".content-area",
      ".inside-article",
      ".site-content",
      '[role="main"]',
      "main",
    ];
    const captureAreaBtn = makeBtn("📰 Capture newsletter column (auto)", () => {
      let found = null;
      let usedSelector = "";
      for (const sel of CONTENT_SELECTORS) {
        const el = document.querySelector(sel);
        if (el) {
          found = el;
          usedSelector = sel;
          break;
        }
      }
      if (!found) {
        standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
        showStatus("✅ Recorded full-page print (no column found). Push when ready.", "ok");
        return;
      }
      const prevOutline = found.style.outline;
      found.style.outline = "3px solid #f59e0b";
      found.scrollIntoView({ behavior: "smooth", block: "nearest" });
      standaloneAddStep(
        { action: "print_to_pdf", selector: usedSelector },
        "print_to_pdf",
        `📰 Print column: ${usedSelector}`
      );
      showStatus(`✅ Recorded print of ${usedSelector}. Push recipe when steps look right.`, "ok");
      setTimeout(() => {
        if (found.style.outline === "3px solid #f59e0b") {
          found.style.outline = prevOutline;
        }
      }, 5000);
    });
    advancedBodyEl.appendChild(captureAreaBtn);

    advancedSection.appendChild(advancedBodyEl);
    body.appendChild(advancedSection);

    // ── Push Recipe to GitHub (standalone mode) ───────────────────────────
    // Only rendered when the Playwright bindings are absent.  Uses the
    // recipeSteps[] accumulated above to build a recipe JSON and push
    // it directly to the repo via the GitHub Contents API.
    if (_inStandaloneMode()) {
      const pushSection = document.createElement("div");
      pushSection.id = "ph-push-section";
      pushSection.style.cssText = [
        "background:#1e293b",
        "border:1px solid #16a34a",
        "border-radius:6px",
        "padding:8px",
        "margin-top:6px",
      ].join(";");

      const pushTitle = document.createElement("div");
      pushTitle.style.cssText = "font-size:10px;font-weight:600;color:#86efac;margin-bottom:6px;";
      pushTitle.textContent = "⬆ Push Recipe to GitHub";
      pushSection.appendChild(pushTitle);

      // GitHub settings check — warn early if PAT/repo are not configured.
      const ghConfigNote = document.createElement("div");
      ghConfigNote.style.cssText = "font-size:9px;display:none;margin-bottom:5px;padding:3px 6px;border-radius:3px;";
      pushSection.appendChild(ghConfigNote);
      if (typeof chrome !== "undefined" && chrome.storage) {
        try {
          chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => {
            if (chrome.runtime?.lastError) return;
            if (!r.gh_pat || !r.gh_repo) {
              ghConfigNote.style.display = "block";
              ghConfigNote.style.background = "#7f1d1d";
              ghConfigNote.style.color = "#fca5a5";
              ghConfigNote.textContent = "⚠️ GitHub PAT / repo not set — open the extension popup → ⚙️ Settings before pushing.";
            } else {
              ghConfigNote.style.display = "block";
              ghConfigNote.style.background = "#14532d";
              ghConfigNote.style.color = "#86efac";
              ghConfigNote.textContent = `✓ GitHub configured for ${r.gh_repo}`;
            }
          });
        } catch (_e) {}
      }

      const makeInput = (placeholder, id) => {
        const inp = document.createElement("input");
        inp.type = "text";
        inp.placeholder = placeholder;
        inp.id = id;
        inp.style.cssText = [
          "width:100%",
          "border:1px solid #374151",
          "border-radius:4px",
          "padding:4px 6px",
          "background:#0f172a",
          "color:#f9fafb",
          "font-size:10px",
          "margin-bottom:4px",
          "box-sizing:border-box",
          "font-family:inherit",
        ].join(";");
        return inp;
      };

      const keyInput = makeInput("Parish key (auto-detected if blank)", "ph-parish-key");
      const nameInput = makeInput("Display name (auto-detected if blank)", "ph-display-name");

      const harvestStatusLine = document.createElement("div");
      harvestStatusLine.style.cssText = "font-size:9px;color:#93c5fd;margin-bottom:4px;display:none;";
      pushSection.appendChild(harvestStatusLine);
      pushSection.appendChild(keyInput);
      pushSection.appendChild(nameInput);

      const _refreshHarvestStatusLine = async (parishKey) => {
        const key = String(parishKey || "").trim().toLowerCase();
        if (!key) {
          harvestStatusLine.style.display = "none";
          return;
        }
        const settings = await _storageGet(["gh_repo"]);
        const ghRepo = String(settings.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
        try {
          const [reportResp, failResp] = await Promise.all([
            fetch(`https://raw.githubusercontent.com/${ghRepo}/main/Bulletins/report.json`),
            fetch(`https://raw.githubusercontent.com/${ghRepo}/main/parishes/consecutive_failures.json`),
          ]);
          let line = "";
          if (reportResp.ok) {
            const report = await reportResp.json();
            const downloaded = (report.downloaded || []).some((r) => r.parish === key);
            const failed = (report.failed || []).find((r) => r.parish === key);
            if (downloaded) {
              line = `✅ Last harvest (${report.target_date || "recent"}): downloaded OK`;
              harvestStatusLine.style.color = "#86efac";
            } else if (failed) {
              const reason = String(failed.reason || failed.error || "failed").slice(0, 90);
              const training = _standaloneRecipeSteps().length > 0;
              const onPdf = detectPageType().type === "direct_pdf";
              if (training || onPdf) {
                line = `ℹ️ Last Sunday's run failed (${reason}) — push this recipe to fix it`;
                harvestStatusLine.style.color = "#fde68a";
              } else {
                line = `❌ Last harvest: ${reason}`;
                harvestStatusLine.style.color = "#fca5a5";
              }
              if (window.ph_copilot?.rememberIssue) {
                window.ph_copilot.rememberIssue(key, { lastIssue: reason });
              }
            }
          }
          if (!line && failResp.ok) {
            const fails = await failResp.json();
            const count = Number(fails[key] || 0);
            if (count >= 2) {
              line = `⚠️ ${count} consecutive harvest failures — retrain this recipe`;
              harvestStatusLine.style.color = "#fde68a";
            }
          }
          if (line) {
            harvestStatusLine.textContent = line;
            harvestStatusLine.style.display = "block";
          } else {
            harvestStatusLine.style.display = "none";
          }
        } catch (_e) {
          harvestStatusLine.style.display = "none";
        }
      };

      const dioceseSelect = document.createElement("select");
      dioceseSelect.id = "ph-diocese-select";
      dioceseSelect.style.cssText = [
        "width:100%",
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:4px 6px",
        "background:#0f172a",
        "color:#f9fafb",
        "font-size:10px",
        "margin-bottom:6px",
        "box-sizing:border-box",
        "font-family:inherit",
      ].join(";");
      const dioceseOpts = [
        { v: "", l: "— select diocese —" },
        { v: "derry", l: "Derry" },
        { v: "down_and_connor", l: "Down and Connor" },
        { v: "raphoe", l: "Raphoe" },
        { v: "donegal", l: "Donegal (custom)" },
      ];
      for (const o of dioceseOpts) {
        const opt = document.createElement("option");
        opt.value = o.v;
        opt.textContent = o.l;
        dioceseSelect.appendChild(opt);
      }
      const dioceseLabel = document.createElement("div");
      dioceseLabel.style.cssText = "font-size:9px;color:#93c5fd;margin-bottom:2px;";
      dioceseLabel.textContent = "Diocese (for recipe folder):";
      pushSection.appendChild(dioceseLabel);
      pushSection.appendChild(dioceseSelect);

      const dioceseLine = document.createElement("div");
      dioceseLine.style.cssText = "font-size:9px;color:#9ca3af;margin-bottom:6px;display:none;";
      pushSection.appendChild(dioceseLine);
      let resolvedDiocese = "";

      // Auto-detect label — shown when fields were filled automatically.
      const autoDetectNote = document.createElement("div");
      autoDetectNote.style.cssText = "font-size:9px;color:#86efac;margin-bottom:3px;display:none;";
      pushSection.appendChild(autoDetectNote);

      const refreshDioceseLine = () => {
        if (resolvedDiocese) {
          dioceseSelect.value = resolvedDiocese;
          dioceseLine.style.display = "block";
          dioceseLine.textContent = `Recipe will save to parishes/recipes/${resolvedDiocese}/`;
        }
      };
      dioceseSelect.addEventListener("change", () => {
        resolvedDiocese = dioceseSelect.value.trim();
        refreshDioceseLine();
        if (resolvedDiocese) void _storageSet({ ph_last_diocese: resolvedDiocese });
      });

      const parishMismatchBanner = document.createElement("div");
      parishMismatchBanner.style.cssText = [
        "display:none",
        "background:#7f1d1d",
        "border:1px solid #ef4444",
        "color:#fecaca",
        "font-size:10px",
        "line-height:1.45",
        "border-radius:6px",
        "padding:6px 8px",
        "margin-bottom:6px",
      ].join(";");
      pushSection.appendChild(parishMismatchBanner);

      const _showParishMismatch = (inferredKey, shownKey) => {
        if (!inferredKey || !shownKey || inferredKey === shownKey) {
          parishMismatchBanner.style.display = "none";
          return;
        }
        parishMismatchBanner.style.display = "block";
        parishMismatchBanner.textContent =
          `⚠️ Parish key mismatch — this page is "${inferredKey}" but the form showed "${shownKey}". ` +
          "Using the current page URL.";
      };

      const _applyResolvedParishToPushForm = (resolved, { notePrefix = "Auto-detected" } = {}) => {
        if (!resolved) return;
        const inferred = resolved.inferredKey || resolved.key || "";
        if (inferred) {
          keyInput.value = inferred;
          autoDetectNote.style.display = "block";
          autoDetectNote.textContent = `✓ ${notePrefix}: ${resolved.name || inferred} (${inferred})`;
        }
        if (resolved.name) nameInput.value = resolved.name;
        if (resolved.diocese && !resolvedDiocese) {
          resolvedDiocese = resolved.diocese;
          refreshDioceseLine();
        }
        updateParishRecordingLine(nameInput.value || resolved.name, inferred, resolved.hostname);
        _showParishMismatch(inferred, resolved.key && resolved.key !== inferred ? resolved.key : "");
      };

      const _bootstrapParishContext = async () => {
        const pageUrl = _pageUrlForParishDetection();
        const hostname = _hostnameFromUrl(pageUrl);
        if (standaloneStartUrl && !_hostsMatch(standaloneStartUrl, pageUrl)) {
          standaloneStartUrl = pageUrl;
        }
        _purgeStaleHostnameMapEntry(hostname, pageUrl);
        const r = await _storageGet(["ph_last_diocese", "ph_hostname_map"]);
        const resolved = _resolveParishContextForPage(pageUrl, r || {});
        if (!resolved.diocese && r.ph_last_diocese && !resolvedDiocese) {
          resolvedDiocese = String(r.ph_last_diocese || "").trim();
          refreshDioceseLine();
        }
        const contactName = await _lookupDisplayNameFromContacts(
          resolved.inferredKey || resolved.key,
          hostname
        );
        if (contactName) {
          resolved.name = contactName;
        }
        if (resolved.inferredKey) {
          resolved.key = resolved.inferredKey;
        }
        _applyResolvedParishToPushForm(resolved);
        await _writeParishDetectDebug(resolved);
        void _refreshHarvestStatusLine(resolved.inferredKey || resolved.key);
        await _loadExistingRecipeIfEmpty(resolved, contactName, hostname);
        void refreshPatternHints();
      };

      _refreshParishPushForm = _bootstrapParishContext;

      let _loadExistingRecipeIfEmpty = async () => {};

      const stepCountEl = document.createElement("div");
      stepCountEl.style.cssText = "font-size:9px;color:#6b7280;margin-bottom:5px;";
      const refreshStepCount = () => {
        stepCountEl.textContent = `${_standaloneRecipeSteps().length} step(s) recorded`;
      };
      refreshStepCount();
      pushSection.appendChild(stepCountEl);

      // Keep count in sync with session steps
      const origRefreshRecipeCount = _refreshRecipeCount;
      _refreshRecipeCount = () => {
        if (origRefreshRecipeCount) origRefreshRecipeCount();
        refreshStepCount();
      };

      const dispatchErrorBanner = document.createElement("div");
      dispatchErrorBanner.style.cssText = [
        "display:none",
        "background:#78350f",
        "border:1px solid #f59e0b",
        "color:#fde68a",
        "font-size:10px",
        "line-height:1.45",
        "border-radius:6px",
        "padding:6px 8px",
        "margin-bottom:6px",
      ].join(";");
      const dispatchErrorText = document.createElement("span");
      const dispatchErrorDismiss = document.createElement("button");
      dispatchErrorDismiss.type = "button";
      dispatchErrorDismiss.textContent = "✕";
      dispatchErrorDismiss.style.cssText = [
        "border:none",
        "background:transparent",
        "color:#fde68a",
        "cursor:pointer",
        "float:right",
        "font-size:12px",
        "padding:0 0 0 6px",
      ].join(";");
      dispatchErrorDismiss.addEventListener("click", () => {
        dispatchErrorBanner.style.display = "none";
      });
      dispatchErrorBanner.appendChild(dispatchErrorDismiss);
      dispatchErrorBanner.appendChild(dispatchErrorText);
      pushSection.appendChild(dispatchErrorBanner);

      const showDispatchErrorBanner = (msg) => {
        dispatchErrorText.textContent = msg;
        dispatchErrorBanner.style.display = "block";
      };

      const driftBanner = document.createElement("div");
      driftBanner.style.cssText = [
        "display:none",
        "background:#78350f",
        "border:1px solid #f59e0b",
        "color:#fde68a",
        "font-size:10px",
        "line-height:1.45",
        "border-radius:6px",
        "padding:6px 8px",
        "margin-bottom:6px",
      ].join(";");
      const driftMsg = document.createElement("div");
      driftMsg.textContent = "This site may have moved — the saved recipe points to a different address.";
      const updateStartUrlBtn = document.createElement("button");
      updateStartUrlBtn.type = "button";
      updateStartUrlBtn.textContent = "Update start_url";
      updateStartUrlBtn.style.cssText = [
        "border:none",
        "border-radius:4px",
        "padding:4px 8px",
        "background:#f59e0b",
        "color:#111827",
        "cursor:pointer",
        "font-size:10px",
        "margin-top:6px",
      ].join(";");
      driftBanner.appendChild(driftMsg);
      driftBanner.appendChild(updateStartUrlBtn);
      advancedBodyEl.appendChild(driftBanner);

      let driftRecipeKey = "";
      let driftRecipeObject = null;
      let driftRecipePath = "";

      const pushBtn = document.createElement("button");
      pushBtn.type = "button";
      pushBtn.textContent = "⬆ Push Recipe to GitHub";
      pushBtn.style.cssText = [
        "border:none",
        "border-radius:6px",
        "padding:6px 10px",
        "background:#16a34a",
        "color:#fff",
        "cursor:pointer",
        "font-size:11px",
        "text-align:left",
        "white-space:normal",
        "font-family:inherit",
        "line-height:1.3",
        "width:100%",
        "margin-bottom:4px",
      ].join(";");

      const loadRecipeFromRawGithub = async (key, diocese) => {
        if (!key) return null;
        const settings = await _storageGet(["gh_repo", "gh_pat"]);
        const ghRepo = String(settings.gh_repo || "").trim();
        if (!ghRepo) return null;
        const headers = {};
        const pat = String(settings.gh_pat || "").trim();
        if (pat) headers.Authorization = `token ${pat}`;
        // Keep this normalization aligned with background.js::_canonicalDioceseSlug.
        const canonicalDioceseSlug = (value) => {
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
          return raw.replace(/&/g, "and").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
        };

        // Try diocese subfolder path first, then fall back to legacy flat path.
        const dioceseSubfolder = canonicalDioceseSlug(diocese) || "unknown";
        const pathsToTry = [
          `parishes/recipes/${dioceseSubfolder}/${key}.json`,
          `parishes/recipes/${key}.json`,
        ];
        for (const filePath of pathsToTry) {
          const rawUrl = `https://raw.githubusercontent.com/${ghRepo}/main/${filePath}`;
          try {
            const resp = await fetch(rawUrl, { headers });
            if (!resp.ok) continue;
            const text = await resp.text();
            return { recipe: JSON.parse(text), filePath };
          } catch (_e) {
            continue;
          }
        }
        return null;
      };

      _loadExistingRecipeIfEmpty = async (resolved, contactName, hostname) => {
        if (_standaloneRecipeSteps().length > 0 || !resolved?.key) return;
        const loaded = await loadRecipeFromRawGithub(resolved.key, resolvedDiocese || resolved.diocese);
        if (!loaded?.recipe) return;
        if (loaded.recipe.display_name && !contactName) {
          nameInput.value = loaded.recipe.display_name;
          updateParishRecordingLine(loaded.recipe.display_name, resolved.key, hostname);
        }
        if (loaded.recipe.diocese && !resolvedDiocese) {
          resolvedDiocese = String(loaded.recipe.diocese || "").trim();
          refreshDioceseLine();
        }
        const imported = _importStandaloneRecipe(loaded.recipe, { showLoadedMessage: false });
        if (imported > 0) {
          refreshStepCount();
          recipeBodyEl.style.display = "block";
          recipeOpen = true;
          recipeToggleEl.textContent = "▼";
          showStatus(`📂 Loaded existing recipe (${imported} steps) from GitHub — edit if needed, then push.`, "info");
        }
      };

      if (typeof chrome !== "undefined" && chrome.storage) {
        try {
          void _bootstrapParishContext();
        } catch (_storageErr) {
          // Extension context may have been invalidated — silently ignore.
        }
      }

      const checkStartUrlDrift = async () => {
        const pageUrl = _pageUrlForParishDetection();
        const hostname = _hostnameFromUrl(pageUrl);
        if (!hostname) return;
        const storageData = await _storageGet(["ph_hostname_map"]);
        const resolved = _resolveParishContextForPage(pageUrl, storageData);
        const key = String(resolved.inferredKey || resolved.key || "")
          .trim()
          .toLowerCase()
          .replace(/\s+/g, "_");
        if (!key) return;
        const diocese = String(resolved.diocese || "").trim();
        const loaded = await loadRecipeFromRawGithub(key, diocese);
        if (!loaded || !loaded.recipe) return;
        const startUrl = String(loaded.recipe.start_url || "").trim();
        if (!startUrl) return;
        let savedHost = "";
        try {
          savedHost = new URL(startUrl).hostname.toLowerCase();
        } catch (_e) {
          return;
        }
        if (savedHost && savedHost !== hostname) {
          driftRecipeKey = key;
          driftRecipeObject = loaded.recipe;
          driftRecipePath = loaded.filePath;
          driftBanner.style.display = "block";
        } else {
          driftBanner.style.display = "none";
        }
      };

      pushBtn.addEventListener("click", async () => {
        const pageUrl = _pageUrlForParishDetection();

        let storageData = {};
        if (typeof chrome !== "undefined" && chrome.storage) {
          try {
            storageData = await new Promise((resolve) => {
              chrome.storage.local.get(["ph_hostname_map", "ph_last_diocese"], (r) => {
                if (chrome.runtime?.lastError) resolve({});
                else resolve(r || {});
              });
            });
          } catch (_storageErr) {
            storageData = {};
          }
        }

        const resolved = _resolveParishContextForPage(pageUrl, storageData);
        const inferredKey = String(resolved.inferredKey || _inferParishKeyFromUrl(pageUrl) || "")
          .trim()
          .toLowerCase()
          .replace(/\s+/g, "_");
        const manualKey = keyInput.value.trim().toLowerCase().replace(/\s+/g, "_");
        // Current page URL always wins — stale Bellaghy text in the form cannot override.
        let key = inferredKey || manualKey;
        if (inferredKey && manualKey && manualKey !== inferredKey) {
          console.warn(
            `Parish Trainer: ignoring stale manual key "${manualKey}" — page URL says "${inferredKey}"`
          );
          _showParishMismatch(inferredKey, manualKey);
        }
        let name = nameInput.value.trim() || resolved.name;
        let diocese = resolved.diocese || resolvedDiocese;

        if (inferredKey) {
          keyInput.value = inferredKey;
          key = inferredKey;
          const contactName = await _lookupDisplayNameFromContacts(inferredKey, _hostnameFromUrl(pageUrl));
          if (contactName) name = contactName;
          if (!name) name = _inferDisplayNameFromUrl(pageUrl) || inferredKey;
        }
        if (name) nameInput.value = name;
        updateParishRecordingLine(name, key, _hostnameFromUrl(pageUrl));
        await _writeParishDetectDebug(resolved, { pushKey: key, pushName: name });

        if (diocese && !resolvedDiocese) {
          resolvedDiocese = diocese;
          refreshDioceseLine();
        }

        if (!key) {
          showStatus("❌ Could not detect parish key from this page URL. Check you are on the parish website.", "error");
          return;
        }
        if (_standaloneRecipeSteps().length === 0) { showStatus("⚠️ No steps recorded yet.", "warn"); return; }
        const ensured = _ensureTerminalPdfStep();
        if (!ensured.ok) {
          showStatus(
            "❌ Finish with PDF capture first — tap 📄 Save this PDF, 📰 Save page as PDF, or 🖼️ image.",
            "error"
          );
          return;
        }
        if (ensured.added) {
          showStatus("✅ PDF step added automatically — pushing…", "info");
        }
        const recorded = _standaloneRecipeSteps();
        const lastStep = recorded[recorded.length - 1];
        if (!lastStep || !_pdfTerminalActions.has(String(lastStep.action || "").toLowerCase())) {
          showStatus(
            "❌ Recipe must end with PDF capture: download, image, print_to_pdf, or crop_screenshot.",
            "error"
          );
          return;
        }

        console.log(`Parish Trainer: pushing recipe for key=${key}, diocese=${diocese}, url=${pageUrl}`);
        const recipe = buildStandaloneRecipe(key, name || key, diocese);
        const sitePattern = (() => {
          const lib = globalThis.PhPatternLibrary;
          if (!lib) return null;
          const detected = detectPageType();
          return {
            page: lib.fingerprintFromPage(detected),
            recipe: lib.fingerprintFromRecipe(recipe),
          };
        })();
        pushBtn.disabled = true;
        pushBtn.textContent = "⏳ Pushing…";
        _logSaveCycle("push_recipe", { parish_key: key, recipe }, { ok: "pending" });
        showStatus("⏳ Pushing recipe to GitHub…", "info");

        _safeSendMessage({ type: "push_recipe", parish_key: key, recipe, site_pattern: sitePattern }, (response, bridgeError) => {
          _logSaveCycle("push_recipe", { parish_key: key, recipe }, bridgeError ? { ok: false, reason: bridgeError } : response);
          pushBtn.disabled = false;
          pushBtn.textContent = "⬆ Push Recipe to GitHub";
          if (bridgeError) {
            showStatus(`❌ ${bridgeError}`, "error");
            return;
          }
          if (response && response.ok) {
            const verb = response.updated ? "updated" : "created";
            const path = response.filePath || `parishes/recipes/${key}.json`;
            const linkUrl = response.url || "";
            const linkPart = linkUrl ? ` → ${linkUrl}` : ` → ${path}`;
            if (response.dispatchOk) {
              dispatchErrorBanner.style.display = "none";
              showStatus(`✅ Recipe ${verb}! Triggering instant Mega PDF rebuild… ${linkPart}`, "ok");
            } else if (response.dispatchError) {
              showDispatchErrorBanner(response.dispatchError);
              showStatus(
                `✅ Recipe ${verb}!${linkPart} ⚠️ Rebuild trigger failed: ${response.dispatchError}`,
                "ok",
              );
            } else {
              showStatus(`✅ Recipe ${verb}!${linkPart}`, "ok");
            }
            if (response.patternLearned) {
              showStatus("📚 Pattern saved — similar parishes will get hints next time.", "ok");
            } else if (response.patternLearnError) {
              console.warn("Pattern learn failed:", response.patternLearnError);
            }
            // Persist diocese and per-domain context for next time.
            if (typeof chrome !== "undefined" && chrome.storage) {
              try {
                if (diocese) chrome.storage.local.set({ ph_last_diocese: diocese });
              } catch (_e) {}
            }
            _cacheParishByDomain(
              standaloneStartUrl || window.location.href,
              key,
              name || key,
              diocese,
              recipe.start_url || window.location.href
            );
            clearStandaloneRecipe();
            refreshStepCount();
            void checkStartUrlDrift();
          } else {
            showStatus(`❌ ${(response && response.error) || "Unknown error. Check GitHub settings in the popup."}`, "error");
          }
        });
      });
      pushSection.appendChild(pushBtn);

      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.textContent = "🗑 Clear steps";
      clearBtn.style.cssText = [
        "border:1px solid #374151",
        "border-radius:6px",
        "padding:4px 8px",
        "background:transparent",
        "color:#9ca3af",
        "cursor:pointer",
        "font-size:10px",
        "font-family:inherit",
        "width:100%",
      ].join(";");
      clearBtn.addEventListener("click", () => {
        clearStandaloneRecipe();
        recipeSteps = [];
        if (_stepsListEl) _clearElement(_stepsListEl);
        refreshStepCount();
        void _clearRecordingSession();
        showStatus("🗑 Steps cleared.", "info");
      });
      advancedBodyEl.appendChild(clearBtn);

      updateStartUrlBtn.addEventListener("click", async () => {
        if (!driftRecipeKey || !driftRecipePath) return;
        updateStartUrlBtn.disabled = true;
        updateStartUrlBtn.textContent = "⏳ Updating…";
        try {
          const loaded = await loadRecipeFromRawGithub(driftRecipeKey);
          const baseRecipe = loaded?.recipe || driftRecipeObject;
          if (!baseRecipe) {
            showStatus("❌ Could not load current recipe for update.", "error");
            return;
          }
          const nextRecipe = {
            ...baseRecipe,
            start_url: window.location.href,
          };
          const commitMessage = `chore: update start_url for ${driftRecipeKey} [from extension]`;
          _safeSendMessage(
            {
              type: "push_github_file",
              path: driftRecipePath,
              content: JSON.stringify(nextRecipe, null, 2),
              commitMessage,
            },
            (response, bridgeError) => {
              _logSaveCycle(
                "update_start_url",
                { path: driftRecipePath, commitMessage },
                bridgeError ? { ok: false, reason: bridgeError } : response
              );
              updateStartUrlBtn.disabled = false;
              updateStartUrlBtn.textContent = "Update start_url";
              if (bridgeError || !response?.ok) {
                showStatus(
                  `❌ ${(bridgeError || response?.error || "Could not update recipe start_url.")}`,
                  "error"
                );
                return;
              }
              driftBanner.style.display = "none";
              showStatus("✅ start_url updated to this page.", "ok");
              _cacheParishByDomain(
                window.location.href,
                driftRecipeKey,
                String(nextRecipe.display_name || driftRecipeKey),
                String(nextRecipe.diocese || ""),
                window.location.href
              );
            }
          );
        } catch (_e) {
          updateStartUrlBtn.disabled = false;
          updateStartUrlBtn.textContent = "Update start_url";
          showStatus("❌ Could not update recipe start_url.", "error");
        }
      });

      void checkStartUrlDrift();

      body.appendChild(pushSection);
    }

    if (window.ph_buildToolbarCopilot && copilotMount) {
      body.appendChild(copilotMount);
      window.ph_buildToolbarCopilot(copilotMount, {
        scan: () => _handleCopilotMessage({ type: "copilot_scan" }),
        highlight: () => _handleCopilotMessage({ type: "copilot_highlight" }),
        record: () => _handleCopilotMessage({ type: "copilot_record" }),
        pin: () => _handleCopilotMessage({ type: "copilot_pin" }),
        click: () => _handleCopilotMessage({ type: "copilot_click" }),
        showStatus,
        getParishKey: () => (document.getElementById("ph-parish-key")?.value || "").trim().toLowerCase(),
        getGhRepo: async () => {
          const r = await _storageGet(["gh_repo"]);
          return r.gh_repo || "Raphoe-Diocese/parish_harvester";
        },
        onParishPicked: (p) => {
          const keyInput = document.getElementById("ph-parish-key");
          const nameInput = document.getElementById("ph-display-name");
          const dioceseSelect = document.getElementById("ph-diocese-select");
          if (keyInput && p.key) keyInput.value = p.key;
          if (nameInput && p.name) nameInput.value = p.name;
          if (dioceseSelect && p.diocese) dioceseSelect.value = p.diocese;
          void _storageSet({
            ph_training_parish: {
              key: p.key,
              name: p.name,
              diocese: p.diocese || "",
            },
            ph_last_diocese: p.diocese || "",
          });
          updateParishRecordingLine(p.name, p.key, _currentHostname());
        },
      });
    }

    const scrollContainer = document.createElement("div");
    scrollContainer.id = "ph-toolbar-scroll";
    scrollContainer.style.cssText = "overflow-y: auto;flex: 1 1 auto;min-height: 0;";
    scrollContainer.appendChild(body);
    bar.appendChild(scrollContainer);
    bar.appendChild(statusBar);

    // ── "Mark Anyway" confirmation button for non-document URLs ───────────
    window.addEventListener("ph-confirm-mark-download", (e) => {
      const url = e.detail && e.detail.url;
      if (!url) return;
      clearTimeout(statusTimer);
      statusBar.style.display = "block";
      statusBar.style.background = "#78350f";
      statusBar.style.color = "#fde68a";
      statusBar.style.opacity = "1";

      const old = statusBar.querySelector(".ph-mark-anyway");
      if (old) statusBar.removeChild(old);

      const markAnywayBtn = document.createElement("button");
      markAnywayBtn.className = "ph-mark-anyway";
      markAnywayBtn.textContent = "⚠️ Mark Anyway";
      markAnywayBtn.style.cssText = [
        "border:none",
        "border-radius:4px",
        "padding:3px 8px",
        "background:#dc2626",
        "color:#fff",
        "cursor:pointer",
        "font-size:10px",
        "margin-left:6px",
        "font-family:inherit",
        "vertical-align:middle",
      ].join(";");
      markAnywayBtn.addEventListener("click", () => {
        markDownloadUrlSafe(url, showStatus, true);
        if (markAnywayBtn.parentNode) {
          markAnywayBtn.parentNode.removeChild(markAnywayBtn);
        }
      });
      statusBar.appendChild(markAnywayBtn);
    });

    // ── Drag behaviour ─────────────────────────────────────────────────────
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;

    header.addEventListener("mousedown", (event) => {
      if (event.button !== 0) return;
      isDragging = true;
      const r = bar.getBoundingClientRect();
      bar.style.transform = "none";
      bar.style.left = `${r.left}px`;
      bar.style.top = `${r.top}px`;
      dragOffsetX = event.clientX - r.left;
      dragOffsetY = event.clientY - r.top;
      header.style.cursor = "grabbing";
      event.preventDefault();
    });

    document.addEventListener("mousemove", (event) => {
      if (!isDragging) return;
      if (!event.buttons) {
        isDragging = false;
        header.style.cursor = "grab";
        return;
      }
      const bw = bar.offsetWidth;
      const bh = bar.offsetHeight;
      const clampedLeft = Math.max(0, Math.min(event.clientX - dragOffsetX, window.innerWidth - bw));
      const clampedTop  = Math.max(0, Math.min(event.clientY - dragOffsetY, window.innerHeight - bh));
      bar.style.left = `${clampedLeft}px`;
      bar.style.top  = `${clampedTop}px`;
    });

    document.addEventListener("mouseup", () => {
      if (!isDragging) return;
      isDragging = false;
      header.style.cursor = "grab";
    });

    return bar;
  };

  // ── Message listener from isolated world / popup / side panel ─────────────

  const _logSaveCycle = (action, request, response) => {
    try {
      console.log("[PH-SAVE]", { action, request, response });
    } catch (_e) {
      // no-op
    }
  };

  const _handleIncomingMessage = (message) => {
    if (!message || typeof message !== "object") {
      return { ok: false, reason: "Invalid message payload." };
    }
    if (message.type === "ph_ping") return { ok: true };

    if (message.type === "toggle_toolbar") {
      const bar = _getToolbarNode();
      if (!bar) {
        _ensureToolbar(true);
      } else if (bar.dataset.phHidden === "true" || bar.style.display === "none") {
        _ensureToolbar(true);
      } else {
        bar.dataset.phHidden = "true";
        bar.style.display = "none";
      }
      return { ok: true };
    }

    if (message.type === "show_toolbar") {
      _ensureToolbar(true);
      void _markRecordingActive();
      return { ok: true };
    }
    if (message.type === "ph_show_toolbar") {
      _ensureToolbar(true);
      void _markRecordingActive();
      window.dispatchEvent(new CustomEvent("ph-retraining-hint", { detail: { parish_key: message.parish_key || "" } }));
      if (_refreshParishPushForm) void _refreshParishPushForm();
      return { ok: true };
    }
    if (message.type === "restore_recording_session") {
      void _restoreRecordingSessionFromStorage();
      return { ok: true };
    }

    const _recordStandaloneStep = (standaloneStep, stepType, stepLabel) => {
      standaloneAddStep(standaloneStep, stepType, stepLabel);
      return { ok: true };
    };

    const _recordBoundStep = ({ type, bindingName, payload, stepType, stepLabel, unavailableReason }) => {
      if (_inStandaloneMode()) {
        let standaloneStep = null;
        if (type === "mark_html") standaloneStep = { action: "print_to_pdf" };
        if (type === "mark_file") standaloneStep = { action: "download", url: String(payload?.url || window.location.href).trim() };
        if (type === "mark_image") standaloneStep = { action: "image", url: String(payload?.url || "").trim() };
        if (standaloneStep) return _recordStandaloneStep(standaloneStep, stepType, stepLabel);
      }

      const fn = window[bindingName];
      if (typeof fn !== "function") {
        return { ok: false, reason: unavailableReason || "Page save handler is not available." };
      }
      try {
        const result = fn(payload);
        if (result === false) {
          return { ok: false, reason: "Page rejected the save action." };
        }
        addSessionStep(stepType, stepLabel);
        return { ok: true };
      } catch (_e) {
        return { ok: false, reason: "Could not save on this page. Try refreshing and retry." };
      }
    };

    const type = message.type;
    if (type === "mark_element") {
      const detected = detectPageType();
      const currentUrl = window.location.href;
      const responseFor = (next) => {
        const response = _handleIncomingMessage(next);
        _logSaveCycle(type, { detectedType: detected.type, next }, response);
        return response;
      };

      if (isDocumentUrl(currentUrl)) {
        return responseFor({ type: "mark_file", url: currentUrl });
      }
      if (detected.type === "wix_viewer" && detected.wixPdfUrl) {
        return responseFor({ type: "mark_file", url: detected.wixPdfUrl });
      }
      const linkCandidates = Array.isArray(detected.links) ? detected.links : [];
      if (linkCandidates.length > 0) {
        const scored = linkCandidates.map((el, idx) => {
          const url = el.getAttribute("href") || "";
          const label = (el.innerText || el.textContent || "").trim();
          return { url, domIdx: idx, ...scoreUrlCandidateStr(url, label, idx) };
        });
        scored.sort(_bulletinDateSortFn);
        const bestUrl = String(scored[0]?.url || "").trim();
        if (bestUrl) {
          return responseFor({ type: "mark_file", url: bestUrl });
        }
      }

      if (detected.type === "image") {
        const candidate = Array.from(document.querySelectorAll("img[src]")).find((img) =>
          isLargeImage(img, 300) || hasBulletinLikeFilename(img.getAttribute("src") || "")
        );
        if (candidate) {
          const rawSrc = candidate.getAttribute("src") || "";
          try {
            const absSrc = new URL(rawSrc, window.location.href).href;
            return responseFor({ type: "mark_image", url: absSrc });
          } catch (_e) {
            // fall through to HTML marker
          }
        }
      }

      if (detected.type === "embed" || detected.type === "iframe_maybe" || detected.type === "wix_viewer") {
        _ensureToolbar(true);
        window.dispatchEvent(new CustomEvent("ph-start-pick-iframe"));
        const response = { ok: true, reason: "Opened frame picker to mark embedded bulletin content." };
        _logSaveCycle(type, { detectedType: detected.type }, response);
        return response;
      }

      if (detected.type === "wix_html") {
        if (_inStandaloneMode()) {
          standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
          const response = { ok: true, reason: "Recorded Wix HTML page as print-to-PDF for mega bulletin." };
          _logSaveCycle(type, { detectedType: detected.type }, response);
          return response;
        }
      }

      return responseFor({ type: "mark_html" });
    }
    if (type === "mark_html") {
      const request = { url: window.location.href };
      const response = _recordBoundStep({
        type,
        bindingName: "ph_mark_html",
        payload: request,
        stepType: "print_to_pdf",
        stepLabel: "📰 Save page as PDF",
        unavailableReason: "Page save handler is unavailable on this page.",
      });
      _logSaveCycle(type, request, response);
      return response;
    }
    if (type === "mark_file") {
      const selectedUrl = String(message.url || window.location.href).trim();
      const request = { url: selectedUrl };
      const response = _recordBoundStep({
        type,
        bindingName: "ph_mark_download_url",
        payload: request,
        stepType: "mark_file",
        stepLabel: `📄 File: ${selectedUrl.slice(-45)}`,
        unavailableReason: "File mark handler is unavailable on this page.",
      });
      _logSaveCycle(type, request, response);
      return response;
    }
    if (type === "mark_dead_url") {
      const request = { url: "dead_url", type: "dead_url" };
      const response = _recordBoundStep({
        type,
        bindingName: "ph_mark_download_url",
        payload: request,
        stepType: "mark_file",
        stepLabel: "🔴 Dead URL",
        unavailableReason: "Dead URL mark handler is unavailable on this page.",
      });
      _logSaveCycle(type, request, response);
      return response;
    }
    if (type === "mark_image") {
      const imageUrl = String(message.url || "").trim();
      if (!imageUrl) {
        const response = { ok: false, reason: "No image URL was provided." };
        _logSaveCycle(type, { url: imageUrl }, response);
        return response;
      }
      const request = { url: imageUrl };
      const response = _recordBoundStep({
        type,
        bindingName: "ph_mark_image",
        payload: request,
        stepType: "mark_image",
        stepLabel: `🖼️ Image: ${imageUrl.slice(-45)}`,
        unavailableReason: "Image mark handler is unavailable on this page.",
      });
      _logSaveCycle(type, request, response);
      return response;
    }
    if (type === "start_crop") {
      startCrop();
      return { ok: true };
    }
    if (type === "start_pick_link") {
      _ensureToolbar(true);
      window.dispatchEvent(new CustomEvent("ph-start-pick-link"));
      return { ok: true };
    }
    if (type === "start_pick_iframe") {
      _ensureToolbar(true);
      window.dispatchEvent(new CustomEvent("ph-start-pick-iframe"));
      return { ok: true };
    }
    if (type === "start_pick_image") {
      _ensureToolbar(true);
      window.dispatchEvent(new CustomEvent("ph-start-pick-image-mode"));
      return { ok: true };
    }
    if (type === "mark_crop") {
      const payload = message?.x != null ? message : null;
      if (!payload) {
        const response = { ok: false, reason: "Crop data is missing." };
        _logSaveCycle(type, message, response);
        return response;
      }
      if (cropSignature(payload) === lastCropSignature) {
        const response = { ok: true };
        _logSaveCycle(type, payload, response);
        return response;
      }
      if (!window.ph_mark_crop) {
        const response = { ok: false, reason: "Crop save handler is unavailable on this page." };
        _logSaveCycle(type, payload, response);
        return response;
      }
      try {
        const cropResult = window.ph_mark_crop(payload);
        if (cropResult === false) {
          const response = { ok: false, reason: "Crop was not saved by the page." };
          _logSaveCycle(type, payload, response);
          return response;
        }
        addSessionStep("mark_crop", `✂️ Crop: ${Math.round(payload.width || 0)}×${Math.round(payload.height || 0)}`);
        const response = { ok: true };
        _logSaveCycle(type, payload, response);
        return response;
      } catch (_e) {
        const response = { ok: false, reason: "Could not save the crop selection. Try again." };
        _logSaveCycle(type, payload, response);
        return response;
      }
    }
    if (type === "document_url_detected") {
      const url = message?.url || "";
      _ensureToolbar(true);
      window.dispatchEvent(new CustomEvent("ph-document-detected", { detail: { url } }));
      return { ok: true };
    }
    return { ok: false, reason: "Unsupported action." };
  };

  // ── Training Copilot ─────────────────────────────────────────────────────

  let _copilotPick = null;
  let _copilotRingEl = null;

  const _copilotClearRing = () => {
    if (_copilotRingEl?.parentNode) _copilotRingEl.parentNode.removeChild(_copilotRingEl);
    _copilotRingEl = null;
  };

  const _copilotCollectLinks = () => {
    const detected = detectPageType();
    const elements = detected.links?.length
      ? Array.from(detected.links)
      : _filterBulletinCandidates(document.querySelectorAll("a[href]"));
    return elements.map((el, domIdx) => {
      const href = el.getAttribute("href") || "";
      let absUrl = href;
      try { absUrl = new URL(href, window.location.href).href; } catch (_e) { /* keep raw */ }
      const label = _getEnrichedLinkLabel(el);
      return {
        el,
        domIdx,
        url: absUrl,
        label,
        selector: buildStableLinkSelector(el),
      };
    });
  };

  const _copilotGetPins = () => new Promise((resolve) => {
    const key = window.ph_copilot?.PINS_KEY || "ph_copilot_pins";
    if (typeof chrome === "undefined" || !chrome.storage?.local) {
      resolve({});
      return;
    }
    chrome.storage.local.get([key], (r) => resolve(r?.[key] && typeof r[key] === "object" ? r[key] : {}));
  });

  const _copilotSavePin = (pin) => new Promise((resolve) => {
    const key = window.ph_copilot?.PINS_KEY || "ph_copilot_pins";
    const host = window.ph_copilot?.normHost?.(window.location.href) || "";
    if (!host || typeof chrome === "undefined" || !chrome.storage?.local) {
      resolve(false);
      return;
    }
    _copilotGetPins().then((pins) => {
      const next = { ...pins, [host]: { ...pin, pinnedAt: new Date().toISOString() } };
      chrome.storage.local.set({ [key]: next }, () => resolve(!chrome.runtime?.lastError));
    });
  });

  const _copilotRingElement = (el) => {
    _copilotClearRing();
    if (!el) return;
    const ring = document.createElement("div");
    ring.id = "ph-copilot-ring";
    Object.assign(ring.style, {
      position: "fixed",
      pointerEvents: "none",
      border: "3px solid #22d3ee",
      background: "rgba(34,211,238,0.15)",
      borderRadius: "6px",
      zIndex: "2147483646",
      boxSizing: "border-box",
      boxShadow: "0 0 12px rgba(34,211,238,0.5)",
    });
    const place = () => {
      const r = el.getBoundingClientRect();
      Object.assign(ring.style, {
        left: `${r.left - 3}px`,
        top: `${r.top - 3}px`,
        width: `${r.width + 6}px`,
        height: `${r.height + 6}px`,
        display: r.width > 0 ? "block" : "none",
      });
    };
    place();
    document.documentElement.appendChild(ring);
    _copilotRingEl = ring;
    const onScroll = () => place();
    window.addEventListener("scroll", onScroll, true);
    ring._cleanup = () => window.removeEventListener("scroll", onScroll, true);
  };

  const _copilotRecordPick = (pick) => {
    if (!pick?.el) return { ok: false, reason: "No link selected." };
    _ensureToolbar(true);
    const clickStep = {
      action: "click",
      selector: pick.selector,
      href: pick.url,
      text: pick.label,
    };
    const clickLabel = `🔗 Click: "${pick.label || pick.selector}"`;
    if (_inStandaloneMode()) {
      standaloneAddStep(clickStep, "click", clickLabel);
      void _persistRecordingSession();
      return { ok: true, reason: "Recorded in recipe." };
    }
    if (typeof window.ph_record_click === "function") {
      try {
        window.ph_record_click({
          tag: (pick.el.tagName || "").toLowerCase(),
          role: (pick.el.getAttribute("role") || "").toLowerCase(),
          text: (pick.el.innerText || pick.el.textContent || "").trim().slice(0, 200),
          href: pick.el.getAttribute("href") || "",
          css_path: cssPath(pick.el),
        });
        addSessionStep("click", clickLabel);
        return { ok: true, reason: "Recorded in recipe." };
      } catch (_e) {
        return { ok: false, reason: "Could not record click." };
      }
    }
    return { ok: false, reason: "Open the floating toolbar first." };
  };

  const _handleCopilotMessage = async (message) => {
    const type = message?.type || "";
    if (type === "copilot_scan") {
      const pins = await _copilotGetPins();
      const links = _copilotCollectLinks();
      const ranked = window.ph_copilot?.rankLinks?.(links, {
        pageUrl: window.location.href,
        pins,
        dateScorer: scoreUrlCandidateStr,
      }) || { best: null, alternatives: [] };
      const detected = detectPageType();
      const pageBrief = window.ph_copilot?.buildPageBrief?.() || {};
      const host = window.ph_copilot?.normHost?.(window.location.href) || "";
      if (ranked.best) {
        const match = links.find((l) => l.domIdx === ranked.best.domIdx) || links[0];
        _copilotPick = match || null;
        if (_copilotPick?.el) _copilotRingElement(_copilotPick.el);
      } else {
        _copilotPick = null;
        _copilotClearRing();
      }
      const advice = window.ph_copilot?.advise?.({
        pageType: detected.type,
        best: ranked.best,
        alternatives: ranked.alternatives,
        pin: pins[host] || null,
        pageUrl: window.location.href,
        pageBrief,
      }) || "No links found.";
      const parishKey = document.getElementById("ph-parish-key")?.value?.trim().toLowerCase() || "";
      if (parishKey && window.ph_copilot?.rememberIssue) {
        window.ph_copilot.rememberIssue(parishKey, {
          lastUrl: window.location.href,
          lastAdvice: advice.slice(0, 240),
          pageType: detected.type,
        });
      }
      const context = {
        best: ranked.best,
        alternatives: ranked.alternatives,
        advice,
        pageType: detected.type,
        pageBrief,
      };
      return { ok: true, advice, context };
    }
    if (type === "copilot_highlight") {
      if (!_copilotPick?.el) return { ok: false, reason: "Run Analyse page first." };
      _copilotRingElement(_copilotPick.el);
      _copilotPick.el.scrollIntoView({ block: "center", behavior: "smooth" });
      return { ok: true };
    }
    if (type === "copilot_record") {
      return _copilotRecordPick(_copilotPick);
    }
    if (type === "copilot_pin") {
      if (!_copilotPick) return { ok: false, reason: "Analyse page first." };
      const ok = await _copilotSavePin({
        text: _copilotPick.label,
        href: _copilotPick.url,
        selector: _copilotPick.selector,
      });
      return ok ? { ok: true } : { ok: false, reason: "Could not save pin." };
    }
    if (type === "copilot_click") {
      if (!_copilotPick?.el) return { ok: false, reason: "Analyse page first." };
      _ensureToolbar(true);
      try {
        _copilotPick.el.click();
      } catch (_e) {
        return { ok: false, reason: "Could not click element." };
      }
      const recorded = _copilotRecordPick(_copilotPick);
      return recorded.ok ? { ok: true, reason: "Clicked and recorded." } : recorded;
    }
    return { ok: false, reason: "Unknown copilot action." };
  };

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.data && event.data.direction === "from-isolated") {
      _handleIncomingMessage(event.data.message);
    }
  });

  if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (message?.type === "get_standalone_steps") {
        sendResponse({ ok: true, count: _standaloneRecipeSteps().length });
        return true;
      }
      if (message?.type === "auto_download_detected") {
        const url = String(message.url || "").trim();
        if (url && _inStandaloneMode()) {
          const steps = _standaloneRecipeSteps();
          const last = steps[steps.length - 1];
          const already =
            last &&
            String(last.action || "").toLowerCase() === "download" &&
            String(last.url || "") === url;
          if (!already) {
            standaloneAddStep(
              { action: "download", url },
              "mark_file",
              `📄 Auto-download: ${url.slice(-50)}`
            );
            _ensureToolbar(true);
            window.dispatchEvent(
              new CustomEvent("ph-recording-continued", {
                detail: { stepCount: _standaloneRecipeSteps().length },
              })
            );
          }
        }
        sendResponse({ ok: true });
        return true;
      }
      if (String(message?.type || "").startsWith("copilot_")) {
        void _handleCopilotMessage(message).then((result) => sendResponse(result));
        return true;
      }
      const result = _handleIncomingMessage(message);
      sendResponse(result);
      return true;
    });
  }

  // ── Click recording ───────────────────────────────────────────────────────

  document.addEventListener(
    "click",
    (event) => {
      // Skip clicks inside the floating toolbar itself
      if (
        event.target instanceof Element &&
        event.target.closest("#ph-floating-toolbar")
      )
        return;
      if (pickLinkActive) return;

      const target =
        event.target instanceof Element
          ? event.target.closest(
              'a,button,[role],input[type="submit"],input[type="button"]'
            )
          : null;
      if (!target) return;
      const clickData = {
        tag: (target.tagName || "").toLowerCase(),
        role: (target.getAttribute("role") || "").toLowerCase(),
        text: (target.innerText || target.textContent || "").trim().slice(0, 200),
        href: target.getAttribute("href") || "",
        css_path: cssPath(target),
      };
      const label = clickData.text
        ? `🔗 Click: "${clickData.text.slice(0, 40)}"`
        : `🔗 Click: ${clickData.css_path.slice(0, 40)}`;
      if (window.ph_record_click) {
        window.ph_record_click(clickData);
        addSessionStep("click", label);
      } else if (_inStandaloneMode() && _getToolbarNode() && _getToolbarNode().style.display !== "none") {
        // Standalone mode: record the navigation click for the recipe
        const text = clickData.text;
        const href = clickData.href;
        const selector = text && text.length >= 3 && text.length <= 60
          ? `${clickData.tag}:has-text("${text.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}")`
          : clickData.css_path;
        const step = { action: "click", selector };
        const fallbacks = [];
        if (href && href.toLowerCase().endsWith(".pdf")) fallbacks.push("a[href$='.pdf']");
        else if (href && href.toLowerCase().endsWith(".docx")) fallbacks.push("a[href$='.docx']");
        if (clickData.css_path && clickData.css_path !== selector) fallbacks.push(clickData.css_path);
        if (fallbacks.length) step.fallback_selectors = fallbacks;
        standaloneAddStep(step, "click", label);
      }
    },
    true
  );

  // ── Dead page overlay ────────────────────────────────────────────────────────
  const _showDeadPageOverlay = () => {
    // Already shown?
    if (document.getElementById("ph-dead-page-overlay")) return;

    const overlay = document.createElement("div");
    overlay.id = "ph-dead-page-overlay";
    Object.assign(overlay.style, {
      position: "fixed",
      top: "20px",
      left: "50%",
      transform: "translateX(-50%)",
      zIndex: "2147483647",
      background: "#1f2937",
      color: "#f9fafb",
      fontFamily: "system-ui, -apple-system, sans-serif",
      fontSize: "13px",
      borderRadius: "10px",
      boxShadow: "0 4px 24px rgba(0,0,0,0.7)",
      padding: "16px 20px",
      maxWidth: "420px",
      width: "90vw",
      textAlign: "center",
      border: "2px solid #dc2626",
    });

    const icon = document.createElement("div");
    icon.textContent = "🔴";
    icon.style.cssText = "font-size:28px;margin-bottom:8px;";
    overlay.appendChild(icon);

    const heading = document.createElement("div");
    heading.textContent = "This website appears to be dead or unreachable.";
    heading.style.cssText = "font-weight:700;font-size:14px;margin-bottom:6px;color:#fca5a5;";
    overlay.appendChild(heading);

    const sub = document.createElement("div");
    sub.textContent = "You can mark it as dead in the terminal window — press D then Enter.";
    sub.style.cssText = "color:#9ca3af;font-size:11px;margin-bottom:12px;line-height:1.5;";
    overlay.appendChild(sub);

    const markBtn = document.createElement("button");
    markBtn.textContent = "🗑️ Mark as Dead Website";
    markBtn.type = "button";
    Object.assign(markBtn.style, {
      border: "none",
      borderRadius: "6px",
      padding: "10px 20px",
      background: "#dc2626",
      color: "#fff",
      cursor: "pointer",
      fontSize: "13px",
      fontWeight: "600",
      fontFamily: "inherit",
      width: "100%",
      marginBottom: "8px",
    });
    markBtn.addEventListener("click", () => {
      heading.textContent = "⏳ Marking as dead…";
      heading.style.color = "#fde68a";
      markBtn.disabled = true;
      markBtn.style.opacity = "0.5";

      let settled = false;
      const fail = (reason) => {
        heading.textContent = `❌ Mark as dead failed: ${reason}`;
        heading.style.color = "#fca5a5";
        sub.textContent = "No changes were confirmed. Please retry.";
        markBtn.disabled = false;
        markBtn.style.opacity = "1";
      };

      const timeout = setTimeout(() => {
        if (settled) return;
        settled = true;
        fail("timeout_waiting_for_confirmation_5s");
      }, 5000);

      _safeSendMessage({ type: "mark_dead_url" }, (response, error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        if (error) {
          fail(error);
          return;
        }
        if (response && typeof response === "object" && response.ok === true) {
          heading.textContent = "✅ Marked as dead. You can close this tab.";
          heading.style.color = "#86efac";
          sub.textContent = "The harvester will skip this parish in future runs.";
          markBtn.disabled = true;
          markBtn.style.opacity = "0.5";
          return;
        }
        fail(
          (response && typeof response === "object" && (response.reason || response.error)) ||
          "no_explicit_ok_from_page"
        );
      });
    });
    overlay.appendChild(markBtn);

    const dismissBtn = document.createElement("button");
    dismissBtn.textContent = "Dismiss";
    dismissBtn.type = "button";
    Object.assign(dismissBtn.style, {
      border: "1px solid #374151",
      borderRadius: "6px",
      padding: "6px 14px",
      background: "transparent",
      color: "#9ca3af",
      cursor: "pointer",
      fontSize: "11px",
      fontFamily: "inherit",
    });
    dismissBtn.addEventListener("click", () => {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    });
    overlay.appendChild(dismissBtn);

    document.documentElement.appendChild(overlay);
  };

  // Detect Chrome net-error pages and show the dead overlay
  const _detectAndShowDeadOverlay = () => {
    const isDeadPage = (
      document.getElementById("main-frame-error") !== null ||
      window.location.href.startsWith("chrome-error://") ||
      (document.title && (
        document.title.toLowerCase().includes("err_name_not_resolved") ||
        document.title.toLowerCase().includes("err_connection_refused") ||
        document.title.toLowerCase().includes("err_connection_timed_out") ||
        document.title.toLowerCase().includes("this site can't be reached") ||
        document.title.toLowerCase().includes("this webpage is not available")
      ))
    );
    if (isDeadPage) _showDeadPageOverlay();
  };

  // Run on load and after short delays (Chrome error pages may render slowly)
  _detectAndShowDeadOverlay();
  setTimeout(_detectAndShowDeadOverlay, 500);
  setTimeout(_detectAndShowDeadOverlay, 1500);

  // ── Auto-show toolbar when Playwright training bindings are detected ──────

  const _TRAINING_BINDINGS = ["ph_mark_html", "ph_mark_download_url", "ph_mark_crop"];
  const _AUTO_SHOW_DELAYS_MS = [0, 300, 1000, 2500, 4000, 7000];

  const _tryAutoShowToolbar = () => {
    if (_TRAINING_BINDINGS.some((b) => typeof window[b] === "function")) {
      _ensureToolbar(true);
    }
  };

  _AUTO_SHOW_DELAYS_MS.forEach((delay) => setTimeout(_tryAutoShowToolbar, delay));

  window.addEventListener("pageshow", () => {
    if (_refreshParishPushForm) void _refreshParishPushForm();
  });

  void _restoreRecordingSessionFromStorage();
})();
