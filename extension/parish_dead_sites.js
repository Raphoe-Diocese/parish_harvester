/**
 * Dead / broken parish site registry — shared by popup + background.
 */
(function initParishDeadSites(global) {
  const PH_DEAD_PARISHES_KEY = "ph_dead_parishes";

  const PH_EVIDENCE_FILES = {
    "Derry Diocese": "parishes/derry_diocese_bulletin_urls.txt",
    "Down & Connor Diocese": "parishes/down_and_connor_bulletin_urls.txt",
    "Raphoe Diocese": "parishes/raphoe_diocese_bulletin_urls.txt",
  };

  function phUrlToParishKey(url, headerName = "") {
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
        hostname === "filesafe.space" ||
        hostname.endsWith(".filesafe.space") ||
        hostname === "google.com" ||
        hostname.endsWith(".google.com")
      ) {
        if (headerName) return headerName.toLowerCase().split("(")[0].trim().replace(/[^a-z0-9]/g, "");
        return hostname.split(".")[0].replace(/[^a-z0-9]/g, "");
      }
      return hostname.split(".")[0] || hostname;
    } catch (_e) {
      return "";
    }
  }

  function phParseEvidence(text, dioceseName) {
    const parishes = [];
    let cur = null;

    for (const rawLine of String(text || "").split("\n")) {
      const line = rawLine.trim();
      const nameMatch = line.match(/^#\s*---\s*(.+?)\s*---\s*$/);
      if (nameMatch) {
        if (cur) parishes.push(cur);
        cur = {
          name: nameMatch[1],
          diocese: dioceseName,
          pageUrl: null,
          keyOverride: null,
          bulletinUrls: [],
          disabled: false,
          key: null,
        };
        continue;
      }
      if (!cur) continue;
      const pageMatch = line.match(/^#\s*page:\s*(.+)$/i);
      if (pageMatch) {
        cur.pageUrl = pageMatch[1].trim();
        continue;
      }
      const keyMatch = line.match(/^#\s*key:\s*(.+)$/i);
      if (keyMatch) {
        cur.keyOverride = keyMatch[1].trim();
        continue;
      }
      if (/^#\s*DISABLED/i.test(line)) cur.disabled = true;
      if (line.startsWith("#") || !line) continue;
      cur.bulletinUrls.push(line);
    }
    if (cur) parishes.push(cur);

    for (const p of parishes) {
      const firstUrl = p.bulletinUrls[0] || p.pageUrl || "";
      p.key = p.keyOverride || (firstUrl ? phUrlToParishKey(firstUrl, p.name) : "");
      p.key = String(p.key || "").toLowerCase().replace(/[^a-z0-9]+/g, "");
    }
    return parishes;
  }

  function phMatchParishFromUrl(tabUrl, parishes) {
    if (!tabUrl || !Array.isArray(parishes)) return null;
    let tabKey = "";
    try {
      tabKey = phUrlToParishKey(tabUrl);
    } catch (_e) {
      return null;
    }
    if (!tabKey) return null;

    return parishes.find((p) => {
      if (p.key === tabKey) return true;
      const allUrls = [p.pageUrl, ...p.bulletinUrls].filter(Boolean);
      return allUrls.some((u) => phUrlToParishKey(u, p.name) === tabKey);
    }) || null;
  }

  function phDisableParishInEvidence(text, parishName) {
    const lines = String(text || "").split("\n");
    const escaped = parishName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const headerRe = new RegExp(`^#\\s*---\\s*${escaped}\\s*---`, "i");
    let inserted = false;
    for (let i = 0; i < lines.length; i++) {
      if (headerRe.test(lines[i].trim())) {
        if (!lines[i + 1]?.includes("DISABLED")) {
          lines.splice(i + 1, 0, "# DISABLED — website gone / removed from harvest via extension");
          inserted = true;
        }
        break;
      }
    }
    if (!inserted) return { ok: false, error: "Parish section not found in evidence file." };
    return { ok: true, text: lines.join("\n") };
  }

  async function phGetDeadParishes(storageGet) {
    const data = await storageGet([PH_DEAD_PARISHES_KEY]);
    const list = data?.[PH_DEAD_PARISHES_KEY];
    return Array.isArray(list) ? list : [];
  }

  async function phUpsertDeadParish(storageGet, storageSet, entry) {
    const list = await phGetDeadParishes(storageGet);
    const key = String(entry?.key || "").toLowerCase();
    const next = list.filter((p) => String(p.key || "").toLowerCase() !== key);
    next.unshift({
      key,
      name: entry.name || key,
      diocese: entry.diocese || "",
      url: entry.url || "",
      reason: entry.reason || "Website gone or unreachable.",
      marked_at: entry.marked_at || new Date().toISOString(),
      evidence_disabled: Boolean(entry.evidence_disabled),
    });
    await storageSet({ [PH_DEAD_PARISHES_KEY]: next });
    return next;
  }

  async function phRemoveDeadParishLocal(storageGet, storageSet, parishKey) {
    const key = String(parishKey || "").toLowerCase();
    const list = await phGetDeadParishes(storageGet);
    const next = list.filter((p) => String(p.key || "").toLowerCase() !== key);
    await storageSet({ [PH_DEAD_PARISHES_KEY]: next });
    return next;
  }

  const api = {
    PH_DEAD_PARISHES_KEY,
    PH_EVIDENCE_FILES,
    phUrlToParishKey,
    phParseEvidence,
    phMatchParishFromUrl,
    phDisableParishInEvidence,
    phGetDeadParishes,
    phUpsertDeadParish,
    phRemoveDeadParishLocal,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  global.PH_DEAD_SITES = api;
})(typeof globalThis !== "undefined" ? globalThis : window);
