(() => {
  if (globalThis.__phContentInstalled && typeof globalThis.__phContentDispatch === "function") {
    if (typeof globalThis.__phBridgeSetDispatch === "function") {
      globalThis.__phBridgeSetDispatch(globalThis.__phContentDispatch);
    }
    return;
  }
  if (globalThis.__phContentInstalled && !globalThis.__phContentDispatch) {
    globalThis.__phContentInstalled = false;
  }
  globalThis.__phContentInstalled = true;

  // ── Session state ────────────────────────────────────────────────────────
  let cropOverlay = null;
  let lastCropSignature = "";
  let toolbar = null;
  const TOOLBAR_ID = "ph-floating-toolbar";
  let toolbarReadyLogged = false;
  let recipeSteps = []; // single source of truth for both UI preview and standalone recipe push
  let lastPushedRecipeNote = "";
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
  let _skipLoadExistingRecipe = false;

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
  // WordPress / Divi edit mode and your own ParishPress site — never hijack the page.
  const _isEditorPageUrl = (url = "") => {
    try {
      const parsed = new URL(String(url || _pageUrlForParishDetection()));
      const href = parsed.href.toLowerCase();
      const path = parsed.pathname.toLowerCase();
      if (
        href.includes("et_fb=1") ||
        path.includes("/wp-admin") ||
        href.includes("customize.php") ||
        href.includes("elementor-preview") ||
        href.includes("fl_builder") ||
        (href.includes("action=edit") && path.includes("post.php"))
      ) {
        return true;
      }
      const host = parsed.hostname.toLowerCase().replace(/^www\./, "");
      if (host === "parishpress.net" && !path.includes("/wp-content/uploads/parish-bulletins/")) {
        return true;
      }
      return false;
    } catch (_e) {
      return false;
    }
  };
  const _dismissToolbar = (clearSession = false) => {
    const bar = _getToolbarNode();
    if (bar) {
      bar.dataset.phHidden = "true";
      bar.style.display = "none";
    }
    stopPickLinkMode?.();
    stopPickImageMode?.();
    if (clearSession || _isEditorPageUrl()) {
      void _clearRecordingSession();
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

  let _persistDebounceTimer = null;
  let _persistPendingExtra = {};

  const _persistRecordingSessionNow = async (extra = {}) => {
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

  const _flushRecordingSession = async (extra = {}) => {
    if (_persistDebounceTimer) {
      clearTimeout(_persistDebounceTimer);
      _persistDebounceTimer = null;
    }
    if (extra && typeof extra === "object") {
      Object.assign(_persistPendingExtra, extra);
    }
    const pending = _persistPendingExtra;
    _persistPendingExtra = {};
    await _persistRecordingSessionNow(pending);
  };

  const _persistRecordingSession = (extra = {}) => {
    if (!_inStandaloneMode()) return;
    Object.assign(_persistPendingExtra, extra || {});
    if (_persistDebounceTimer) clearTimeout(_persistDebounceTimer);
    _persistDebounceTimer = setTimeout(() => {
      _persistDebounceTimer = null;
      const pending = _persistPendingExtra;
      _persistPendingExtra = {};
      void _persistRecordingSessionNow(pending);
    }, 300);
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

  const _prefersClickByTextLink = (text = "") =>
    /click here|current newsletter|this week|weekly bulletin|read more|view newsletter|load current/i.test(
      String(text || "")
    );

  const _isPdfOrDocUrl = (url) => {
    if (!url) return false;
    const path = String(url).split("?")[0].toLowerCase();
    return /\.(pdf|docx?|pptx?|odt|ods)(\?|#|$)/i.test(path);
  };

  const _markNavigationStart = (url, atMs) => {
    try {
      sessionStorage.setItem(
        "ph_train_nav_started",
        JSON.stringify({
          url: String(url || window.location.href),
          at: Number(atMs) || Date.now(),
        })
      );
    } catch (_e) {
      // ignore
    }
  };

  const _bootstrapFixNowLoadTimer = () => {
    if (!_inStandaloneMode()) return;
    const timerEl =
      globalThis.__phPageLoadTimerLine ||
      document.getElementById("ph-page-load-timer");
    if (!timerEl) return;
    timerEl.style.display = "block";
    _attachPageLoadTimer(timerEl);
  };

  const _applyFixNowToolbar = async (message) => {
    const navAt = Number(message?.nav_started_at);
    if (Number.isFinite(navAt) && navAt > 0) {
      _markNavigationStart(window.location.href, navAt);
    } else {
      _markNavigationStart(window.location.href);
    }
    _sessionMaxLoadMs = 0;
    recipeSteps = [];
    standaloneStartUrl = _pageUrlForParishDetection();
    _skipLoadExistingRecipe = true;
    const bar = _ensureToolbar(true);
    if (bar) {
      bar.dataset.phFixNow = "1";
      bar.dataset.phParishName = String(message?.parish_key || "").replace(/_/g, " ");
    }
    await _persistRecordingSessionNow({ fixNow: true });
    _bootstrapFixNowLoadTimer();
    window.dispatchEvent(
      new CustomEvent("ph-retraining-hint", {
        detail: { parish_key: message?.parish_key || "" },
      })
    );
    if (typeof showStatus === "function") {
      showStatus(
        "🔧 Fix now — wait for the load timer, then point at the bulletin.",
        "info"
      );
    }
    if (_refreshParishPushForm) void _refreshParishPushForm();
  };

  const _clearNavigationMark = () => {
    try {
      sessionStorage.removeItem("ph_train_nav_started");
    } catch (_e) {
      // ignore
    }
  };

  const _formatLoadDuration = (ms) => {
    const n = Math.max(0, Math.round(Number(ms) || 0));
    if (n < 1000) return `${n}ms`;
    const sec = Math.floor(n / 1000);
    if (sec < 60) return `${sec}s`;
    const min = Math.floor(sec / 60);
    const rem = sec % 60;
    return rem ? `${min}m ${rem}s` : `${min}m`;
  };

  const _navigationStartedAtMs = () => {
    try {
      const raw = sessionStorage.getItem("ph_train_nav_started");
      if (raw) {
        const parsed = JSON.parse(raw);
        const target = String(parsed?.url || "");
        const at = Number(parsed?.at || 0);
        if (at > 0 && (!target || target === window.location.href)) return at;
      }
    } catch (_e) {
      // ignore
    }
    const nav = performance.getEntriesByType?.("navigation")?.[0];
    if (nav && Number.isFinite(nav.startTime) && performance.timeOrigin) {
      return performance.timeOrigin + nav.startTime;
    }
    return Date.now();
  };

  let _pageLoadTimerStop = null;
  let _sessionMaxLoadMs = 0;

  const _getCurrentPageLoadMs = () => {
    const nav = performance.getEntriesByType?.("navigation")?.[0];
    if (nav && nav.loadEventEnd > 0) return Math.round(nav.loadEventEnd);
    const startedAt = _navigationStartedAtMs();
    return Math.max(0, Date.now() - startedAt);
  };

  const _getObservedLoadMsForRecipe = () => {
    const current = _getCurrentPageLoadMs();
    return Math.max(_sessionMaxLoadMs, current);
  };

  const HARVEST_TIMEOUT_BUFFER_MS = 10_000;
  const HARVEST_TIMEOUT_BUFFER_S = 10;

  const _recipeTimeoutsFromLoadMs = (loadMs, stepCount = 3) => {
    const ms = Math.max(0, Number(loadMs) || 0);
    if (ms < 1000) return null;
    const steps = Math.max(1, Number(stepCount) || 1);
    return {
      observed_load_ms: ms,
      timeout_ms: Math.min(
        Math.max(ms * 2 + HARVEST_TIMEOUT_BUFFER_MS, 45_000 + HARVEST_TIMEOUT_BUFFER_MS),
        300_000
      ),
      total_timeout_s: Math.min(
        Math.max(
          Math.ceil(ms / 1000) * steps * 2 + 45 + HARVEST_TIMEOUT_BUFFER_S,
          180 + HARVEST_TIMEOUT_BUFFER_S,
          steps * 120 + HARVEST_TIMEOUT_BUFFER_S
        ),
        900
      ),
    };
  };

  const _attachPageLoadTimer = (el) => {
    if (_pageLoadTimerStop) _pageLoadTimerStop();
    if (!el) return;
    el.style.display = "block";
    let stopped = false;
    let interval = null;

    const tick = () => {
      if (stopped) return;
      const nav = performance.getEntriesByType?.("navigation")?.[0];
      const domMs =
        nav && nav.domContentLoadedEventEnd > 0 ? Math.round(nav.domContentLoadedEventEnd) : null;
      const loadMs = nav && nav.loadEventEnd > 0 ? Math.round(nav.loadEventEnd) : null;
      const startedAt = _navigationStartedAtMs();
      const elapsed = Math.max(0, Date.now() - startedAt);
      _sessionMaxLoadMs = Math.max(_sessionMaxLoadMs, elapsed);
      const stillLoading = document.readyState !== "complete" || !loadMs;

      if (stillLoading) {
        el.style.color = elapsed >= 30000 ? "#fde68a" : "#93c5fd";
        const commitHint =
          elapsed >= 45000 && document.readyState !== "complete"
            ? " — WordPress may never finish; harvest will use commit navigation"
            : "";
        el.textContent =
          elapsed >= 60000
            ? `⏱ Still loading… ${_formatLoadDuration(elapsed)} — very slow site${commitHint}`
            : elapsed >= 15000
              ? `⏱ Still loading… ${_formatLoadDuration(elapsed)} — slow site${commitHint}`
              : `⏱ Still loading… ${_formatLoadDuration(elapsed)}`;
        return;
      }

      _clearNavigationMark();
      const total = loadMs || elapsed;
      _sessionMaxLoadMs = Math.max(_sessionMaxLoadMs, total);
      const domPart = domMs ? ` · page readable at ${_formatLoadDuration(domMs)}` : "";
      const timeoutHint = _recipeTimeoutsFromLoadMs(total);
      const saveHint = timeoutHint
        ? ` · harvest wait ${_formatLoadDuration(timeoutHint.total_timeout_s * 1000)} saved to recipe`
        : "";
      if (total >= 60000) {
        el.style.color = "#fca5a5";
        el.textContent =
          `⏱ Loaded in ${_formatLoadDuration(total)}${domPart}${saveHint} — very slow site`;
      } else if (total >= 15000) {
        el.style.color = "#fde68a";
        el.textContent = `⏱ Loaded in ${_formatLoadDuration(total)}${domPart}${saveHint} — slow site`;
      } else {
        el.style.color = "#86efac";
        el.textContent = `⏱ Loaded in ${_formatLoadDuration(total)}${domPart}${saveHint}`;
      }
      stopped = true;
      if (interval) clearInterval(interval);
    };

    interval = setInterval(tick, 500);
    window.addEventListener("load", tick, { once: true });
    document.addEventListener("readystatechange", tick);
    tick();

    _pageLoadTimerStop = () => {
      stopped = true;
      if (interval) clearInterval(interval);
      document.removeEventListener("readystatechange", tick);
      _pageLoadTimerStop = null;
    };
  };

  const _openBulletinInNewTabNow = (absUrl, selectedEl) => {
    if (!absUrl) return false;
    try {
      const link = document.createElement("a");
      link.href = absUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      link.remove();
      return true;
    } catch (_e) {
      // try element click next
    }
    if (selectedEl instanceof Element) {
      const anchor =
        selectedEl.closest("a[href]") || (selectedEl.tagName === "A" ? selectedEl : null);
      if (anchor) {
        const prevTarget = anchor.getAttribute("target");
        anchor.setAttribute("target", "_blank");
        try {
          anchor.click();
          if (prevTarget == null) anchor.removeAttribute("target");
          else anchor.setAttribute("target", prevTarget);
          return true;
        } catch (_e2) {
          if (prevTarget == null) anchor.removeAttribute("target");
          else anchor.setAttribute("target", prevTarget);
        }
      }
    }
    try {
      const popup = window.open(absUrl, "_blank", "noopener,noreferrer");
      return Boolean(popup);
    } catch (_e3) {
      return false;
    }
  };

  const _openUrlInRecordingTab = async (absUrl, showStatus) => {
    if (!absUrl || typeof chrome === "undefined" || !chrome.runtime?.sendMessage) return false;
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
        if (showStatus) {
          showStatus(
            _isPdfOrDocUrl(absUrl)
              ? "✅ Step saved — bulletin opened in a new tab."
              : "✅ Step saved — extension continues in the new tab.",
            "ok"
          );
        }
        return true;
      }
    } catch (_e) {
      // Fall through to same-tab navigation.
    }
    return false;
  };

  const _navigateRecordingToUrl = async (absUrl, selectedEl, showStatus) => {
    if (!absUrl) return false;

    // Persist before navigation — debounced save often never runs before the tab unloads.
    await _flushRecordingSession({ pendingUrl: absUrl });

    // Open synchronously first — async awaits below break the user-gesture chain
    // and Chrome blocks window.open after recording/persist delays.
    if (_openBulletinInNewTabNow(absUrl, selectedEl)) {
      if (showStatus) {
        showStatus(
          _isPdfOrDocUrl(absUrl)
            ? "✅ Step saved — bulletin opened in a new tab."
            : "✅ Step saved — extension continues in the new tab.",
          "ok"
        );
      }
      return true;
    }

    const opened = await _openUrlInRecordingTab(absUrl, showStatus);
    if (opened) return true;

    if (showStatus) {
      showStatus(
        "✅ Step saved — opening link in this tab (allow pop-ups for a new tab).",
        "info"
      );
    }
    _markNavigationStart(absUrl);
    window.location.assign(absUrl);
    return true;
  };

  const _restoreRecordingSessionFromStorage = async () => {
    if (!_inStandaloneMode()) return false;
    const pageUrl = _pageUrlForParishDetection();
    if (_isEditorPageUrl(pageUrl)) {
      const bar = _getToolbarNode();
      if (bar) {
        bar.dataset.phHidden = "true";
        bar.style.display = "none";
      }
      await _clearRecordingSession();
      return false;
    }
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

    if (session.fixNow) {
      await _applyFixNowToolbar({
        reason: "fix_now",
        parish_key: session.parish_key || "",
        nav_started_at: session.updatedAt || Date.now(),
      });
      return true;
    }

    _ensureToolbar(true);
    window.dispatchEvent(
      new CustomEvent("ph-recording-continued", {
        detail: { stepCount: _standaloneRecipeSteps().length },
      })
    );
    const restoredSteps = _standaloneRecipeSteps();
    const hasClick = restoredSteps.some(
      (s) => String(s?.action || "").trim().toLowerCase() === "click"
    );
    const hasPrint = restoredSteps.some((s) => {
      const a = String(s?.action || "").trim().toLowerCase();
      return a === "print_to_pdf" || a === "html";
    });
    if (hasClick && !hasPrint) {
      window.dispatchEvent(
        new CustomEvent("ph-retraining-hint", {
          detail: {
            parish_key: session.parish_key || "",
            hint: "homepage_click_done",
          },
        })
      );
    }
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

  const _slimDiagnosisForPush = (snapshot) => {
    if (!snapshot || typeof snapshot !== "object") return null;
    return {
      collected_at: snapshot.collected_at,
      extension_version: snapshot.extension_version,
      page_url: snapshot.page_url,
      parish_key: snapshot.parish_key,
      page_type: snapshot.page_type,
      site_intake: snapshot.site_intake,
      html_fingerprint: snapshot.html_fingerprint,
      counts: snapshot.counts,
      issues: Array.isArray(snapshot.issues) ? snapshot.issues.slice(0, 15) : [],
    };
  };

  // ── Safe message bridge ───────────────────────────────────────────────────
  // content.js now runs in the ISOLATED world so chrome.runtime is always
  // available.  _safeSendMessage uses the direct API and falls back to the
  // window.postMessage ↔ isolated.js bridge only if chrome.runtime becomes
  // unavailable (e.g. after an extension reload mid-session).
  // callback(response, errorString) — errorString is non-null on failure.
  const _safeSendMessage = (message, callback) => {
    const pushRecipe = message?.type === "push_recipe";
    const TIMEOUT_MS = pushRecipe ? 45000 : 15000;

    // ── Direct path ──────────────────────────────────────────────────────
    if (typeof chrome !== "undefined" && chrome?.runtime?.sendMessage) {
      try {
        let settled = false;
        let timer = null;
        if (pushRecipe) {
          timer = setTimeout(() => {
            if (settled) return;
            settled = true;
            callback(
              null,
              "Push is taking longer than expected. Check GitHub for the recipe file — if it saved, reload the page. Otherwise verify your PAT in Settings."
            );
          }, TIMEOUT_MS);
        }
        chrome.runtime.sendMessage(message, (res) => {
          if (settled) return;
          settled = true;
          if (timer) clearTimeout(timer);
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
    if (window.ph_parish_pickers?.inferParishKeyFromUrl) {
      return window.ph_parish_pickers.inferParishKeyFromUrl(url);
    }
    if (!url) return "";
    try {
      const parsed = new URL(url);
      const hostname = parsed.hostname.toLowerCase().replace(/^www\d*\./, "");
      return hostname.split(".")[0] || "";
    } catch (_e) {
      return "";
    }
  };

  const _siteCacheKeyForUrl = (url) =>
    window.ph_parish_pickers?.siteCacheKey?.(url) ||
    (() => {
      try {
        return new URL(url).hostname.toLowerCase();
      } catch (_e) {
        return "";
      }
    })();

  const _inferDisplayNameFromUrl = (url) => {
    const key = _inferParishKeyFromUrl(url);
    if (!key) return "";
    return key.charAt(0).toUpperCase() + key.slice(1);
  };

  // Resolve parish key/name from the CURRENT page URL — never reuse a stale
  // ph_training_parish from a different website (e.g. bellaghyparish bleeding
  // into threepatrons.org).
  const _resolveParishContextForPage = (pageUrl, storageData = {}) => {
    if (window.ph_parish_pickers?.resolveFromPage) {
      return window.ph_parish_pickers.resolveFromPage(pageUrl || window.location.href, storageData);
    }
    const inferredKey = _inferParishKeyFromUrl(pageUrl || window.location.href);
    const inferredName = _inferDisplayNameFromUrl(pageUrl || window.location.href);
    return { key: inferredKey, name: inferredName, diocese: "", hostname: "", inferredKey };
  };

  const _parishKeyMatchesPageUrl = (key, pageUrl) => {
    const inferred = _inferParishKeyFromUrl(pageUrl);
    const norm = (s) => String(s || "").trim().toLowerCase().replace(/\s+/g, "_");
    const k = norm(key);
    const i = norm(inferred);
    if (!k) return false;
    if (!i) return true;
    if (k === i) return true;
    const urlHit = window.ph_parish_pickers?.lookupByUrl?.(pageUrl);
    if (urlHit?.key && norm(urlHit.key) === k) return true;
    try {
      const hostSeg = new URL(pageUrl).hostname.toLowerCase().replace(/^www\d*\./, "").split(".")[0] || "";
      if (hostSeg && hostSeg !== "mcn" && (k === hostSeg || hostSeg.includes(k) || k.includes(hostSeg))) {
        return true;
      }
    } catch (_e) {
      // ignore
    }
    return false;
  };

  const _purgeStaleHostnameMapEntry = (hostname, pageUrl) => {
    const cacheKey = _siteCacheKeyForUrl(pageUrl);
    if (!cacheKey || typeof chrome === "undefined" || !chrome.storage) return;
    try {
      chrome.storage.local.get(["ph_hostname_map"], (r) => {
        if (chrome.runtime?.lastError) return;
        const hostnameMap = (r.ph_hostname_map && typeof r.ph_hostname_map === "object")
          ? { ...r.ph_hostname_map }
          : {};
        const stale = hostnameMap[cacheKey] || (hostname ? hostnameMap[hostname] : null);
        if (!stale) return;
        const staleKey = String(stale.parish_key || stale.key || "").trim().toLowerCase().replace(/\s+/g, "_");
        if (!staleKey || _parishKeyMatchesPageUrl(staleKey, pageUrl)) return;
        delete hostnameMap[cacheKey];
        if (hostname) delete hostnameMap[hostname];
        try { chrome.storage.local.set({ ph_hostname_map: hostnameMap }); } catch (_e) {}
      });
    } catch (_e) {
      // ignore
    }
  };

  // Persist per-domain parish context after a successful push.
  const _cacheParishByDomain = (url, key, name, diocese, startUrl = "") => {
    const cacheKey = _siteCacheKeyForUrl(url || startUrl);
    if (!cacheKey || !key) return;
    if (typeof chrome === "undefined" || !chrome.storage) return;
    let hostname = "";
    try {
      hostname = new URL(url || startUrl).hostname;
    } catch (_e) {
      // ignore
    }
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
        cache[cacheKey] = context;
        hostnameMap[cacheKey] = context;
        try { chrome.storage.local.set({ ph_parish_by_domain: cache, ph_hostname_map: hostnameMap }); } catch (_e) {}
      });
    } catch (_e) {}
  };

  const _standaloneRecipeSteps = () =>
    recipeSteps
      .filter((entry) => entry && entry.recipeStep && typeof entry.recipeStep.action === "string")
      .map((entry) => entry.recipeStep);

  globalThis.__phStandaloneStepCount = () => _standaloneRecipeSteps().length;

  /** Start page for Sunday harvest — current page unless a click chain began elsewhere. */
  const _resolveRecipeStartUrl = () => {
    const pageUrl = _pageUrlForParishDetection();
    const recorded = _standaloneRecipeSteps();
    const hasClick = recorded.some(
      (step) => String(step?.action || "").trim().toLowerCase() === "click"
    );
    if (!hasClick) {
      return pageUrl;
    }
    if (standaloneStartUrl && _hostsMatch(standaloneStartUrl, pageUrl)) {
      return standaloneStartUrl;
    }
    return pageUrl;
  };

  const standaloneAddStep = (step, uiType = "", uiLabel = "") => {
    if (!_inStandaloneMode()) return;
    // Replace an existing download/image/html step if one already exists
    const terminal = ["download", "image", "image_stack", "print_to_pdf", "crop_screenshot"];
    if (terminal.includes(step.action)) {
      const idx = recipeSteps.findIndex((entry) =>
        terminal.includes(String(entry?.recipeStep?.action || ""))
      );
      if (idx >= 0) {
        recipeSteps.splice(idx, 1);
      }
    }
    const stepAction = String(step?.action || "").trim().toLowerCase();
    const hadClickBefore = _standaloneRecipeSteps().some(
      (s) => String(s?.action || "").trim().toLowerCase() === "click"
    );
    recipeSteps.push({
      type: uiType || step.action || "step",
      label: uiLabel || _recipeStepToUiLabel(step),
      recipeStep: step,
    });
    if (_stepsListEl) _renderSessionSteps();
    if (_refreshRecipeCount) _refreshRecipeCount();
    if (stepAction === "click" && !hadClickBefore) {
      standaloneStartUrl = window.location.href;
    } else if (!standaloneStartUrl) {
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
    const startUrl = _resolveRecipeStartUrl();
    // Harvester opens start_url before replaying steps — keep UI step count = JSON steps.
    steps.push(..._standaloneRecipeSteps());
    const usesCloudFolder = steps.some(
      (s) => s && (s.cloud_folder || s.date_format === "YY.MM.DD")
    );
    let recipe = {
      version: 1,
      parish_key: parishKey,
      display_name: displayName,
      diocese: diocese || "",
      start_url: startUrl,
      steps,
      ...(usesCloudFolder ? { cloud_folder: true, date_format: "YY.MM.DD" } : {}),
    };
    const loadTimeouts = _recipeTimeoutsFromLoadMs(_getObservedLoadMsForRecipe(), steps.length);
    if (loadTimeouts) {
      Object.assign(recipe, loadTimeouts);
    } else {
      const stepCount = Math.max(steps.length, 1);
      recipe.timeout_ms = recipe.timeout_ms || 90_000 + HARVEST_TIMEOUT_BUFFER_MS;
      recipe.total_timeout_s = Math.min(
        Math.max(stepCount * 120 + 60 + HARVEST_TIMEOUT_BUFFER_S, 180 + HARVEST_TIMEOUT_BUFFER_S),
        900
      );
    }
    const hasMessengerPrint = steps.some(
      (s) =>
        s &&
        (s.action === "print_to_pdf" || s.action === "html") &&
        (recipe.site_type === "parish_messenger" || recipe.playbook_type === "parish_messenger")
    );
    if (hasMessengerPrint) {
      recipe.total_timeout_s = Math.max(
        Number(recipe.total_timeout_s) || 0,
        300 + HARVEST_TIMEOUT_BUFFER_S
      );
    }
    try {
      const host = startUrl ? new URL(startUrl).hostname.toLowerCase() : "";
      const observedMs = _getObservedLoadMsForRecipe();
      if (
        host.includes("derriaghycatholicparish.com")
        || host.includes("portstewartparish.website")
        || observedMs >= 45_000
      ) {
        recipe.navigation_wait_until = "commit";
        recipe.timeout_ms = Math.max(Number(recipe.timeout_ms) || 0, 300_000);
        recipe.total_timeout_s = Math.max(
          Number(recipe.total_timeout_s) || 0,
          host.includes("portstewart") ? 900 : 600
        );
      }
      if (
        (host.includes("portstewartparish.website") || host.includes("portstewartparish.ie"))
        && startUrl
        && startUrl.startsWith("https://")
      ) {
        recipe.start_url = startUrl.replace(/^https:/i, "http:");
      }
    } catch (_hostErr) {
      // ignore invalid start_url
    }
    if (window.ph_site_memory?.enrichRecipe) {
      recipe = window.ph_site_memory.enrichRecipe(recipe, detectPageType());
    }
    const pageCtxForRecipe = detectPageType();
    if (pageCtxForRecipe.type === "google_drive_static") {
      const viewUrl = String(pageCtxForRecipe.driveViewUrl || _googleDriveViewUrl(window.location.href) || "").trim();
      const downloadUrl = String(pageCtxForRecipe.autoDownloadUrl || _googleDriveDirectDownloadUrl(window.location.href) || "").trim();
      if (viewUrl) recipe.start_url = viewUrl;
      if (downloadUrl) {
        const dlIdx = recipe.steps.findIndex((s) => String(s?.action || "").toLowerCase() === "download");
        const dlStep = {
          action: "download",
          url: downloadUrl,
          use_captured_url: true,
        };
        if (dlIdx >= 0) recipe.steps[dlIdx] = dlStep;
        else recipe.steps.push(dlStep);
      }
    }
    const clickStep = steps.find((s) => String(s?.action || "").toLowerCase() === "click");
    if (clickStep?.pick_strategy) {
      recipe.bulletin_layout = {
        strategy: clickStep.pick_strategy,
        position: clickStep.bulletin_position || "top",
      };
    }
    return recipe;
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
    if (action === "image_stack") {
      const count = Number(step.count || step.urls?.length || 2);
      return `Capture top ${count} bulletin images (weekly stack)`;
    }
    return `${action || "step"}: ${JSON.stringify(step).slice(0, 80)}`;
  };

  const _importStandaloneRecipe = (recipe, { showLoadedMessage = true } = {}) => {
    if (!_inStandaloneMode() || !recipe || !Array.isArray(recipe.steps)) return 0;
    const pageUrl = _pageUrlForParishDetection();
    const savedStart = String(recipe.start_url || "").trim();
    if (savedStart && _hostsMatch(savedStart, pageUrl)) {
      standaloneStartUrl = savedStart;
    } else {
      standaloneStartUrl = pageUrl;
    }
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
      const ghRepo = String(settings.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
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
    const mount = document.getElementById("ph-trainer-mount");
    if (mount) {
      const inMount = mount.querySelector(`#${TOOLBAR_ID}`);
      if (inMount) {
        toolbar = inMount;
        return inMount;
      }
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

  const _getToolbarMount = () => {
    if (typeof globalThis.__phGetToolbarMount === "function") {
      return globalThis.__phGetToolbarMount();
    }
    return document.body || document.documentElement;
  };

  const _ensureToolbar = (visible = true) => {
    _cleanupDuplicateToolbars();
    let node = _getToolbarNode();
    const stubNode = node?.dataset?.phStub === "1" ? node : null;

    if (node?.dataset?.phStub === "1") {
      node = null;
      toolbar = null;
    }

    if (!node) {
      let created = null;
      try {
        created = createToolbar();
      } catch (fullErr) {
        console.error("[Parish Trainer] createToolbar failed:", fullErr);
        if (globalThis.ph_toolbar_diag?.setError) {
          globalThis.ph_toolbar_diag.setError(`Full toolbar failed: ${fullErr}`);
        }
        try {
          created =
            typeof globalThis.__phCreateMinimalToolbar === "function"
              ? globalThis.__phCreateMinimalToolbar()
              : createMinimalToolbar();
        } catch (minErr) {
          console.error("[Parish Trainer] minimal toolbar failed:", minErr);
          if (globalThis.ph_toolbar_diag?.setError) {
            globalThis.ph_toolbar_diag.setError(`Minimal toolbar failed: ${minErr}`);
          }
          if (stubNode) {
            const status = stubNode.querySelector("#ph-stub-status");
            if (status) {
              status.textContent = `Trainer error: ${minErr}`;
              status.style.color = "#fca5a5";
            }
            stubNode.style.borderColor = "#ef4444";
            node = stubNode;
            toolbar = stubNode;
          } else {
            throw minErr;
          }
          created = null;
        }
      }
      if (created) {
        const mount = _getToolbarMount();
        created.style.pointerEvents = "auto";
        mount.appendChild(created);
        node = created;
        toolbar = node;
        if (stubNode?.parentNode) {
          stubNode.parentNode.removeChild(stubNode);
        }
      }
    }
    if (visible && node) {
      node.dataset.phHidden = "false";
      node.style.display = "flex";
      _notifyRecordingTabActive();
      if (!toolbarReadyLogged && node.dataset.phStub !== "1") {
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

  let _pageTypeCache = { url: "", at: 0, result: null };

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

  const _STABLE_LINK_TEXT_RE =
    /\b(download file|download pdf|view newsletter|read newsletter|latest bulletin|parish news)\b/i;

  const _textLooksDated = (value) => {
    const text = String(value || "");
    if (!text) return false;
    if (extractDateFromUrl(text)?.year) return true;
    return /\b\d{1,2}(?:st|nd|rd|th)?\b/i.test(text) && /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b/i.test(text);
  };

  const _isSequentialNewsletterUrl = (url) =>
    /\/(?:newsletters|weekly-bulletins)\/\d+\//i.test(String(url || ""));

  const _inferBulletinPosition = (el) => {
    if (!(el instanceof Element)) return "top";
    const links = Array.from(
      document.querySelectorAll(
        'a[href$=".pdf"], a[href*=".pdf"], a[href$=".docx"], a[href*=".docx"], a[href*="/Newsletters/"], a[href*="/Weekly-Bulletins/"]'
      )
    ).filter((node) => !_isNonBulletinPdf(node.href || "", node.innerText || ""));
    if (links.length <= 1) return "top";
    const idx = links.findIndex((node) => node === el || node.contains(el) || el.contains(node));
    if (idx < 0) return "top";
    if (idx === 0) return "top";
    if (idx >= links.length - 1) return "bottom";
    return "middle";
  };

  const _enrichClickStepForWeeklyReplay = (clickStep, el) => {
    const next = { ...clickStep };
    const href = String(next.href || "").trim();
    const selector = String(next.selector || "").trim();
    const text = String(next.text || "").trim();
    const looksLikeBulletinLink =
      /\.pdf|\.docx/i.test(href) ||
      /\[href[^\]]*\.pdf/i.test(selector) ||
      /:has-text\("download file"\)/i.test(selector) ||
      _isSequentialNewsletterUrl(href) ||
      /\/newsletters\/|\/weekly-bulletins\//i.test(selector) ||
      (/\bbulletin\b/i.test(text) && _isSequentialNewsletterUrl(href));

    if (!looksLikeBulletinLink) return next;

    next.pick_strategy = next.pick_strategy || "newest_dated";
    next.bulletin_position = next.bulletin_position || _inferBulletinPosition(el);
    const fallbacks = new Set(Array.isArray(next.fallback_selectors) ? next.fallback_selectors : []);
    fallbacks.add("a[href$='.pdf']");
    fallbacks.add("a[href*='.pdf']");
    if (_isSequentialNewsletterUrl(href) || /banagherparish|threepatrons/i.test(window.location.hostname || "")) {
      fallbacks.add('a[href*="/Newsletters/"]');
      fallbacks.add('a[href*="/Weekly-Bulletins/"]');
      if (!/\/newsletters\/|\/weekly-bulletins\//i.test(selector)) {
        next.selector = href.includes("/Weekly-Bulletins/")
          ? 'a[href*="/Weekly-Bulletins/"]'
          : 'a[href*="/Newsletters/"]';
      }
    }
    next.fallback_selectors = Array.from(fallbacks);
    return next;
  };

  const buildStableLinkSelector = (el) => {
    if (!el) return "";
    const anchor =
      el.tagName === "A" ? el : (el.closest && el.closest("a[href]")) || el;
    if (anchor?.classList?.contains("mod_downloadlink")) {
      return "a.mod_downloadlink[href]";
    }
    if (anchor?.closest?.(".mod_dropfiles_latest, .mod_dropfiles_list")) {
      return "a.mod_downloadlink[href]";
    }
    const tag = (anchor || el).tagName.toLowerCase();
    const href = ((anchor || el).getAttribute("href") || "").trim();
    const text = ((anchor || el).innerText || (anchor || el).textContent || "")
      .trim()
      .replace(/\s+/g, " ")
      .slice(0, 120);
    const role = el.getAttribute("role") || "";
    const escapeForSelector = (s) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    if (href && /\/weekly-bulletins\/\d+\//i.test(href)) {
      return 'a[href*="/Weekly-Bulletins/"]';
    }
    if (href && /\/newsletters\/\d+\//i.test(href)) {
      return 'a[href*="/Newsletters/"]';
    }
    if (href && /\.pdf/i.test(href)) {
      const stableMatch = text.match(_STABLE_LINK_TEXT_RE);
      if (stableMatch && !_textLooksDated(stableMatch[0])) {
        return `${tag}:has-text("${escapeForSelector(stableMatch[0])}")`;
      }
      const tail = href.split("/").filter(Boolean).pop() || href;
      if (tail.length >= 6 && !_textLooksDated(tail)) {
        return `a[href*="${escapeForSelector(tail)}"]`;
      }
      return "a[href$='.pdf']";
    }
    if (text && text.length >= 3 && text.length <= 100 && !_textLooksDated(text)) {
      const short = text.slice(0, 60);
      return `${tag}:has-text("${escapeForSelector(short)}")`;
    }
    if (role && text) {
      return `[role="${role}"]:has-text("${escapeForSelector(text.slice(0, 60))}")`;
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

  // Admin / non-bulletin PDFs (Gift Aid forms, GDPR guides, etc.) — never treat as weekly bulletin.
  const _isNonBulletinPdf = (url, label) => {
    const text = `${url || ""} ${label || ""}`.toLowerCase();
    if (/\b(bulletin|newsletter)\b/i.test(text)) return false;
    return (
      /dataentry|giftaid|standingorder|donation|prayer|safeguarding|privacy|gdpr|diocese|sitemap|application|registration|volunteer|finances|financial|parishdraw|mcn\s*media/i.test(
        text
      )
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

  const _unwrapGoogleViewerSrc = (src) => {
    const lower = (src || "").toLowerCase();
    if (!lower.includes("docs.google.com/viewer") && !lower.includes("docs.google.com/gview")) {
      return src;
    }
    try {
      const urlParam = new URL(src, window.location.href).searchParams.get("url");
      return urlParam ? decodeURIComponent(urlParam) : src;
    } catch (_e) {
      return src;
    }
  };

  const _pickBestOnewebNewsletterUrl = () => {
    const iframes = Array.from(document.querySelectorAll("iframe[src]"));
    const scored = [];
    for (let i = 0; i < iframes.length; i++) {
      const resolved = _unwrapGoogleViewerSrc(iframes[i].getAttribute("src") || "");
      if (
        !/onewebmedia/i.test(resolved) ||
        !/newsletter/i.test(resolved) ||
        !/\.docx/i.test(resolved) ||
        _isNonBulletinPdf(resolved, "")
      ) {
        continue;
      }
      scored.push({ url: resolved, ...scoreUrlCandidateStr(resolved, "", i) });
    }
    scored.sort(_bulletinDateSortFn);
    return scored[0]?.url || "";
  };

  const _pickBestWeeklyBulletinUrl = () => {
    const scored = [];
    const addCandidate = (rawUrl, label, domIdx, bonus = 0) => {
      if (!rawUrl) return;
      let abs = "";
      try {
        abs = new URL(rawUrl, window.location.href).href;
      } catch (_e) {
        return;
      }
      const lower = abs.toLowerCase();
      if (_isNonBulletinPdf(abs, label)) return;
      const looksWeekly =
        /weekly-bulletins|\/newsletters\/|\/files\/\d+\/[^/?#]*sunday/i.test(lower);
      if (!looksWeekly && !_looksLikeBulletinDownloadUrl(abs, label)) return;
      const scoredItem = { url: abs, ...scoreUrlCandidateStr(abs, label, domIdx) };
      scoredItem.total = (scoredItem.total || 0) + bonus;
      scored.push(scoredItem);
    };

    const downloadLinks = Array.from(document.querySelectorAll("a.mod_downloadlink[href]"));
    for (let i = 0; i < downloadLinks.length; i++) {
      const el = downloadLinks[i];
      const href = el.getAttribute("href") || el.href || "";
      const row = el.closest(".mod_file");
      const title =
        row?.querySelector(".mod_dropfiles_downloadlink")?.getAttribute("title") ||
        row?.querySelector(".mod_dropfiles_downloadlink")?.textContent ||
        el.getAttribute("aria-label") ||
        "";
      addCandidate(href, String(title || "").trim(), i, 25);
    }

    const links = Array.from(document.querySelectorAll("a[href], [data-href], [data-url], [data-file]"));
    for (let i = 0; i < links.length; i++) {
      const el = links[i];
      if (el.matches("a.mod_downloadlink")) continue;
      const href =
        el.getAttribute("href") ||
        el.getAttribute("data-href") ||
        el.getAttribute("data-url") ||
        el.getAttribute("data-file") ||
        el.href ||
        "";
      const label = (el.innerText || el.textContent || el.getAttribute("title") || "").trim();
      addCandidate(href, label, i + downloadLinks.length);
    }
    scored.sort(_bulletinDateSortFn);
    return scored[0]?.url || "";
  };

  const _hrefFromBulletinClick = (el) => {
    if (!(el instanceof Element)) return "";
    const downloadLink = el.closest("a.mod_downloadlink[href]");
    if (downloadLink) {
      try {
        return new URL(downloadLink.getAttribute("href") || downloadLink.href || "", window.location.href).href;
      } catch (_e) {
        return "";
      }
    }
    const modFile = el.closest(".mod_file");
    if (modFile) {
      const rowDownload = modFile.querySelector("a.mod_downloadlink[href]");
      if (rowDownload) {
        try {
          return new URL(rowDownload.getAttribute("href") || rowDownload.href || "", window.location.href).href;
        } catch (_e2) {
          return "";
        }
      }
    }
    const direct = el.closest(
      'a[href*="Weekly-Bulletins"], a[href*="weekly-bulletins"], a[href*="/Newsletters/"], a[href*="/files/"]'
    );
    if (direct) {
      try {
        return new URL(direct.getAttribute("href") || direct.href || "", window.location.href).href;
      } catch (_e) {
        return "";
      }
    }
    const row =
      el.closest("li, tr, article, section, [class*='bulletin'], [class*='Bulletin']") ||
      el.parentElement;
    if (row) {
      const nearby = row.querySelector(
        'a[href*="Weekly-Bulletins"], a[href*="weekly-bulletins"], a[href*="/Newsletters/"], a[href*="/files/"]'
      );
      if (nearby) {
        try {
          return new URL(nearby.getAttribute("href") || nearby.href || "", window.location.href).href;
        } catch (_e2) {
          return "";
        }
      }
      const dataEl = row.querySelector("[data-href], [data-url], [data-file]");
      if (dataEl) {
        const raw =
          dataEl.getAttribute("data-href") ||
          dataEl.getAttribute("data-url") ||
          dataEl.getAttribute("data-file") ||
          "";
        if (raw) {
          try {
            return new URL(raw, window.location.href).href;
          } catch (_e3) {
            return "";
          }
        }
      }
    }
    return "";
  };

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
    if (/\/files\/\d+\/(?:newsletters|weekly-bulletins)\//i.test(url)) return true;
    if (/\/newsletters\/\d+\//i.test(url)) return true;
    if (/\/files\/\d+\/weekly-bulletins\//i.test(url)) return true;
    if (/\/weekly-bulletins\//i.test(url)) return true;
    if (/\/files\/\d+\/[^/?#]*sunday/i.test(url)) return true;
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
    // Extensionless PDF routes (server returns application/pdf, e.g. cappaghparish.com/b/2)
    if (/\/b\/\d+$/i.test(lowerPath)) return true;
    return false;
  };

  const _extractGoogleDriveFileId = (url) => {
    const text = String(url || "");
    const fileMatch = text.match(/drive\.google\.com\/file\/d\/([^/?#]+)/i);
    if (fileMatch) return fileMatch[1];
    const idMatch = text.match(/[?&]id=([^&#]+)/i);
    return idMatch ? idMatch[1] : "";
  };

  const _googleDriveDirectDownloadUrl = (fileIdOrUrl) => {
    const id =
      /^[a-zA-Z0-9_-]{10,}$/.test(String(fileIdOrUrl || ""))
        ? String(fileIdOrUrl)
        : _extractGoogleDriveFileId(fileIdOrUrl);
    if (!id) return "";
    return `https://drive.usercontent.google.com/download?id=${encodeURIComponent(id)}&export=download`;
  };

  const _googleDriveViewUrl = (fileIdOrUrl) => {
    const id =
      /^[a-zA-Z0-9_-]{10,}$/.test(String(fileIdOrUrl || ""))
        ? String(fileIdOrUrl)
        : _extractGoogleDriveFileId(fileIdOrUrl);
    if (!id) return "";
    return `https://drive.google.com/file/d/${id}/view`;
  };

  const _isGoogleDriveFileViewUrl = (url) =>
    /drive\.google\.com\/file\/d\//i.test(String(url || ""));

  const _isGoogleDriveDirectDownloadUrl = (url) =>
    /drive\.usercontent\.google\.com\/download/i.test(String(url || ""));

  // Chrome (and some hosts) serve PDFs without a .pdf suffix in the address bar.
  const _pageIsNativePdfViewer = () => {
    try {
      if (document.contentType === "application/pdf") return true;
    } catch (_e) {
      // ignore
    }
    const embeds = document.querySelectorAll(
      'embed[type="application/pdf"], object[type="application/pdf"]'
    );
    for (const el of embeds) {
      const src = (el.getAttribute("src") || el.getAttribute("data") || "").trim();
      if (!src || src === "about:blank") return true;
      try {
        const abs = new URL(src, window.location.href).href;
        if (abs === window.location.href) return true;
      } catch (_e) {
        return true;
      }
    }
    if (document.body && document.body.children.length <= 2) {
      if (document.body.querySelector('embed[type="application/pdf"]')) return true;
    }
    return false;
  };

  const _urlLooksLikeDirectPdf = (url) => {
    if (!url) return false;
    if (isDocumentUrl(url)) return true;
    if (/\.pdf(\?|$)/i.test(url)) return true;
    return false;
  };

  const _CLOUD_DATE_YY_MM_DD_RE = /(?<!\d)(\d{2})\.(\d{2})\.(\d{2})(?:\.pdf)?(?!\d)/i;

  const _isCloudFolderUrl = (url) => {
    const lower = String(url || "").toLowerCase();
    if (lower.includes("drive.google.com") && lower.includes("/folders/")) return true;
    if (lower.includes("onedrive.live.com") && (lower.includes("?id=") || lower.includes("/redir"))) {
      return true;
    }
    if (lower.includes("sharepoint.com") && (lower.includes("/documents") || lower.includes("/shared"))) {
      return true;
    }
    if (lower.includes("1drv.ms")) return true;
    return false;
  };

  const _detectCloudDateFormat = (text) => {
    if (_CLOUD_DATE_YY_MM_DD_RE.test(String(text || ""))) return "YY.MM.DD";
    return null;
  };

  const _formatCloudFolderLabel = (d, withPdf = true) => {
    const yy = String(d.getFullYear() % 100).padStart(2, "0");
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const bare = `${yy}.${mm}.${dd}`;
    return withPdf ? `${bare}.pdf` : bare;
  };

  const _findCloudFolderRowForDate = (targetDate) => {
    const labelPdf = _formatCloudFolderLabel(targetDate, true);
    const labelBare = _formatCloudFolderLabel(targetDate, false);
    const selectors = '[role="row"], [role="gridcell"], tr, [data-id], div[data-tooltip]';
    const nodes = Array.from(document.querySelectorAll(selectors));
    for (const el of nodes) {
      const text = (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
      if (!text) continue;
      if (text.includes(labelPdf) || text === labelBare || text.startsWith(labelBare)) {
        const row = el.closest('[role="row"]') || el;
        return row;
      }
    }
    return null;
  };

  let _lastHarvestIssue = "";
  let _needsRetrain = false;

  const IMAGE_CONTENT_AREA_SELECTOR = ".entry-content, article, main, [role='main']";
  const IMAGE_CONTENT_CLASS_HINT_RE = /(entry-content|post-content|article|main)/i;
  const MIN_CONTENT_IMAGE_WIDTH = 200;

  const getImageWidth = (img) => {
    const lib = globalThis.PhHtmlFingerprint;
    if (lib?.imageWidth) return lib.imageWidth(img);
    const widthAttr = Number(img.getAttribute("width") || 0);
    if (Number.isFinite(widthAttr) && widthAttr > 0) return widthAttr;
    const renderWidth = Number(img.width || 0);
    if (Number.isFinite(renderWidth) && renderWidth > 0) return renderWidth;
    const rectWidth = Number(img.getBoundingClientRect?.().width || 0);
    return Number.isFinite(rectWidth) ? rectWidth : 0;
  };

  const _isWordPressHtmlBulletinPage = () => {
    try {
      return Boolean(globalThis.PhHtmlFingerprint?.isWordPressHtmlBulletinPage?.(document));
    } catch (_e) {
      return false;
    }
  };

  const _hasBulletinImageInContent = (minWidth = MIN_CONTENT_IMAGE_WIDTH) => {
    try {
      return Boolean(
        globalThis.PhHtmlFingerprint?.hasBulletinImageInContent?.(document, minWidth)
      );
    } catch (_e) {
      return false;
    }
  };

  const DECORATIVE_IMG_RE =
    /logo|icon|avatar|gravatar|emoji|spinner|badge|social|wp-smiley/i;

  const isLikelyBulletinImage = (img) => {
    const blob = `${img.className} ${img.alt || ""} ${img.src || ""} ${img.id || ""}`;
    if (DECORATIVE_IMG_RE.test(blob)) return false;
    if (/bulletin|newsletter|notice|weekly/i.test(blob)) return true;
    if (img.closest(".entry-content, .post-content, article")) return true;
    return false;
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

  const hasPickableImageInContentAreas = (minWidth = MIN_CONTENT_IMAGE_WIDTH) => {
    if (_isWordPressHtmlBulletinPage()) return false;
    return _hasBulletinImageInContent(minWidth);
  };

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

  /** PDF Embedder inline viewer (Antrim-style): bulletin is already on-page in iframe/embed. */
  const _findPdfembInlinePdfUrl = () => {
    const candidates = [];
    const push = (raw, label = "") => {
      if (!raw || typeof raw !== "string") return;
      const href = raw.trim();
      if (!href || href.startsWith("javascript:") || href.startsWith("#")) return;
      try {
        const resolved = new URL(href, window.location.href).href;
        const lower = resolved.toLowerCase();
        if (!lower.includes(".pdf")) return;
        if (_isNonBulletinPdf(resolved, label)) return;
        candidates.push({ url: resolved, label, ...scoreUrlCandidateStr(resolved, label, candidates.length) });
      } catch (_e) {
        // ignore bad URLs
      }
    };
    const selectors = [
      'a.pdfemb-viewer[href*=".pdf"]',
      'a[class*="pdfemb"][href*=".pdf"]',
      'iframe[src*=".pdf"]',
      'embed[src*=".pdf"]',
      'object[data*=".pdf"]',
      '[id^="pdfemb-embed-"] iframe[src]',
      '[class*="pdfemb"] iframe[src]',
      '[class*="pdfemb"] embed[src]',
    ];
    for (const sel of selectors) {
      document.querySelectorAll(sel).forEach((el) => {
        const label = (el.innerText || el.textContent || el.getAttribute("title") || "").trim();
        push(
          el.getAttribute("href") ||
            el.getAttribute("src") ||
            el.getAttribute("data") ||
            el.getAttribute("data-pdfurl") ||
            el.getAttribute("data-url"),
          label
        );
      });
    }
    document.querySelectorAll('[id^="pdfemb-embed-"], [class*="pdfemb-embed"]').forEach((el) => {
      push(el.getAttribute("data-pdfurl") || el.getAttribute("data-url"), el.id || "");
    });
    if (!candidates.length) {
      try {
        const html = document.documentElement?.innerHTML?.slice(0, 250000) || "";
        const re = /https?:\/\/[^\s"'<>]+\.pdf/gi;
        let m;
        while ((m = re.exec(html)) !== null) {
          push(m[0], m[0].split("/").pop() || "");
        }
      } catch (_htmlScan) {
        // ignore
      }
    }
    if (!candidates.length) return "";
    candidates.sort(_bulletinDateSortFn);
    return candidates[0]?.url || "";
  };

  const _detectPageTypeImpl = () => {
    const url = window.location.href.toLowerCase();

    const _htmlFingerprintDetect = () => {
      const lib = globalThis.PhHtmlFingerprint;
      if (!lib?.scanPage) return null;
      const scan = lib.scanPage(document);
      const b = scan?.best;
      if (!b || !b.pageType) return null;

      const typeMap = {
        wp_pdfemb_list: "pdfemb",
        image_bulletin: "image",
        iframe_viewer: "iframe_maybe",
        parish_messenger_embed: "parish_messenger",
        wix_pdf_viewer: "wix_viewer",
      };
      const type = typeMap[b.pageType] || b.pageType;
      const emojiMap = {
        weekly_bulletin_download: "📥",
        oneweb_docx: "📄",
        pdfemb: "🔗",
        parish_messenger: "📰",
        wix_html: "📰",
        mdocs_bulletin_list: "📥",
        wp_block_file_bulletin: "📄",
        stacked_image_bulletin: "🖼️",
        wix_viewer: "📐",
        cloud_folder: "☁️",
        iframe_maybe: "📐",
        pdf_links: "🔗",
        image: "🖼️",
      };

      const result = {
        emoji: emojiMap[type] || "🔍",
        summary: b.label,
        advice: b.advice,
        type,
        htmlFingerprint: b.id,
        fingerprintScore: b.score,
        fingerprintMarkers: b.markersFound,
        fingerprintScan: scan,
      };
      if (b.bestDownloadUrl) {
        result.autoDownloadUrl = b.bestDownloadUrl;
        if (type === "oneweb_docx") result.autoNewsletterUrl = b.bestDownloadUrl;
      } else if (type === "pdfemb" || b.id === "wordpress_pdfemb") {
        const inlinePdf = _findPdfembInlinePdfUrl();
        if (inlinePdf) {
          result.type = "pdfemb_embed";
          result.autoDownloadUrl = inlinePdf;
          result.emoji = "📄";
          result.summary = "PDF Embedder — bulletin PDF is embedded on this page.";
          result.advice =
            "Tap the green Save bulletin PDF button below (one step). Then Send & test.";
        }
      }
      if (b.doNot?.length) result.fingerprintDoNot = b.doNot;
      if (b.advice && !result.advice) result.advice = b.advice;
      return result;
    };

    // 1. Current page IS a PDF (URL suffix, extensionless route, or Chrome PDF viewer)
    if (
      url.endsWith(".pdf") ||
      url.includes(".pdf?") ||
      url.includes("/pdf/") ||
      _urlLooksLikeDirectPdf(url) ||
      _pageIsNativePdfViewer()
    ) {
      return {
        emoji: "📄",
        summary: "This page IS a PDF document.",
        advice: /\/pdf\/\d{6}\.pdf/i.test(url)
          ? "Tap Save this PDF. Tab title may mention Word/docx — that is normal. Harvester rewrites the date in the URL each Sunday."
          : "Tap the green Save this PDF button, then Send & test.",
        type: "direct_pdf",
      };
    }

    // 1b. Google Drive / OneDrive folder of dated PDFs
    if (_isCloudFolderUrl(url)) {
      const sunday = _nextSundayDate();
      const expected = _formatCloudFolderLabel(sunday, true);
      const rowVisible = Boolean(_findCloudFolderRowForDate(sunday));
      return {
        emoji: "☁️",
        summary: "Cloud folder — weekly PDFs listed by date (YY.MM.DD).",
        advice: rowVisible
          ? `Tap Pick this Sunday's row (${expected}), then Save this PDF on the file page.`
          : `This Sunday's file (${expected}) not visible yet — pick the newest dated row, then Save PDF.`,
        type: "cloud_folder",
        expectedLabel: expected,
        rowVisible,
      };
    }

    // 1b2. Google Drive — single permanent file (Raphoe, Glenswilly, etc.)
    if (_isGoogleDriveFileViewUrl(url) || _isGoogleDriveDirectDownloadUrl(url)) {
      const fileId = _extractGoogleDriveFileId(url);
      const downloadUrl = _googleDriveDirectDownloadUrl(fileId || url);
      const viewUrl = _googleDriveViewUrl(fileId || url) || url;
      return {
        emoji: "📁",
        summary: "Google Drive — permanent bulletin file (same link each week).",
        advice:
          "Train on this Drive preview page — tap the green Save Drive bulletin button (one step). Do not open the instant-download link.",
        type: "google_drive_static",
        htmlFingerprint: "google_drive_file",
        autoDownloadUrl: downloadUrl,
        driveViewUrl: viewUrl,
      };
    }

    // 1c3. WordPress PDF Embedder — before HTML fingerprint (global WP CSS can false-match wp-block-file).
    const pdfembElsEarly = Array.from(
      document.querySelectorAll(
        'a.pdfemb-viewer, a[class*="pdfemb"], [id^="pdfemb-embed-"], [class*="pdfemb-embed"]'
      )
    );
    const pdfembLinksEarly = pdfembElsEarly.filter((el) => {
      const href =
        el.getAttribute("href") ||
        el.getAttribute("data-url") ||
        el.getAttribute("data-pdfurl") ||
        "";
      if (href.length > 0) return true;
      const inner = el.querySelector && el.querySelector("iframe[src], embed[src]");
      return inner && (inner.getAttribute("src") || "").toLowerCase().includes(".pdf");
    });
    if (pdfembElsEarly.length > 0 || pdfembLinksEarly.length > 0) {
      const inlinePdf =
        _findPdfembInlinePdfUrl() ||
        _pickBestWeeklyBulletinUrl() ||
        (globalThis.PhHtmlFingerprint?.scanPage?.(document)?.best?.bestDownloadUrl || "");
      if (inlinePdf && /\.pdf/i.test(inlinePdf)) {
        return {
          emoji: "📄",
          summary: "PDF Embedder — bulletin PDF is embedded on this page.",
          advice:
            "Tap the green Save bulletin PDF button below (one step). Then Send & test.",
          type: "pdfemb_embed",
          htmlFingerprint: "wordpress_pdfemb",
          autoDownloadUrl: inlinePdf,
        };
      }
      const count = Math.max(pdfembElsEarly.length, pdfembLinksEarly.length);
      const anchors = pdfembElsEarly.filter(
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
          "Tap 🔗 1. Follow a link, or 🔍 Find bulletin → 🎯 Pick newest bulletin, to record the right bulletin link.",
        type: "pdfemb",
        htmlFingerprint: "wordpress_pdfemb",
        links: anchors,
      };
    }

    // 1d. Full HTML fingerprint scan (CMS / plugin markers in page source)
    const fpDetect = _htmlFingerprintDetect();
    if (fpDetect) {
      const skipCloud = fpDetect.type === "cloud_folder" && !_isCloudFolderUrl(url);
      const skipImage =
        fpDetect.type === "image" &&
        (!_hasBulletinImageInContent(MIN_CONTENT_IMAGE_WIDTH) || _isWordPressHtmlBulletinPage());
      if (!skipCloud && !skipImage) {
        return fpDetect;
      }
    }

    // 1c2. mDocs PDF bulletin table (Portstewart etc.) — before HTML newsletter heuristics
    if (
      document.querySelector("table.mdocs, .mdocs-table, a.mdocs-download, a[href*='mdocs-file']")
    ) {
      return {
        emoji: "📥",
        summary: "mDocs PDF bulletin table — real downloadable PDF files.",
        advice:
          "Click Download on this week's row (usually top), then capture the PDF download. Do NOT use Save page as PDF.",
        type: "mdocs_bulletin_list",
        htmlFingerprint: "mdocs_bulletin_table",
      };
    }

    // 1c. WordPress HTML text newsletter (Clonleigh-style) before loose image heuristics
    if (_isWordPressHtmlBulletinPage()) {
      return {
        emoji: "📰",
        summary: "WordPress HTML newsletter — bulletin text is on this page.",
        advice: 'Click "Save page as PDF" — Sunday harvest prints this into the mega bulletin.',
        type: "wix_html",
        htmlFingerprint: "wordpress_html_post",
      };
    }

    // 1e. Parish Services / Parish Messenger embed (dmaparish, ardstraw, culdaff, etc.)
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

    const _unwrapViewerSrc = _unwrapGoogleViewerSrc;

    const onewebNewsletterFrames = iframes.filter((f) => {
      const resolved = _unwrapViewerSrc(f.getAttribute("src") || "");
      return (
        /onewebmedia/i.test(resolved) &&
        /newsletter/i.test(resolved) &&
        /\.docx/i.test(resolved)
      );
    });
    const autoNewsletterUrl = _pickBestOnewebNewsletterUrl();
    if (
      onewebNewsletterFrames.length > 0 &&
      (document.querySelector('script[src*="onewebstatic"]') ||
        /onewebstatic|one\.com/i.test(document.documentElement.innerHTML.slice(0, 8000)))
    ) {
      return {
        emoji: "📰",
        summary: `One.com bulletin — ${onewebNewsletterFrames.length} newsletter(s) found in page HTML (previews load slowly).`,
        advice: autoNewsletterUrl
          ? "Automatic — tap Save newsletter (auto) or Push. No need to wait for Google previews."
          : "Tap Bulletin in a frame → pick ✅ NEWSLETTER … docx (newest date).",
        type: "oneweb_docx",
        autoNewsletterUrl,
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
        advice: "Tap 📐 2. Bulletin in frame (under Extra) to choose the correct frame.",
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
          "Tap 📐 2. Bulletin in frame (under Extra). Background PDF detection also runs automatically as fallback.",
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

    // 5. Generic PDF / document links (incl. Banagher /Newsletters/ without .pdf suffix)
    const newsletterListLinks = _filterBulletinCandidates(
      Array.from(
        document.querySelectorAll('a[href*="/Newsletters/"], a[href*="/Weekly-Bulletins/"]')
      )
    );
    const pdfLinks = _filterBulletinCandidates(
      Array.from(document.querySelectorAll("a[href]")).filter((a) => {
        const href = (a.getAttribute("href") || "").toLowerCase();
        return (
          href.includes(".pdf") ||
          href.includes(".docx") ||
          href.includes("/wp-content/uploads/") ||
          /\/newsletters\/\d+\//i.test(href) ||
          /\/weekly-bulletins\/\d+\//i.test(href)
        );
      })
    );
    const combinedLinks = newsletterListLinks.length
      ? Array.from(new Set([...newsletterListLinks, ...pdfLinks]))
      : pdfLinks;
    if (combinedLinks.length > 0) {
      const bulletinLinks = combinedLinks.filter((a) => {
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
        summary: `Found ${combinedLinks.length} bulletin link(s)${
          bulletinLinks.length > 0
            ? ` (${bulletinLinks.length} look like weekly bulletins)`
            : ""
        }.`,
        advice:
          "Tap 🎯 Pick newest bulletin, or 🔗 Follow a link and confirm the newest row.",
        type: "pdf_links",
        links: bulletinLinks.length > 0 ? bulletinLinks : combinedLinks,
        bulletinLinks,
      };
    }

    // 5b. Three Patrons / Banagher-style weekly bulletin list (cloud auto-download)
    const pageHost = (() => {
      try {
        return new URL(window.location.href).hostname.toLowerCase();
      } catch (_e) {
        return "";
      }
    })();
    const bodyText = String(document.body?.innerText || "");
    const dropfilesWidget = document.querySelector(".mod_dropfiles_latest, .mod_dropfiles_list");
    const dropfilesDownloads = Array.from(document.querySelectorAll("a.mod_downloadlink[href]"));
    const weeklyBulletinLinks = Array.from(
      document.querySelectorAll('a[href*="Weekly-Bulletins"], a[href*="weekly-bulletins"], a[href*="/Newsletters/"]')
    );
    const hasWeeklySection =
      Boolean(dropfilesWidget) ||
      dropfilesDownloads.length > 0 ||
      /weekly\s+bulletins/i.test(bodyText) ||
      weeklyBulletinLinks.length > 0 ||
      /threepatrons\.org|banagherparish\.com/i.test(pageHost);
    if (hasWeeklySection && (dropfilesDownloads.length > 0 || /weekly\s+bulletin|sunday\s+\d/i.test(bodyText))) {
      return {
        emoji: "📥",
        summary: "Weekly bulletin list — Joomla Dropfiles cloud download.",
        advice:
          "Click the cloud ↓ (a.mod_downloadlink) on this Sunday's row. PDF downloads automatically — trainer records it. Then Push.",
        type: "weekly_bulletin_download",
        sitePlugin: dropfilesWidget ? "joomla_dropfiles" : "",
      };
    }

    // 6. Image bulletins — only when a large bulletin image is actually in the article body
    if (_hasBulletinImageInContent(400)) {
      const bulletinImages = Array.from(
        document.querySelectorAll(".entry-content img, .post-content img, article img")
      ).filter(
        (img) => isLikelyBulletinImage(img) && isLargeImage(img, 400)
      );
      return {
        emoji: "🖼️",
        summary:
          bulletinImages.length > 0
            ? `Found ${bulletinImages.length} bulletin image(s) in the article.`
            : "Found a large bulletin image on this page.",
        advice: "Extra → 🖼️ Pick an image on this page (not Save page as PDF).",
        type: "image",
      };
    }

    const allLinks = document.querySelectorAll("a[href],button");

    // HTML text bulletin — Wix sites with dated slug
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
      const htmlBulletinPage = _pathLooksLikeNewsletterPage();
      return {
        emoji: htmlBulletinPage ? "📰" : "📋",
        summary: htmlBulletinPage
          ? "HTML text bulletin — the newsletter text is on this page (not a PDF file)."
          : "HTML page — no PDF or document links detected.",
        advice: htmlBulletinPage
          ? 'Tap "Save page as PDF" — Sunday harvest prints this page into the mega bulletin.'
          : "Tap Save page as PDF if the bulletin is text on this page, or Follow a link to reach the PDF.",
        type: htmlBulletinPage ? "wix_html" : "html",
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

  const detectPageType = () => {
    const url = window.location.href;
    const now = Date.now();
    if (
      _pageTypeCache.url === url
      && _pageTypeCache.result
      && now - _pageTypeCache.at < 2500
    ) {
      return _pageTypeCache.result;
    }
    const result = _detectPageTypeImpl();
    _pageTypeCache = { url, at: now, result };
    return result;
  };

  const _invalidatePageTypeCache = () => {
    _pageTypeCache = { url: "", at: 0, result: null };
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
    if (_inStandaloneMode() && (type === "mark_file" || type === "download")) {
      standaloneAddStep(
        { action: "download", url: window.location.href },
        type,
        label
      );
      return;
    }
    if (_inStandaloneMode() && type === "click") {
      return;
    }
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
      empty.textContent = lastPushedRecipeNote || "No steps recorded yet — tap Step 2 Save on a PDF page, or Step 1 on a news page.";
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
    if (downloadUrl && _isPdfOrDocUrl(downloadUrl)) {
      standaloneAddStep(
        { action: "download", url: downloadUrl, use_captured_url: true },
        "mark_file",
        `📄 Download: ${downloadUrl.slice(-50)}`
      );
    }
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
      const path = new URL(_pageUrlForParishDetection()).pathname || "";
      if (/\/(news|newsletter|bulletin|parishnews|nuacht|notice|board)(\/|$|\.)/i.test(path)) {
        return true;
      }
      if (/notice[\s_-]*board/i.test(path)) return true;
      if (/\/\d{4}\/\d{2}\/\d{2}\//i.test(path) && /newsletter|bulletin|pastoral/i.test(path)) {
        return true;
      }
      return /newsletter|bulletin|pastoral-area|notice.?board/i.test(path);
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
    if (_inStandaloneMode()) {
      const pageHref = String(window.location.href || "").trim();
      const onPdfPage = _isPdfOrDocUrl(pageHref) || _pageIsNativePdfViewer();
      standaloneAddStep(
        onPdfPage
          ? { action: "download", url: pageHref, use_captured_url: true }
          : { action: "download", url, use_captured_url: true },
        "mark_file",
        onPdfPage ? "📄 Save PDF from this page" : `📄 File: ${url.slice(-50)}`
      );
      if (showStatus) showStatus("✅ Bulletin saved — scroll down to Send & test.", "ok");
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
            isBulletin = !_isNonBulletinPdf(resolvedUrl, "");
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
    }
    if (_inStandaloneMode()) {
      // Build a real, replayable crop_screenshot step so Send & test works.
      // Previously this only added a UI row that could never be pushed.
      const toSection = (s) => {
        const out = {
          x: Math.round(Number(s.x) || 0),
          y: Math.round(Number(s.y) || 0),
          page_x: Math.round(Number(s.pageX != null ? s.pageX : s.x) || 0),
          page_y: Math.round(Number(s.pageY != null ? s.pageY : s.y) || 0),
          width: Math.round(Number(s.width) || 0),
          height: Math.round(Number(s.height) || 0),
        };
        if (s.element_selector) out.element_selector = s.element_selector;
        return out;
      };
      const cropStep = { action: "crop_screenshot", ...toSection(payload) };
      if (Array.isArray(payload.sections) && payload.sections.length > 1) {
        cropStep.sections = payload.sections.map(toSection);
      }
      standaloneAddStep(
        cropStep,
        "crop_screenshot",
        `✂️ Crop bulletin (${cropStep.width}×${cropStep.height})`
      );
    } else {
      if (!window.ph_mark_crop) {
        console.warn("Parish Trainer: ph_mark_crop binding is unavailable.");
      }
      addSessionStep("crop", "✂️ Crop recorded");
    }
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

  // ── createMinimalToolbar (fallback when full UI fails) ────────────────────

  const createMinimalToolbar = () => {
    const bar = document.createElement("div");
    bar.id = TOOLBAR_ID;
    bar.dataset.phMinimal = "1";
    bar.style.cssText = [
      "position:fixed",
      "top:12px",
      "right:12px",
      "z-index:2147483647",
      "display:flex",
      "flex-direction:column",
      "gap:8px",
      "min-width:300px",
      "max-width:380px",
      "padding:10px",
      "border-radius:10px",
      "background:#111827",
      "color:#f9fafb",
      "border:2px solid #16a34a",
      "box-shadow:0 12px 40px rgba(0,0,0,.55)",
      "font:12px/1.4 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif",
      "pointer-events:auto",
      "max-height:calc(100vh - 24px)",
      "overflow:auto",
    ].join(";");

    const title = document.createElement("div");
    title.style.fontWeight = "700";
    title.textContent = "Parish bulletin fixer (simplified)";
    bar.appendChild(title);

    let pageSummary = "Scanning page…";
    try {
      const ctx = detectPageType();
      pageSummary = `${ctx.emoji || "📋"} ${ctx.summary || ctx.type || "unknown page"}`;
    } catch (err) {
      pageSummary = `Page scan failed: ${err}`;
    }
    const hint = document.createElement("div");
    hint.style.cssText = "font-size:11px;color:#cbd5e1;";
    hint.textContent = pageSummary;
    bar.appendChild(hint);

    const status = document.createElement("div");
    status.style.cssText = "font-size:10px;color:#86efac;min-height:14px;";
    const showMiniStatus = (msg, isErr = false) => {
      status.textContent = msg;
      status.style.color = isErr ? "#fca5a5" : "#86efac";
    };
    bar.appendChild(status);

    const mkBtn = (label, bg, onClick) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      btn.style.cssText = [
        "border:none",
        "border-radius:6px",
        "padding:8px 10px",
        "background:" + bg,
        "color:#fff",
        "cursor:pointer",
        "font-size:11px",
        "text-align:left",
        "font-family:inherit",
      ].join(";");
      btn.addEventListener("click", onClick);
      return btn;
    };

    bar.appendChild(
      mkBtn("👉 Step 1: Point at bulletin link", "#16a34a", () => {
        startPickLinkMode(
          (el) => {
            const selector = buildStableLinkSelector(el);
            const href = el.getAttribute("href") || "";
            const text = (el.innerText || el.textContent || "").trim().slice(0, 80);
            standaloneAddStep(
              { action: "click", selector, href, text },
              "click",
              `🔗 Click: "${text || selector}"`
            );
            showMiniStatus(`✅ Click recorded (${_standaloneRecipeSteps().length} steps)`);
          },
          showMiniStatus
        );
      })
    );

    bar.appendChild(
      mkBtn("💾 Step 2: Save bulletin PDF", "#2563eb", () => {
        const url = window.location.href;
        const ctx = detectPageType();
        if (ctx.type === "direct_pdf" || /\.pdf(\?|#|$)/i.test(url)) {
          standaloneAddStep({ action: "download", url }, "mark_file", `📄 ${url.slice(-50)}`);
          showMiniStatus("✅ PDF URL saved");
          return;
        }
        if (ctx.type === "wix_html" || ctx.type === "html") {
          standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
          showMiniStatus("✅ Save page as PDF recorded");
          return;
        }
        showMiniStatus("Point at the bulletin link first, or open the PDF page", true);
      })
    );

    bar.appendChild(
      mkBtn("📰 Save page as PDF (HTML bulletin)", "#7c3aed", () => {
        standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
        showMiniStatus("✅ HTML → PDF step recorded");
      })
    );

    const stepsEl = document.createElement("div");
    stepsEl.style.cssText = "font-size:10px;color:#9ca3af;";
    const refreshSteps = () => {
      const n = _standaloneRecipeSteps().length;
      stepsEl.textContent = n ? `${n} step(s) recorded — open extension popup to Send & test` : "No steps yet";
    };
    refreshSteps();
    bar.appendChild(stepsEl);
    window.addEventListener("ph-recording-continued", refreshSteps);

    if (globalThis.ph_toolbar_diag?.attachPanel) {
      globalThis.ph_toolbar_diag.attachPanel(bar, { open: true, autoRun: true });
    }

    const closeBtn = mkBtn("✕ Hide", "#374151", () => {
      _dismissToolbar(true);
    });
    bar.appendChild(closeBtn);

    return bar;
  };

  globalThis.__phCreateMinimalToolbar = createMinimalToolbar;

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
    title.textContent = "⠿ Parish bulletin fixer";
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
      _dismissToolbar(true);
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

    const playbookPanel = document.createElement("div");
    playbookPanel.id = "ph-playbook-panel";
    playbookPanel.style.cssText = [
      "background:#0f172a",
      "border:1px solid #334155",
      "border-radius:8px",
      "padding:6px 8px",
      "margin-bottom:6px",
    ].join(";");

    const journeyStepBar = document.createElement("div");
    journeyStepBar.id = "ph-journey-bar";

    const wizardQ = document.createElement("div");
    wizardQ.style.cssText = "display:none;font-size:11px;font-weight:600;margin-bottom:6px;color:#93c5fd;";

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
    compactPageHint.style.cssText = "display:none;font-size:10px;color:#9ca3af;line-height:1.4;margin-bottom:6px;";

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
    moreOptionsSummary.textContent = "Other options (auto-guess link, image, frame…)";
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
    stuckLink.style.display = "none";
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
    let pageLoadTimerLine = null;

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
      const savedLoadTimer = pageLoadTimerLine;
      const savedIdentify = identifyResult;
      _clearElement(guidedPanel);
      if (savedPattern) guidedPanel.appendChild(savedPattern);
      if (savedParish) guidedPanel.appendChild(savedParish);
      if (savedLoadTimer) guidedPanel.appendChild(savedLoadTimer);
      guidedPanel.appendChild(journeyStepBar);
      guidedPanel.appendChild(playbookPanel);
      guidedPanel.appendChild(nextStepBanner);
      guidedPanel.appendChild(wizardQ);
      guidedPanel.appendChild(compactPageHint);
      guidedPanel.appendChild(wizardBtns);
      guidedPanel.appendChild(moreOptionsSection);
      if (savedIdentify) guidedPanel.appendChild(savedIdentify);
      guidedPanel.appendChild(stuckLink);
      _refreshGuidedContext();
    };

    const _pdfTerminalActions = new Set(["download", "image", "image_stack", "print_to_pdf", "crop_screenshot"]);

    const _isHarvestClickTerminal = (step) => {
      if (!step || String(step.action || "").toLowerCase() !== "click") return false;
      const blob = `${step.selector || ""} ${step.href || ""}`;
      return /mod_downloadlink|mdocs-file|mdocs-download|table\.mdocs/i.test(blob);
    };

    const _ensureTerminalPdfStep = () => {
      const recorded = _standaloneRecipeSteps();
      const last = recorded[recorded.length - 1];
      if (last && _isHarvestClickTerminal(last)) {
        return { ok: true, added: false, clickOnly: true };
      }
      if (last && _pdfTerminalActions.has(String(last.action || "").toLowerCase())) {
        return { ok: true, added: false };
      }
      const pageUrl = window.location.href;
      const pageCtx = detectPageType();
      if (
        pageCtx.type === "direct_pdf" ||
        _urlLooksLikeDirectPdf(pageUrl) ||
        _pageIsNativePdfViewer()
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
      if (pageCtx.type === "oneweb_docx" && pageCtx.autoNewsletterUrl) {
        standaloneAddStep(
          {
            action: "download",
            url: pageCtx.autoNewsletterUrl,
            url_pattern: "*newsletter*.docx",
          },
          "mark_file",
          `📄 Newsletter: ${pageCtx.autoNewsletterUrl.split("/").pop()}`
        );
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "download" };
      }
      if (
        pageCtx.autoDownloadUrl &&
        (pageCtx.type === "pdfemb_embed" ||
          pageCtx.type === "google_drive_static" ||
          pageCtx.type === "weekly_bulletin_download" ||
          pageCtx.type === "mdocs_bulletin_list" ||
          pageCtx.htmlFingerprint === "joomla_dropfiles_weekly" ||
          pageCtx.htmlFingerprint === "mdocs_bulletin_table" ||
          pageCtx.htmlFingerprint === "sequential_weekly_bulletins" ||
          pageCtx.htmlFingerprint === "wordpress_pdfemb")
      ) {
        standaloneAddStep(
          {
            action: "download",
            url: pageCtx.autoDownloadUrl,
            use_captured_url: true,
            url_pattern: pageCtx.type === "mdocs_bulletin_list" ? "*.pdf" : undefined,
          },
          "mark_file",
          `📄 Download: ${pageCtx.autoDownloadUrl.slice(-50)}`
        );
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "download" };
      }
      if (pageCtx.type === "weekly_bulletin_download") {
        const bulletinUrl = _pickBestWeeklyBulletinUrl();
        if (bulletinUrl) {
          standaloneAddStep(
            { action: "download", url: bulletinUrl, use_captured_url: true },
            "mark_file",
            `📄 Download: ${bulletinUrl.slice(-50)}`
          );
          if (_stepsListEl) _renderSessionSteps();
          if (_refreshRecipeCount) _refreshRecipeCount();
          void _persistRecordingSession();
          _refreshGuidedContext();
          return { ok: true, added: true, action: "download" };
        }
      }
      if (
        pageCtx.type === "mdocs_bulletin_list" ||
        pageCtx.htmlFingerprint === "mdocs_bulletin_table" ||
        /mdocs-file|table\.mdocs/i.test(document.documentElement.innerHTML.slice(0, 80000))
      ) {
        const mdocsUrl = pageCtx.autoDownloadUrl || "";
        if (mdocsUrl && !_isNonBulletinPdf(mdocsUrl, "")) {
          standaloneAddStep(
            { action: "download", url: mdocsUrl, use_captured_url: true, url_pattern: "*.pdf" },
            "mark_file",
            `📄 mDocs PDF: ${mdocsUrl.slice(-50)}`
          );
        } else {
          standaloneAddStep(
            { action: "download", use_captured_url: true, url_pattern: "*.pdf" },
            "mark_file",
            "📄 mDocs PDF download (newest row)"
          );
        }
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "download" };
      }
      if (
        pageCtx.type === "pdfemb" ||
        pageCtx.type === "pdfemb_embed" ||
        pageCtx.htmlFingerprint === "wordpress_pdfemb" ||
        pageCtx.htmlFingerprint === "wp_pdfemb_list"
      ) {
        if (pageCtx.autoDownloadUrl) {
          standaloneAddStep(
            {
              action: "download",
              url: pageCtx.autoDownloadUrl,
              use_captured_url: true,
              url_pattern: "*.pdf",
            },
            "mark_file",
            `📄 PDF Embedder: ${pageCtx.autoDownloadUrl.slice(-50)}`
          );
        } else {
          standaloneAddStep(
            { action: "download", url_pattern: "*.pdf" },
            "mark_file",
            "📄 PDF Embedder — newest bulletin PDF"
          );
        }
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "download" };
      }
      if (
        pageCtx.type === "wp_block_file_bulletin" ||
        pageCtx.htmlFingerprint === "wp_block_file_bulletin"
      ) {
        const embedUrl = pageCtx.autoDownloadUrl || "";
        standaloneAddStep(
          embedUrl
            ? { action: "download", url: embedUrl, url_pattern: "*bulletin*.pdf" }
            : { action: "download", url_pattern: "*bulletin*.pdf" },
          "mark_file",
          "📄 Bulletin PDF from wp-block-file embed"
        );
        if (_stepsListEl) _renderSessionSteps();
        if (_refreshRecipeCount) _refreshRecipeCount();
        void _persistRecordingSession();
        _refreshGuidedContext();
        return { ok: true, added: true, action: "download" };
      }
      const fallbackBulletinUrl = _pickBestWeeklyBulletinUrl();
      if (fallbackBulletinUrl) {
        standaloneAddStep(
          { action: "download", url: fallbackBulletinUrl },
          "mark_file",
          `📄 Download: ${fallbackBulletinUrl.slice(-50)}`
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
      try {
      const stepCount = _standaloneRecipeSteps().length;
      const pageCtx = detectPageType();
      compactPageHint.textContent = pageCtx.summary || "";
      compactPageHint.style.display = pageCtx.summary ? "block" : "none";

      const onDirectPdf = pageCtx.type === "direct_pdf";
      const wpBlockPage = _isWpBlockBulletinPage(pageCtx);
      const pdfLinkListPage =
        pageCtx.type === "pdf_links" ||
        pageCtx.type === "parish_messenger" ||
        pageCtx.type === "pdfemb";
      if (clickFirstBtn) {
        clickFirstBtn.style.display =
          onDirectPdf || (wpBlockPage && stepCount === 0) || pdfLinkListPage
            ? "none"
            : "block";
      }

      if (wpBlockPage && stepCount === 0 && !onDirectPdf) {
        wizardQ.textContent =
          pageCtx.type === "google_drive_static"
            ? "Google Drive permanent bulletin"
            : "Bulletin PDF is already on this page";
        nextStepBanner.style.display = "block";
        nextStepBanner.textContent =
          pageCtx.type === "google_drive_static"
            ? "👇 Train on this Drive preview page — tap Save Drive bulletin, then Send & test. Do not open the instant-download link."
            : "👇 Tap the green Save bulletin PDF button below (one step). Then Send & test.";
        if (moreOptionsSection) moreOptionsSection.style.display = "";
      } else if (onDirectPdf) {
        const recorded = _standaloneRecipeSteps();
        const hasTerminal = recorded.some((s) =>
          _pdfTerminalActions.has(String(s?.action || "").toLowerCase())
        );
        nextStepBanner.style.display = "block";
        nextStepBanner.textContent = hasTerminal
          ? "✅ Bulletin saved — scroll down and tap Send & test."
          : "👇 Tap the green Save button, then Send & test.";
        wizardQ.textContent = "You are on the bulletin PDF";
        if (contextPrimaryBtn) {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent = "💾 Step 2: Save this PDF";
        }
        if (moreOptionsSection) moreOptionsSection.style.display = "none";
        if (stuckLink) stuckLink.style.display = "none";
      } else if (stepCount > 0) {
        if (contextPrimaryBtn) contextPrimaryBtn.style.background = "#2563eb";
        if (moreOptionsSection) moreOptionsSection.style.display = "";
        if (stuckLink) stuckLink.style.display = "none";
        nextStepBanner.style.display = "block";
        nextStepBanner.textContent =
          `✅ ${stepCount} step${stepCount === 1 ? "" : "s"} saved. ` +
          "Need another menu click? Use Step 1 again. Otherwise save the bulletin, then Send & test.";
        wizardQ.textContent = `Step ${stepCount + 1}`;
      } else {
        if (moreOptionsSection) moreOptionsSection.style.display = "";
        if (stuckLink) stuckLink.style.display = "none";
        nextStepBanner.style.display = "none";
        wizardQ.textContent = "Step 1";
      }

      if (contextPrimaryBtn) {
        const showContext =
          pageCtx.type === "direct_pdf" ||
          pageCtx.type === "oneweb_docx" ||
          pageCtx.type === "weekly_bulletin_download" ||
          pageCtx.type === "mdocs_bulletin_list" ||
          pageCtx.type === "iframe" ||
          pageCtx.type === "iframe_maybe" ||
          pageCtx.type === "wix_viewer" ||
          pageCtx.type === "wix_html" ||
          pageCtx.type === "parish_messenger" ||
          pageCtx.type === "cloud_folder" ||
          (pageCtx.type === "html" && _pathLooksLikeNewsletterPage()) ||
          pageCtx.type === "pdf_links" ||
          wpBlockPage;
        if (pageCtx.type === "direct_pdf") {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent = "💾 Step 2: Save this PDF";
        } else if (pageCtx.type === "oneweb_docx") {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent = pageCtx.autoNewsletterUrl
            ? "💾 Step 2: Save newsletter"
            : "📐 Step 2: Bulletin in a frame";
        } else if (pageCtx.type === "weekly_bulletin_download") {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#2563eb";
          contextPrimaryBtn.textContent = "📥 Step 2: Download this week's row";
        } else if (pageCtx.type === "mdocs_bulletin_list") {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent = "📥 Step 1: Download bulletin PDF";
        } else if (wpBlockPage) {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent =
            pageCtx.type === "google_drive_static"
              ? stepCount > 0
                ? "📁 Re-save Drive bulletin download"
                : "📁 Step 1: Save Drive bulletin (static URL)"
              : stepCount > 0
                ? "📄 Re-save bulletin PDF (from embed)"
                : "📄 Step 1: Save bulletin PDF (from embed)";
        } else if (pageCtx.type === "wix_html" || (pageCtx.type === "html" && _pathLooksLikeNewsletterPage())) {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.textContent = "💾 Step 2: Save page as PDF";
        } else if (pageCtx.type === "parish_messenger" || pageCtx.type === "pdf_links" || pageCtx.type === "pdfemb") {
          const linkCount = (pageCtx.links || pageCtx.bulletinLinks || []).length;
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.style.background = "#16a34a";
          contextPrimaryBtn.textContent = linkCount
            ? `🎯 Pick newest bulletin (${linkCount} links)`
            : "🎯 Pick newest bulletin";
        } else if (pageCtx.type === "cloud_folder") {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.textContent = "📅 Step 1: Pick this Sunday's row";
        } else if (
          pageCtx.type === "iframe" ||
          pageCtx.type === "iframe_maybe" ||
          pageCtx.type === "wix_viewer"
        ) {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.textContent = "📐 Step 2: Bulletin in a frame";
        } else if (pageCtx.type === "image") {
          contextPrimaryBtn.style.display = "block";
          contextPrimaryBtn.textContent = "🖼️ Step 2: Point at bulletin image";
        } else {
          contextPrimaryBtn.style.display = showContext ? "block" : "none";
        }
      }

      const htmlCapturePage =
        pageCtx.type === "wix_html" ||
        (pageCtx.type === "html" && _pathLooksLikeNewsletterPage());
      const mdocsPdfPage = pageCtx.type === "mdocs_bulletin_list";
      // Sort the wheat from the chaff: when the site type is a confident
      // "link/file → PDF" flow, hide the HTML-text and image buttons so the
      // user only sees the one action that fits this page.
      const pdfFlowType =
        onDirectPdf ||
        wpBlockPage ||
        mdocsPdfPage ||
        pageCtx.type === "pdfemb" ||
        pageCtx.type === "pdf_links" ||
        pageCtx.type === "parish_messenger" ||
        pageCtx.type === "cloud_folder" ||
        pageCtx.type === "weekly_bulletin_download" ||
        pageCtx.type === "oneweb_docx" ||
        pageCtx.type === "iframe" ||
        pageCtx.type === "iframe_maybe" ||
        pageCtx.type === "wix_viewer";
      if (savePagePdfBtn) {
        savePagePdfBtn.style.display =
          pdfFlowType || (htmlCapturePage && stepCount === 0) ? "none" : "block";
      }
      if (pickImageBtn) {
        pickImageBtn.style.display = pdfFlowType ? "none" : "block";
        pickImageBtn.style.background = pageCtx.type === "image" ? "#16a34a" : "#2563eb";
      }
      if (imageCropBtn) {
        imageCropBtn.style.display = pdfFlowType ? "none" : "block";
      }
      if (getPdfBtn) {
        getPdfBtn.style.display = wpBlockPage || mdocsPdfPage ? "none" : "block";
      }

      if (playbookPanel && window.ph_playbook?.render) {
        const recorded = _standaloneRecipeSteps();
        const hasTerminal = recorded.some((s) =>
          _pdfTerminalActions.has(String(s?.action || "").toLowerCase())
        );
        const planState = {
          stepCount: recorded.length,
          hasTerminal,
          lastHarvestIssue: _lastHarvestIssue,
          needsRetrain: _needsRetrain,
          expectedCloudLabel: pageCtx.expectedLabel || "",
          cloudRowVisible: pageCtx.rowVisible,
          fixNow: Boolean(bar.dataset.phFixNow),
          parishName: bar.dataset.phParishName || "",
        };
        window.ph_playbook.render(playbookPanel, pageCtx, planState);
        if (window.ph_playbook.renderJourneyBar) {
          const plan = window.ph_playbook.getPlan(pageCtx, planState);
          window.ph_playbook.renderJourneyBar(journeyStepBar, plan.journeyStep);
        }
        const mem = window.ph_site_memory?.getForPageType?.(pageCtx.type, null, pageCtx);
        if (mem && playbookPanel.nextSibling?.dataset?.phMemory !== "1") {
          let memoryEl = playbookPanel.querySelector("[data-ph-memory='1']");
          if (!memoryEl) {
            memoryEl = document.createElement("div");
            memoryEl.dataset.phMemory = "1";
            memoryEl.style.cssText =
              "font-size:9px;color:#a5b4fc;line-height:1.45;background:#1e1b4b;border:1px solid #4338ca;border-radius:6px;padding:6px 8px;margin-top:6px;white-space:pre-wrap;";
            playbookPanel.appendChild(memoryEl);
          }
          memoryEl.textContent = window.ph_site_memory.formatHintBlock(mem);
        }
      }
      if (pinLinkBtn) {
        pinLinkBtn.style.display = "none";
      }
      } catch (guidedErr) {
        console.error("[Parish Trainer] guided context refresh failed:", guidedErr);
        if (globalThis.ph_toolbar_diag?.setError) {
          globalThis.ph_toolbar_diag.setError(`Guided panel: ${guidedErr}`);
        }
      }
    };

    let _guidedContextTimer = null;
    const _scheduleRefreshGuidedContext = () => {
      if (_guidedContextTimer) return;
      _guidedContextTimer = setTimeout(() => {
        _guidedContextTimer = null;
        _refreshGuidedContext();
      }, 200);
    };

    // Show a confirmation step after a link is picked
    const _scoreBulletinLinkElements = (linkElements) => {
      const scored = (linkElements || []).map((el, idx) => {
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
      const hasAnyDate = pool.some((c) => c.hasDate);
      const ambiguous =
        !hasAnyDate || (pool.length > 1 && pool[0].dateScore === pool[1].dateScore);
      return { pool, ambiguous, hasAnyDate };
    };

    const _recordBulletinListPick = (selectedEl, { openAfter = false } = {}) => {
      const selector = buildStableLinkSelector(selectedEl);
      const href =
        _hrefFromBulletinClick(selectedEl) ||
        selectedEl.getAttribute("href") ||
        "";
      const text = _getEnrichedLinkLabel(selectedEl).slice(0, 60);
      const clickLabel = `🔗 Newest bulletin: "${text || selector}"`;
      const clickStep = _enrichClickStepForWeeklyReplay(
        { action: "click", selector, href, text },
        selectedEl
      );
      const autoHarvestDownload =
        Boolean(clickStep.pick_strategy) ||
        _looksLikeBulletinDownloadUrl(href, text);

      if (!openAfter && autoHarvestDownload) {
        standaloneAddStep(clickStep, "click", clickLabel);
        void _persistRecordingSession();
        _notifyRecordingTabActive();
        showStatus(
          "✅ Newest bulletin recorded — harvest picks the latest link and downloads it each Sunday. Tap Send & test.",
          "ok"
        );
        resetGuidedPanel();
        return true;
      }

      standaloneAddStep(clickStep, "click", clickLabel);
      void _persistRecordingSession();
      if (!openAfter) {
        showStatus(`✅ Click step recorded: "${text || selector}"`, "ok");
        resetGuidedPanel();
        return true;
      }
      return false;
    };

    const showBulletinPickConfirm = (selectedEl) => {
      const selector = buildStableLinkSelector(selectedEl);
      const href = selectedEl.getAttribute("href") || "";
      const text = _getEnrichedLinkLabel(selectedEl).slice(0, 80);
      const displayDate = getDisplayDate(href, text);

      _clearElement(guidedPanel);
      if (patternHintWrap) guidedPanel.appendChild(patternHintWrap);
      if (parishRecordingLine) guidedPanel.appendChild(parishRecordingLine);
      if (pageLoadTimerLine) guidedPanel.appendChild(pageLoadTimerLine);

      const confirmQ = document.createElement("div");
      confirmQ.style.cssText = "font-weight:700;color:#93c5fd;margin-bottom:6px;font-size:12px;";
      confirmQ.textContent = "Is this this week's bulletin?";
      guidedPanel.appendChild(confirmQ);

      const preview = document.createElement("div");
      preview.style.cssText =
        "font-size:10px;color:#e2e8f0;line-height:1.45;background:#0f172a;border-radius:4px;padding:8px;margin-bottom:8px;border:1px solid #334155;";
      const dateLine = displayDate
        ? `<div style="color:#fbbf24;font-weight:600;margin-bottom:4px;">📅 ${displayDate}</div>`
        : "";
      preview.innerHTML =
        `${dateLine}<div style="font-weight:600;margin-bottom:4px;">${text || "(link text)"}</div>` +
        `<div style="color:#9ca3af;font-size:9px;word-break:break-all;">${(href || "").slice(0, 120)}</div>` +
        `<div style="color:#6b7280;font-size:9px;margin-top:6px;">Each Sunday the harvester picks the <strong>newest</strong> matching link on this page — not this exact filename.</div>`;
      guidedPanel.appendChild(preview);

      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;flex-direction:column;gap:6px;";

      const yesBtn = makeSmallBtn(
        "✅ Yes — save this pick",
        "#16a34a",
        () => {
          if (_recordBulletinListPick(selectedEl, { openAfter: false })) return;
          showStatus("✅ Bulletin pick saved — tap Send & test when ready.", "ok");
          resetGuidedPanel();
        },
        "Save this as the bulletin link for Sunday harvest"
      );
      yesBtn.style.width = "100%";
      yesBtn.style.padding = "8px 10px";
      yesBtn.style.fontSize = "11px";

      const wrongBtn = makeSmallBtn(
        "❌ Wrong — let me point at the right link",
        "#b91c1c",
        () => {
          resetGuidedPanel();
          startPickLinkMode(showBulletinPickConfirm, showStatus);
          showStatus("Click the correct bulletin link on the page.", "info");
        },
        "Use crosshair to pick a different row"
      );
      wrongBtn.style.width = "100%";
      wrongBtn.style.padding = "8px 10px";
      wrongBtn.style.fontSize = "11px";

      const pickListBtn = makeSmallBtn(
        "📋 Show other candidates",
        "#374151",
        () => {
          const result = detectPageType();
          const pickableLinks = result.links || result.bulletinLinks || [];
          const { pool, hasAnyDate } = _scoreBulletinLinkElements(pickableLinks);
          if (pool.length > 1) {
            showPickMultipleChoice(pool.slice(0, 5), hasAnyDate);
          } else {
            startPickLinkMode(showBulletinPickConfirm, showStatus);
          }
        },
        "See up to 5 newest links if the auto-pick looks wrong"
      );
      pickListBtn.style.width = "100%";
      pickListBtn.style.fontSize = "9px";

      btnRow.appendChild(yesBtn);
      btnRow.appendChild(wrongBtn);
      btnRow.appendChild(pickListBtn);
      guidedPanel.appendChild(btnRow);

      if (selectedEl instanceof Element) {
        const prevOutline = selectedEl.style.outline;
        selectedEl.style.outline = "3px solid #f59e0b";
        selectedEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        setTimeout(() => {
          if (selectedEl.style.outline === "3px solid #f59e0b") {
            selectedEl.style.outline = prevOutline;
          }
        }, 4000);
      }
    };

    const _runPickNewestBulletin = () => {
      const result = detectPageType();
      const pickableLinks = result.links || result.bulletinLinks || [];
      if (!pickableLinks.length) {
        showStatus("❌ No bulletin links found — use Other options → point at a specific link.", "error");
        startPickLinkMode(showBulletinPickConfirm, showStatus);
        return;
      }
      const { pool, ambiguous, hasAnyDate } = _scoreBulletinLinkElements(pickableLinks);
      if (!pool.length) {
        showStatus("❌ Could not score bulletin links on this page.", "error");
        return;
      }
      if (ambiguous && pool.length > 1) {
        showPickMultipleChoice(pool.slice(0, 5), hasAnyDate);
        return;
      }
      showBulletinPickConfirm(pool[0].el);
    };

    const showPickConfirmation = (selectedEl) => {
      const selector = buildStableLinkSelector(selectedEl);
      const href = selectedEl.getAttribute("href") || "";
      const text = _getEnrichedLinkLabel(selectedEl).slice(0, 60);
      const clickLabel = `🔗 Click: "${text || selector}"`;
      const clickStep = _enrichClickStepForWeeklyReplay(
        {
          action: "click",
          selector,
          href,
          text,
        },
        selectedEl
      );
      const cloudFmt = _detectCloudDateFormat(text);
      if (cloudFmt || _isCloudFolderUrl(window.location.href)) {
        clickStep.date_format = cloudFmt || "YY.MM.DD";
        clickStep.cloud_folder = true;
      }

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
      if (pageLoadTimerLine) guidedPanel.appendChild(pageLoadTimerLine);

      const confirmQ = document.createElement("div");
      confirmQ.style.cssText = "font-weight:600;color:#93c5fd;margin-bottom:6px;font-size:11px;";
      confirmQ.textContent = "Step 2 — Is this the bulletin? Tap green if yes.";
      guidedPanel.appendChild(confirmQ);

      const plainPick = document.createElement("div");
      plainPick.style.cssText =
        "font-size:10px;color:#e2e8f0;line-height:1.45;background:#0f172a;border-radius:4px;padding:6px 8px;margin-bottom:6px;";
      const linkText = (selectedEl.innerText || selectedEl.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80);
      const strategy = clickStep.pick_strategy || "newest_dated";
      const position = clickStep.bulletin_position || "top";
      const weeklyLine =
        strategy === "newest_dated"
          ? `Each Sunday the harvester picks the <strong>newest dated</strong> bulletin PDF on this page (usually near the <strong>${position}</strong>).`
          : strategy === "last_match"
            ? "Each Sunday the harvester clicks the <strong>last</strong> matching bulletin link on the page."
            : `Each Sunday the harvester clicks the <strong>first</strong> matching bulletin link (near the ${position}).`;
      plainPick.innerHTML =
        `${weeklyLine}<br><span style="color:#9ca3af;font-size:9px;">You picked: ${linkText || "this link"}. The filename/date changes every week — that is normal.</span>`;
      guidedPanel.appendChild(plainPick);

      const techDetails = document.createElement("details");
      techDetails.style.cssText = "margin-bottom:6px;font-size:9px;color:#6b7280;";
      const techSummary = document.createElement("summary");
      techSummary.textContent = "Technical details";
      techSummary.style.cursor = "pointer";
      techDetails.appendChild(techSummary);
      const preview = document.createElement("div");
      preview.style.cssText = "margin-top:4px;word-break:break-all;line-height:1.4;";

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
      techDetails.appendChild(preview);
      guidedPanel.appendChild(techDetails);

      if (window.ph_playbook?.renderJourneyBar) {
        window.ph_playbook.renderJourneyBar(journeyStepBar, 2);
      }

      const btnRow = document.createElement("div");
      btnRow.style.cssText = "display:flex;gap:5px;flex-wrap:wrap;flex-direction:column;";

      const _recordClickAndMaybeOpen = async (openLink) => {
        let absUrl = _hrefFromBulletinClick(selectedEl) || "";
        if (!absUrl) {
          const rawHref = selectedEl.getAttribute("href") || "";
          if (rawHref) {
            try {
              absUrl = new URL(rawHref, window.location.href).href;
            } catch (_e) {
              showStatus("❌ Could not read that link.", "error");
              return;
            }
          }
        }

        const useDownloadOnly =
          openLink === "download" &&
          absUrl &&
          _looksLikeBulletinDownloadUrl(absUrl, text) &&
          !_prefersClickByTextLink(text);

        if (useDownloadOnly) {
          stopPickLinkMode();
          if (!_recordStandaloneClick()) {
            showStatus("❌ Could not record click.", "error");
            return;
          }
          standaloneAddStep(
            { action: "download", url: absUrl, use_captured_url: true },
            "mark_file",
            `📄 Download: ${absUrl.slice(-50)}`
          );
          await _flushRecordingSession();
          _notifyRecordingTabActive();
          showStatus("✅ Click saved — opening bulletin. Tap Save this PDF on the PDF page.", "ok");
          if (absUrl) await _navigateRecordingToUrl(absUrl, selectedEl, showStatus);
          else resetGuidedPanel();
          return;
        }

        if (_inStandaloneMode()) {
          if (!_recordStandaloneClick()) {
            showStatus("❌ Could not record click.", "error");
            return;
          }
        } else if (window.ph_record_click) {
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

        if (openLink === "stay") {
          await _flushRecordingSession();
          showStatus(`✅ Click step recorded: "${text || selector}"`);
          resetGuidedPanel();
          return;
        }

        if (!absUrl) {
          showStatus("❌ This link has no URL to open.", "error");
          resetGuidedPanel();
          return;
        }
        stopPickLinkMode();
        await _navigateRecordingToUrl(absUrl, selectedEl, showStatus);
      };

      const yesOpenBtn = makeSmallBtn(
        "✅ Yes — that's the bulletin (open it)",
        "#374151",
        () => {
          void _recordClickAndMaybeOpen("open");
        },
        "Opens the link — only if you need to check the PDF in the browser"
      );
      yesOpenBtn.style.width = "100%";
      yesOpenBtn.style.fontSize = "10px";
      yesOpenBtn.style.padding = "6px 10px";

      const recordOnlyBtn = makeSmallBtn(
        "✅ Record this bulletin — done (recommended)",
        "#16a34a",
        () => {
          if (_recordBulletinListPick(selectedEl, { openAfter: false })) return;
          void _recordClickAndMaybeOpen("stay");
        },
        "Harvest picks the newest link and downloads each Sunday — no need to open the PDF"
      );
      recordOnlyBtn.style.width = "100%";
      recordOnlyBtn.style.fontSize = "11px";
      recordOnlyBtn.style.padding = "8px 10px";

      const stayBtn = makeSmallBtn(
        "Stay on this page (menu / no navigation)",
        "#374151",
        () => {
          void _recordClickAndMaybeOpen("stay");
        },
        "Only record the click — use for dropdown menus"
      );
      stayBtn.style.width = "100%";
      stayBtn.style.fontSize = "9px";

      const pickAgainBtn = makeSmallBtn(
        "🔄 Pick a different link",
        "#374151",
        () => {
          resetGuidedPanel();
          startPickLinkMode(showPickConfirmation, showStatus);
        },
        "Select a different link"
      );
      pickAgainBtn.style.width = "auto";
      pickAgainBtn.style.fontSize = "9px";

      btnRow.appendChild(recordOnlyBtn);
      btnRow.appendChild(yesOpenBtn);
      btnRow.appendChild(stayBtn);
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
        pickBtn.addEventListener("click", () => showBulletinPickConfirm(el));
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
          const allImages = pickedImages.slice();
          allImages.push({ url: absUrl, el: imgEl });
          const urls = allImages
            .map((entry) => String(entry?.url || "").trim())
            .filter(Boolean);
          if (urls.length === 0) {
            showStatus("❌ Could not read image URLs. Try a different image.", "error");
            resetGuidedPanel();
            return;
          }

          const useStack = urls.length > 1;
          const recipeStep = useStack
            ? { action: "image_stack", count: urls.length, urls }
            : { action: "image", url: urls[0] };
          const uiLabel = useStack
            ? `🖼️ Stack ${urls.length} images: …${urls[0].slice(-35)}`
            : `🖼️ Image: ${urls[0].slice(-50)}`;

          if (!useStack && window.ph_mark_image) {
            try {
              const request = { url: urls[0] };
              const markResult = window.ph_mark_image(request);
              const response = markResult === false
                ? { ok: false, reason: "Page rejected the image save." }
                : { ok: true };
              _logSaveCycle("mark_image", request, response);
              if (markResult === false) {
                showStatus(`❌ ${response.reason}`, "error");
                return;
              }
              addSessionStep("mark_image", uiLabel);
              showStatus(`✅ Image recorded: ${urls[0].slice(-40)}`);
            } catch (_e) {
              _logSaveCycle("mark_image", { url: urls[0] }, { ok: false, reason: "Could not record image. Try refreshing." });
              showStatus("❌ Could not record image. Try refreshing.", "error");
            }
          } else {
            standaloneAddStep(
              recipeStep,
              useStack ? "image_stack" : "mark_image",
              uiLabel
            );
            showStatus(
              useStack
                ? `✅ ${urls.length} images saved — harvester will grab top ${urls.length} each week`
                : `✅ Image noted: ${urls[0].slice(-40)}`
            );
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
    let savePagePdfBtn = null;
    let pickImageBtn = null;
    let imageCropBtn = null;
    let pinLinkBtn = null;
    let getPdfBtn = null;

    const _isStaticOneStepPage = (pageCtx = detectPageType()) =>
      pageCtx.type === "wp_block_file_bulletin" ||
      pageCtx.type === "pdfemb_embed" ||
      pageCtx.type === "google_drive_static" ||
      pageCtx.htmlFingerprint === "wp_block_file_bulletin";

    const _isWpBlockBulletinPage = _isStaticOneStepPage;

    const _captureWpBlockOrMdocsFromPage = (pageCtx = detectPageType()) => {
      const result = _ensureTerminalPdfStep();
      if (result?.ok && result.added) {
        showStatus("✅ Bulletin PDF saved — scroll down and tap Send & test.", "ok");
      } else if (result?.ok) {
        showStatus("✅ Bulletin step already recorded.", "ok");
      } else {
        showStatus("❌ Could not read the bulletin PDF on this page.", "error");
      }
      _refreshGuidedContext();
    };

    clickFirstBtn = makeSmallBtn(
      "👉 Step 1: Point at the bulletin link",
      "#16a34a",
      () => startPickLinkMode(showPickConfirmation, showStatus),
      "Your cursor becomes a crosshair — click the link that opens this week's bulletin (e.g. Parish News at the top)."
    );

    pinLinkBtn = makeSmallBtn(
      "🤖 Auto-guess bulletin link",
      "#6d28d9",
      async () => {
        showStatus("⏳ Finding best bulletin link on this page…", "info");
        const scan = await _handleCopilotMessage({ type: "copilot_scan" });
        if (!scan?.ok || !scan.context?.best) {
          showStatus("❌ Could not find a bulletin link — use Follow a link and pick it yourself.", "error");
          return;
        }
        const pick = scan.context?.best;
        const pin = await _handleCopilotMessage({ type: "copilot_pin" });
        if (pin?.ok) {
          const recorded = pick ? _copilotRecordPick(pick) : { ok: false };
          if (recorded.ok) {
            showStatus(
              `✅ Click step recorded: "${pick.label || pick.selector}". Now open that link and finish with Save PDF / Save page.`,
              "ok"
            );
            _refreshGuidedContext?.();
          } else {
            showStatus(
              "📌 Pinned for this website. Use Follow a link to record the click step, then finish with Save PDF / Save page.",
              "ok"
            );
          }
        } else {
          showStatus(`❌ ${pin?.reason || "Could not pin."}`, "error");
        }
      },
      "Extension guesses the bulletin link and records a click step. You still open it and save the capture step."
    );

    contextPrimaryBtn = makeSmallBtn(
      "💾 Step 2: Save the bulletin",
      "#2563eb",
      () => {
        const pageCtx = detectPageType();
        if (_isWpBlockBulletinPage(pageCtx)) {
          _captureWpBlockOrMdocsFromPage(pageCtx);
          return;
        }
        if (
          pageCtx.type === "mdocs_bulletin_list" ||
          pageCtx.htmlFingerprint === "mdocs_bulletin_table"
        ) {
          _captureWpBlockOrMdocsFromPage(pageCtx);
          return;
        }
        if (pageCtx.type === "direct_pdf") {
          markDownloadUrlSafe(window.location.href, showStatus, false);
          return;
        }
        if (pageCtx.type === "oneweb_docx" && pageCtx.autoNewsletterUrl) {
          markDownloadUrlSafe(pageCtx.autoNewsletterUrl, showStatus, true);
          showStatus(
            `✅ Auto-detected newsletter — ready to Push (no iframe wait).`,
            "ok"
          );
          return;
        }
        if (pageCtx.type === "weekly_bulletin_download") {
          const bulletinUrl = pageCtx.autoDownloadUrl || _pickBestWeeklyBulletinUrl();
          if (bulletinUrl) {
            markDownloadUrlSafe(bulletinUrl, showStatus, true);
            showStatus(
              "✅ Bulletin download URL recorded — click cloud ↓ on page or Push Recipe now.",
              "ok"
            );
            return;
          }
          showStatus(
            "⚠️ Could not find a bulletin link — click the cloud ↓ icon on this Sunday's row.",
            "warn"
          );
          return;
        }
        if (pageCtx.type === "wix_html") {
          standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
          showStatus("✅ Recorded: page will print into the mega bulletin.", "ok");
          return;
        }
        if (pageCtx.type === "html") {
          if (_pathLooksLikeNewsletterPage()) {
            standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
            showStatus("✅ Recorded: this page will print into the mega bulletin.", "ok");
            return;
          }
          startPickLinkMode(showPickConfirmation, showStatus);
          return;
        }
        if (pageCtx.type === "pdf_links" || pageCtx.type === "parish_messenger" || pageCtx.type === "pdfemb") {
          _runPickNewestBulletin();
          return;
        }
        if (pageCtx.type === "cloud_folder") {
          const sunday = _nextSundayDate();
          const row = _findCloudFolderRowForDate(sunday);
          if (!row) {
            showStatus(
              `⚠️ Row ${_formatCloudFolderLabel(sunday)} not found — use Follow a link and pick the newest dated PDF.`,
              "warn"
            );
            startPickLinkMode(showPickConfirmation, showStatus);
            return;
          }
          showPickConfirmation(row);
          return;
        }
        if (pageCtx.type === "image") {
          pickedImages = [];
          startPickImageMode(showPickImageConfirmation, showStatus);
          return;
        }
        window.dispatchEvent(new CustomEvent("ph-start-pick-iframe"));
      },
      "Finish capture on this page — PDF download, print HTML, or pick embedded frame"
    );
    contextPrimaryBtn.style.display = "none";

    wizardBtns.appendChild(clickFirstBtn);
    wizardBtns.appendChild(contextPrimaryBtn);

    savePagePdfBtn = makeSmallBtn(
      "📰 Save page as PDF (HTML text bulletin)",
      "#7c3aed",
      () => {
        standaloneAddStep({ action: "print_to_pdf" }, "print_to_pdf", "📰 Save page as PDF");
        showStatus("✅ Recorded: this page will be printed into the mega bulletin on Sunday.", "ok");
      },
      "Bulletin is text on the page (WordPress/Wix/HTML notice board) — harvester prints it to PDF"
    );
    pickImageBtn = makeSmallBtn(
      "🖼️ Pick bulletin image on this page",
      "#2563eb",
      () => {
        pickedImages = [];
        startPickImageMode(showPickImageConfirmation, showStatus);
      },
      "The bulletin is a picture on the page — click to select it"
    );
    imageCropBtn = makeSmallBtn(
      "✂️ Crop bulletin from screen",
      "#2563eb",
      () => {
        bar.dataset.phHidden = "true";
        bar.style.display = "none";
        startCrop();
      },
      "Draw a rectangle around the bulletin if it is not a normal image link"
    );
    wizardBtns.appendChild(savePagePdfBtn);
    wizardBtns.appendChild(pickImageBtn);
    wizardBtns.appendChild(imageCropBtn);

    moreOptionsBody.appendChild(pinLinkBtn);

      const manualPickLinkBtn = makeSmallBtn(
      "🔗 Point at a specific link manually",
      "#374151",
      () => startPickLinkMode(showBulletinPickConfirm, showStatus),
      "Crosshair pick — use if auto-pick or the candidate list is wrong"
    );
    manualPickLinkBtn.style.marginTop = "4px";
    moreOptionsBody.appendChild(manualPickLinkBtn);

    const pdfBtn = makeSmallBtn(
      "📄 Get a PDF",
      "#374151",
      () => markDownloadUrlSafe(window.location.href, showStatus, false),
      "Advanced: save PDF when you are already on the raw PDF file (not needed on embed bulletin pages)"
    );
    getPdfBtn = pdfBtn;
    const noBulletinBtn = makeSmallBtn(
      "🚫 No bulletin here (skip)",
      "#6b7280",
      () => {
        if (typeof window.ph_mark_download_url === "function") {
          try {
            window.ph_mark_download_url({ url: "no_bulletin", type: "no_bulletin" });
          } catch (_e) {}
          addSessionStep("no_bulletin", "🚫 No bulletin — skipped");
          showStatus("🚫 Marked as no bulletin. You can now close this tab or move on.");
          return;
        }
        // Standalone mode can't persist a "no bulletin" mark from this page,
        // so tell the truth instead of pretending it was saved.
        showStatus(
          "🚫 'No bulletin' can't be saved from here. Leave this parish untrained, or mark it in the Problems tab.",
          "warn"
        );
      },
      "Record that this parish has no bulletin and skip it"
    );

    moreOptionsBody.appendChild(pdfBtn);
    moreOptionsBody.appendChild(noBulletinBtn);

    parishRecordingLine = document.createElement("div");
    parishRecordingLine.style.cssText = [
      "display:none",
      "font-size:10px",
      "font-weight:600",
      "color:#bbf7d0",
      "margin-bottom:6px",
    ].join(";");

    pageLoadTimerLine = document.createElement("div");
    pageLoadTimerLine.id = "ph-page-load-timer";
    pageLoadTimerLine.style.cssText = [
      "display:none",
      "font-size:9px",
      "line-height:1.4",
      "margin-bottom:6px",
      "padding:4px 6px",
      "border-radius:4px",
      "background:#0f172a",
      "border:1px solid #334155",
    ].join(";");
    pageLoadTimerLine.title = "How long this page took to load while you train the recipe";

    guidedPanel.appendChild(parishRecordingLine);
    guidedPanel.appendChild(pageLoadTimerLine);
    guidedPanel.appendChild(journeyStepBar);
    guidedPanel.appendChild(playbookPanel);
    guidedPanel.appendChild(nextStepBanner);
    guidedPanel.appendChild(wizardQ);
    guidedPanel.appendChild(compactPageHint);
    guidedPanel.appendChild(wizardBtns);
    guidedPanel.appendChild(moreOptionsSection);
    guidedPanel.appendChild(stuckLink);
    updateParishRecordingLine("", "", _currentHostname());
    globalThis.__phPageLoadTimerLine = pageLoadTimerLine;
    if (_inStandaloneMode()) _attachPageLoadTimer(pageLoadTimerLine);
    try {
      _refreshGuidedContext();
    } catch (guidedErr) {
      console.error("[Parish Trainer] guided context refresh failed:", guidedErr);
      if (globalThis.ph_toolbar_diag?.setError) {
        globalThis.ph_toolbar_diag.setError(`Guided panel: ${guidedErr}`);
      }
    }

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
      if (pageLoadTimerLine && _inStandaloneMode()) _attachPageLoadTimer(pageLoadTimerLine);
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
    window.addEventListener("ph-retraining-hint", (e) => {
      if (e?.detail?.hint === "homepage_click_done") {
        showStatus(
          "✅ Homepage click kept — this Wix bulletin is HTML. Tap Save page as PDF, then Send & test.",
          "ok"
        );
        return;
      }
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

      // "Pick newest bulletin" — same as the main green button (kept for Find bulletin scan)
      const pickableLinks = result.links || result.bulletinLinks || [];
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
            _runPickNewestBulletin();
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
      const htmlFp = globalThis.PhHtmlFingerprint;
      const htmlSummary = htmlFp?.formatScanSummary?.(detected.fingerprintScan || htmlFp.scanPage?.());
      _safeSendMessage({ type: "fetch_site_patterns" }, (resp, _err) => {
        if (!resp?.ok) return;
        const matches = lib.findSimilar(pageFp, resp.patterns || {});
        const lines = [lib.buildHintText(pageFp, matches)];
        if (htmlSummary) lines.push(htmlSummary);
        patternHintWrap.style.display = "block";
        patternHintBanner.textContent = lines.join("\n\n");
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
    const recipeStartUrlEl = document.createElement("div");
    recipeStartUrlEl.style.cssText =
      "font-size:9px;color:#93c5fd;margin-bottom:4px;word-break:break-all;line-height:1.35;";
    recipeStartUrlEl.textContent = "Sunday start URL: (record a step)";
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

    recipeBodyEl.appendChild(recipeStartUrlEl);
    recipeBodyEl.appendChild(stepsListEl);
    recipeBodyEl.appendChild(undoBtn);
    recipeSection.appendChild(recipeHeaderEl);
    recipeSection.appendChild(recipeBodyEl);

    // Wire up the recipe count refresh callback
    _refreshRecipeCount = () => {
      const sentCount = _standaloneRecipeSteps().length;
      if (sentCount > 0) {
        lastPushedRecipeNote = "";
        recipeTitleEl.textContent = `📋 Recipe Preview (${sentCount} step${sentCount !== 1 ? "s" : ""})`;
      } else if (lastPushedRecipeNote) {
        recipeTitleEl.textContent = "📋 Recipe Preview — sent to GitHub";
      } else {
        recipeTitleEl.textContent = "📋 Recipe Preview (0 steps)";
      }
      const startPreview = _resolveRecipeStartUrl();
      recipeStartUrlEl.textContent = startPreview
        ? `Sunday start URL: ${startPreview}`
        : "Sunday start URL: (record a step)";
      _scheduleRefreshGuidedContext();
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

    if (globalThis.ph_toolbar_diag?.attachPanel) {
      globalThis.ph_toolbar_diag.attachPanel(body, { open: false, autoRun: true });
    }

    // Copilot chat UI removed — playbook + pin cover training without API cost.

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
      pushTitle.style.cssText = "font-size:11px;font-weight:700;color:#86efac;margin-bottom:6px;";
      pushTitle.textContent = "🚀 Step 3 — Send & test (this parish only)";
      pushSection.appendChild(pushTitle);

      // GitHub settings check — warn early if PAT/repo are not configured.
      const ghConfigNote = document.createElement("div");
      ghConfigNote.style.cssText = "font-size:9px;display:none;margin-bottom:5px;padding:3px 6px;border-radius:3px;";
      pushSection.appendChild(ghConfigNote);
      if (typeof chrome !== "undefined" && chrome.storage) {
        try {
          chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => {
            if (chrome.runtime?.lastError) return;
            const repo = String(r.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
            if (!r.gh_pat) {
              ghConfigNote.style.display = "block";
              ghConfigNote.style.background = "#7f1d1d";
              ghConfigNote.style.color = "#fca5a5";
              ghConfigNote.textContent = "⚠️ GitHub PAT not set — open the extension popup → ⚙️ Settings before pushing.";
            } else {
              ghConfigNote.style.display = "block";
              ghConfigNote.style.background = "#14532d";
              ghConfigNote.style.color = "#86efac";
              ghConfigNote.textContent = `✓ GitHub configured for ${repo}`;
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

      const inputStyle = [
        "width:100%",
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:4px 6px",
        "background:#0f172a",
        "color:#f9fafb",
        "font-size:10px",
        "box-sizing:border-box",
        "font-family:inherit",
      ].join(";");

      const trainerTip = document.createElement("div");
      trainerTip.style.cssText = "font-size:9px;color:#93c5fd;line-height:1.4;margin-bottom:6px;display:none;";
      pushSection.appendChild(trainerTip);

      let parishPickerTouched = false;
      let diocesePickerTouched = false;

      const parishFormExpanded = document.createElement("div");
      parishFormExpanded.style.cssText = "display:none;";

      const wrongParishWrap = document.createElement("div");
      wrongParishWrap.style.cssText = "margin-bottom:6px;display:none;";
      const wrongParishBtn = document.createElement("button");
      wrongParishBtn.type = "button";
      wrongParishBtn.textContent = "Wrong parish? Change it";
      wrongParishBtn.style.cssText = [
        "border:none",
        "background:transparent",
        "color:#93c5fd",
        "font-size:9px",
        "padding:0",
        "cursor:pointer",
        "text-decoration:underline",
        "font-family:inherit",
      ].join(";");
      wrongParishBtn.addEventListener("click", () => {
        parishPickerTouched = true;
        parishFormExpanded.style.display = "block";
        wrongParishWrap.style.display = "none";
        parishSearchCombo?.input?.focus?.();
      });
      wrongParishWrap.appendChild(wrongParishBtn);

      const _setParishFormMode = (resolved) => {
        const key = resolved?.inferredKey || resolved?.key || "";
        const confident = Boolean(key && resolved && !resolved.lowConfidence);
        if (confident && !parishPickerTouched) {
          parishFormExpanded.style.display = "none";
          wrongParishWrap.style.display = "block";
        } else {
          parishFormExpanded.style.display = "block";
          wrongParishWrap.style.display = confident ? "block" : "none";
        }
      };

      const parishSearchCombo = window.ph_parish_pickers?.createSearchCombo
        ? window.ph_parish_pickers.createSearchCombo({
            label: "Find parish (type a few letters)",
            placeholder: "e.g. dunfanaghy, holy-cross, rap…",
            inputStyle,
            onChange: (item) => {
              if (!item) return;
              parishPickerTouched = true;
              const key = item.key || item.value || "";
              if (key) keyInput.value = key;
              if (item.name) nameInput.value = item.name;
              if (item.diocese) {
                resolvedDiocese = item.diocese;
                diocesePickerExpanded = false;
                dioceseCombo?.setValue(item.diocese, item.diocese.replace(/_/g, " "));
                refreshDioceseLine();
              }
              autoDetectNote.style.display = "block";
              autoDetectNote.style.color = "#86efac";
              autoDetectNote.textContent = `✓ You picked: ${item.name || key} (${key})`;
              parishMismatchBanner.style.display = "none";
            },
          })
        : null;
      if (parishSearchCombo) parishFormExpanded.appendChild(parishSearchCombo.wrap);

      const keyInput = makeInput("Parish key (folder name on GitHub)", "ph-parish-key");
      const nameInput = makeInput("Display name (shown in mega bulletin)", "ph-display-name");
      parishFormExpanded.appendChild(keyInput);
      parishFormExpanded.appendChild(nameInput);
      pushSection.appendChild(wrongParishWrap);
      pushSection.appendChild(parishFormExpanded);
      const harvestStatusLine = document.createElement("div");
      harvestStatusLine.style.cssText = "font-size:9px;color:#93c5fd;margin-bottom:4px;display:none;";
      pushSection.appendChild(harvestStatusLine);
      keyInput.addEventListener("input", () => {
        parishPickerTouched = true;
      });
      nameInput.addEventListener("input", () => {
        parishPickerTouched = true;
      });

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
              const ukDate = (() => {
                const raw = String(report.target_date || "");
                const m = raw.match(/(\d{4})-(\d{2})-(\d{2})/);
                return m ? `${m[3]}/${m[2]}/${m[1]}` : (raw || "recent");
              })();
              line = `✅ Last harvest (${ukDate}): downloaded OK`;
              harvestStatusLine.style.color = "#86efac";
            } else if (failed) {
              const reason = String(failed.reason || failed.error || "failed").slice(0, 90);
              // Stale-failure guard: if the recipe was re-saved AFTER this
              // harvest ran, the failure predates the fix — don't scare the user
              // with an error that no longer applies.
              let fixedSince = false;
              try {
                const reportDate = String(report.target_date || "").slice(0, 10);
                const loadedRec = await loadRecipeFromRawGithub(key);
                const recDate = String(loadedRec?.recipe?.recorded_date || "").slice(0, 10);
                if (recDate && reportDate && recDate > reportDate) fixedSince = true;
              } catch (_e) {}
              if (fixedSince) {
                _lastHarvestIssue = "";
                _needsRetrain = false;
                line = "✅ Fix saved since the last run — press Send & test (or wait for Sunday) to confirm.";
                harvestStatusLine.style.color = "#86efac";
                _refreshGuidedContext();
              } else {
                const training = _standaloneRecipeSteps().length > 0;
                const onPdf = detectPageType().type === "direct_pdf";
                _lastHarvestIssue = reason;
                _needsRetrain = false;
                const cloudFail =
                  /cloud folder|yy\.mm\.dd|html_render|folder listing|re-train/i.test(reason) ||
                  (failed.file_type === "html_render" && _isCloudFolderUrl(pageUrl));
                if (cloudFail || reason.includes("outdated")) {
                  _needsRetrain = true;
                }
                if (training || onPdf) {
                  line = _needsRetrain
                    ? `⚠️ Retrain needed — last harvest: ${reason}`
                    : `ℹ️ Last Sunday's run failed (${reason}) — push this recipe to fix it`;
                  harvestStatusLine.style.color = _needsRetrain ? "#fca5a5" : "#fde68a";
                } else {
                  line = _needsRetrain
                    ? `⚠️ Retrain this recipe — last harvest: ${reason}`
                    : `❌ Last harvest: ${reason}`;
                  harvestStatusLine.style.color = "#fca5a5";
                }
                if (window.ph_copilot?.rememberIssue) {
                  window.ph_copilot.rememberIssue(key, { lastIssue: reason, needsRetrain: _needsRetrain });
                }
                _refreshGuidedContext();
              }
            }
          }
          if (!line && failResp.ok) {
            const fails = await failResp.json();
            const count = Number(fails[key] || 0);
            if (count >= 2) {
              _needsRetrain = true;
              _lastHarvestIssue = `${count} consecutive harvest failures`;
              line = `⚠️ ${count} consecutive harvest failures — retrain this recipe`;
              harvestStatusLine.style.color = "#fde68a";
              _refreshGuidedContext();
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

      let resolvedDiocese = "";
      let dioceseCombo = null;
      let diocesePickerExpanded = false;
      const NEW_DIOCESE_VALUE = "__new_diocese__";
      const newDioceseWrap = document.createElement("div");
      newDioceseWrap.style.display = "none";
      const newDioceseInput = document.createElement("input");
      newDioceseInput.type = "text";
      newDioceseInput.placeholder = "New folder name, e.g. cloyne, killaloe";
      newDioceseInput.style.cssText = inputStyle + ";margin-bottom:4px;";
      const newDioceseHint = document.createElement("div");
      newDioceseHint.style.cssText = "font-size:9px;color:#6b7280;margin-bottom:6px;line-height:1.35;";
      newDioceseHint.textContent =
        "Creates parishes/recipes/your_name/ on GitHub when you push. Use lowercase — spaces become underscores.";
      newDioceseWrap.appendChild(newDioceseInput);
      newDioceseWrap.appendChild(newDioceseHint);

      const _slugifyDioceseInput = (value) =>
        String(value || "")
          .trim()
          .toLowerCase()
          .replace(/&/g, "and")
          .replace(/[^a-z0-9]+/g, "_")
          .replace(/^_+|_+$/g, "");

      const dioceseLine = document.createElement("div");
      dioceseLine.style.cssText = "font-size:9px;color:#9ca3af;margin-bottom:6px;display:none;";
      pushSection.appendChild(dioceseLine);

      const dioceseCompactRow = document.createElement("div");
      dioceseCompactRow.style.cssText = [
        "display:none",
        "align-items:center",
        "justify-content:space-between",
        "gap:6px",
        "margin-bottom:6px",
        "font-size:10px",
      ].join(";");
      const dioceseCompactLabel = document.createElement("span");
      dioceseCompactLabel.style.cssText = "color:#86efac;flex:1;line-height:1.35;";
      const dioceseChangeBtn = document.createElement("button");
      dioceseChangeBtn.type = "button";
      dioceseChangeBtn.textContent = "▼";
      dioceseChangeBtn.title = "Change diocese folder (only if this parish is in the wrong folder)";
      dioceseChangeBtn.style.cssText = [
        "border:1px solid #374151",
        "border-radius:4px",
        "padding:2px 6px",
        "background:#1e293b",
        "color:#9ca3af",
        "cursor:pointer",
        "font-size:10px",
        "font-family:inherit",
        "flex-shrink:0",
      ].join(";");
      dioceseCompactRow.appendChild(dioceseCompactLabel);
      dioceseCompactRow.appendChild(dioceseChangeBtn);
      pushSection.appendChild(dioceseCompactRow);

      const dioceseChangeWrap = document.createElement("div");
      dioceseChangeWrap.style.display = "none";
      pushSection.appendChild(dioceseChangeWrap);

      const _refreshParishPickerItems = async () => {
        if (!parishSearchCombo) return;
        const settings = await _storageGet(["gh_repo"]);
        const reg = await window.ph_parish_pickers.loadRegistry(settings.gh_repo);
        let items = [];
        if (resolvedDiocese && resolvedDiocese !== NEW_DIOCESE_VALUE && reg.parishesByDiocese[resolvedDiocese]) {
          items = reg.parishesByDiocese[resolvedDiocese].map((p) => ({
            value: p.key,
            key: p.key,
            name: p.name,
            label: `${p.name} (${p.key})`,
            diocese: resolvedDiocese,
          }));
        } else {
          items = Object.values(reg.byKey).map((p) => ({
            value: p.key,
            key: p.key,
            name: p.name,
            label: `${p.name} (${p.key})`,
            diocese: p.diocese,
          }));
        }
        const seenKeys = new Set();
        items = items.filter((p) => {
          const k = String(p.key || "").toLowerCase();
          if (!k || seenKeys.has(k)) return false;
          if (window.ph_parish_pickers?.isJunkParishKey?.(k)) return false;
          seenKeys.add(k);
          return true;
        });
        parishSearchCombo.setItems(items.sort((a, b) => a.label.localeCompare(b.label)));
      };

      const refreshDioceseLine = () => {
        const known = resolvedDiocese && resolvedDiocese !== NEW_DIOCESE_VALUE;
        if (known && !diocesePickerExpanded && !diocesePickerTouched) {
          dioceseCompactRow.style.display = "flex";
          dioceseChangeWrap.style.display = "none";
          dioceseLine.style.display = "none";
          dioceseCompactLabel.textContent =
            `✓ ${resolvedDiocese.replace(/_/g, " ")} — parishes/recipes/${resolvedDiocese}/`;
          dioceseChangeBtn.textContent = "▼";
        } else if (known && diocesePickerExpanded) {
          dioceseCompactRow.style.display = "flex";
          dioceseChangeWrap.style.display = "block";
          dioceseLine.style.display = "block";
          dioceseLine.textContent = `Change diocese folder (current: ${resolvedDiocese})`;
          dioceseCompactLabel.textContent =
            `✓ ${resolvedDiocese.replace(/_/g, " ")} — parishes/recipes/${resolvedDiocese}/`;
          dioceseChangeBtn.textContent = "▲";
        } else if (resolvedDiocese === NEW_DIOCESE_VALUE) {
          dioceseCompactRow.style.display = "none";
          dioceseChangeWrap.style.display = "block";
          dioceseLine.style.display = "block";
          dioceseLine.textContent = "Enter new diocese folder name below.";
        } else {
          dioceseCompactRow.style.display = "none";
          dioceseChangeWrap.style.display = "block";
          dioceseLine.style.display = "block";
          dioceseLine.textContent = "Pick diocese folder for this parish.";
        }
        void _refreshParishPickerItems();
      };

      dioceseChangeBtn.addEventListener("click", () => {
        diocesePickerExpanded = !diocesePickerExpanded;
        if (!diocesePickerExpanded) dioceseCombo?.closeMenu?.();
        refreshDioceseLine();
        if (diocesePickerExpanded) {
          dioceseCombo?.input?.focus?.();
          dioceseCombo?.openMenu?.();
        }
      });

      let dioceseSelect;
      if (window.ph_parish_pickers?.createSearchCombo) {
        dioceseCombo = window.ph_parish_pickers.createSearchCombo({
          label: "Change diocese folder",
          placeholder: "Type to search dioceses…",
          inputStyle,
          autoOpenOnFocus: false,
          onChange: (item, val) => {
            diocesePickerTouched = true;
            if (val === NEW_DIOCESE_VALUE) {
              resolvedDiocese = NEW_DIOCESE_VALUE;
              newDioceseWrap.style.display = "block";
              refreshDioceseLine();
              return;
            }
            newDioceseWrap.style.display = "none";
            resolvedDiocese = val || "";
            if (resolvedDiocese) {
              diocesePickerExpanded = false;
              void _storageSet({ ph_last_diocese: resolvedDiocese });
            }
            refreshDioceseLine();
          },
        });
        dioceseChangeWrap.appendChild(dioceseCombo.wrap);
        dioceseChangeWrap.appendChild(newDioceseWrap);
        dioceseSelect = {
          get value() {
            if (resolvedDiocese === NEW_DIOCESE_VALUE) {
              return _slugifyDioceseInput(newDioceseInput.value);
            }
            const raw = resolvedDiocese || dioceseCombo?.getValue() || "";
            return _slugifyDioceseInput(raw) || raw;
          },
          focus: () => dioceseCombo?.input?.focus?.(),
        };
      } else {
        const dioceseSelectEl = document.createElement("select");
        dioceseSelectEl.id = "ph-diocese-select";
        dioceseSelectEl.style.cssText = inputStyle + ";margin-bottom:6px;";
        for (const o of [
          { v: "", l: "— select diocese —" },
          { v: "derry", l: "Derry" },
          { v: "raphoe", l: "Raphoe" },
        ]) {
          const opt = document.createElement("option");
          opt.value = o.v;
          opt.textContent = o.l;
          dioceseSelectEl.appendChild(opt);
        }
        pushSection.appendChild(dioceseSelectEl);
        dioceseSelectEl.addEventListener("change", () => {
          resolvedDiocese = dioceseSelectEl.value.trim();
          refreshDioceseLine();
        });
        dioceseSelect = dioceseSelectEl;
      }

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

      const autoDetectNote = document.createElement("div");
      autoDetectNote.style.cssText = "font-size:9px;color:#86efac;margin-bottom:3px;display:none;";
      pushSection.appendChild(autoDetectNote);

      const _showTrainerTip = (resolved) => {
        if (!trainerTip) return;
        if (resolved?.lowConfidence && !parishPickerTouched) {
          trainerTip.style.display = "block";
          trainerTip.textContent =
            "💡 Not sure this parish is right? Use Find parish above — type a few letters (e.g. holy or dunfanaghy).";
        } else if (resolved?.urlMatched) {
          trainerTip.style.display = "none";
        } else {
          trainerTip.style.display = "none";
        }
      };

      const _loadDioceseComboItems = async () => {
        if (!dioceseCombo) return;
        const settings = await _storageGet(["gh_repo"]);
        const reg = await window.ph_parish_pickers.loadRegistry(settings.gh_repo);
        const items = (reg.dioceses || []).map((d) => ({
          value: d,
          label: d.replace(/_/g, " "),
        }));
        items.push({ value: NEW_DIOCESE_VALUE, label: "➕ Create new diocese folder…" });
        dioceseCombo.setItems(items);
      };

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

      const _applyResolvedParishToPushForm = (resolved, { notePrefix = "Matched from this page URL" } = {}) => {
        if (!resolved) return;
        const inferred = resolved.inferredKey || resolved.key || "";
        if (!resolved.diocese && inferred) {
          const registryHit = window.ph_parish_pickers?.lookupByKey?.(inferred);
          if (registryHit?.diocese) resolved.diocese = registryHit.diocese;
        }
        if (inferred && !parishPickerTouched) {
          keyInput.value = inferred;
          autoDetectNote.style.display = "block";
          autoDetectNote.style.color = resolved.lowConfidence ? "#fde68a" : "#86efac";
          autoDetectNote.textContent = resolved.lowConfidence
            ? `⚠️ Best guess: ${resolved.name || inferred} (${inferred}) — tap Wrong parish? if needed`
            : `✓ Recording for ${resolved.name || inferred} (${inferred})`;
        }
        if (resolved.name && !parishPickerTouched) nameInput.value = resolved.name;
        if (resolved.diocese && !diocesePickerTouched) {
          resolvedDiocese = resolved.diocese;
          diocesePickerExpanded = false;
          dioceseCombo?.setValue(resolved.diocese, resolved.diocese.replace(/_/g, " "));
          refreshDioceseLine();
        }
        updateParishRecordingLine(nameInput.value || resolved.name, inferred, resolved.hostname);
        _showParishMismatch(inferred, resolved.key && resolved.key !== inferred ? resolved.key : "");
        _showTrainerTip(resolved);
        _setParishFormMode(resolved);
      };

      const _bootstrapParishContext = async () => {
        const pageUrl = _pageUrlForParishDetection();
        const hostname = _hostnameFromUrl(pageUrl);
        const recorded = _standaloneRecipeSteps();
        const hasClick = recorded.some(
          (s) => String(s?.action || "").trim().toLowerCase() === "click"
        );
        const activeSession = await _getRecordingSessionForCurrentHost();
        if (hasClick && activeSession?.startUrl && _hostsMatch(activeSession.startUrl, pageUrl)) {
          standaloneStartUrl = activeSession.startUrl;
        } else if (!hasClick || !standaloneStartUrl || !_hostsMatch(standaloneStartUrl, pageUrl)) {
          standaloneStartUrl = pageUrl;
        }
        _purgeStaleHostnameMapEntry(hostname, pageUrl);
        const settings = await _storageGet(["ph_last_diocese", "ph_hostname_map", "gh_repo"]);
        await window.ph_parish_pickers?.loadRegistry?.(settings.gh_repo);
        await _loadDioceseComboItems();
        const resolved = _resolveParishContextForPage(pageUrl, settings || {});
        if (!resolved.diocese && settings.ph_last_diocese && !resolvedDiocese && !diocesePickerTouched) {
          resolvedDiocese = String(settings.ph_last_diocese || "").trim();
          dioceseCombo?.setValue(resolvedDiocese, resolvedDiocese.replace(/_/g, " "));
          refreshDioceseLine();
        }
        if (resolved.inferredKey) {
          resolved.key = resolved.inferredKey;
        }
        _applyResolvedParishToPushForm(resolved);
        void _writeParishDetectDebug(resolved);
        setTimeout(() => {
          void _refreshHarvestStatusLine(resolved.inferredKey || resolved.key);
          void refreshPatternHints();
        }, 1500);
        await _loadExistingRecipeIfEmpty(resolved, resolved.name, hostname);
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

      const formatPushDiagnosisHtml = (response) => {
        const lines = [];
        const v = response.githubVerify;
        if (v && v.ok) {
          lines.push(
            `<strong>GitHub copy verified:</strong> ${v.stepCount} step(s)` +
            (v.lastAction ? `, ends with <code>${v.lastAction}</code>` : "") +
            (v.recorded_date ? `, dated ${v.recorded_date}` : "")
          );
          if (v.skip || v.needs_retraining) {
            lines.push("⚠️ Recipe still has skip/retraining flags — harvest will ignore it.");
          }
        } else if (v && v.error) {
          lines.push(`⚠️ Could not verify recipe on GitHub: ${v.error}`);
        }
        if (response.stepsPreservedFromOld) {
          lines.push(
            "⚠️ <strong>No steps in your push</strong> — GitHub kept the OLD steps. Re-record and push again."
          );
        }
        if (response.filePath) {
          lines.push(`File: <code>${response.filePath}</code>`);
        }
        return lines.join("<br>");
      };

      const showPostPushBanner = (response, headlineHtml, tone = "ok") => {
        postPushBanner.style.display = "block";
        if (tone === "warn") {
          postPushBanner.style.color = "#fde68a";
          postPushBanner.style.background = "#78350f";
          postPushBanner.style.borderColor = "#f59e0b";
        } else if (tone === "err") {
          postPushBanner.style.color = "#fecaca";
          postPushBanner.style.background = "#7f1d1d";
          postPushBanner.style.borderColor = "#ef4444";
        } else {
          postPushBanner.style.color = "#86efac";
          postPushBanner.style.background = "#14532d";
          postPushBanner.style.borderColor = "#16a34a";
        }
        const diag = formatPushDiagnosisHtml(response);
        postPushBanner.innerHTML = headlineHtml + (diag ? `<br><br>${diag}` : "");
      };

      let _postPushWatchToken = 0;

      const _restartBulletinPickAfterWrongHarvest = () => {
        while (recipeSteps.length > 0) {
          const last = recipeSteps[recipeSteps.length - 1];
          const action = String(last?.recipeStep?.action || "").toLowerCase();
          if (action === "download" || action === "click") {
            undoSessionStep();
          } else {
            break;
          }
        }
        if (typeof refreshStepCount === "function") refreshStepCount();
        resetGuidedPanel();
        showStatus("Pick the correct bulletin, confirm it, then Send & test again.", "warn");
        const pushEl = document.getElementById("ph-push-section");
        if (pushEl) pushEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
        _runPickNewestBulletin();
      };

      const _showHarvestPdfVerify = ({ parishKey, displayName, pdfUrl, pushResponse }) => {
        postPushBanner.style.display = "block";
        postPushBanner.style.color = "#e2e8f0";
        postPushBanner.style.background = "#1e3a5f";
        postPushBanner.style.borderColor = "#2563eb";
        _clearElement(postPushBanner);

        const head = document.createElement("div");
        head.style.cssText = "font-size:11px;font-weight:700;margin-bottom:6px;line-height:1.4;";
        head.innerHTML =
          `✅ <strong>${displayName}</strong> — harvest downloaded a PDF.<br>` +
          `<span style="font-weight:600;color:#93c5fd;">Open it and check: is this the right bulletin?</span>`;
        postPushBanner.appendChild(head);

        const openRow = document.createElement("div");
        openRow.style.cssText = "margin-bottom:8px;font-size:10px;";
        const openLink = document.createElement("a");
        openLink.href = pdfUrl;
        openLink.target = "_blank";
        openLink.rel = "noopener noreferrer";
        openLink.style.cssText = "color:#93c5fd;font-weight:600;";
        openLink.textContent = "Open PDF in new tab →";
        openRow.appendChild(openLink);
        postPushBanner.appendChild(openRow);

        const btnRow = document.createElement("div");
        btnRow.style.cssText = "display:flex;flex-direction:column;gap:6px;";

        const yesBtn = document.createElement("button");
        yesBtn.type = "button";
        yesBtn.textContent = "✅ PDF is correct — done";
        yesBtn.style.cssText =
          "border:none;border-radius:4px;padding:8px 10px;background:#16a34a;color:#fff;cursor:pointer;font-size:11px;font-weight:600;font-family:inherit;";
        yesBtn.addEventListener("click", () => {
          showPostPushBanner(
            pushResponse,
            `✅ <strong>${displayName}</strong> — you confirmed the PDF. Recorded on GitHub. ` +
              `<a href="${pdfUrl}" target="_blank" rel="noopener noreferrer">Open PDF</a>`,
            "ok"
          );
          showStatus(`✅ ${displayName} — PDF confirmed.`, "ok");
          try {
            chrome.runtime.sendMessage({
              type: "problems_refresh",
              parish_key: parishKey,
              display_name: displayName,
            });
          } catch (_e) {}
        });

        const wrongBtn = document.createElement("button");
        wrongBtn.type = "button";
        wrongBtn.textContent = "❌ Wrong pick — fix recipe";
        wrongBtn.style.cssText =
          "border:none;border-radius:4px;padding:8px 10px;background:#b91c1c;color:#fff;cursor:pointer;font-size:11px;font-weight:600;font-family:inherit;";
        wrongBtn.addEventListener("click", () => {
          _restartBulletinPickAfterWrongHarvest();
          postPushBanner.style.display = "none";
        });

        btnRow.appendChild(yesBtn);
        btnRow.appendChild(wrongBtn);
        postPushBanner.appendChild(btnRow);
      };

      const _startPostPushHarvestWatch = (parishKey, displayName, pushResponse, dispatchAt) => {
        const token = ++_postPushWatchToken;
        void (async () => {
          const settings = await _storageGet(["gh_pat", "gh_repo"]);
          const mod = globalThis.phGithubRecipePush;
          if (!settings.gh_pat || !mod?.pollHarvestUntilDone) return;
          const ghRepo = String(settings.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
          const startedAt = Number(dispatchAt) || Date.now();
          const result = await mod.pollHarvestUntilDone({
            gh_pat: settings.gh_pat,
            gh_repo: settings.gh_repo,
            parish_key: parishKey,
            startedAt,
            onProgress: ({ elapsed, runStatus, queued }) => {
              if (token !== _postPushWatchToken) return;
              let statusLabel = "checking result";
              if (queued || runStatus === "queued") {
                statusLabel = "queued (full harvest may be ahead)";
              } else if (runStatus === "in_progress") {
                statusLabel = "running on GitHub";
              } else if (runStatus === "starting" || runStatus === "waiting") {
                statusLabel = "waiting for GitHub Actions";
              } else if (runStatus === "pending") {
                statusLabel = "queued on GitHub";
              }
              showPostPushBanner(
                pushResponse,
                `⏳ <strong>${displayName}</strong> — ${statusLabel} (${elapsed}s)…`
              );
            },
          });
          if (token !== _postPushWatchToken) return;
          if (result.ok) {
            const pdfUrl =
              result.item?.url ||
              `https://raw.githubusercontent.com/${ghRepo}/main/Bulletins/current/${parishKey}.pdf`;
            showStatus(`✅ ${displayName} test passed — open the PDF and confirm it's correct.`, "ok");
            _showHarvestPdfVerify({
              parishKey,
              displayName,
              pdfUrl,
              pushResponse,
            });
            try {
              chrome.runtime.sendMessage({ type: "problems_refresh", parish_key: parishKey, display_name: displayName });
            } catch (_e) {}
            return;
          }
          if (result.stale) {
            const reason = String(result.reason || result.item?.error || "Bulletin too old").slice(0, 160);
            showPostPushBanner(
              pushResponse,
              `🕐 <strong>${displayName}</strong> — recipe worked! Bulletin too old for this week (recorded on GitHub). ` +
              `${reason} · Open Problems tab.`,
              "warn"
            );
            showStatus(`🕐 ${displayName} — recipe OK, bulletin stale (recorded on GitHub).`, "warn");
            try {
              chrome.runtime.sendMessage({ type: "problems_refresh", parish_key: parishKey, display_name: displayName });
            } catch (_e) {}
            return;
          }
          if (result.ok === false) {
            const reason = String(result.reason || "Harvest failed").slice(0, 200);
            showPostPushBanner(
              pushResponse,
              `❌ <strong>${displayName}</strong> — ${reason} (recorded on GitHub). ` +
              `<a href="${result.runUrl}" target="_blank" rel="noopener noreferrer">Actions log</a> · Problems tab.`,
              "err"
            );
            showStatus(`❌ ${displayName} test failed — see Problems tab.`, "error");
            try {
              chrome.runtime.sendMessage({ type: "problems_refresh", parish_key: parishKey, display_name: displayName });
            } catch (_e) {}
            return;
          }
          showPostPushBanner(
            pushResponse,
            `⚠️ <strong>${displayName}</strong> — still waiting after ${result.elapsed}s. ` +
            `<a href="${result.runUrl}" target="_blank" rel="noopener noreferrer">Open Actions</a> or Problems tab.`,
            "warn"
          );
        })();
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

      // Positive counterpart to the drift warning: reassure the user when a
      // working recipe already exists so they stop re-training things that
      // are already fine.
      const readyBanner = document.createElement("div");
      readyBanner.style.cssText = [
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
      advancedBodyEl.appendChild(readyBanner);

      let driftRecipeKey = "";
      let driftRecipeObject = null;
      let driftRecipePath = "";

      const postPushBanner = document.createElement("div");
      postPushBanner.style.cssText = [
        "display:none",
        "font-size:10px",
        "line-height:1.45",
        "color:#86efac",
        "background:#14532d",
        "border:1px solid #16a34a",
        "border-radius:6px",
        "padding:6px 8px",
        "margin-bottom:6px",
      ].join(";");
      pushSection.appendChild(postPushBanner);

      const pushBtn = document.createElement("button");
      pushBtn.type = "button";
      pushBtn.textContent = "🚀 Send & test on GitHub";
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
        const ghRepo = String(settings.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
        if (!ghRepo) return null;
        // raw.githubusercontent.com serves public files. Adding an Authorization
        // header makes the browser send a CORS preflight that GitHub's raw host
        // rejects, which blocks every recipe lookup. Public repo => no auth header.
        const headers = {};
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

        // Try diocese subfolder path first, then scan all known folders, then legacy flat path.
        const dioceseSubfolder = canonicalDioceseSlug(diocese) || "unknown";
        const pathsToTry = [
          `parishes/recipes/${dioceseSubfolder}/${key}.json`,
          ...["derry", "down_and_connor", "raphoe", "unknown"]
            .filter((d) => d !== dioceseSubfolder)
            .map((d) => `parishes/recipes/${d}/${key}.json`),
          `parishes/recipes/${key}.json`,
        ];
        for (const filePath of pathsToTry) {
          const rawUrl = `https://raw.githubusercontent.com/${ghRepo}/main/${filePath}?t=${Date.now()}`;
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
        if (_skipLoadExistingRecipe) {
          _skipLoadExistingRecipe = false;
          return;
        }
        if (_standaloneRecipeSteps().length > 0 || !resolved?.key) return;
        const activeSession = await _getRecordingSessionForCurrentHost();
        if (
          activeSession?.active &&
          (Array.isArray(activeSession.steps) && activeSession.steps.length > 0 ||
            activeSession.pendingUrl ||
            activeSession.fixNow)
        ) {
          return;
        }
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
          readyBanner.style.display = "none";
        } else {
          driftBanner.style.display = "none";
          const stepCount = Array.isArray(loaded.recipe.steps) ? loaded.recipe.steps.length : 0;
          if (stepCount > 0) {
            const dn = String(loaded.recipe.display_name || key).trim();
            const when = String(loaded.recipe.recorded_date || "").trim();
            readyBanner.textContent =
              `✓ You already have a working recipe for ${dn} — ${stepCount} step${stepCount === 1 ? "" : "s"}` +
              (when ? `, saved ${when}` : "") +
              `. No need to re-train — just press “Send & test on GitHub”.`;
            readyBanner.style.display = "block";
          } else {
            readyBanner.style.display = "none";
          }
        }
      };

      pushBtn.addEventListener("click", async () => {
        const pageUrl = _pageUrlForParishDetection();

        let storageData = {};
        if (typeof chrome !== "undefined" && chrome.storage) {
          try {
            storageData = await new Promise((resolve) => {
              chrome.storage.local.get(["ph_hostname_map", "ph_last_diocese", "gh_repo"], (r) => {
                if (chrome.runtime?.lastError) resolve({});
                else resolve(r || {});
              });
            });
          } catch (_storageErr) {
            storageData = {};
          }
        }

        await window.ph_parish_pickers?.loadRegistry?.(storageData.gh_repo);

        const resolved = _resolveParishContextForPage(pageUrl, storageData);
        const inferredKey = String(resolved.inferredKey || _inferParishKeyFromUrl(pageUrl) || "")
          .trim()
          .toLowerCase()
          .replace(/\s+/g, "_");
        const manualKey = keyInput.value.trim().toLowerCase().replace(/\s+/g, "_");
        let key = parishPickerTouched ? manualKey : (inferredKey || manualKey);
        if (!parishPickerTouched && inferredKey && manualKey && manualKey !== inferredKey) {
          console.warn(
            `Parish Trainer: ignoring stale manual key "${manualKey}" — page URL says "${inferredKey}"`
          );
          _showParishMismatch(inferredKey, manualKey);
          key = inferredKey;
        }
        let name = nameInput.value.trim() || resolved.name;
        let diocese = dioceseSelect.value || resolved.diocese || resolvedDiocese;
        if (diocese === NEW_DIOCESE_VALUE || resolvedDiocese === NEW_DIOCESE_VALUE) {
          diocese = _slugifyDioceseInput(newDioceseInput.value);
          if (!diocese) {
            showStatus("❌ Enter a name for the new diocese folder (e.g. cloyne).", "error");
            newDioceseInput.focus();
            return;
          }
          if (["recipes", "unknown", "main"].includes(diocese)) {
            showStatus("❌ That diocese name is reserved — pick another.", "error");
            return;
          }
        }
        if (!diocese) {
          showStatus("❌ Could not detect diocese for this parish — tap ▼ next to the diocese line to pick one.", "error");
          diocesePickerExpanded = true;
          refreshDioceseLine();
          dioceseCombo?.input?.focus?.();
          return;
        }
        resolvedDiocese = diocese;
        refreshDioceseLine();

        if (!parishPickerTouched && inferredKey) {
          keyInput.value = inferredKey;
          key = inferredKey;
          const hit = window.ph_parish_pickers?.lookupByKey?.(inferredKey);
          if (hit?.name && !nameInput.value.trim()) name = hit.name;
          if (!name) name = _inferDisplayNameFromUrl(pageUrl) || inferredKey;
        }
        // Parish registry wins over stale ph_last_diocese / hostname cache.
        const registryHit = window.ph_parish_pickers?.lookupByKey?.(key);
        if (registryHit?.diocese) {
          diocese = registryHit.diocese;
          if (!diocesePickerTouched) {
            resolvedDiocese = registryHit.diocese;
            dioceseCombo?.setValue(registryHit.diocese, registryHit.diocese.replace(/_/g, " "));
            refreshDioceseLine();
          }
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
        if (window.ph_parish_pickers?.isJunkParishKey?.(key)) {
          showStatus(
            "❌ That parish key looks like a dated PDF filename — use Find parish to pick the real parish (e.g. buncranaparish).",
            "error"
          );
          return;
        }
        const ensuredTerminal = _ensureTerminalPdfStep();
        if (_standaloneRecipeSteps().length === 0) {
          showStatus(
            "⚠️ No steps recorded yet — tap 💾 Step 2: Save this PDF (or 👉 Step 1 on a news page).",
            "warn"
          );
          return;
        }
        if (!ensuredTerminal.ok) {
          showStatus(
            "❌ Finish with PDF capture first — tap 💾 Step 2: Save this PDF, 📰 Save page as PDF, or 🖼️ image.",
            "error"
          );
          return;
        }
        if (ensuredTerminal.added) {
          globalThis.__phLastAutoTerminal = {
            added: true,
            action: ensuredTerminal.action || "download",
            at: new Date().toISOString(),
          };
          showStatus("✅ PDF step added automatically — sending…", "info");
        } else {
          globalThis.__phLastAutoTerminal = null;
        }
        const recorded = _standaloneRecipeSteps();
        const lastStep = recorded[recorded.length - 1];
        const lastAction = String(lastStep?.action || "").toLowerCase();
        if (
          !lastStep
          || (!_pdfTerminalActions.has(lastAction) && !_isHarvestClickTerminal(lastStep))
        ) {
          showStatus(
            "❌ Recipe must end with PDF capture: download, image, image_stack, print_to_pdf, crop_screenshot, or a Dropfiles/mDocs click.",
            "error"
          );
          return;
        }

        console.log(`Parish Trainer: pushing recipe for key=${key}, diocese=${diocese}, url=${pageUrl}`);
        void _flushRecordingSession();
        const recipe = buildStandaloneRecipe(key, name || key, diocese);
        const detected = detectPageType();
        let diagnosisSnapshot = null;
        if (globalThis.ph_recipe_diag?.runFullDiagnosis) {
          try {
            diagnosisSnapshot = await Promise.race([
              globalThis.ph_recipe_diag.runFullDiagnosis(),
              new Promise((resolve) => setTimeout(() => resolve(null), 300)),
            ]);
          } catch (diagErr) {
            console.warn("Parish Trainer: pre-push diagnosis skipped:", diagErr);
          }
        }
        diagnosisSnapshot = _slimDiagnosisForPush(diagnosisSnapshot);
        const sitePattern = (() => {
          const mem = window.ph_site_memory;
          if (mem?.patternPayloadFromPage) {
            return mem.patternPayloadFromPage(detected, recipe);
          }
          const lib = globalThis.PhPatternLibrary;
          if (!lib) return null;
          return {
            page: lib.fingerprintFromPage(detected),
            recipe: lib.fingerprintFromRecipe(recipe),
          };
        })();
        pushBtn.disabled = true;
        pushBtn.textContent = "⏳ Sending…";
        const _resetPushBtn = () => {
          pushBtn.disabled = false;
          pushBtn.textContent = "🚀 Send & test on GitHub";
        };
        const pushSafetyTimer = setTimeout(_resetPushBtn, 50000);
        const pushProgress15 = setTimeout(() => {
          if (pushBtn.disabled) showStatus("⏳ Still saving to GitHub… (check PAT in Settings if this hangs)", "info");
        }, 15000);
        _logSaveCycle("push_recipe", { parish_key: key, recipe }, { ok: "pending" });
        showStatus("⏳ Pushing recipe to GitHub…", "info");

        const _finishPushUi = (response, { isFollowup = false } = {}) => {
          if (!response?.ok) return;
          const verb = response.updated ? "updated" : "created";
          const path = response.filePath || `parishes/recipes/${key}.json`;
          const linkUrl = response.url || "";
          const linkPart = linkUrl ? ` → ${linkUrl}` : ` → ${path}`;

          if (response.stepsPreservedFromOld && !isFollowup) {
            showStatus(
              "⚠️ GitHub kept the OLD recipe steps — record new steps on this page, then Send & test again.",
              "warn"
            );
            showPostPushBanner(
              response,
              `⚠️ <strong>${name || key}</strong> — no new steps were sent; old recipe unchanged. Record PDF steps first.`,
              "warn"
            );
            return;
          }

          const dispatchAt = Date.now();
          if (response.dispatchOk) {
            dispatchErrorBanner.style.display = "none";
            showStatus(
              `✅ Recipe ${verb}! Saved — test on GitHub (usually 1–3 min, not the mega PDF).`,
              "ok"
            );
            showPostPushBanner(
              response,
              `⏳ <strong>${name || key}</strong> — single-parish test running (${0}s)…`
            );
            _startPostPushHarvestWatch(key, name || key, response, dispatchAt);
            try {
              chrome.runtime.sendMessage({
                type: "problems_refresh",
                parish_key: key,
                display_name: name || key,
                dispatch_at: dispatchAt,
              });
            } catch (_e) {
              // Side panel may be closed.
            }
          } else if (response.dispatchPending && !isFollowup) {
            showStatus(`✅ Recipe ${verb}! Saved to GitHub — starting harvest test…`, "ok");
            showPostPushBanner(
              response,
              `⏳ <strong>${name || key}</strong> — starting single-parish test…`
            );
            _startPostPushHarvestWatch(key, name || key, response, dispatchAt);
          } else if (response.dispatchError) {
            showDispatchErrorBanner(response.dispatchError);
            showStatus(
              `✅ Recipe ${verb}!${linkPart} ⚠️ Test harvest failed to start: ${response.dispatchError}`,
              "ok",
            );
            showPostPushBanner(
              response,
              "Recipe saved but GitHub test did not start — open Problems and tap ▶ Check result.",
              "warn"
            );
          } else if (!isFollowup) {
            showStatus(`✅ Recipe ${verb}!${linkPart}`, "ok");
            showPostPushBanner(
              response,
              "Recipe saved. Open Problems → ▶ Check result to test it.",
              "warn"
            );
          }
          if (response.patternLearned) {
            showStatus("📚 Pattern saved — similar parishes will get hints next time.", "ok");
          } else if (response.patternLearnError) {
            console.warn("Pattern learn failed:", response.patternLearnError);
          }
          if (!isFollowup) {
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
            const pushedSteps = recorded.length;
            lastPushedRecipeNote =
              `✅ Sent ${pushedSteps} step${pushedSteps === 1 ? "" : "s"} to GitHub — watch the Problems tab for the bulletin link.`;
            clearStandaloneRecipe();
            refreshStepCount();
            void checkStartUrlDrift();
          }
        };

        globalThis.__phOnPushFollowup = (followup) => {
          if (!followup || followup.type !== "push_recipe_followup") return;
          if (String(followup.parish_key || "") !== key) return;
          if (followup.patternLearned || followup.diagnosisSaved) {
            console.log("Parish Trainer: push followup extras", followup);
          }
        };

        const _sanitizeRecipeQuick = async (rawRecipe) => {
          try {
            return await Promise.race([
              new Promise((resolve) => {
                if (!chrome?.runtime?.sendMessage) {
                  resolve(rawRecipe);
                  return;
                }
                chrome.runtime.sendMessage({ type: "sanitize_recipe", recipe: rawRecipe }, (res) => {
                  resolve(res?.recipe || rawRecipe);
                });
              }),
              new Promise((resolve) => setTimeout(() => resolve(rawRecipe), 2000)),
            ]);
          } catch (_e) {
            return rawRecipe;
          }
        };

        const _runFastPush = async () => {
          try {
            const settings = await _storageGet(["gh_pat", "gh_repo"]);
            if (!settings.gh_pat) {
              showStatus("❌ GitHub PAT not configured. Open extension popup → Settings.", "error");
              return;
            }
            const pushMod = globalThis.phGithubRecipePush;
            if (!pushMod?.pushRecipe) {
              showStatus("❌ Reload extension (chrome://extensions) then refresh this page.", "error");
              return;
            }

            const recipeToPush = await _sanitizeRecipeQuick(recipe);
            showStatus("⏳ Saving recipe to GitHub…", "info");
            const pushResult = await pushMod.pushRecipe({
              gh_pat: settings.gh_pat,
              gh_repo: settings.gh_repo,
              parish_key: key,
              recipe: recipeToPush,
            });

            if (!pushResult.ok) {
              _logSaveCycle("push_recipe", { parish_key: key, recipe: recipeToPush }, pushResult);
              showStatus(`❌ ${pushResult.error}`, "error");
              return;
            }

            clearTimeout(pushSafetyTimer);
            clearTimeout(pushProgress15);
            _resetPushBtn();

            // Read the file back from GitHub so we never claim "saved" when it
            // went to the wrong folder or kept the old steps.
            const pushedRecipe = pushResult.recipe || recipeToPush;
            const intendedSteps = Array.isArray(pushedRecipe.steps) ? pushedRecipe.steps.length : 0;
            let savedSteps = intendedSteps;
            let savedPath = pushResult.filePath || "(unknown path)";
            if (pushMod.verifyRecipe) {
              showStatus("⏳ Confirming the save landed on GitHub…", "info");
              const verify = await pushMod.verifyRecipe({
                gh_pat: settings.gh_pat,
                gh_repo: settings.gh_repo,
                parish_key: key,
                expectedRecipe: pushedRecipe,
                expectedSteps: intendedSteps,
                expectedFolder: recipeToPush.diocese || "",
              });
              if (!verify.ok) {
                showStatus(
                  `❌ GitHub did NOT confirm the save (${verify.error}). Tap Send & test again in a few seconds.`,
                  "error"
                );
                return;
              }
              savedSteps = verify.savedSteps;
              savedPath = verify.filePath || savedPath;
              if (!verify.matches) {
                showStatus(
                  `⚠️ GitHub still shows the old recipe (${savedSteps} step(s), yours ${intendedSteps}). Wait 5 seconds and tap Send & test again.`,
                  "warn"
                );
                return;
              }
            }
            showStatus(
              `✅ Confirmed: ${savedSteps} step(s) saved to ${savedPath} — single-parish test starting (1–3 min)…`,
              "ok"
            );

            const dispatchAt = Date.now();
            const dispatchResult = await pushMod.dispatchHarvestTest({
              gh_pat: settings.gh_pat,
              gh_repo: settings.gh_repo,
              parish_key: key,
              diocese: recipeToPush.diocese || pushedRecipe.diocese || "",
            });

            const response = {
              ok: true,
              url: pushResult.url,
              filePath: pushResult.filePath,
              updated: pushResult.updated,
              dispatchOk: dispatchResult.ok,
              dispatchError: dispatchResult.ok ? "" : (dispatchResult.error || "Dispatch failed"),
              dispatchPending: !dispatchResult.ok,
              stepsPushed: Array.isArray(recipeToPush.steps) ? recipeToPush.steps.length : 0,
              stepsPreservedFromOld: false,
            };
            _logSaveCycle("push_recipe", { parish_key: key, recipe: recipeToPush }, response);
            _finishPushUi(response, { isFollowup: false });

            if (chrome?.runtime?.sendMessage) {
              chrome.runtime.sendMessage({
                type: "push_recipe_followup_work",
                parish_key: key,
                recipe: pushResult.recipe || recipeToPush,
                site_pattern: sitePattern,
                diagnosis_snapshot: diagnosisSnapshot,
                diagnosis_source: "push_recipe",
                dispatchOk: dispatchResult.ok,
                filePath: pushResult.filePath,
                updated: pushResult.updated,
                url: pushResult.url,
              }).catch(() => {});
            }
          } catch (pushErr) {
            _logSaveCycle("push_recipe", { parish_key: key, recipe }, { ok: false, error: String(pushErr) });
            showStatus(`❌ ${String(pushErr)}`, "error");
          } finally {
            clearTimeout(pushSafetyTimer);
            clearTimeout(pushProgress15);
            _resetPushBtn();
          }
        };
        void _runFastPush();
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
    if (message.type === "ph_ping" || message.type === "ping") return { ok: true };

    if (message.type === "toggle_toolbar") {
      try {
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
      } catch (err) {
        return { ok: false, reason: String(err) };
      }
    }

    if (message.type === "show_toolbar") {
      try {
        _ensureToolbar(true);
        void _markRecordingActive();
        return { ok: true };
      } catch (err) {
        return { ok: false, reason: String(err) };
      }
    }
    if (message.type === "ph_show_toolbar") {
      try {
        if (message.reason === "fix_now") {
          void _applyFixNowToolbar(message);
          return { ok: true };
        }
        const bar = _ensureToolbar(true);
        delete bar?.dataset?.phFixNow;
        delete bar?.dataset?.phParishName;
        void _markRecordingActive();
        if (_refreshParishPushForm) void _refreshParishPushForm();
        return { ok: true };
      } catch (err) {
        return { ok: false, reason: String(err) };
      }
    }
    if (message.type === "restore_recording_session") {
      void _restoreRecordingSessionFromStorage();
      return { ok: true };
    }

    if (message.type === "push_recipe_followup") {
      if (typeof globalThis.__phOnPushFollowup === "function") {
        globalThis.__phOnPushFollowup(message);
      }
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
    const cloudFmt = _detectCloudDateFormat(pick.label);
    if (cloudFmt || _isCloudFolderUrl(window.location.href)) {
      clickStep.date_format = cloudFmt || "YY.MM.DD";
      clickStep.cloud_folder = true;
    }
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
    if (!event.data || event.data.direction !== "from-isolated") return;
    // Ignore chrome runtime messages mirrored through postMessage — bridge_boot handles those.
    const mirroredType = event.data.message?.type;
    if (mirroredType && mirroredType !== "mark_element") return;
    _handleIncomingMessage(event.data.message);
  });

  const _phBridgeDispatch = (message, sendResponse) => {
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
    if (message.type === "ph_run_full_diagnosis") {
      void (async () => {
        try {
          if (!globalThis.ph_recipe_diag?.runFullDiagnosis) {
            sendResponse({ ok: false, reason: "Diagnosis kit not loaded — reload extension." });
            return;
          }
          const report = await globalThis.ph_recipe_diag.runFullDiagnosis();
          sendResponse({
            ok: true,
            text: globalThis.ph_recipe_diag.formatReport(report),
            report,
          });
        } catch (err) {
          sendResponse({ ok: false, reason: String(err) });
        }
      })();
      return true;
    }
    if (String(message?.type || "").startsWith("copilot_")) {
      void _handleCopilotMessage(message).then((result) => sendResponse(result));
      return true;
    }
    const result = _handleIncomingMessage(message);
    sendResponse(result);
    return true;
  };

  if (typeof globalThis.__phBridgeSetDispatch === "function") {
    globalThis.__phContentDispatch = _phBridgeDispatch;
    globalThis.__phBridgeSetDispatch(_phBridgeDispatch);
  } else if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) =>
      _phBridgeDispatch(message, sendResponse)
    );
  }

  globalThis.__phShowToolbar = () => {
    _ensureToolbar(true);
    void _markRecordingActive();
  };

  globalThis.__phDiagExport = () => {
    const pageUrl = _pageUrlForParishDetection();
    let parishKey = "";
    try {
      const inferred = _inferParishKeyFromUrl(pageUrl);
      parishKey = String(inferred || "").trim().toLowerCase();
    } catch (_e) {
      parishKey = "";
    }
    const detected = detectPageType();
    let htmlScan = null;
    try {
      if (globalThis.PhHtmlFingerprint?.scanPage) {
        htmlScan = globalThis.PhHtmlFingerprint.scanPage(document);
      }
    } catch (_e) {
      htmlScan = null;
    }
    const recipeDetail = _standaloneRecipeSteps();
  const sessionDetail = recipeSteps.map((s) => ({
      action: s.action || "",
      label: s.label || "",
      text: s.text || "",
    }));
    return {
      page_url: pageUrl,
      parish_key: parishKey,
      page_type: detected,
      html_fingerprint_scan: htmlScan,
      html_fingerprint_id: detected.htmlFingerprint || htmlScan?.best?.id || "",
      recipe_steps: recipeDetail,
      recipe_steps_detail: recipeDetail,
      session_ui_steps: recipeSteps.length,
      session_steps_detail: sessionDetail,
      standalone_start_url: standaloneStartUrl || "",
      in_standalone_mode: _inStandaloneMode(),
      toolbar_visible: Boolean(_getToolbarNode() && _getToolbarNode().style.display !== "none"),
      last_auto_terminal: globalThis.__phLastAutoTerminal || null,
    };
  };

  document.addEventListener("ph-show-toolbar", () => {
    try {
      globalThis.__phShowToolbar();
    } catch (err) {
      if (globalThis.ph_toolbar_diag?.setError) {
        globalThis.ph_toolbar_diag.setError(String(err));
      }
    }
  });

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
        let href = clickData.href;
        const bulletinHref = _hrefFromBulletinClick(target);
        if (bulletinHref) href = bulletinHref;
        const step = _enrichClickStepForWeeklyReplay(
          {
            action: "click",
            selector: buildStableLinkSelector(target),
            href,
            text,
          },
          target
        );
        if (clickData.css_path && clickData.css_path !== step.selector) {
          step.fallback_selectors = Array.from(
            new Set([...(step.fallback_selectors || []), clickData.css_path])
          );
        }

        if (href && _looksLikeBulletinDownloadUrl(href, text)) {
          if (step.pick_strategy) {
            standaloneAddStep(step, "click", label);
            void _persistRecordingSession();
            showStatus(
              "✅ Newest bulletin link recorded — harvest downloads it each Sunday.",
              "ok"
            );
          } else {
            _standaloneAddClickAndDownload(step, href, label, null);
          }
          _ensureToolbar(true);
          window.dispatchEvent(
            new CustomEvent("ph-recording-continued", {
              detail: { stepCount: _standaloneRecipeSteps().length },
            })
          );
          return;
        }
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
    if (_isEditorPageUrl()) return;
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
