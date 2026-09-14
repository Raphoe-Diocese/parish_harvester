#!/usr/bin/env node
/**
 * C5 — executable extension JS tests (no browser).
 * 1) pollHarvestUntilDone is ok only when last_tested_at changes.
 * 2) every chrome.runtime.sendMessage({type}) in content.js / sidepanel.js
 *    has a listener (background.js, or sidepanel.js for broadcasts).
 */
import fs from "fs";
import path from "path";
import vm from "vm";
import assert from "assert";
import { fileURLToPath } from "url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

function loadGithubRecipePush(fetchImpl) {
  const code = fs.readFileSync(
    path.join(ROOT, "extension", "github_recipe_push.js"),
    "utf8"
  );
  const sandbox = {
    fetch: fetchImpl,
    Date,
    setTimeout,
    clearTimeout,
    AbortController,
    atob,
    btoa,
    encodeURIComponent,
    decodeURIComponent,
    TextEncoder,
    TextDecoder,
    console,
  };
  sandbox.globalThis = sandbox;
  sandbox.self = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(code, sandbox);
  if (!sandbox.phGithubRecipePush?.pollHarvestUntilDone) {
    throw new Error("phGithubRecipePush.pollHarvestUntilDone missing after load");
  }
  return sandbox.phGithubRecipePush;
}

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => "" },
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

function statusPayload(lastTestedAt, outcome = "ok") {
  return {
    parishes: {
      bangorparish: {
        outcome,
        last_tested_at: lastTestedAt,
        display_name: "Bangor",
      },
    },
  };
}

function makeFetch({ lastTestedAt, runCreatedAt, outcome = "ok" }) {
  const statusJson = statusPayload(lastTestedAt, outcome);
  const encoded = Buffer.from(JSON.stringify(statusJson), "utf8").toString("base64");
  return async (url) => {
    const href = String(url);
    if (href.includes("/actions/workflows/harvest.yml/runs")) {
      return jsonResponse({
        workflow_runs: [
          {
            id: 99,
            html_url: "https://github.com/Raphoe-Diocese/parish_harvester/actions/runs/99",
            created_at: runCreatedAt,
            display_title: "Harvest bangorparish",
            name: "Harvest",
            status: "completed",
            conclusion: "success",
          },
        ],
      });
    }
    if (href.includes("/commits?path=")) {
      return jsonResponse([
        {
          sha: "deadbeef",
          commit: { committer: { date: lastTestedAt } },
        },
      ]);
    }
    if (href.includes("/contents/parishes/parish_status.json")) {
      return jsonResponse({ content: encoded });
    }
    throw new Error(`unexpected fetch ${href}`);
  };
}

async function testPollHarvestUntilDone() {
  const oldAt = "2026-09-01T10:00:00.000Z";
  const newAt = "2026-09-13T22:00:00.000Z";

  const apiChanged = loadGithubRecipePush(
    makeFetch({
      lastTestedAt: newAt,
      runCreatedAt: new Date(Date.now() - 20000).toISOString(),
    })
  );
  const changed = await apiChanged.pollHarvestUntilDone({
    gh_pat: "test-pat",
    gh_repo: "Raphoe-Diocese/parish_harvester",
    parish_key: "bangorparish",
    startedAt: Date.now() - 1000,
    previousTestedAt: oldAt,
    maxWaitMs: 8000,
  });
  assert.strictEqual(changed.ok, true, "ok when last_tested_at changed");

  const startedLong = Date.now() - 95_000;
  const runAt = new Date(Date.now() - 60_000).toISOString();
  const apiSame = loadGithubRecipePush(
    makeFetch({ lastTestedAt: oldAt, runCreatedAt: runAt })
  );
  const same = await apiSame.pollHarvestUntilDone({
    gh_pat: "test-pat",
    gh_repo: "Raphoe-Diocese/parish_harvester",
    parish_key: "bangorparish",
    startedAt: startedLong,
    previousTestedAt: oldAt,
    maxWaitMs: 120_000,
  });
  assert.strictEqual(same.ok, false, "not ok when last_tested_at is unchanged");

  const apiLeftover = loadGithubRecipePush(
    makeFetch({ lastTestedAt: oldAt, runCreatedAt: runAt })
  );
  const leftover = await apiLeftover.pollHarvestUntilDone({
    gh_pat: "test-pat",
    gh_repo: "Raphoe-Diocese/parish_harvester",
    parish_key: "bangorparish",
    startedAt: startedLong,
    previousTestedAt: "",
    maxWaitMs: 120_000,
  });
  assert.strictEqual(
    leftover.ok,
    false,
    "not ok when leftover last_tested_at is older than this test"
  );
  console.log("ok: pollHarvestUntilDone requires last_tested_at change");
}

