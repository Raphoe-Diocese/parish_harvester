(() => {
  if (globalThis.__phBridgeInstalled) {
    return;
  }
  globalThis.__phBridgeInstalled = true;

  const TOOLBAR_ID = "ph-floating-toolbar";

  globalThis.__phGetToolbarMount = () => {
    let mount = document.getElementById("ph-trainer-mount");
    if (!mount) {
      mount = document.createElement("div");
      mount.id = "ph-trainer-mount";
      mount.setAttribute("data-ph-trainer", "1");
      mount.style.cssText = [
        "position:fixed!important",
        "top:0!important",
        "left:0!important",
        "width:100%!important",
        "height:0!important",
        "z-index:2147483647!important",
        "pointer-events:none!important",
        "margin:0!important",
        "padding:0!important",
        "border:none!important",
      ].join(";");
      const root = document.body || document.documentElement;
      root.appendChild(mount);
    }
    return mount;
  };

  let dispatch = null;
  const pendingUpgrades = [];

  const isPing = (type) => type === "ph_ping" || type === "ping";
  const isToolbarMessage = (type) => type === "show_toolbar" || type === "toggle_toolbar" || type === "ph_show_toolbar";

  const _getToolbarEl = () => {
    const mount = document.getElementById("ph-trainer-mount");
    if (mount) {
      const inMount = mount.querySelector(`#${TOOLBAR_ID}`);
      if (inMount) return inMount;
    }
    return document.getElementById(TOOLBAR_ID);
  };

  const _showStubToolbar = () => {
    let bar = _getToolbarEl();
    if (!bar) {
      bar = document.createElement("div");
      bar.id = TOOLBAR_ID;
      bar.dataset.phStub = "1";
      bar.style.cssText = [
        "position:fixed",
        "top:16px",
        "right:16px",
        "z-index:2147483647",
        "display:flex",
        "flex-direction:column",
        "gap:8px",
        "min-width:240px",
        "max-width:340px",
        "padding:12px 14px",
        "border-radius:10px",
        "background:#111827",
        "color:#f9fafb",
        "border:2px solid #f59e0b",
        "box-shadow:0 12px 40px rgba(0,0,0,.55)",
        "font:12px/1.35 system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif",
        "pointer-events:auto",
      ].join(";");
      bar.innerHTML = [
        '<div style="font-weight:700;font-size:14px;">Parish Trainer</div>',
        '<div id="ph-stub-status" style="opacity:.95;">Loading recipe toolbar…</div>',
      ].join("");
      globalThis.__phGetToolbarMount().appendChild(bar);
      if (globalThis.ph_toolbar_diag?.attachStubPanel) {
        globalThis.ph_toolbar_diag.attachStubPanel(bar);
      }
    }
    bar.dataset.phHidden = "false";
    bar.style.display = "flex";
    return bar;
  };

  const _showStubError = (message) => {
    if (globalThis.ph_toolbar_diag?.setError) {
      globalThis.ph_toolbar_diag.setError(message);
    }
    const bar = _showStubToolbar();
    const status = bar.querySelector("#ph-stub-status");
    if (status) {
      status.textContent = String(message || "Trainer failed to load. Refresh the page and try again.");
      status.style.color = "#fca5a5";
    }
    bar.style.borderColor = "#ef4444";
  };

  const _handleStubToolbar = (type) => {
    const bar = _getToolbarEl();
    if (type === "toggle_toolbar" && bar && bar.dataset.phHidden !== "true" && bar.style.display !== "none") {
      bar.dataset.phHidden = "true";
      bar.style.display = "none";
      return;
    }
    _showStubToolbar();
  };

  const _upgradeToolbar = (message) => {
    if (!dispatch) {
      pendingUpgrades.push(message);
      return;
    }
    setTimeout(() => {
      try {
        dispatch(message, (response) => {
          const bar = _getToolbarEl();
          const fullReady = bar && bar.dataset.phStub !== "1" && bar.isConnected;
          if (!fullReady) {
            _showStubError(
              (response && (response.reason || response.error)) ||
                "Full trainer did not mount on this page."
            );
          }
        });
      } catch (err) {
        _showStubError(String(err));
      }
    }, 30);
  };

  const _flushPendingUpgrades = () => {
    if (!dispatch) return;
    while (pendingUpgrades.length) {
      const message = pendingUpgrades.shift();
      if (!message) continue;
      _upgradeToolbar(message);
    }
  };

  const _waitForDispatch = (message, sendResponse, attempt = 0) => {
    if (dispatch) {
      try {
        dispatch(message, sendResponse);
      } catch (err) {
        try {
          sendResponse({ ok: false, reason: String(err) });
        } catch (_e) {
          // Response channel may already be closed.
        }
      }
      return;
    }
    if (attempt >= 180) {
      try {
        sendResponse({
          ok: false,
          reason: "Parish Trainer did not finish loading on this page. Refresh the tab, then open the extension again.",
        });
      } catch (_e) {
        // no-op
      }
      return;
    }
    setTimeout(() => _waitForDispatch(message, sendResponse, attempt + 1), 100);
  };

  globalThis.__phBridgeSetDispatch = (fn) => {
    dispatch = typeof fn === "function" ? fn : null;
    _flushPendingUpgrades();
    const stub = _getToolbarEl();
    if (stub?.dataset?.phStub === "1") {
      const status = stub.querySelector("#ph-stub-status");
      if (status) status.textContent = "Upgrading to full trainer…";
    }
  };

  document.addEventListener("ph-show-toolbar", () => {
    _handleStubToolbar("show_toolbar");
    _upgradeToolbar({ type: "show_toolbar" });
  });

  if (typeof chrome !== "undefined" && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      const type = message?.type;
      if (type === "ph_bridge_ready") {
        sendResponse({ ok: Boolean(dispatch) });
        return true;
      }
      if (isPing(type)) {
        sendResponse({ ok: true, bridge_ready: Boolean(dispatch) });
        return true;
      }
      if (isToolbarMessage(type)) {
        if (dispatch) {
          try {
            dispatch(message, sendResponse);
            return true;
          } catch (err) {
            if (globalThis.ph_toolbar_diag?.setError) {
              globalThis.ph_toolbar_diag.setError(String(err));
            }
            _handleStubToolbar(type);
            sendResponse({ ok: true, toolbar: true, full: false, reason: String(err) });
            return true;
          }
        }
        _handleStubToolbar(type);
        _upgradeToolbar(message);
        const bar = _getToolbarEl();
        sendResponse({ ok: true, toolbar: Boolean(bar), full: false });
        return true;
      }
      if (!dispatch) {
        _waitForDispatch(message, sendResponse);
        return true;
      }
      try {
        const keepChannel = dispatch(message, sendResponse);
        return keepChannel !== false;
      } catch (err) {
        sendResponse({ ok: false, reason: String(err) });
        return true;
      }
    });
  }
})();
