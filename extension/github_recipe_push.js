/**
 * Shared GitHub recipe push + harvest dispatch (content script + service worker).
 * Content calls this directly so pushes survive MV3 service-worker sleep.
 */
(function initPhGithubRecipePush(global) {
  const DIOCESE_FOLDERS = ["clogher", "derry", "down_and_connor", "raphoe", "unknown"];

  /** Map recipe/slug names to harvest.yml workflow_dispatch diocese input. */
  const harvestWorkflowDiocese = (value) => {
    const slug = canonicalDioceseSlug(value);
    if (!slug) return "all";
    if (slug === "clogher") return "clogher_diocese";
    if (slug === "derry") return "derry_diocese";
    if (slug === "raphoe") return "raphoe_diocese";
    if (slug === "down_and_connor") return "down_and_connor";
    return slug;
  };

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
    if (raw === "clogher" || raw === "clogher_diocese" || raw === "clogher diocese") return "clogher";
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
      return await fetch(url, {
        cache: "no-store",
        ...init,
        headers,
        signal: controller.signal,
      });
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

    // Stale or missing sha (422) — refetch latest sha and retry once.
    if (putResp.status === 422) {
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
      const errText = await githubApiError(putResp);
      if (putResp.status === 422 && /does not match/i.test(errText)) {
        return {
          ok: false,
          error:
            "GitHub recipe changed since this tab loaded — tap Send & test once more (or reload the page first).",
        };
      }
      return { ok: false, error: errText };
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

  const dispatchHarvestTest = async ({ gh_pat, gh_repo: storedRepo, parish_key, diocese }) => {
    const gh_pat_clean = String(gh_pat || "").trim();
    if (!gh_pat_clean) return { ok: false, error: "GitHub PAT not configured." };
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim().toLowerCase();
    const dioceseInput = harvestWorkflowDiocese(diocese);
    const headers = authHeaders(gh_pat_clean, true);
    const resp = await fetchGithub(
      `https://api.github.com/repos/${gh_repo}/actions/workflows/harvest.yml/dispatches`,
      headers,
      20000,
      {
        method: "POST",
        body: JSON.stringify({
          ref: "main",
          inputs: { diocese: dioceseInput, target_parish: key, run_tests: "false" },
        }),
      }
    );
    if (resp.status === 204) return { ok: true };
    if (resp.status === 403) {
      return { ok: false, error: "PAT missing 'workflow' scope — regenerate token with workflow checked." };
    }
    if (resp.status === 404) {
      return {
        ok: false,
        error:
          `GitHub could not start harvest.yml (404). Check repo is ${gh_repo}, the workflow is on main and not disabled, and the PAT can write Actions.`,
      };
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

  const fetchLatestFileCommit = async ({ gh_pat, gh_repo, path }) => {
    const repo = resolveGhRepo(gh_repo);
    const pat = String(gh_pat || "").trim();
    if (!path) return null;
    try {
      const resp = await fetchGithub(
        `https://api.github.com/repos/${repo}/commits?path=${encodeURIComponent(path)}&sha=main&per_page=1`,
        {
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "Cache-Control": "no-cache",
          ...(pat ? { Authorization: authHeaderValue(pat) } : {}),
        },
        12000,
        { cache: "no-store" }
      );
      if (!resp.ok) return null;
      const data = await resp.json();
      const first = Array.isArray(data) ? data[0] : null;
      if (!first?.sha) return null;
      return {
        sha: first.sha,
        date: first.commit?.committer?.date || first.commit?.author?.date || "",
      };
    } catch (_e) {
      return null;
    }
  };

  const attachStatusFetchMeta = (doc, commit) => {
    if (!doc || typeof doc !== "object") return doc;
    doc._ext_fetched_at = new Date().toISOString();
    if (commit?.date) doc._ext_repo_updated_at = commit.date;
    if (commit?.sha) doc._ext_repo_sha = commit.sha;
    return doc;
  };

  const fetchParishStatusJson = async ({ gh_pat, gh_repo: storedRepo }) => {
    const gh_repo = resolveGhRepo(storedRepo);
    const pat = String(gh_pat || "").trim();
    const commit = await fetchLatestFileCommit({
      gh_pat: pat,
      gh_repo,
      path: "parishes/parish_status.json",
    });
    const ref = commit?.sha;
    if (!ref) return null;
    if (pat) {
      try {
        const resp = await fetchGithub(
          `https://api.github.com/repos/${gh_repo}/contents/parishes/parish_status.json?ref=${encodeURIComponent(ref)}`,
          { ...authHeaders(pat), "Cache-Control": "no-cache" },
          15000,
          { cache: "no-store" }
        );
        if (resp.ok) {
          const data = await resp.json();
          return attachStatusFetchMeta(JSON.parse(decodeGithubContent(data.content) || "{}"), commit);
        }
      } catch (_e) {
        // fall through to raw at the same commit
      }
    }
    const raw = await fetch(
      `https://raw.githubusercontent.com/${gh_repo}/${ref}/parishes/parish_status.json?t=${Date.now()}`,
      { cache: "no-store" }
    );
    if (!raw.ok) return null;
    return attachStatusFetchMeta(await raw.json(), commit);
  };

  function parishStatusFromDoc(statusDoc, parishKey) {
    const key = String(parishKey || "").trim();
    const keyLower = key.toLowerCase();
    let row = statusDoc?.parishes?.[key];
    if (!row && statusDoc?.parishes) {
      row = Object.entries(statusDoc.parishes).find(
        ([k]) => String(k).toLowerCase() === keyLower
      )?.[1];
    }
    if (!row) return null;
    const item = { ...row, parish: key };
    if (row.outcome === "ok") return { status: "ok", item };
    if (row.outcome === "stale") {
      return {
        status: "stale",
        item: { ...item, error: row.error || row.reason || "Bulletin too old (recipe worked)" },
      };
    }
    if (row.outcome === "failed") return { status: "failed", item };
    if (row.outcome === "html_only") return { status: "html_link", item };
    if (row.outcome === "skipped" || row.outcome === "disabled") {
      return { status: row.outcome, item };
    }
    return { status: "unknown", item };
  }

  const parishPdfExists = async ({ gh_pat, gh_repo: storedRepo, parish_key }) => {
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim();
    const pat = String(gh_pat || "").trim();
    if (!pat || !key) return false;
    const paths = [
      `Bulletins/${key}.pdf`,
      `Bulletins/current/${key}.pdf`,
      `Bulletins/stale/${key}.pdf`,
    ];
    for (const filePath of paths) {
      try {
        const resp = await fetchGithub(
          `https://api.github.com/repos/${gh_repo}/contents/${filePath}`,
          authHeaders(pat),
          12000
        );
        if (resp.ok) return true;
      } catch (_e) {
        // try the next harvest proof path
      }
    }
    return false;
  };

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const SEND_TEST_MAX_WAIT_MS = 15 * 60 * 1000;

  function formatUkDateFromIso(iso) {
    const match = String(iso || "").match(/(\d{4})-(\d{2})-(\d{2})/);
    return match ? `${match[3]}/${match[2]}/${match[1]}` : "";
  }

  function isFreshHarvestTimestamp(iso, startedAt, skewMs = 120000) {
    const ms = iso ? new Date(iso).getTime() : NaN;
    return Number.isFinite(ms) && ms >= Number(startedAt) - skewMs;
  }

  function harvestRunMatchesParish(run, parishKey, afterMs) {
    if (!run) return false;
    const created = new Date(run.created_at).getTime();
    if (!Number.isFinite(created) || created < afterMs - 30_000) return false;
    const key = String(parishKey || "").trim().toLowerCase();
    if (!key) return false;
    const title = `${run.display_title || ""} ${run.name || ""}`.toLowerCase();
    return title.includes(key);
  }

  async function findLatestHarvestRun(gh_pat, gh_repo, afterMs, parishKey) {
    try {
      const resp = await fetchGithub(
        `https://api.github.com/repos/${gh_repo}/actions/workflows/harvest.yml/runs?per_page=25&event=workflow_dispatch`,
        authHeaders(gh_pat),
        15000
      );
      if (!resp.ok) return { run: null, listError: `GitHub Actions list ${resp.status}` };
      const data = await resp.json();
      const runs = Array.isArray(data.workflow_runs) ? data.workflow_runs : [];
      const matches = runs.filter((run) => harvestRunMatchesParish(run, parishKey, afterMs));
      return { run: matches[0] || null, listError: null };
    } catch (_e) {
      return { run: null, listError: "Could not list GitHub Actions runs" };
    }
  }

  function parishHarvestStatus(report, parishKey) {
    const key = String(parishKey || "").trim().toLowerCase();
    const find = (rows) => (rows || []).find(
      (row) => String(row?.parish || "").trim().toLowerCase() === key
    );
    const downloaded = find(report?.downloaded);
    if (downloaded) return { status: "ok", item: downloaded };
    const stale = find(report?.stale_rejected);
    if (stale) {
      return {
        status: "stale",
        item: {
          ...stale,
          error: stale.error || stale.reason || "Bulletin too old (recipe worked)",
        },
      };
    }
    const failed = find(report?.failed);
    if (failed) {
      if (/Stale bulletin rejected/i.test(String(failed.error || ""))) {
        return { status: "stale", item: failed };
      }
      return { status: "failed", item: failed };
    }
    const htmlLink = find(report?.html_links);
    if (htmlLink) return { status: "html_link", item: htmlLink };
    return { status: "unknown", item: null };
  }

  function outcomeFromFreshStatus(parishStatus, runUrl, elapsed) {
    if (!parishStatus || parishStatus.status === "unknown") return null;
    if (parishStatus.status === "ok") {
      return { ok: true, runUrl, item: parishStatus.item, elapsed };
    }
    if (parishStatus.status === "stale") {
      return {
        ok: false,
        stale: true,
        runUrl,
        item: parishStatus.item,
        elapsed,
        reason: parishStatus.item?.error || parishStatus.item?.reason || "Bulletin too old (recipe worked)",
      };
    }
    if (parishStatus.status === "html_link") {
      return {
        ok: false,
        runUrl,
        item: parishStatus.item,
        elapsed,
        reason: "HTML-only bulletin (no PDF saved)",
      };
    }
    if (parishStatus.status === "failed") {
      return {
        ok: false,
        runUrl,
        item: parishStatus.item,
        elapsed,
        reason: parishStatus.item?.reason || parishStatus.item?.error || "Harvest failed",
      };
    }
    return null;
  }

  /** Poll GitHub until parish_status updates, the run finishes, or we time out. */
  async function pollHarvestUntilDone({
    gh_pat,
    gh_repo: storedRepo,
    parish_key,
    startedAt,
    previousTestedAt = "",
    onProgress,
    maxWaitMs = SEND_TEST_MAX_WAIT_MS,
  }) {
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim().toLowerCase();
    const started = Number(startedAt) || Date.now();
    let runUrl = `https://github.com/${gh_repo}/actions/workflows/harvest.yml`;
    let tracked = null;
    let listError = null;
    let attempt = 0;

    while (Date.now() - started < maxWaitMs) {
      if (attempt > 0) {
        await sleep(attempt < 12 ? 5000 : 10000);
      }
      const elapsed = Math.round((Date.now() - started) / 1000);
      const listed = await findLatestHarvestRun(gh_pat, gh_repo, started, key);
      listError = listed.listError;
      const run = listed.run;
      if (run?.html_url) runUrl = run.html_url;
      if (run && (!tracked || run.id !== tracked.id)) {
        const runNewer = !tracked || new Date(run.created_at).getTime() >= new Date(tracked.created_at).getTime();
        if (runNewer) tracked = run;
      }

      const isOurRun = Boolean(tracked && run && run.id === tracked.id);
      const active = isOurRun ? run : tracked;
      const workflowDone = Boolean(active && active.status === "completed");
      const workflowRunning = Boolean(
        active && (active.status === "in_progress" || active.status === "queued" || active.status === "pending")
      );
      const workflowFailed = workflowDone && active.conclusion === "failure";
      const workflowCancelled = workflowDone && (active.conclusion === "cancelled" || active.conclusion === "skipped");
      const workflowSucceeded = workflowDone && active.conclusion === "success";

      const statusDoc = await fetchParishStatusJson({ gh_pat, gh_repo: storedRepo });
      const fromStatus = statusDoc ? parishStatusFromDoc(statusDoc, key) : null;
      const testedAt = String(fromStatus?.item?.last_tested_at || "").trim();
      const prevTested = String(previousTestedAt || "").trim();
      const freshResult = Boolean(testedAt) && (
        (prevTested && testedAt !== prevTested) ||
        isFreshHarvestTimestamp(testedAt, started, 5000)
      );
      let parishStatus = { status: "unknown", item: null };
      if (freshResult && fromStatus) {
        parishStatus = fromStatus;
      }

      let runStatus = "starting";
      if (listError && !tracked) runStatus = "no_actions_read";
      else if (isOurRun && active) runStatus = active.status;
      else if (tracked) runStatus = "waiting";
      else if (elapsed > 45) runStatus = "queued";

      onProgress?.({
        attempt,
        elapsed,
        runUrl,
        runStatus,
        parishStatus: parishStatus.status,
        queued: !tracked && elapsed > 45,
      });

      const freshOutcome = outcomeFromFreshStatus(parishStatus, runUrl, elapsed);
      if (freshOutcome) return freshOutcome;

      if (workflowSucceeded) {
        // Do not treat a leftover Bulletins/current PDF as this test passing.
      }
      if (workflowCancelled) {
        return {
          ok: false,
          runUrl,
          item: parishStatus.item,
          elapsed,
          reason: "GitHub cancelled this test (another Send & test for the same parish may have replaced it).",
        };
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
      if (workflowDone && !freshResult && elapsed > 90) {
        return {
          ok: false,
          runUrl,
          item: parishStatus.item,
          elapsed,
          reason:
            "Harvest finished but parish_status.json did not update. Open Actions, then refresh Problems.",
        };
      }
      if (!tracked && elapsed > 120 && listError) {
        onProgress?.({
          attempt,
          elapsed,
          runUrl,
          runStatus: "no_actions_read",
          parishStatus: "unknown",
          queued: false,
        });
      }
      attempt += 1;
    }

    const elapsed = Math.round((Date.now() - started) / 1000);
    const statusDoc = await fetchParishStatusJson({ gh_pat, gh_repo: storedRepo });
    const fromStatus = statusDoc ? parishStatusFromDoc(statusDoc, key) : null;
    const testedAt = String(fromStatus?.item?.last_tested_at || "").trim();
    const when = formatUkDateFromIso(testedAt);
    const fileOutcome = fromStatus && fromStatus.status !== "unknown"
      ? outcomeFromFreshStatus(fromStatus, runUrl, elapsed)
      : null;
    const timeoutNote = fromStatus && fromStatus.status !== "unknown"
      ? `Timed out after 15 min. GitHub currently says ${fromStatus.status}${when ? ` as of ${when}` : ""}.`
      : (listError
        ? `${listError}. PAT needs Actions: Read so the extension can watch the run — or wait and refresh Problems from parish_status.json.`
        : "Timed out waiting for last_tested_at to change. Open Actions, then refresh Problems.");
    if (fileOutcome) {
      return { ...fileOutcome, timedOut: true, reason: timeoutNote };
    }
    return {
      ok: false,
      timedOut: true,
      runUrl,
      item: fromStatus?.item || null,
      elapsed,
      reason: timeoutNote,
    };
  }

  const recipeStepsFingerprint = (steps) => {
    if (!Array.isArray(steps)) return "[]";
    return JSON.stringify(
      steps.map((step) => {
        const action = String(step?.action || "").trim().toLowerCase();
        const out = { action };
        if (step?.selector) out.selector = String(step.selector);
        if (step?.text) out.text = String(step.text).slice(0, 120);
        if (step?.pick_strategy) out.pick_strategy = String(step.pick_strategy);
        if (step?.bulletin_position) out.bulletin_position = String(step.bulletin_position);
        if (step?.use_captured_url) out.use_captured_url = true;
        if (step?.url_pattern) out.url_pattern = String(step.url_pattern);
        if (step?.use_target_url) out.use_target_url = true;
        if (action === "goto" && step?.url) out.url = String(step.url);
        return out;
      })
    );
  };

  const recipesMatchForVerify = (savedRecipe, expectedRecipe) => {
    if (!expectedRecipe || typeof expectedRecipe !== "object") return null;
    const savedSteps = Array.isArray(savedRecipe?.steps) ? savedRecipe.steps : [];
    const expectedSteps = Array.isArray(expectedRecipe?.steps) ? expectedRecipe.steps : [];
    return recipeStepsFingerprint(savedSteps) === recipeStepsFingerprint(expectedSteps);
  };

  /**
   * Read the recipe back from GitHub after a push so "saved" is never a lie.
   * Compares step fingerprints (not just counts) and retries briefly while GitHub
   * catches up — avoids false "clear steps" errors from hidden goto injection.
   */
  const verifyRecipe = async ({
    gh_pat,
    gh_repo: storedRepo,
    parish_key,
    expectedSteps,
    expectedRecipe,
    expectedFolder,
  }) => {
    const gh_repo = resolveGhRepo(storedRepo);
    const key = String(parish_key || "").trim().toLowerCase().replace(/\s+/g, "_");
    if (!key) return { ok: false, error: "No parish_key to verify." };
    const pat = String(gh_pat || "").trim();
    const wantCount = Array.isArray(expectedRecipe?.steps)
      ? expectedRecipe.steps.length
      : Number(expectedSteps);
    let lastLocated = null;
    for (let attempt = 0; attempt < 4; attempt += 1) {
      if (attempt > 0) await sleep(1500);
      try {
        lastLocated = await locateRecipe(pat, gh_repo, key, expectedFolder || "");
      } catch (err) {
        if (attempt === 3) {
          return { ok: false, error: `Could not read back from GitHub: ${String(err)}` };
        }
        continue;
      }
      if (!lastLocated?.existingRecipe) {
        if (attempt === 3) {
          return { ok: false, error: "Recipe file not found on GitHub after save." };
        }
        continue;
      }
      const savedRecipe = lastLocated.existingRecipe;
      const savedSteps = Array.isArray(savedRecipe.steps) ? savedRecipe.steps.length : 0;
      const contentMatch = recipesMatchForVerify(savedRecipe, expectedRecipe);
      const countMatch = !Number.isFinite(wantCount) || wantCount <= 0 || savedSteps === wantCount;
      const matches = contentMatch === true || (contentMatch === null && countMatch);
      if (matches) {
        return {
          ok: true,
          filePath: lastLocated.filePath,
          diocese: lastLocated.diocese,
          savedSteps,
          expectedSteps: wantCount,
          matches: true,
        };
      }
    }
    const savedSteps = Array.isArray(lastLocated?.existingRecipe?.steps)
      ? lastLocated.existingRecipe.steps.length
      : 0;
    return {
      ok: true,
      filePath: lastLocated?.filePath || "",
      diocese: lastLocated?.diocese || "",
      savedSteps,
      expectedSteps: wantCount,
      matches: false,
    };
  };

  global.phGithubRecipePush = {
    canonicalDioceseSlug,
    harvestWorkflowDiocese,
    resolveGhRepo,
    locateRecipe,
    pushRecipe,
    verifyRecipe,
    dispatchHarvestTest,
    fetchReportJson,
    fetchLatestFileCommit,
    fetchParishStatusJson,
    parishPdfExists,
    pollHarvestUntilDone,
    findLatestHarvestRun,
    harvestRunMatchesParish,
    isFreshHarvestTimestamp,
    parishHarvestStatus,
    parishStatusFromDoc,
    authHeaderValue,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
