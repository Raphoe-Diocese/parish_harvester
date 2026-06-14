/**
 * Training Copilot — side panel UI
 */
(() => {
  const chatEl = document.getElementById("ai-chat");
  const inputEl = document.getElementById("ai-input");
  const analyseBtn = document.getElementById("ai-analyse");
  const highlightBtn = document.getElementById("copilot-highlight");
  const recordBtn = document.getElementById("copilot-record");
  const pinBtn = document.getElementById("copilot-pin");
  const clickBtn = document.getElementById("copilot-click");
  const sendBtn = document.getElementById("ai-send");

  if (!chatEl || !analyseBtn) return;

  let _lastContext = null;

  const appendMsg = (role, text) => {
    const div = document.createElement("div");
    div.className = `ai-msg ${role}`;
    div.textContent = text;
    chatEl.appendChild(div);
    chatEl.scrollTop = chatEl.scrollHeight;
  };

  const setActionState = (enabled) => {
    [highlightBtn, recordBtn, pinBtn, clickBtn].forEach((btn) => {
      if (btn) btn.disabled = !enabled;
    });
  };

  const dispatch = (payload) => new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tab = tabs[0];
      if (!tab?.id || !/^https?:\/\//i.test(tab.url || "")) {
        resolve({ ok: false, reason: "unsupported_url" });
        return;
      }
      chrome.runtime.sendMessage({
        type: "dispatch_to_tab",
        tabId: tab.id,
        payload,
        allowInject: true,
      }, (result) => {
        resolve(result || { ok: false });
      });
    });
  });

  const runAnalyse = async () => {
    appendMsg("system", "⏳ Scanning page…");
    const result = await dispatch({ type: "copilot_scan" });
    if (!result?.ok) {
      appendMsg("assistant", "❌ Could not read this tab. Refresh the parish page and try again.");
      setActionState(false);
      return;
    }
    _lastContext = result.context || null;
    const advice = String(result.context?.advice || result.advice || "No advice.");
    appendMsg("assistant", advice);
    setActionState(Boolean(result.context?.best));
    if (typeof window._spSetStatus === "function") {
      window._spSetStatus("✅ Copilot analysed page.", "ok");
    }
  };

  analyseBtn.addEventListener("click", () => { void runAnalyse(); });

  const sendChat = async () => {
    const text = (inputEl?.value || "").trim();
    if (!text) return;
    if (inputEl) inputEl.value = "";
    appendMsg("user", text);
    const reply = window.ph_copilot?.replyToChat?.(text, _lastContext) || "Click Analyse page.";
    appendMsg("assistant", reply);
    if (/analyse|scan|look|help|confus/.test(text.toLowerCase()) && !_lastContext) {
      void runAnalyse();
    }
  };

  if (sendBtn) sendBtn.addEventListener("click", () => { void sendChat(); });
  if (inputEl) {
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void sendChat();
      }
    });
  }

  if (highlightBtn) {
    highlightBtn.addEventListener("click", async () => {
      const r = await dispatch({ type: "copilot_highlight" });
      appendMsg("system", r?.ok ? "🟡 Highlight on page." : "❌ Could not highlight.");
    });
  }

  if (recordBtn) {
    recordBtn.addEventListener("click", async () => {
      const r = await dispatch({ type: "copilot_record" });
      appendMsg("system", r?.ok ? "✅ Click step recorded in toolbar recipe." : `❌ ${r?.reason || "Record failed"}`);
    });
  }

  if (pinBtn) {
    pinBtn.addEventListener("click", async () => {
      const r = await dispatch({ type: "copilot_pin" });
      appendMsg("system", r?.ok ? "📌 Pinned for this site." : `❌ ${r?.reason || "Pin failed"}`);
      if (r?.ok) void runAnalyse();
    });
  }

  if (clickBtn) {
    clickBtn.addEventListener("click", async () => {
      appendMsg("system", "⏳ Clicking highlighted link…");
      const r = await dispatch({ type: "copilot_click" });
      appendMsg("system", r?.ok ? "✅ Clicked and recorded." : `❌ ${r?.reason || "Click failed"}`);
    });
  }

  appendMsg("system", "Training Copilot ready. Open a parish page → Analyse page.");
  setActionState(false);
})();
