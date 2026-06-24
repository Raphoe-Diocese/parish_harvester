(() => {
  if (globalThis.ph_toolbar_diag) {
    return;
  }

  const _line = (label, value) => `${label}: ${value}`;

  const _extVersion = () => {
    try {
      return chrome.runtime.getManifest().version;
    } catch (_e) {
      return "unknown";
    }
  };

  const _toolbarEl = () => {
    const mount = document.getElementById("ph-trainer-mount");
    if (mount) {
      const inMount = mount.querySelector("#ph-floating-toolbar");
      if (inMount) return inMount;
    }
    return document.getElementById("ph-floating-toolbar");
  };

  const collect = async (extra = {}) => {
    const bar = _toolbarEl();
    const rect = bar ? bar.getBoundingClientRect() : null;
    const mount = document.getElementById("ph-trainer-mount");
    const pageUrl = (() => {
      try {
        return window.location.href;
      } catch (_e) {
        return "";
      }
    })();

    let ghPat = false;
    let ghRepo = "";
    if (typeof chrome !== "undefined" && chrome.storage?.local) {
      try {
        const stored = await new Promise((resolve) => {
          chrome.storage.local.get(["gh_pat", "gh_repo"], (r) => resolve(r || {}));
        });
        ghPat = Boolean(String(stored.gh_pat || "").trim());
        ghRepo = String(stored.gh_repo || "Raphoe-Diocese/parish_harvester").trim();
      } catch (_e) {
        // no-op
      }
    }

    let bridgePing = null;
    try {
      bridgePing = {
        ok: Boolean(globalThis.__phBridgeInstalled),
        bridge_ready: Boolean(globalThis.__phContentDispatch),
      };
    } catch (err) {
      bridgePing = { ok: false, error: String(err) };
    }

    const stepsCount =
      typeof globalThis.__phStandaloneStepCount === "function"
        ? globalThis.__phStandaloneStepCount()
        : null;

    return {
      collected_at: new Date().toISOString(),
      extension_version: _extVersion(),
      page_url: pageUrl,
      bridge_installed: Boolean(globalThis.__phBridgeInstalled),
      content_installed: Boolean(globalThis.__phContentInstalled),
      content_dispatch: Boolean(globalThis.__phContentDispatch),
      mount_present: Boolean(mount),
      mount_connected: Boolean(mount?.isConnected),
      toolbar_present: Boolean(bar),
      toolbar_connected: Boolean(bar?.isConnected),
      toolbar_mode: bar?.dataset?.phStub === "1" ? "stub" : bar?.dataset?.phMinimal === "1" ? "minimal" : bar ? "full" : "missing",
      toolbar_minimal: bar?.dataset?.phMinimal === "1",
      toolbar_display: bar?.style?.display || "n/a",
      toolbar_hidden: bar?.dataset?.phHidden || "n/a",
      toolbar_rect: rect
        ? `${Math.round(rect.width)}x${Math.round(rect.height)} @ ${Math.round(rect.left)},${Math.round(rect.top)}`
        : "not visible",
      toolbar_on_screen:
        rect && rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight,
      last_error: String(globalThis.__phLastToolbarError || "").trim(),
      bridge_ping_ok: bridgePing?.ok === true,
      bridge_ping_ready: bridgePing?.bridge_ready === true,
      gh_pat: ghPat,
      gh_repo: ghRepo,
      recipe_steps: stepsCount,
      user_agent: navigator.userAgent || "",
      ...extra,
    };
  };

  const formatLines = (data) => {
    const d = data || {};
    return [
      "Parish Trainer toolbar diagnostic",
      "===============================",
      _line("Time", d.collected_at || "n/a"),
      _line("Extension", d.extension_version || "n/a"),
      _line("Page URL", d.page_url || "n/a"),
      _line("Bridge installed", d.bridge_installed ? "yes" : "no"),
      _line("Content installed", d.content_installed ? "yes" : "no"),
      _line("Content dispatch", d.content_dispatch ? "yes" : "no"),
      _line("Mount on page", d.mount_present ? (d.mount_connected ? "yes (connected)" : "yes (detached)") : "no"),
      _line("Toolbar element", d.toolbar_present ? (d.toolbar_connected ? "yes (connected)" : "yes (detached)") : "MISSING"),
      _line("Toolbar mode", d.toolbar_mode || "n/a"),
      d.toolbar_minimal ? _line("Minimal trainer", "yes (full UI failed — simplified buttons active)") : null,
      _line("Toolbar display", d.toolbar_display || "n/a"),
      _line("Toolbar on screen", d.toolbar_on_screen ? "yes" : "NO — likely hidden or zero size"),
      _line("Toolbar rect", d.toolbar_rect || "n/a"),
      _line("Bridge ping", d.bridge_ping_ok ? (d.bridge_ping_ready ? "ok (full ready)" : "ok (stub only)") : "failed"),
      _line("GitHub PAT", d.gh_pat ? "yes" : "no"),
      _line("GitHub repo", d.gh_repo || "n/a"),
      _line("Recipe steps", d.recipe_steps == null ? "n/a" : String(d.recipe_steps)),
      d.last_error ? _line("Last error", d.last_error) : null,
      "",
      "Paste this block to your AI assistant or Franky.",
    ].filter(Boolean);
  };

  const setError = (message) => {
    globalThis.__phLastToolbarError = String(message || "").trim();
  };

  const _renderInto = async (container, { autoRun = true } = {}) => {
    if (!container) return;
    const output = container.querySelector(".ph-diag-output") || document.createElement("div");
    output.className = "ph-diag-output";
    output.style.cssText =
      "margin-top:6px;font-size:9px;line-height:1.45;color:#cbd5e1;white-space:pre-wrap;word-break:break-word;max-height:140px;overflow:auto;background:#0f172a;border:1px solid #374151;border-radius:4px;padding:6px;";

    const run = async () => {
      output.textContent = "Running diagnostics…";
      const data = await collect();
      output.textContent = formatLines(data).join("\n");
      container.dataset.phDiagText = output.textContent;
    };

    const btnRow = container.querySelector(".ph-diag-buttons");
    if (!btnRow) {
      const row = document.createElement("div");
      row.className = "ph-diag-buttons";
      row.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-top:4px;";

      const mkBtn = (label, bg, handler) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = label;
        btn.style.cssText = [
          "border:none",
          "border-radius:5px",
          "padding:4px 8px",
          "background:" + bg,
          "color:#fff",
          "cursor:pointer",
          "font-size:10px",
          "font-family:inherit",
        ].join(";");
        btn.addEventListener("click", handler);
        return btn;
      };

      row.appendChild(mkBtn("Run diagnostics", "#2563eb", () => void run()));
      row.appendChild(
        mkBtn("Copy for AI", "#374151", () => {
          const text = container.dataset.phDiagText || output.textContent || "";
          navigator.clipboard.writeText(text).then(() => {
            output.textContent = (container.dataset.phDiagText || "") + "\n\n✅ Copied to clipboard.";
          }).catch((err) => {
            setError(String(err));
            output.textContent = (container.dataset.phDiagText || "") + "\n\n❌ Copy failed.";
          });
        })
      );
      row.appendChild(
        mkBtn("Retry full toolbar", "#16a34a", () => {
          if (typeof globalThis.__phShowToolbar === "function") {
            try {
              globalThis.__phShowToolbar();
            } catch (err) {
              setError(String(err));
            }
          }
          document.dispatchEvent(new CustomEvent("ph-show-toolbar"));
          setTimeout(() => void run(), 500);
        })
      );
      container.appendChild(row);
    }

    if (!output.parentNode) container.appendChild(output);
    if (autoRun) await run();
  };

  const attachPanel = (parentEl, options = {}) => {
    if (!parentEl) return null;
    const details = document.createElement("details");
    details.className = "ph-toolbar-diag";
    details.style.cssText = [
      "background:#1e293b",
      "border:1px solid #475569",
      "border-radius:6px",
      "overflow:hidden",
    ].join(";");
    if (options.open) details.open = true;

    const summary = document.createElement("summary");
    summary.textContent = "🔍 Diagnostics (bridge / visibility)";
    summary.style.cssText = "padding:6px 8px;cursor:pointer;font-size:10px;font-weight:600;color:#93c5fd;list-style-position:inside;";
    details.appendChild(summary);

    const inner = document.createElement("div");
    inner.style.cssText = "padding:6px 8px;border-top:1px solid #374151;";
    details.appendChild(inner);

    parentEl.appendChild(details);
    void _renderInto(inner, options);
    return details;
  };

  const attachStubPanel = (bar) => {
    if (!bar || bar.querySelector(".ph-toolbar-diag")) return;
    const wrap = document.createElement("div");
    wrap.style.cssText = "margin-top:8px;";
    bar.appendChild(wrap);
    attachPanel(wrap, { open: true, autoRun: true });
  };

  globalThis.ph_toolbar_diag = {
    collect,
    formatLines,
    setError,
    attachPanel,
    attachStubPanel,
    renderInto: _renderInto,
  };
})();