function extractSendMessageTypes(src) {
  const types = new Set();
  const re = /sendMessage\(\s*\{[\s\S]{0,120}?type:\s*["']([a-z0-9_]+)["']/g;
  let match;
  while ((match = re.exec(src))) {
    types.add(match[1]);
  }
  return types;
}

function extractHandlerTypes(src) {
  const types = new Set();
  const re =
    /(?:message\??\.type|type)\s*(?:===|!==)\s*["']([a-z0-9_]+)["']/g;
  let match;
  while ((match = re.exec(src))) {
    types.add(match[1]);
  }
  return types;
}

function testMessageHandlers() {
  const content = fs.readFileSync(path.join(ROOT, "extension", "content.js"), "utf8");
  const sidepanel = fs.readFileSync(path.join(ROOT, "extension", "sidepanel.js"), "utf8");
  const background = fs.readFileSync(path.join(ROOT, "extension", "background.js"), "utf8");

  const sent = new Set([
    ...extractSendMessageTypes(content),
    ...extractSendMessageTypes(sidepanel),
  ]);
  // problems_refresh is a broadcast the Problems tab listens for; Chrome
  // delivers runtime messages to the side panel as well as the worker.
  const handled = new Set([
    ...extractHandlerTypes(background),
    ...extractHandlerTypes(sidepanel),
  ]);

  assert.ok(sent.size > 0, "expected sendMessage types in content.js / sidepanel.js");
  const missing = [...sent].filter((type) => !handled.has(type)).sort();
  assert.deepStrictEqual(
    missing,
    [],
    `sendMessage types with no handler: ${missing.join(", ")}`
  );
  console.log(`ok: ${sent.size} sendMessage types have handlers (${[...sent].sort().join(", ")})`);
}

// 14/09/2026: Send & test on St Patrick's Belfast replaced the whole
// waf_retry_wordpress recipe with 3 Playwright clicks and no site_type.
// The harvester then 403'd. pushRecipe must keep engine fields.
function makePushFetch(existingRecipe, putLog) {
  const encoded = Buffer.from(JSON.stringify(existingRecipe), "utf8").toString("base64");
  return async (url, init = {}) => {
    const href = String(url);
    const method = String(init.method || "GET").toUpperCase();
    if (href.includes("/contents/parishes/recipes/down_and_connor/stpatricksbelfast.json")) {
      if (method === "GET") {
        return jsonResponse({ sha: "abc123", content: encoded, encoding: "base64" });
      }
      if (method === "PUT") {
        const body = JSON.parse(init.body);
        putLog.push(JSON.parse(Buffer.from(body.content, "base64").toString("utf8")));
        return jsonResponse({ content: { html_url: "https://github.com/x/y/blob/main/r.json" } });
      }
    }
    if (href.includes("/contents/parishes/recipes/")) {
      return jsonResponse({ message: "Not Found" }, 404);
    }
    return jsonResponse({}, 404);
  };
}

async function testPushKeepsEngineRecipe() {
  const existing = {
    parish_key: "stpatricksbelfast",
    display_name: "St Patrick's, Belfast",
    diocese: "down_and_connor",
    start_url: "https://www.stpatricksbelfast.org/category/weekly-bulletins",
    steps: [{ action: "goto", url: "https://www.stpatricksbelfast.org/category/weekly-bulletins" }],
    site_type: "waf_retry_wordpress",
    post_slug_patterns: ["weekly-bulletin-for-sunday-"],
    harvest_note: "WAF blocks browsers; plain HTTP only.",
    do_not: ["Do not switch to Playwright clicks."],
  };
  const putLog = [];
  const mod = loadGithubRecipePush(makePushFetch(existing, putLog));
  const clickRecipe = {
    parish_key: "stpatricksbelfast",
    display_name: "St Patrick's, Belfast",
    diocese: "down_and_connor",
    start_url:
      "https://www.stpatricksbelfast.org/weekly-bulletins/weekly-bulletin-for-sunday-13-september-2026/",
    steps: [
      {
        action: "click",
        href: "https://www.stpatricksbelfast.org/weekly-bulletins/weekly-bulletin-for-sunday-13-september-2026/",
        selector: "a",
      },
      { action: "print_to_pdf" },
    ],
  };
  const res = await mod.pushRecipe({
    gh_pat: "ghp_test",
    gh_repo: "Raphoe-Diocese/parish_harvester",
    parish_key: "stpatricksbelfast",
    recipe: clickRecipe,
  });
  assert.strictEqual(res.ok, true, res.error);
  assert.strictEqual(res.keptEngineRecipe, true, "engine recipe should be kept");
  assert.strictEqual(putLog.length, 1, "one PUT expected");
  const pushed = putLog[0];
  assert.strictEqual(pushed.site_type, "waf_retry_wordpress");
  assert.deepStrictEqual(pushed.post_slug_patterns, ["weekly-bulletin-for-sunday-"]);
  assert.strictEqual(pushed.harvest_note, existing.harvest_note);
  assert.deepStrictEqual(pushed.do_not, existing.do_not);
  assert.strictEqual(pushed.start_url, existing.start_url, "start_url must stay the listing");
  assert.deepStrictEqual(pushed.steps, existing.steps, "Playwright clicks must not replace the engine steps");
  assert.strictEqual(pushed.example_post_url, clickRecipe.steps[0].href);
  console.log("ok: pushRecipe keeps waf_retry_wordpress recipe and saves example_post_url");

  // Plain recipe (no engine site_type): new steps win, other fields survive.
  const plain = {
    parish_key: "stpatricksbelfast",
    display_name: "St Patrick's, Belfast",
    diocese: "down_and_connor",
    start_url: "https://example.org/bulletins",
    steps: [{ action: "goto", url: "https://example.org/bulletins" }],
    timeout_ms: 45000,
    harvest_note: "Keep me.",
  };
  const putLog2 = [];
  const mod2 = loadGithubRecipePush(makePushFetch(plain, putLog2));
  const res2 = await mod2.pushRecipe({
    gh_pat: "ghp_test",
    gh_repo: "Raphoe-Diocese/parish_harvester",
    parish_key: "stpatricksbelfast",
    recipe: {
      parish_key: "stpatricksbelfast",
      start_url: "https://example.org/bulletins",
      steps: [{ action: "click", selector: "a.pdf" }, { action: "download" }],
    },
  });
  assert.strictEqual(res2.ok, true, res2.error);
  assert.strictEqual(res2.keptEngineRecipe, false);
  assert.strictEqual(putLog2[0].steps.length, 2);
  assert.strictEqual(putLog2[0].timeout_ms, 45000, "timeout_ms must survive a steps push");
  assert.strictEqual(putLog2[0].harvest_note, "Keep me.");
  assert.strictEqual(putLog2[0].display_name, plain.display_name);
  console.log("ok: pushRecipe replaces steps but keeps the other recipe fields");
}

async function main() {
  testMessageHandlers();
  await testPollHarvestUntilDone();
  await testPushKeepsEngineRecipe();
  console.log("C5 extension JS tests passed");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
