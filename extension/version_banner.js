/** T4: show when this PC is behind GitHub main. Cache 10 min. */
(function attachTrainerVersionBanner(root) {
  const CACHE_KEY = "ph_newest_trainer_version";
  const CACHE_AT_KEY = "ph_newest_trainer_version_at";
  const CACHE_MS = 10 * 60 * 1000;
  const MANIFEST_URL =
    "https://raw.githubusercontent.com/Raphoe-Diocese/parish_harvester/main/extension/manifest.json";

  function compareVersions(a, b) {
    const pa = String(a || "")
      .split(".")
      .map((n) => parseInt(n, 10) || 0);
    const pb = String(b || "")
      .split(".")
      .map((n) => parseInt(n, 10) || 0);
    const len = Math.max(pa.length, pb.length);
    for (let i = 0; i < len; i += 1) {
      const da = pa[i] || 0;
      const db = pb[i] || 0;
      if (da > db) return 1;
      if (da < db) return -1;
    }
    return 0;
  }

  function behindMessage(installed, newest) {
    return `Installed ${installed} · newest ${newest} — Reload / Load unpacked from Desktop latest ext`;
  }

  async function fetchNewestVersion() {
    try {
      const stored = await chrome.storage.local.get([CACHE_KEY, CACHE_AT_KEY]);
      const cached = String(stored[CACHE_KEY] || "").trim();
      const at = Number(stored[CACHE_AT_KEY] || 0);
      if (cached && Date.now() - at < CACHE_MS) return cached;
      const res = await fetch(MANIFEST_URL, { cache: "no-store" });
      if (!res.ok) return cached;
      const data = await res.json();
      const newest = String(data.version || "").trim();
      if (newest) {
        await chrome.storage.local.set({
          [CACHE_KEY]: newest,
          [CACHE_AT_KEY]: Date.now(),
        });
      }
      return newest || cached;
    } catch (_err) {
      return "";
    }
  }

  async function paintVersionEl(el, installed) {
    if (!el) return;
    const ver = String(installed || "").trim();
    el.textContent = ver ? `v${ver}` : "";
    const newest = await fetchNewestVersion();
    if (newest && compareVersions(ver, newest) < 0) {
      el.textContent = behindMessage(ver, newest);
      el.title =
        "This PC is behind GitHub main. chrome://extensions → Reload. Folder: Desktop latest ext";
    }
  }

  root.phCompareTrainerVersions = compareVersions;
  root.phPaintTrainerVersion = paintVersionEl;
})(globalThis);
