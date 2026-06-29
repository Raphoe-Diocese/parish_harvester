/**
 * Official parish display names from parish website URLs.
 * Rule: use the parish website hostname, not informal local names (e.g. Dungloe → Templecrone Parish).
 */
(function (global) {
  const SLUG_OVERRIDES = {
    naomhfionan: "Falcarragh",
    steunanscathedral: "Cathedral",
    "gort-a-choirce": "Gortahork",
    milfordrathmullanparishes: "Milford Kilkeel",
    newtownkilleaparish: "Newtown Killea",
    stranorlarparish: "Stranolar",
    tawnawillyparish: "Tawnawilly",
    inverparish: "Inver",
    annagryparish: "Annagry",
    templecroneparish: "Templecrone",
    "glenfin-parish": "Glenfin",
    "drive-1kna8f6t54": "Gartan/Termon",
    "drive-14alaxt4mv": "Glenties",
    "drive-1m6sogz3de": "Irish Martyrs",
    "drive-1jmslbrliw": "Raphoe",
    "drive-1hh7w-ew0v": "Templecrone",
    "drive-1rjeey-ayy": "Bruckless",
    "holy-cross-church": "Dunfanaghy",
    ballintra: "Ballintra Parish",
    kilmacrenan: "Kilmacrenan",
    rathmullan: "Rathmullan",
    carrigart: "Mevagh",
    "drumholm-parish": "Drumholm",
  };

  const NON_PARISH_HOST_SUFFIXES = [
    "facebook.com",
    "google.com",
    "usercontent.google.com",
    "mcn.live",
    "parishpress.net",
    "filesafe.space",
    "raw.githubusercontent.com",
  ];

  function hostSlug(url) {
    try {
      const parsed = new URL(url);
      let host = parsed.hostname.toLowerCase().replace(/^www\d*\./, "");
      if (/\bi\d+\.wp\.com\b/.test(host)) {
        const parts = parsed.pathname.replace(/^\//, "").split("/");
        if (parts.length > 0) host = parts[0].toLowerCase();
      }
      return host.split(".")[0] || "";
    } catch (_e) {
      return "";
    }
  }

  function officialDisplayNameFromUrl(url) {
    const text = String(url || "").trim();
    if (!text.startsWith("http")) return "";
    let host = "";
    try {
      host = new URL(text).hostname.toLowerCase().replace(/^www\d*\./, "");
    } catch (_e) {
      return "";
    }
    if (!host) return "";
    if (NON_PARISH_HOST_SUFFIXES.some((s) => host === s || host.endsWith("." + s))) return "";
    if (host.includes("facebook") || host.includes("google")) return "";

    const slug = hostSlug(text);
    if (!slug) return "";
    if (SLUG_OVERRIDES[slug]) return SLUG_OVERRIDES[slug];

    let core = slug;
    let suffix = "";
    if (core.toLowerCase().startsWith("parishof")) core = core.slice(8);
    if (core.endsWith("parishes")) {
      core = core.slice(0, -8);
      suffix = " Parishes";
    } else if (core.endsWith("parish")) {
      core = core.slice(0, -6);
      suffix = " Parish";
    }

    const words = core.replace(/-/g, " ").replace(/_/g, " ").split(/\s+/).filter(Boolean);
    const titled = words.map((word, i) => {
      const low = word.toLowerCase();
      if (i > 0 && (low === "of" || low === "and" || low === "the")) return low;
      return word.charAt(0).toUpperCase() + word.slice(1);
    });
    let name = titled.join(" ");
    if (suffix && !name.toLowerCase().endsWith(suffix.trim().toLowerCase())) {
      name += suffix;
    }
    return name.trim();
  }

  global.phOfficialParishName = {
    officialDisplayNameFromUrl,
    hostSlug,
  };
})(typeof globalThis !== "undefined" ? globalThis : window);
