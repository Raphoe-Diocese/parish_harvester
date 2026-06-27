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
        const hit = await tryPath(preferred, 8000);
        if (hit) return hit;
      } catch (err) {
        console.warn("phGithubRecipePush: preferred path failed", err);
      }
    }

    const others = DIOCESE_FOLDERS.filter((d) => d !== preferred);
    const probes = await Promise.all(
      others.map((dio) => tryPath(dio, 5000).catch(() => null))
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

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function findLatestHarvestRun(gh_pat, gh_repo, afterMs) {
    try {
      const resp = await fetchGithub(
        `https://api.github.com/repos/${gh_repo}/actions/workflows/harvest.yml/runs?per_page=20&event=workflow_dispatch`,
        authHeaders(gh_pat),
        15000
      );
      if (!resp.ok) return null;
      const data = await resp.json();
      const runs = Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
      const cutoff = afterMs - 120_000;
      return runs.find((run) => new Date(run.created_at).getTime() >= cutoff) || runs[0] || null;
    } catch (_e) {
      return null;
    }
  }

  function parishHarvestStatus(report, parishKey) {
    const key = String(parishKey || "").trim().toLowerCase();
    const downloaded = (report?.downloaded || []).find(
      (row) => String(row?.parish || "").trim().toLowerCase() === key
    );
    if (downloaded) return { status: "ok", item: downloaded };
    const failed = (report?.failed || []).find(
      (row) => String(row?.parish || "").trim().toLowerCase() === key
    );
    if (failed) return { status: "failed", item: failed };
    return { status: "unknown", item: null };
  }

  /** Poll GitHub until single-parish harvest succeeds, fails, or times out. */
  async function pollHarvestUntilDone({
    gh_pat,
    gh_repo: storedRepo,
    parish_key,
    startedAt,
    onProgress,
    maxAttempts = 40,
  }) {
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim().toLowerCase();
    const started = Number(startedAt) || Date.now();
    let runUrl = `https://github.com/${gh_repo}/actions/workflows/harvest.yml`;
    let trackedRunId = null;

    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      if (attempt > 0) {
        const delay = attempt < 12 ? 5000 : 10000;
        await sleep(delay);
      }
      const elapsed = Math.round((Date.now() - started) / 1000);
      const run = await findLatestHarvestRun(gh_pat, gh_repo, started);
      if (run?.html_url) runUrl = run.html_url;

      const runStartedMs = run ? new Date(run.created_at).getTime() : 0;
      const runBelongsToUs = run && runStartedMs >= started - 60_000;
      if (runBelongsToUs && !trackedRunId) trackedRunId = run.id;

      const isOurRun = trackedRunId && run && run.id === trackedRunId;
      const workflowDone = isOurRun && run.status === "completed";
      const workflowRunning =
        isOurRun && (run.status === "in_progress" || run.status === "queued" || run.status === "pending");
      const workflowFailed = workflowDone && run.conclusion === "failure";
      const workflowSucceeded = workflowDone && run.conclusion === "success";

      let parishStatus = { status: "unknown", item: null };
      let pdfOk = false;
      if (workflowDone || workflowRunning || attempt >= 2) {
        const report = await fetchReportJson({ gh_pat, gh_repo: storedRepo });
        parishStatus = report ? parishHarvestStatus(report, key) : { status: "unknown", item: null };
        if (workflowSucceeded) {
          pdfOk = await parishPdfExists({ gh_pat, gh_repo: storedRepo, parish_key: key });
        }
      }

      const runStatus = isOurRun ? run.status : trackedRunId ? "waiting" : "starting";
      onProgress?.({
        attempt,
        elapsed,
        runUrl,
        runStatus,
        parishStatus: parishStatus.status,
        queued: !trackedRunId && elapsed > 45,
      });

      if (workflowSucceeded && (parishStatus.status === "ok" || pdfOk)) {
        return { ok: true, runUrl, item: parishStatus.item, elapsed };
      }
      if (workflowFailed) {
        return {
          ok: false,
          runUrl,
          item: parishStatus.item,
          elapsed,
          reason: parishStatus.item?.reason || parishStatus.item?.error || "GitHub Actions run failed",
        };
      }
      if (workflowDone && parishStatus.status === "failed") {
        return {
          ok: false,
          runUrl,
          item: parishStatus.item,
          elapsed,
          reason: parishStatus.item?.reason || parishStatus.item?.error || "Harvest failed",
        };
      }
      if (workflowRunning) continue;

      if (!trackedRunId && elapsed > 90) {
        onProgress?.({
          attempt,
          elapsed,
          runUrl,
          runStatus: "queued",
          parishStatus: "unknown",
          queued: true,
        });
      }
    }

    return {
      ok: null,
      runUrl,
      elapsed: Math.round((Date.now() - started) / 1000),
      reason: "Timed out waiting for harvest result",
    };
  }

  global.phGithubRecipePush = {
    canonicalDioceseSlug,
    resolveGhRepo,
    locateRecipe,
    pushRecipe,
    dispatchHarvestTest,
    fetchReportJson,
    parishPdfExists,
    pollHarvestUntilDone,
    findLatestHarvestRun,
    parishHarvestStatus,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
