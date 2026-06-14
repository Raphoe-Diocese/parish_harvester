/**
 * Training Copilot — lives on the floating toolbar ON the parish website.
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
    const wrap = document.createElement("div");
    wrap.id = "ph-toolbar-copilot";
    wrap.style.cssText = [
      "background:#0f172a",
      "border:1px solid #0e7490",
      "border-radius:8px",
      "padding:8px",
      "margin-bottom:6px",
    ].join(";");

    const title = document.createElement("div");
    title.style.cssText = "font-size:11px;font-weight:700;color:#67e8f9;margin-bottom:6px;";
    title.textContent = "🤖 Copilot — on this page";
    wrap.appendChild(title);

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
    wrap.appendChild(parishRow);

    const memoryLine = document.createElement("div");
    memoryLine.style.cssText = "font-size:9px;color:#fde68a;margin-bottom:6px;display:none;line-height:1.4;";
    wrap.appendChild(memoryLine);

    const chatEl = document.createElement("div");
    chatEl.style.cssText = "max-height:140px;overflow-y:auto;background:#111827;border:1px solid #334155;border-radius:6px;padding:6px;margin-bottom:6px;font-size:10px;line-height:1.45;";
    wrap.appendChild(chatEl);

    const appendMsg = (role, text) => {
      const div = document.createElement("div");
      div.style.cssText = role === "user"
        ? "margin:0 0 6px 12px;padding:5px 6px;background:#1d4ed8;color:#eff6ff;border-radius:6px;"
        : "margin:0 0 6px 0;padding:5px 6px;background:#1e293b;color:#e5e7eb;border-radius:6px;";
      div.textContent = text;
      chatEl.appendChild(div);
      chatEl.scrollTop = chatEl.scrollHeight;
    };

    const inputRow = document.createElement("div");
    inputRow.style.cssText = "display:flex;gap:4px;margin-bottom:6px;";
    const inputEl = document.createElement("input");
    inputEl.type = "text";
    inputEl.placeholder = "Ask: where is the bulletin?";
    inputEl.style.cssText = "flex:1;border:1px solid #374151;border-radius:4px;padding:5px;background:#0f172a;color:#f9fafb;font-size:10px;font-family:inherit;";
    const sendBtn = document.createElement("button");
    sendBtn.type = "button";
    sendBtn.textContent = "Send";
    sendBtn.style.cssText = "width:auto;padding:5px 8px;font-size:10px;background:#2563eb;border:none;border-radius:4px;color:#fff;cursor:pointer;";
    inputRow.appendChild(inputEl);
    inputRow.appendChild(sendBtn);
    wrap.appendChild(inputRow);

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
    const analyseBtn = mkBtn("🔍 Analyse", "#0f766e");
    const highlightBtn = mkBtn("🟡 Highlight", "#374151", true);
    const recordBtn = mkBtn("✅ Record", "#16a34a", true);
    const pinBtn = mkBtn("📌 Pin", "#374151", true);
    const clickBtn = mkBtn("👆 Click", "#7c3aed", true);
    [analyseBtn, highlightBtn, recordBtn, pinBtn, clickBtn].forEach((b) => btnRow.appendChild(b));
    wrap.appendChild(btnRow);

    let _ctx = null;
    let _parishes = [];

    const setActions = (on) => {
      [highlightBtn, recordBtn, pinBtn, clickBtn].forEach((b) => {
        b.disabled = !on;
        b.style.opacity = on ? "1" : "0.5";
      });
    };

    const runAnalyse = async () => {
      appendMsg("system", "⏳ Looking at this page…");
      const res = await api.scan();
      if (!res?.ok) {
        appendMsg("assistant", "❌ Could not scan — refresh the page.");
        setActions(false);
        return;
      }
      _ctx = res.context || null;
      appendMsg("assistant", res.advice || res.context?.advice || "Done.");
      setActions(Boolean(_ctx?.best || _ctx?.pageBrief?.bulletinOnPage));
      if (api.showStatus) api.showStatus("✅ Copilot analysed this page.", "info");
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
        void window.ph_copilot?.getMemory?.(p.key).then((mem) => {
          if (mem?.lastIssue) {
            memoryLine.style.display = "block";
            memoryLine.textContent = `⚠️ Last problem: ${mem.lastIssue}`;
          } else {
            memoryLine.style.display = "none";
          }
        });
      } catch (_e) { /* ignore */ }
    });

    parishLoad.addEventListener("click", () => { void refreshParishes(); });

    sendBtn.addEventListener("click", () => {
      const t = inputEl.value.trim();
      if (!t) return;
      inputEl.value = "";
      appendMsg("user", t);
      appendMsg("assistant", window.ph_copilot?.replyToChat?.(t, _ctx) || "Click Analyse.");
      if (/analyse|look|help|see|bulletin|confus/i.test(t)) void runAnalyse();
    });
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); sendBtn.click(); }
    });

    analyseBtn.addEventListener("click", () => { void runAnalyse(); });
    highlightBtn.addEventListener("click", () => { void api.highlight(); });
    recordBtn.addEventListener("click", async () => {
      const r = await api.record();
      appendMsg("system", r?.ok ? "✅ Recorded in recipe." : `❌ ${r?.reason || "failed"}`);
    });
    pinBtn.addEventListener("click", async () => {
      const r = await api.pin();
      appendMsg("system", r?.ok ? "📌 Pinned." : `❌ ${r?.reason || "failed"}`);
      if (r?.ok) void runAnalyse();
    });
    clickBtn.addEventListener("click", async () => {
      const r = await api.click();
      appendMsg("system", r?.ok ? "✅ Clicked." : `❌ ${r?.reason || "failed"}`);
    });

    mountEl.appendChild(wrap);
    appendMsg("system", "I'm on the page with you. Click Analyse when ready.");
    void refreshParishes();
    void runAnalyse();

    return { refreshParishes, runAnalyse };
  };

  window.ph_buildToolbarCopilot = buildToolbarCopilot;
})();
