/**
 * Plain-English playbook — what to do on THIS page (no jargon).
 */
(() => {
  const PLAIN_INTRO =
    "You are showing the computer where this parish hides its weekly bulletin. " +
    "When you are done, it tests just this parish on GitHub (not the big combined PDF).";

  const PLANS = {
    direct_pdf: {
      title: "You are already on the bulletin PDF",
      now: "Tap the green Save button below, then Send & test.",
      steps: [
        "Save this PDF (one tap).",
        "Send & test — wait for the green tick in the Problems tab.",
      ],
    },
    cloud_folder: {
      title: "Bulletins live in a cloud folder",
      now: "Pick this week's dated row (newest at top), then save the PDF.",
      steps: [
        "Point at this Sunday's PDF row.",
        "When the file opens → save it → Send & test.",
      ],
    },
    parish_messenger: {
      title: "Parish Messenger site",
      now: "Point at View Newsletter — not Gift Aid or GDPR.",
      steps: [
        "Point at the newsletter link.",
        "When the PDF opens → save it → Send & test.",
      ],
    },
    pdf_links: {
      title: "This page lists bulletin PDFs",
      now: "Point at the top / newest Parish News or bulletin link.",
      steps: [
        "Point at the newest bulletin link (usually the first row).",
        "Green Yes opens it — save if needed → Send & test.",
      ],
    },
    pdfemb: {
      title: "WordPress PDF list",
      now: "Point at this week's bulletin in the list.",
      steps: ["Point at the bulletin link.", "Save PDF → Send & test."],
    },
    wix_html: {
      title: "Bulletin is a web page (not a PDF file)",
      now: "Save this page as PDF, then Send & test.",
      steps: ["Use Save page as PDF.", "Send & test."],
    },
    wix_date_grid: {
      title: "Calendar of old bulletins",
      now: "Point at this Sunday's entry in the grid.",
      steps: ["Point at this week's row.", "Save → Send & test."],
    },
    wix_viewer: {
      title: "PDF inside a viewer",
      now: "Open the real PDF or use Bulletin in a frame.",
      steps: ["Get to the actual PDF.", "Save → Send & test."],
    },
    iframe: {
      title: "PDF is inside a box on the page",
      now: "Use Bulletin in a frame, then save the PDF.",
      steps: ["Pick the frame with the bulletin.", "Save PDF → Send & test."],
    },
    oneweb_docx: {
      title: "One.com newsletter (Word file)",
      now: "Tap Save newsletter — it is automatic on this site.",
      steps: ["Save newsletter (auto).", "Send & test."],
    },
    iframe_maybe: {
      title: "Bulletin might be in a frame",
      now: "Try Bulletin in a frame, or point at a PDF link.",
      steps: ["Find the bulletin.", "Save → Send & test."],
    },
    image: {
      title: "Bulletin is a picture",
      now: "Point at the bulletin image.",
      steps: ["Pick the image.", "Send & test."],
    },
    weekly_bulletin_download: {
      title: "Weekly list with a download icon",
      now: "Click the cloud ↓ on this week's row — or tap the button below.",
      steps: ["Download this week's row.", "Send & test."],
    },
    mdocs_bulletin_list: {
      title: "PDF bulletin table (mDocs plugin)",
      now: "Point at Download on this week's row — real PDF files, NOT Save page as PDF.",
      steps: [
        "Step 1: Point at the Download link on the newest bulletin row.",
        "Step 2: Capture the PDF download (never Save page as PDF or Crop).",
        "Send & test.",
      ],
    },
    html: {
      title: "Normal parish web page",
      now: "Point at News / Newsletter — or Save page as PDF if the bulletin text is already on screen.",
      steps: [
        "If bulletin text is on this page: tap Save page as PDF.",
        "If it is a picture: tap Pick bulletin image.",
        "Otherwise point at the link that opens the bulletin.",
        "Send & test when done.",
      ],
    },
    unknown: {
      title: "Open the parish newsletter page first",
      now: "Go to where the weekly bulletin is listed, then the toolbar will update.",
      steps: ["Find the news / newsletter page on this website."],
    },
  };

  const _defaultPlan = (pageCtx) => ({
    title: pageCtx.summary || "Train this parish",
    now: pageCtx.advice || "Point at the link that opens the weekly bulletin.",
    steps: [
      "Point at the bulletin link.",
      "Send & test when the steps look right.",
    ],
  });

  const getPlan = (pageCtx, state = {}) => {
    const type = pageCtx?.type || "unknown";
    const base = PLANS[type] || _defaultPlan(pageCtx);
    const steps = [...base.steps];
    let now = base.now || "";
    const stepCount = Number(state.stepCount || 0);
    const hasTerminal = Boolean(state.hasTerminal);

    if (state.fixNow) {
      now = `Fixing ${state.parishName || "this parish"} — ${now}`;
    }
    if (stepCount > 0 && !hasTerminal) {
      now = `${stepCount} step${stepCount === 1 ? "" : "s"} saved — ${now}`;
    }
    if (hasTerminal) {
      now = "Ready! Scroll down and tap Send & test.";
    }
    if (state.needsRetrain) {
      steps.unshift("Last Sunday failed — re-point at the bulletin, then Send & test again.");
    }
    if (type === "cloud_folder" && state.expectedCloudLabel) {
      if (state.cloudRowVisible === false) {
        steps.push(`Row ${state.expectedCloudLabel} not visible yet — pick the newest dated file.`);
      }
    }
    return {
      emoji: pageCtx?.emoji || "📋",
      title: base.title,
      now,
      steps,
      pushReady: hasTerminal && stepCount > 0,
      journeyStep: hasTerminal ? 3 : stepCount > 0 ? 2 : 1,
    };
  };

  const render = (el, pageCtx, state) => {
    if (!el) return;
    const plan = getPlan(pageCtx, state);
    el.replaceChildren();
    el.dataset.journeyStep = String(plan.journeyStep);

    const nowLine = document.createElement("div");
    nowLine.style.cssText =
      "font-size:11px;font-weight:600;color:#f9fafb;line-height:1.45;margin-bottom:6px;";
    nowLine.textContent = `${plan.emoji} ${plan.now}`;
    el.appendChild(nowLine);

    const details = document.createElement("details");
    details.style.cssText = "margin:0;";
    const summary = document.createElement("summary");
    summary.style.cssText = "cursor:pointer;font-size:9px;color:#9ca3af;list-style-position:inside;";
    summary.textContent = `More help: ${plan.title}`;
    details.appendChild(summary);

    const inner = document.createElement("div");
    inner.style.cssText = "margin-top:6px;";
    const intro = document.createElement("div");
    intro.style.cssText = "font-size:9px;color:#93c5fd;line-height:1.45;margin-bottom:6px;";
    intro.textContent = PLAIN_INTRO;
    inner.appendChild(intro);

    const ol = document.createElement("ol");
    ol.style.cssText = "margin:0 0 6px 16px;padding:0;font-size:9px;line-height:1.5;color:#cbd5e1;";
    for (const s of plan.steps) {
      const li = document.createElement("li");
      li.style.marginBottom = "3px";
      li.textContent = s;
      ol.appendChild(li);
    }
    inner.appendChild(ol);

    const doNot = Array.isArray(pageCtx?.fingerprintDoNot) ? pageCtx.fingerprintDoNot : [];
    if (doNot.length) {
      const avoid = document.createElement("div");
      avoid.style.cssText =
        "font-size:9px;color:#fecaca;line-height:1.45;background:#450a0a;border:1px solid #991b1b;border-radius:6px;padding:5px 6px;margin-bottom:4px;";
      avoid.textContent = `Do not click: ${doNot.join(" · ")}`;
      inner.appendChild(avoid);
    }

    if (state.needsRetrain) {
      const warn = document.createElement("div");
      warn.style.cssText = "font-size:9px;color:#fca5a5;margin-bottom:4px;";
      warn.textContent = "⚠️ Last Sunday's automatic download failed for this parish.";
      inner.appendChild(warn);
    } else if (plan.pushReady) {
      const ok = document.createElement("div");
      ok.style.cssText = "font-size:9px;color:#86efac;";
      ok.textContent = "✅ Ready to send & test.";
      inner.appendChild(ok);
    } else if (stepCountFromState(state) > 0) {
      const wait = document.createElement("div");
      wait.style.cssText = "font-size:9px;color:#fde68a;";
      wait.textContent = "⏳ Keep going until the bulletin is captured.";
      inner.appendChild(wait);
    }

    details.appendChild(inner);
    el.appendChild(details);
  };

  const stepCountFromState = (state) => Number(state?.stepCount || 0);

  const renderJourneyBar = (el, step) => {
    if (!el) return;
    const s = Math.min(3, Math.max(1, Number(step) || 1));
    const labels = ["1 Find link", "2 Confirm", "3 Send & test"];
    el.replaceChildren();
    const wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;gap:4px;margin-bottom:6px;";
    for (let i = 1; i <= 3; i += 1) {
      const pill = document.createElement("div");
      const active = i === s;
      const done = i < s;
      pill.style.cssText = [
        "flex:1",
        "text-align:center",
        "font-size:9px",
        "line-height:1.3",
        "padding:4px 2px",
        "border-radius:5px",
        "border:1px solid",
        active ? "background:#1d4ed8;border-color:#3b82f6;color:#fff;font-weight:700"
          : done ? "background:#14532d;border-color:#16a34a;color:#86efac"
          : "background:#0f172a;border-color:#374151;color:#6b7280",
      ].join(";");
      pill.textContent = (done ? "✓ " : "") + labels[i - 1];
      wrap.appendChild(pill);
    }
    el.appendChild(wrap);
  };

  window.ph_playbook = { getPlan, render, renderJourneyBar, PLAIN_INTRO };
})();
