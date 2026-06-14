/**
 * Parish registry + searchable diocese/parish pickers.
 * Fixes shared-host sites (mcn.live, etc.) where hostname alone is wrong.
 */
(() => {
  const SHARED_HOSTS = new Set(["mcn.live", "www.mcn.live", "filesafe.space"]);
  const PATH_SKIP_SEGMENTS = new Set([
    "camera", "wp-content", "uploads", "index.html", "index.htm", "file", "view",
  ]);

  const CONTACT_FILES = [
    { path: "parishes/derry_diocese_contacts.json", diocese: "derry" },
    { path: "parishes/down_and_connor_contacts.json", diocese: "down_and_connor" },
    { path: "parishes/raphoe_diocese_contacts.json", diocese: "raphoe" },
  ];

  const BULLETIN_FILES = [
    { path: "parishes/derry_diocese_bulletin_urls.txt", diocese: "derry" },
    { path: "parishes/down_and_connor_bulletin_urls.txt", diocese: "down_and_connor" },
    { path: "parishes/raphoe_diocese_bulletin_urls.txt", diocese: "raphoe" },
  ];

  const registry = {
    loaded: false,
    ghRepo: "",
    byUrl: {},
    byKey: {},
    dioceses: [],
    parishesByDiocese: {},
  };

  const _isJunkParishKey = (key) => {
    const k = String(key || "").trim().toLowerCase();
    if (!k || k.length < 4) return true;
    if (/^\d{6,8}(-pdf)?$/.test(k)) return true;
    if (/^\d{2}\.\d{2}\.\d{2}(-pdf)?$/.test(k)) return true;
    if (/-pdf$/.test(k) && /\d{5,}/.test(k)) return true;
    return false;
  };

  const _resolveSectionNameToKey = (sectionName) => {
    const needle = String(sectionName || "")
      .toLowerCase()
      .replace(/\([^)]*\)/g, " ")
      .replace(/&/g, "and")
      .replace(/[^a-z0-9]+/g, " ")
      .trim();
    if (!needle) return "";
    const words = needle.split(/\s+/).filter((w) => w.length >= 3);
    let best = "";
    let bestScore = 0;
    for (const [key, meta] of Object.entries(registry.byKey)) {
      if (_isJunkParishKey(key)) continue;
      const display = String(meta.name || key).toLowerCase();
      const keyNorm = key.replace(/parish$/i, "");
      let score = 0;
      if (display.includes(needle) || needle.includes(display.split(" ")[0])) score += 3;
      for (const w of words) {
        if (display.includes(w)) score += 2;
        if (key.includes(w) || keyNorm.includes(w)) score += 2;
      }
      if (score > bestScore) {
        bestScore = score;
        best = key;
      }
    }
    return bestScore >= 2 ? best : "";
  };

  const _pruneRegistry = () => {
    for (const k of Object.keys(registry.byKey)) {
      if (_isJunkParishKey(k)) delete registry.byKey[k];
    }
    for (const [url, hit] of Object.entries(registry.byUrl)) {
      if (!hit || _isJunkParishKey(hit.key)) delete registry.byUrl[url];
    }
    registry.parishesByDiocese = {};
    for (const [key, meta] of Object.entries(registry.byKey)) {
      const dio = String(meta.diocese || "").trim();
      if (!dio) continue;
      if (!registry.parishesByDiocese[dio]) registry.parishesByDiocese[dio] = [];
      if (!registry.parishesByDiocese[dio].some((p) => p.key === key)) {
        registry.parishesByDiocese[dio].push({
          key,
          name: meta.name || key,
        });
      }
    }
    for (const dio of Object.keys(registry.parishesByDiocese)) {
      registry.parishesByDiocese[dio].sort((a, b) =>
        String(a.name).localeCompare(String(b.name))
      );
    }
  };

  const normalizeUrlKey = (url) => {
    if (!url) return "";
    try {
      const u = new URL(url);
      const host = u.hostname.toLowerCase().replace(/^www\d*\./, "");
      const path = u.pathname.replace(/\/+$/, "").toLowerCase();
      return `${host}${path}`;
    } catch (_e) {
      return "";
    }
  };

  const siteCacheKey = (url) => {
    const norm = normalizeUrlKey(url);
    if (!norm) return "";
    try {
      const host = new URL(url).hostname.toLowerCase().replace(/^www\d*\./, "");
      if (SHARED_HOSTS.has(host) || SHARED_HOSTS.has(new URL(url).hostname.toLowerCase())) {
        return norm;
      }
      return host;
    } catch (_e) {
      return norm;
    }
  };

  const pathSlugFromUrl = (url) => {
    try {
      const parts = new URL(url).pathname.split("/").filter(Boolean);
      for (let i = parts.length - 1; i >= 0; i--) {
        const seg = parts[i].toLowerCase();
        if (PATH_SKIP_SEGMENTS.has(seg)) continue;
        if (seg.length < 3) continue;
        return seg.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "");
      }
    } catch (_e) {
      // ignore
    }
    return "";
  };

  const inferParishKeyFromUrl = (url) => {
    if (!url) return "";
    const hit = registry.byUrl[normalizeUrlKey(url)];
    if (hit?.key) return hit.key;
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
        return "";
      }
      const pathKey = pathSlugFromUrl(url);
      if (pathKey && (SHARED_HOSTS.has(hostname) || hostname.split(".").length <= 2)) {
        if (registry.byKey[pathKey]) return pathKey;
        return pathKey;
      }
      return hostname.split(".")[0] || "";
    } catch (_e) {
      return "";
    }
  };

  const _indexEntry = (key, name, diocese, website) => {
    const k = String(key || "").trim().toLowerCase().replace(/\s+/g, "_");
    if (!k || _isJunkParishKey(k)) return;
    const display = String(name || k).trim();
    const dio = String(diocese || "").trim();
    if (!registry.byKey[k]) {
      registry.byKey[k] = { key: k, name: display, diocese: dio, urls: [] };
    } else {
      if (display) registry.byKey[k].name = display;
      if (dio) registry.byKey[k].diocese = dio;
    }
    const norm = normalizeUrlKey(website);
    if (norm) {
      registry.byUrl[norm] = { key: k, name: display, diocese: dio };
      if (!registry.byKey[k].urls.includes(norm)) registry.byKey[k].urls.push(norm);
    }
    if (dio) {
      if (!registry.parishesByDiocese[dio]) registry.parishesByDiocese[dio] = [];
      if (!registry.parishesByDiocese[dio].some((p) => p.key === k)) {
        registry.parishesByDiocese[dio].push({ key: k, name: display });
      }
    }
  };

  const _parseBulletinUrls = (text, diocese) => {
    let curKey = "";
    let curName = "";
    for (const raw of String(text || "").split("\n")) {
      const line = raw.trim();
      const nameMatch = line.match(/^#\s*---\s*(.+?)\s*---\s*$/);
      if (nameMatch) {
        curName = nameMatch[1].trim();
        curKey = "";
        continue;
      }
      const keyMatch = line.match(/^#\s*key:\s*(.+)$/i);
      if (keyMatch) {
        curKey = keyMatch[1].trim().toLowerCase().replace(/\s+/g, "_");
        continue;
      }
      if (!line || line.startsWith("#")) continue;
      if (line.startsWith("http://") || line.startsWith("https://")) {
        let key = curKey || _resolveSectionNameToKey(curName);
        if (!key) continue;
        _indexEntry(key, curName || registry.byKey[key]?.name || key, diocese, line);
      }
    }
  };

  const _indexRecipesFromGithub = async (repo, headers) => {
    for (const dio of registry.dioceses) {
      if (!dio || dio === "unknown") continue;
      try {
        const resp = await fetch(
          `https://api.github.com/repos/${repo}/contents/parishes/recipes/${dio}`,
          { headers }
        );
        if (!resp.ok) continue;
        const items = await resp.json();
        for (const item of items) {
          if (!item || item.type !== "file" || !String(item.name || "").endsWith(".json")) {
            continue;
          }
          const key = String(item.name).slice(0, -5).trim().toLowerCase();
          if (_isJunkParishKey(key)) continue;
          if (!registry.byKey[key]) {
            _indexEntry(key, key.replace(/parish$/i, "").replace(/_/g, " "), dio, "");
          } else if (!registry.byKey[key].diocese) {
            registry.byKey[key].diocese = dio;
          }
        }
      } catch (_e) {
        // try next diocese folder
      }
    }
  };

  const loadRegistry = async (ghRepo) => {
    const repo = String(ghRepo || "Raphoe-Diocese/parish_harvester").trim();
    if (registry.loaded && registry.ghRepo === repo) return registry;
    registry.ghRepo = repo;
    registry.byUrl = {};
    registry.byKey = {};
    registry.parishesByDiocese = {};
    registry.dioceses = [];

    for (const file of CONTACT_FILES) {
      try {
        const resp = await fetch(`https://raw.githubusercontent.com/${repo}/main/${file.path}`);
        if (!resp.ok) continue;
        const data = await resp.json();
        for (const [key, entry] of Object.entries(data || {})) {
          if (!entry || typeof entry !== "object") continue;
          _indexEntry(
            key,
            entry.display_name || entry.name || key,
            file.diocese,
            entry.website || entry.url || ""
          );
        }
      } catch (_e) {
        // try next file
      }
    }

    for (const file of BULLETIN_FILES) {
      try {
        const resp = await fetch(`https://raw.githubusercontent.com/${repo}/main/${file.path}`);
        if (!resp.ok) continue;
        _parseBulletinUrls(await resp.text(), file.diocese);
      } catch (_e) {
        // try next file
      }
    }

    try {
      const settings = await new Promise((resolve) => {
        if (typeof chrome === "undefined" || !chrome.storage) {
          resolve({});
          return;
        }
        chrome.storage.local.get(["gh_pat"], (r) => resolve(r || {}));
      });
      const pat = String(settings.gh_pat || "").trim();
      const headers = { Accept: "application/vnd.github+json" };
      if (pat) headers.Authorization = `token ${pat}`;
      const resp = await fetch(`https://api.github.com/repos/${repo}/contents/parishes/recipes`, {
        headers,
      });
      if (resp.ok) {
        const items = await resp.json();
        registry.dioceses = items
          .filter((item) => item.type === "dir")
          .map((item) => item.name)
          .filter((d) => d && d !== "unknown")
          .sort();
        for (const dio of registry.dioceses) {
          if (!registry.parishesByDiocese[dio]) registry.parishesByDiocese[dio] = [];
        }
        await _indexRecipesFromGithub(repo, headers);
      }
    } catch (_e) {
      registry.dioceses = ["derry", "down_and_connor", "raphoe"];
    }

    if (registry.dioceses.length === 0) {
      registry.dioceses = ["derry", "down_and_connor", "raphoe"];
    }

    _pruneRegistry();

    registry.loaded = true;
    return registry;
  };

  const lookupByUrl = (url) => registry.byUrl[normalizeUrlKey(url)] || null;

  const lookupByKey = (key) => registry.byKey[String(key || "").trim().toLowerCase()] || null;

  const resolveFromPage = (pageUrl, storageData = {}) => {
    const url = pageUrl || "";
    const cacheKey = siteCacheKey(url);
    const urlHit = lookupByUrl(url);
    const inferredKey = urlHit?.key || inferParishKeyFromUrl(url);
    const keyHit = inferredKey ? lookupByKey(inferredKey) : null;

    let key = inferredKey || "";
    let name = urlHit?.name || keyHit?.name || "";
    let diocese = urlHit?.diocese || keyHit?.diocese || "";

    const hostMap =
      storageData.ph_hostname_map && typeof storageData.ph_hostname_map === "object"
        ? storageData.ph_hostname_map
        : {};
    const cached = cacheKey ? hostMap[cacheKey] : null;
    if (cached && typeof cached === "object") {
      const mappedKey = String(cached.parish_key || cached.key || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "_");
      const mappedName = String(cached.display_name || cached.name || "").trim();
      const mappedDiocese = String(cached.diocese || "").trim();
      if (mappedDiocese) diocese = mappedDiocese;
      if (mappedName) name = mappedName;
      if (mappedKey && normalizeUrlKey(cached.start_url || "") === normalizeUrlKey(url)) {
        key = mappedKey;
      } else if (mappedKey && !inferredKey) {
        key = mappedKey;
      }
    }

    if (!name && key) {
      const hit = lookupByKey(key);
      if (hit?.name) name = hit.name;
    }

    let hostname = "";
    try {
      hostname = new URL(url).hostname.toLowerCase();
    } catch (_e) {
      // ignore
    }

    return {
      key,
      name,
      diocese,
      hostname,
      inferredKey: inferredKey || key,
      urlMatched: Boolean(urlHit),
      lowConfidence: Boolean(inferredKey && !urlHit && !keyHit),
    };
  };

  const createSearchCombo = ({
    placeholder = "Type to search…",
    items = [],
    value = "",
    label = "",
    onChange,
    inputStyle = "",
  }) => {
    const wrap = document.createElement("div");
    wrap.style.cssText = "position:relative;margin-bottom:6px;";

    if (label) {
      const lbl = document.createElement("label");
      lbl.style.cssText = "display:block;font-size:9px;color:#9ca3af;margin-bottom:2px;";
      lbl.textContent = label;
      wrap.appendChild(lbl);
    }

    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = placeholder;
    input.autocomplete = "off";
    input.style.cssText = inputStyle;
    input.value = value;
    wrap.appendChild(input);

    const menu = document.createElement("div");
    menu.style.cssText = [
      "display:none",
      "position:absolute",
      "left:0",
      "right:0",
      "top:100%",
      "z-index:20",
      "max-height:140px",
      "overflow-y:auto",
      "background:#0f172a",
      "border:1px solid #374151",
      "border-radius:4px",
      "margin-top:2px",
      "box-shadow:0 4px 12px rgba(0,0,0,.4)",
    ].join(";");
    wrap.appendChild(menu);

    let selectedValue = value;
    let filtered = items.slice();

    const formatLabel = (item) => {
      if (!item) return "";
      if (typeof item === "string") return item;
      return item.label || item.name || item.key || item.value || "";
    };

    const renderMenu = () => {
      menu.replaceChildren();
      if (filtered.length === 0) {
        menu.style.display = "none";
        return;
      }
      for (const item of filtered.slice(0, 12)) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.style.cssText = [
          "display:block",
          "width:100%",
          "text-align:left",
          "border:none",
          "background:transparent",
          "color:#e2e8f0",
          "font-size:10px",
          "padding:5px 8px",
          "cursor:pointer",
          "font-family:inherit",
        ].join(";");
        btn.textContent = formatLabel(item);
        btn.addEventListener("mouseenter", () => {
          btn.style.background = "#1e293b";
        });
        btn.addEventListener("mouseleave", () => {
          btn.style.background = "transparent";
        });
        btn.addEventListener("mousedown", (e) => {
          e.preventDefault();
          const val = typeof item === "string" ? item : item.value || item.key || "";
          selectedValue = val;
          input.value = formatLabel(item);
          menu.style.display = "none";
          if (onChange) onChange(item, val);
        });
        menu.appendChild(btn);
      }
      menu.style.display = "block";
    };

    const applyFilter = (q) => {
      const query = String(q || "").trim().toLowerCase();
      if (!query) {
        filtered = items.slice();
      } else {
        filtered = items.filter((item) => {
          const blob = formatLabel(item).toLowerCase();
          const val = (typeof item === "string" ? item : item.value || item.key || "").toLowerCase();
          return blob.includes(query) || val.includes(query);
        });
      }
      renderMenu();
    };

    input.addEventListener("focus", () => applyFilter(input.value));
    input.addEventListener("input", () => {
      selectedValue = "";
      applyFilter(input.value);
      if (onChange) onChange(null, "");
    });
    input.addEventListener("blur", () => {
      setTimeout(() => {
        menu.style.display = "none";
      }, 150);
    });

    return {
      wrap,
      input,
      setItems: (next) => {
        items = Array.isArray(next) ? next : [];
        applyFilter(input.value);
      },
      setValue: (val, display) => {
        selectedValue = val || "";
        input.value = display || val || "";
      },
      getValue: () => selectedValue || input.value.trim(),
      getDisplay: () => input.value.trim(),
    };
  };

  window.ph_parish_pickers = {
    normalizeUrlKey,
    siteCacheKey,
    inferParishKeyFromUrl,
    loadRegistry,
    lookupByUrl,
    lookupByKey,
    resolveFromPage,
    createSearchCombo,
    SHARED_HOSTS,
    isJunkParishKey: _isJunkParishKey,
  };
})();
