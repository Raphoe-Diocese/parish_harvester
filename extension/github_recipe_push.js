/**
 * Shared GitHub recipe push + harvest dispatch (content script + service worker).
 * Content calls this directly so pushes survive MV3 service-worker sleep.
 */
(function initPhGithubRecipePush(global) {
  const DIOCESE_FOLDERS = ["derry", "down_and_connor", "raphoe", "unknown"];

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
    if (raw === "raphoe" || raw === "raphoe_diocese" || raw === "raphoe diocese") return "raphoe";
    return raw.replace(/&/g, "and").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  };

  const resolveGhRepo = (storedRepo) => {
    const value = String(storedRepo || "").trim();
    return value || "Raphoe-Diocese/parish_harvester";
  };

  const decodeGithubContent = (content) => {
    if (!content) return "";
    try {
      return decodeURIComponent(
        atob(String(content).replace(/\n/g, ""))
          .split("")
          .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
          .join("")
      );
    } catch (_e) {
      return "";
    }
  };

  const fetchGithub = async (url, headers, timeoutMs = 20000, init = {}) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...init, headers, signal: controller.signal });
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error(`GitHub timed out after ${Math.round(timeoutMs / 1000)}s`);
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  };

  const githubApiError = async (resp) => {
    try {
      const data = await resp.json();
      return data?.message || `GitHub API ${resp.status}`;
    } catch (_e) {
      return `GitHub API ${resp.status}`;
    }
  };

  const authHeaderValue = (gh_pat) => {
    const p = String(gh_pat || "").trim();
    // Fine-grained PATs require Bearer; classic PATs use token (Bearer also works).
    if (p.startsWith("github_pat_")) return `Bearer ${p}`;
    return `token ${p}`;
  };

  const authHeaders = (gh_pat, withJson = false) => {
    const headers = {
      Authorization: authHeaderValue(gh_pat),
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    };
    if (withJson) headers["Content-Type"] = "application/json";
    return headers;
  };

  const encodeGithubBase64 = (text) => {
    const bytes = new TextEncoder().encode(String(text));
    let binary = "";
    for (let i = 0; i < bytes.length; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  };

  const locateRecipe = async (gh_pat, gh_repo, key, preferredDiocese) => {
    const headers = authHeaders(gh_pat);
    const preferred = canonicalDioceseSlug(preferredDiocese) || "";

    const tryPath = async (dio, timeoutMs = 10000) => {
      const filePath = `parishes/recipes/${dio}/${key}.json`;
      const apiBase = `https://api.github.com/repos/${gh_repo}/contents/${filePath}`;
      const getResp = await fetchGithub(apiBase, headers, timeoutMs);
      if (getResp.status === 404) return null;
      if (!getResp.ok) throw new Error(await githubApiError(getResp));
      const existing = await getResp.json();
      let existingRecipe = null;
      try {
        existingRecipe = JSON.parse(decodeGithubContent(existing.content) || "{}");
      } catch (_e) {
        existingRecipe = null;
      }
      return {
        filePath,
        apiBase,
        diocese: dio,
        existingSha: existing.sha || null,
        existingRecipe,
      };
    };

    if (preferred) {
      try {
        const hit = await tryPath(preferred, 12000);
        if (hit) return hit;
      } catch (err) {
        console.warn("phGithubRecipePush: preferred path failed", err);
      }
    }

    const others = DIOCESE_FOLDERS.filter((d) => d !== preferred);
    const probes = await Promise.all(
      others.map((dio) => tryPath(dio, 8000).catch(() => null))
    );
    const found = probes.find(Boolean);
    if (found) return found;

    const dio = preferred || "unknown";
    const filePath = `parishes/recipes/${dio}/${key}.json`;
    return {
      filePath,
      apiBase: `https://api.github.com/repos/${gh_repo}/contents/${filePath}`,
      diocese: dio,
      existingSha: null,
      existingRecipe: null,
    };
  };

  const pushRecipe = async ({ gh_pat, gh_repo: storedRepo, parish_key, recipe }) => {
    const gh_pat_clean = String(gh_pat || "").trim();
    if (!gh_pat_clean) {
      return { ok: false, error: "GitHub PAT not configured. Open extension popup → Settings." };
    }
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim().toLowerCase().replace(/\s+/g, "_");
    if (!key) return { ok: false, error: "No parish_key provided." };

    const incoming = recipe && typeof recipe === "object" ? { ...recipe } : {};
    const recipeDioceseRaw = String(incoming.diocese || "").trim();
    const located = await locateRecipe(gh_pat_clean, gh_repo, key, recipeDioceseRaw);
    const existingRecipe = located.existingRecipe;
    const existingSha = located.existingSha;
    const stepsReplaced = Array.isArray(incoming.steps) && incoming.steps.length > 0;

    const merged = existingRecipe && !stepsReplaced
      ? {
          ...existingRecipe,
          ...incoming,
          steps: existingRecipe.steps,
          start_url: incoming.start_url?.trim() ? incoming.start_url : existingRecipe.start_url,
          display_name: incoming.display_name?.trim() || existingRecipe.display_name,
          diocese: incoming.diocese?.trim() || existingRecipe.diocese,
        }
      : {
          ...(stepsReplaced ? {} : existingRecipe || {}),
          ...incoming,
          steps: stepsReplaced ? incoming.steps : (existingRecipe?.steps || incoming.steps),
        };

    merged.recorded_date = new Date().toISOString().slice(0, 10);
    merged.parish_key = key;
    if (located.diocese) merged.diocese = located.diocese;
    delete merged.skip;
    delete merged.status;
    delete merged.needs_retraining;

    const headers = authHeaders(gh_pat_clean, true);
    const encoded = encodeGithubBase64(JSON.stringify(merged, null, 2));
    const putBody = {
      message: `chore: update recipe for ${key} [${merged.diocese || "unknown"}]`,
      content: encoded,
      branch: "main",
      ...(existingSha ? { sha: existingSha } : {}),
    };

    let putResp = await fetchGithub(
      located.apiBase,
      headers,
      25000,
      { method: "PUT", body: JSON.stringify(putBody) }
    );

    // File exists but locate missed sha (timeout/auth blip) — refetch sha and retry once.
    if (putResp.status === 422 && !putBody.sha) {
      try {
        const refetch = await fetchGithub(located.apiBase, authHeaders(gh_pat_clean), 12000);
        if (refetch.ok) {
          const refData = await refetch.json();
          if (refData?.sha) {
            putBody.sha = refData.sha;
            putResp = await fetchGithub(
              located.apiBase,
              headers,
              25000,
              { method: "PUT", body: JSON.stringify(putBody) }
            );
          }
        }
      } catch (_retryErr) {
        // fall through to error handling
      }
    }

    if (!putResp.ok) {
      return { ok: false, error: await githubApiError(putResp) };
    }
    const result = await putResp.json();
    return {
      ok: true,
      url: result?.content?.html_url || `https://github.com/${gh_repo}/blob/main/${located.filePath}`,
      filePath: located.filePath,
      updated: Boolean(existingSha),
      recipe: merged,
    };
  };

  const dispatchHarvestTest = async ({ gh_pat, gh_repo: storedRepo, parish_key }) => {
    const gh_pat_clean = String(gh_pat || "").trim();
    if (!gh_pat_clean) return { ok: false, error: "GitHub PAT not configured." };
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim().toLowerCase();
    const headers = authHeaders(gh_pat_clean, true);
    const resp = await fetchGithub(
      `https://api.github.com/repos/${gh_repo}/actions/workflows/harvest.yml/dispatches`,
      headers,
      20000,
      {
        method: "POST",
        body: JSON.stringify({
          ref: "main",
          inputs: { diocese: "all", target_parish: key, run_tests: "false" },
        }),
      }
    );
    if (resp.status === 204) return { ok: true };
    if (resp.status === 403) {
      return { ok: false, error: "PAT missing 'workflow' scope — regenerate token with workflow checked." };
    }
    return { ok: false, error: await githubApiError(resp) };
  };

  const fetchReportJson = async ({ gh_pat, gh_repo: storedRepo }) => {
    const gh_repo = resolveGhRepo(storedRepo);
    const pat = String(gh_pat || "").trim();
    if (pat) {
      try {
        const resp = await fetchGithub(
          `https://api.github.com/repos/${gh_repo}/contents/Bulletins/report.json`,
          authHeaders(pat),
          15000
        );
        if (resp.ok) {
          const data = await resp.json();
          return JSON.parse(decodeGithubContent(data.content) || "{}");
        }
      } catch (_e) {
        // fall through to raw
      }
    }
    const raw = await fetch(
      `https://raw.githubusercontent.com/${gh_repo}/main/Bulletins/report.json?t=${Date.now()}`,
      { cache: "no-store" }
    );
    if (!raw.ok) return null;
    return raw.json();
  };

  const parishPdfExists = async ({ gh_pat, gh_repo: storedRepo, parish_key }) => {
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim();
    const pat = String(gh_pat || "").trim();
    if (!pat || !key) return false;
    try {
      const resp = await fetchGithub(
        `https://api.github.com/repos/${gh_repo}/contents/Bulletins/current/${key}.pdf`,
        authHeaders(pat),
        12000
      );
      return resp.ok;
    } catch (_e) {
      return false;
    }
  };

  global.phGithubRecipePush = {
    canonicalDioceseSlug,
    resolveGhRepo,
    locateRecipe,
    pushRecipe,
    dispatchHarvestTest,
    fetchReportJson,
    parishPdfExists,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
