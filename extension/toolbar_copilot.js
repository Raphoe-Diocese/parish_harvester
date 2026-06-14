/**
 * Optional page help — collapsed by default. No chat; one-click analyse only.
 */
(() => {
  const EVIDENCE_FILES = {
    "Derry Diocese": "parishes/derry_diocese_bulletin_urls.txt",
    "Down and Connor": "parishes/down_and_connor_diocese_bulletin_urls.txt",
    "Raphoe Diocese": "parishes/raphoe_diocese_bulletin_urls.txt",
  };

  const _slug = (dioceseName) => {
    const map = {
      "Derry Diocese": "derry",
      "Down and Connor": "down_and_connor",
      "Raphoe Diocese": "raphoe",
    };
    return map[dioceseName] || dioceseName.toLowerCase().replace(/[^a-z0-9]+/g, "_");
  };

  const _urlToKey = (url, name) => {
    try {
      const host = new URL(url).hostname.toLowerCase().replace(/^www\d*\./, "");
      const seg = host.split(".")[0] || "";
      if (seg) return seg;
    } catch (_e) { /* fall through */ }
    return String(name || "").toLowerCase().replace(/[^a-z0-9]+/g, "_");
  };

  const _parseEvidence = (text, dioceseName) => {
    const parishes = [];
    let cur = null;
    for (const rawLine of text.split("\n")) {
      const line = rawLine.trim();
      const nameMatch = line.match(/^#\s*---\s*(.+?)\s*---\s*$/);
      if (nameMatch) {
        if (cur) parishes.push(cur);
        cur = { name: nameMatch[1], diocese: dioceseName, pageUrl: null, keyOverride: null, bulletinUrls: [], key: null };
        continue;
      }
      if (!cur) continue;
      const pageMatch = line.match(/^#\s*page:\s*(.+)$/i);
      if (pageMatch) { cur.pageUrl = pageMatch[1].trim(); continue; }
      const keyMatch = line.match(/^#\s*key:\s*(.+)$/i);
      if (keyMatch) { cur.keyOverride = keyMatch[1].trim(); continue; }
      if (line.startsWith("#") || !line) continue;
      cur.bulletinUrls.push(line);
    }
    if (cur) parishes.push(cur);
    for (const p of parishes) {
      const u = p.bulletinUrls[0] || p.pageUrl || "";
      p.key = p.keyOverride || _urlToKey(u, p.name);
      p.dioceseSlug = _slug(dioceseName);
    }
    return parishes;
  };

  const loadParishList = async (ghRepo) => {
    const repo = String(ghRepo || "Raphoe-Diocese/parish_harvester").trim();
    const all = [];
    for (const [dioceseName, path] of Object.entries(EVIDENCE_FILES)) {
      try {
        const resp = await fetch(`https://raw.githubusercontent.com/${repo}/main/${path}`);
        if (!resp.ok) continue;
        const text = await resp.text();
        all.push(..._parseEvidence(text, dioceseName));
      } catch (_e) { /* skip */ }
    }
    all.sort((a, b) => a.name.localeCompare(b.name));
    return all;
  };

  const buildToolbarCopilot = (mountEl, api) => {
    const wrap = document.createElement("details");
    wrap.id = "ph-toolbar-copilot";
    wrap.open = false;
    wrap.style.cssText = [
      "background:#0f172a",
      "border:1px solid #334155",
      "border-radius:8px",
      "margin-top:6px",
    ].join(";");

    const summary = document.createElement("summary");
    summary.style.cssText = "padding:8px;cursor:pointer;font-size:10px;font-weight:600;color:#9ca3af;list-style-position:inside;";
    summary.textContent = "Need help finding the bulletin? (optional)";
    wrap.appendChild(summary);

    const inner = document.createElement("div");
    inner.style.cssText = "padding:0 8px 8px;";

    const tipLine = document.createElement("div");
    tipLine.style.cssText = "font-size:10px;color:#cbd5e1;line-height:1.45;margin-bottom:6px;";
    tipLine.textContent = "Use the green buttons above first. Open this only if you are stuck.";
    inner.appendChild(tipLine);

    const parishRow = document.createElement("div");
    parishRow.style.cssText = "display:flex;gap:4px;margin-bottom:6px;flex-wrap:wrap;";
    const parishSelect = document.createElement("select");
    parishSelect.style.cssText = "flex:1;min-width:120px;border:1px solid #374151;border-radius:4px;padding:4px;background:#1e293b;color:#f9fafb;font-size:10px;";
    const parishLoad = document.createElement("button");
    parishLoad.type = "button";
    parishLoad.textContent = "↺";
    parishLoad.title = "Reload parish list";
    parishLoad.style.cssText = "width:auto;padding:4px 8px;font-size:10px;background:#374151;border:none;border-radius:4px;color:#fff;cursor:pointer;";
    parishRow.appendChild(parishSelect);
    parishRow.appendChild(parishLoad);
    inner.appendChild(parishRow);

    const adviceLine = document.createElement("div");
    adviceLine.style.cssText = "font-size:10px;color:#e5e7eb;background:#111827;border:1px solid #334155;border-radius:6px;padding:6px;margin-bottom:6px;line-height:1.45;display:none;";
    inner.appendChild(adviceLine);

    const btnRow = document.createElement("div");
    btnRow.style.cssText = "display:flex;gap:4px;flex-wrap:wrap;";
    const mkBtn = (label, bg, disabled = false) => {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = label;
      b.disabled = disabled;
      b.style.cssText = `width:auto;padding:4px 7px;font-size:9px;background:${bg};border:none;border-radius:4px;color:#fff;cursor:pointer;opacity:${disabled ? 0.5 : 1};`;
      return b;
    };
    const analyseBtn = mkBtn("🔍 Analyse page", "#0f766e");
    const highlightBtn = mkBtn("🟡 Highlight", "#374151", true);
    const recordBtn = mkBtn("✅ Record pick", "#16a34a", true);
    const pinBtn = mkBtn("📌 Pin link", "#374151", true);
    const clickBtn = mkBtn("👆 Click pick", "#7c3aed", true);
    [analyseBtn, highlightBtn, recordBtn, pinBtn, clickBtn].forEach((b) => btnRow.appendChild(b));
    inner.appendChild(btnRow);

    wrap.appendChild(inner);

    let _ctx = null;
    let _parishes = [];

    const setActions = (on) => {
      [highlightBtn, recordBtn, pinBtn, clickBtn].forEach((b) => {
        b.disabled = !on;
        b.style.opacity = on ? "1" : "0.5";
      });
    };

    const runAnalyse = async () => {
      adviceLine.style.display = "block";
      adviceLine.textContent = "⏳ Looking at links on this page…";
      const res = await api.scan();
      if (!res?.ok) {
        adviceLine.textContent = "Could not scan — refresh the page and try again.";
        setActions(false);
        return;
      }
      _ctx = res.context || null;
      adviceLine.textContent = res.advice || res.context?.advice || "Done.";
      setActions(Boolean(_ctx?.best || _ctx?.pageBrief?.bulletinOnPage));
      if (api.showStatus) api.showStatus("✅ Page analysed.", "info");
    };

    const fillParishSelect = (parishes, selectedKey) => {
      parishSelect.replaceChildren();
      const ph = document.createElement("option");
      ph.value = "";
      ph.textContent = "— pick parish (optional) —";
      parishSelect.appendChild(ph);
      for (const p of parishes) {
        const opt = document.createElement("option");
        opt.value = JSON.stringify({ key: p.key, name: p.name, diocese: p.dioceseSlug || _slug(p.diocese) });
        opt.textContent = `${p.name} (${p.diocese})`;
        if (selectedKey && p.key === selectedKey) opt.selected = true;
        parishSelect.appendChild(opt);
      }
    };

    const refreshParishes = async () => {
      parishSelect.disabled = true;
      const repo = await api.getGhRepo?.();
      _parishes = await loadParishList(repo);
      fillParishSelect(_parishes, api.getParishKey?.());
      parishSelect.disabled = false;
    };

    parishSelect.addEventListener("change", () => {
      if (!parishSelect.value) return;
      try {
        const p = JSON.parse(parishSelect.value);
        api.onParishPicked?.(p);
      } catch (_e) { /* ignore */ }
    });

    parishLoad.addEventListener("click", () => { void refreshParishes(); });
    analyseBtn.addEventListener("click", () => { void runAnalyse(); });
    highlightBtn.addEventListener("click", () => { void api.highlight(); });
    recordBtn.addEventListener("click", async () => {
      const r = await api.record();
      if (api.showStatus) {
        api.showStatus(r?.ok ? "✅ Recorded in recipe." : `❌ ${r?.reason || "failed"}`, r?.ok ? "ok" : "error");
      }
    });
    pinBtn.addEventListener("click", async () => {
      const r = await api.pin();
      if (api.showStatus) {
        api.showStatus(r?.ok ? "📌 Link pinned." : `❌ ${r?.reason || "failed"}`, r?.ok ? "ok" : "error");
      }
      if (r?.ok) void runAnalyse();
    });
    clickBtn.addEventListener("click", async () => {
      const r = await api.click();
      if (api.showStatus) {
        api.showStatus(r?.ok ? "✅ Clicked." : `❌ ${r?.reason || "failed"}`, r?.ok ? "ok" : "error");
      }
    });

    mountEl.appendChild(wrap);
    void refreshParishes();

    return { refreshParishes, runAnalyse };
  };

  window.ph_buildToolbarCopilot = buildToolbarCopilot;
})();
