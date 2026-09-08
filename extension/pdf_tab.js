(() => {
  const statusEl = document.getElementById("status");
  const pagesEl = document.getElementById("pages");
  const params = new URLSearchParams(window.location.search);
  const repo = String(params.get("repo") || "Raphoe-Diocese/parish_harvester").trim();
  const path = String(params.get("path") || "").trim();
  const directUrl = String(params.get("url") || "").trim();
  const title = String(params.get("title") || "").trim();

  function setStatus(text, isErr) {
    statusEl.textContent = text;
    statusEl.className = isErr ? "err" : "";
  }

  function authHeader(pat) {
    const token = String(pat || "").trim();
    if (!token) return "";
    return token.startsWith("github_pat_") ? `Bearer ${token}` : `token ${token}`;
  }

  async function githubDownloadUrl(ghRepo, filePath, pat) {
    const resp = await fetch(
      `https://api.github.com/repos/${ghRepo}/contents/${filePath}?ref=main`,
      {
        cache: "no-store",
        headers: {
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          ...(pat ? { Authorization: authHeader(pat) } : {}),
        },
      }
    );
    if (!resp.ok) return "";
    const data = await resp.json();
    if (Number(data?.size || 0) < 512) return "";
    return String(data?.download_url || "").trim();
  }

  async function fetchPdfBytes(url, pat) {
    const headers = {};
    if (pat && /github\.com|githubusercontent\.com/i.test(url)) {
      headers.Authorization = authHeader(pat);
    }
    const resp = await fetch(url, { cache: "no-store", headers });
    if (!resp.ok) throw new Error(`Could not load bulletin (${resp.status})`);
    const buf = new Uint8Array(await resp.arrayBuffer());
    if (buf.length < 5 || buf[0] !== 0x25 || buf[1] !== 0x50 || buf[2] !== 0x44 || buf[3] !== 0x46) {
      throw new Error("That file is not a PDF.");
    }
    return buf;
  }

  async function resolvePdfBytes() {
    const stored = await chrome.storage.local.get(["gh_pat", "gh_repo"]);
    const pat = String(stored?.gh_pat || "").trim();
    const effectiveRepo = String(stored?.gh_repo || repo || "").trim() || repo;
    if (directUrl) {
      return fetchPdfBytes(directUrl, pat);
    }
    if (!path) throw new Error("No bulletin path.");
    const download = await githubDownloadUrl(effectiveRepo, path, pat);
    const url = download || `https://raw.githubusercontent.com/${effectiveRepo}/main/${path}`;
    return fetchPdfBytes(url, pat);
  }

  async function renderPdf(bytes) {
    const pdfjsLib = globalThis.pdfjsLib;
    if (!pdfjsLib) throw new Error("PDF viewer missing.");
    pdfjsLib.GlobalWorkerOptions.workerSrc = chrome.runtime.getURL("pdf.worker.min.js");
    const pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
    const heading = title || (path.split("/").pop() || "Bulletin");
    document.title = heading;
    setStatus(heading);
    const limit = Math.min(pdf.numPages, 20);
    for (let n = 1; n <= limit; n += 1) {
      const page = await pdf.getPage(n);
      const viewport = page.getViewport({ scale: 1.35 });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      canvas.setAttribute("aria-label", `Page ${n}`);
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;
      pagesEl.appendChild(canvas);
    }
  }

  void (async () => {
    try {
      const bytes = await resolvePdfBytes();
      await renderPdf(bytes);
    } catch (err) {
      setStatus(err?.message || "Could not open bulletin.", true);
    }
  })();
})();
