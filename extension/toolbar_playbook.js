/**
 * Parish Trainer playbook — visible "what to do on THIS page" (no AI, no chat).
 */
(() => {
  const PIN_HELP =
    "📌 Pin = remember which link is the bulletin on this website. " +
    "You still open that link once, then finish with Save PDF / Save page / Pick image. " +
    "Pin helps next time you train or when the extension suggests links — it does not skip those steps.";

  const PLANS = {
    direct_pdf: {
      title: "You are on the bulletin PDF",
      steps: [
        "Tap Save this PDF (adds a download step).",
        "Check Recipe Preview ends with download.",
        "Pick diocese → Push Recipe to GitHub.",
        "Optional: Operator Console → Instant rebuild to test.",
      ],
      pin: false,
    },
    cloud_folder: {
      title: "Google Drive / OneDrive folder",
      steps: [
        "Tap Pick this Sunday's PDF row (dated YY.MM.DD, e.g. 26.06.14.pdf).",
        "On the file preview page → Save this PDF.",
        "Push Recipe — Sunday auto-picks the right date each week (2026, 2027, 2028…).",
      ],
      pin: false,
    },
    parish_messenger: {
      title: "Parish Messenger site",
      steps: [
        "Tap Follow a link → pick View Newsletter (not Gift Aid).",
        "When the PDF opens → Save this PDF → Push.",
      ],
      pin: true,
    },
    pdf_links: {
      title: "This page lists PDF links",
      steps: [
        "Tap Follow a link → pick the newest bulletin row.",
        "Record & open link → on PDF page → Save this PDF → Push.",
      ],
      pin: true,
    },
    pdfemb: {
      title: "WordPress PDF list",
      steps: [
        "Tap Follow a link → pick this week's bulletin.",
        "Open PDF → Save this PDF → Push.",
      ],
      pin: true,
    },
    wix_html: {
      title: "HTML text bulletin (WordPress / Wix)",
      steps: [
        "If you need a menu click first → Follow a link.",
        "On the newsletter article page → Save page as PDF → Push.",
      ],
      pin: false,
    },
    wix_date_grid: {
      title: "Wix calendar of bulletins",
      steps: [
        "Follow a link → pick this Sunday's entry.",
        "On that page → Save page as PDF → Push.",
      ],
      pin: true,
    },
    wix_viewer: {
      title: "PDF inside Wix viewer",
      steps: [
        "Tap Bulletin in a frame, or open download in viewer.",
        "When you see the real PDF → Save this PDF → Push.",
      ],
      pin: false,
    },
    iframe: {
      title: "PDF in an embedded frame",
      steps: [
        "Tap Bulletin in a frame → pick the frame with the PDF.",
        "Then Save this PDF → Push.",
      ],
      pin: false,
    },
    oneweb_docx: {
      title: "One.com — automatic (no need to wait for previews)",
      steps: [
        "Bulletin URL read from page HTML instantly — no iframe loading needed.",
        "Tap 📄 Save newsletter (auto) or Push Recipe directly.",
        "Harvester downloads the .docx file directly each Sunday.",
      ],
      pin: false,
    },
    iframe_maybe: {
      title: "Possible PDF frame",
      steps: [
        "Try Bulletin in a frame, or Follow a link to the PDF.",
        "Finish with Save this PDF → Push.",
      ],
      pin: false,
    },
    image: {
      title: "Bulletin may be an image",
      steps: [
        "Tap Pick an image (or crop) on the bulletin picture.",
        "Push when Recipe Preview ends with image or crop.",
      ],
      pin: false,
    },
    weekly_bulletin_download: {
      title: "Weekly bulletin list — cloud download",
      steps: [
        "Click the cloud ↓ icon on this Sunday's row (PDF downloads automatically).",
        "Wait for green ✅ — download step should auto-record.",
        "Push Recipe.",
      ],
      pin: false,
    },
    html: {
      title: "Normal web page",
      steps: [
        "Tap Follow a link → menus like News / Newsletter / Bulletin.",
        "Stop when you reach PDF or newsletter page, then finish capture → Push.",
      ],
      pin: true,
    },
    unknown: {
      title: "Go to the parish bulletin area first",
      steps: [
        "Open the page where the weekly newsletter lives.",
        "The trainer will update with clearer steps.",
      ],
      pin: false,
    },
  };

  const _defaultPlan = (pageCtx) => ({
    title: pageCtx.summary || "Train this parish",
    steps: [
      pageCtx.advice || "Follow menu links toward the bulletin.",
      "Finish with Save PDF, Save page as PDF, or Pick image.",
      "Push Recipe when Recipe Preview looks right.",
    ],
    pin: true,
  });

  const getPlan = (pageCtx, state = {}) => {
    const type = pageCtx?.type || "unknown";
    const base = PLANS[type] || _defaultPlan(pageCtx);
    const steps = [...base.steps];
    const stepCount = Number(state.stepCount || 0);
    const hasTerminal = Boolean(state.hasTerminal);

    if (stepCount > 0 && !hasTerminal) {
      steps.unshift(`✓ ${stepCount} step(s) saved — keep going until you capture the bulletin.`);
    }
    if (hasTerminal) {
      steps.unshift("✓ Bulletin capture recorded — scroll to Push Recipe.");
    }
    if (state.needsRetrain) {
      steps.unshift(
        "⚠️ RETRAIN NEEDED — last Sunday harvest failed. Re-record steps below, then Push."
      );
    }
    if (type === "cloud_folder" && state.expectedCloudLabel) {
      if (state.cloudRowVisible === false) {
        steps.push(
          `This Sunday's row (${state.expectedCloudLabel}) is not on screen yet — pick the newest dated PDF.`
        );
      } else {
        steps.push(`Looking for row: ${state.expectedCloudLabel}`);
      }
    }
    if (state.lastHarvestIssue && !state.needsRetrain) {
      steps.push(`Last Sunday failed: ${state.lastHarvestIssue.slice(0, 70)}… — this push should fix it.`);
    }
    return {
      emoji: pageCtx?.emoji || "📋",
      title: base.title,
      steps,
      showPin: Boolean(base.pin) && type !== "direct_pdf",
      pinHelp: PIN_HELP,
      pushReady: hasTerminal && stepCount > 0,
    };
  };

  const render = (el, pageCtx, state) => {
    if (!el) return;
    const plan = getPlan(pageCtx, state);
    el.replaceChildren();

    const head = document.createElement("div");
    head.style.cssText = "font-size:12px;font-weight:700;color:#f9fafb;margin-bottom:6px;line-height:1.35;";
    head.textContent = `${plan.emoji} ${plan.title}`;
    el.appendChild(head);

    const ol = document.createElement("ol");
    ol.style.cssText = "margin:0 0 8px 18px;padding:0;font-size:10px;line-height:1.5;color:#e2e8f0;";
    for (const s of plan.steps) {
      const li = document.createElement("li");
      li.style.marginBottom = "4px";
      li.textContent = s;
      ol.appendChild(li);
    }
    el.appendChild(ol);

    if (plan.showPin) {
      const pin = document.createElement("div");
      pin.style.cssText = "font-size:9px;color:#c4b5fd;line-height:1.45;background:#1e1b4b;border:1px solid #4c1d95;border-radius:6px;padding:6px 8px;margin-bottom:6px;";
      pin.textContent = plan.pinHelp;
      el.appendChild(pin);
    }

    const check = document.createElement("div");
    check.style.cssText = "font-size:9px;line-height:1.4;";
    if (state.needsRetrain) {
      check.style.color = "#fca5a5";
      check.textContent =
        "⚠️ Recipe flagged for retrain — Sunday could not pick this week's bulletin automatically.";
    } else if (plan.pushReady) {
      check.style.color = "#86efac";
      check.textContent = "✅ Ready to push (capture step present).";
    } else {
      check.style.color = "#fde68a";
      check.textContent = "⏳ Not ready to push yet — need a capture step (download / print / image).";
    }
    el.appendChild(check);
  };

  window.ph_playbook = { getPlan, render, PIN_HELP };
})();
