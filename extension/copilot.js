/**
 * Training Copilot — rule-based page advisor (no API key required).
 * Ranks bulletin links, detects "current newsletter" phrases, ignores admin PDFs.
 */
(() => {
  const STRONG_POSITIVE = [
    /\bcurrent\s+newsletter\b/i,
    /\bthis\s+week(?:'s)?\s+(?:newsletter|bulletin)\b/i,
    /\blatest\s+(?:newsletter|bulletin|weekly)\b/i,
    /\bview\s+newsletter\b/i,
    /\bclick\s+(?:for|here\s+for)?\s*(?:the\s+)?current\b/i,
    /\bthis\s+week\b/i,
    /\bweekly\s+newsletter\b/i,
    /\bparish\s+newsletter\b/i,
    /\bdownload\s+(?:the\s+)?(?:current|latest|this\s+week)/i,
  ];

  const POSITIVE = [
    /\bnewsletter\b/i,
    /\bbulletin\b/i,
    /\bweekly\b/i,
    /\bparish\s+news\b/i,
    /\bview\s+(?:pdf|bulletin|newsletter)\b/i,
  ];

  const NEGATIVE = [
    /\bgift\s*aid\b/i,
    /\bdata\s*entry\b/i,
    /\bdonation\b/i,
    /\bdonate\b/i,
    /\bstripe\b/i,
    /\bpaypal\b/i,
    /\bsafeguarding\b/i,
    /\bprivacy\s+policy\b/i,
    /\baccounts?\b/i,
    /\bstanding\s+order\b/i,
    /\bparish\s+accounts\b/i,
    /\bforms?\b/i,
    /\bregistration\b/i,
  ];

  const PINS_KEY = "ph_copilot_pins";

  const _normHost = (url) => {
    try {
      return new URL(url).hostname.toLowerCase().replace(/^www\d*\./, "");
    } catch (_e) {
      return "";
    }
  };

  const _textBlob = (url, label) => `${url || ""} ${label || ""}`.trim();

  const scorePhrase = (url, label) => {
    const blob = _textBlob(url, label);
    let bonus = 0;
    let penalty = 0;
    let reason = "";

    for (const re of STRONG_POSITIVE) {
      if (re.test(blob)) {
        bonus += 80;
        reason = "Says current/latest newsletter";
        break;
      }
    }
    if (!reason) {
      for (const re of POSITIVE) {
        if (re.test(blob)) {
          bonus += 20;
          reason = "Bulletin/newsletter wording";
          break;
        }
      }
    }
    for (const re of NEGATIVE) {
      if (re.test(blob)) {
        penalty += 120;
        reason = reason ? `${reason} (but looks like admin/form)` : "Admin/form link — skip";
        break;
      }
    }
    if (/\.pdf(\?|$)/i.test(blob)) bonus += 8;
    return { bonus, penalty, reason };
  };

  const matchesPin = (pin, url, label) => {
    if (!pin) return false;
    const blob = _textBlob(url, label).toLowerCase();
    const pinText = String(pin.text || "").toLowerCase().trim();
    const pinHref = String(pin.href || "").toLowerCase().trim();
    if (pinText && blob.includes(pinText.slice(0, Math.min(pinText.length, 40)))) return true;
    if (pinHref) {
      try {
        const abs = new URL(pinHref, url || "https://example.com").pathname.toLowerCase();
        if (blob.includes(abs.split("/").pop() || "")) return true;
      } catch (_e) {
        if (blob.includes(pinHref)) return true;
      }
    }
    return false;
  };

  const rankLinks = (links, { pageUrl = "", pins = null, dateScorer = null } = {}) => {
    const host = _normHost(pageUrl);
    const pin = pins && host ? pins[host] : null;

    const ranked = (Array.isArray(links) ? links : []).map((item, domIdx) => {
      const url = String(item.url || item.href || "").trim();
      const label = String(item.label || item.text || "").trim();
      const phrase = scorePhrase(url, label);
      let pinBonus = 0;
      if (pin && matchesPin(pin, url, label)) {
        pinBonus = 200;
        phrase.reason = "📌 Pinned link for this site";
      }
      let dateScore = 0;
      let hasDate = false;
      let hasFullDate = false;
      if (typeof dateScorer === "function") {
        const d = dateScorer(url, label, domIdx);
        dateScore = d.dateScore || 0;
        hasDate = Boolean(d.hasDate);
        hasFullDate = Boolean(d.hasFullDate);
      }
      const total =
        dateScore * 100 +
        phrase.bonus +
        pinBonus -
        phrase.penalty +
        (item.domIdx ?? domIdx);
      return {
        url,
        label,
        domIdx: item.domIdx ?? domIdx,
        selector: item.selector || "",
        dateScore,
        hasDate,
        hasFullDate,
        phraseBonus: phrase.bonus,
        phrasePenalty: phrase.penalty,
        pinBonus,
        reason: phrase.reason,
        total,
        rejected: phrase.penalty >= 120 && phrase.bonus < 40,
      };
    });

    ranked.sort((a, b) => {
      if (a.rejected !== b.rejected) return a.rejected ? 1 : -1;
      if (a.pinBonus !== b.pinBonus) return b.pinBonus - a.pinBonus;
      if (a.hasFullDate && b.hasFullDate) return b.dateScore - a.dateScore;
      if (a.hasFullDate) return -1;
      if (b.hasFullDate) return 1;
      if (a.hasDate && b.hasDate) return b.dateScore - a.dateScore;
      if (a.hasDate) return -1;
      if (b.hasDate) return 1;
      return b.total - a.total;
    });

    const best = ranked.find((r) => !r.rejected) || ranked[0] || null;
    const alternatives = ranked.filter((r) => !r.rejected && r !== best).slice(0, 3);
    return { best, alternatives, all: ranked };
  };

  const buildPageBrief = () => {
    const headings = [];
    for (const el of document.querySelectorAll("h1,h2,h3,.entry-title,.post-title")) {
      const t = (el.innerText || el.textContent || "").trim().replace(/\s+/g, " ");
      if (t && t.length >= 8 && t.length <= 200) headings.push(t);
      if (headings.length >= 6) break;
    }
    const navNewsletter = [];
    for (const a of document.querySelectorAll("a[href]")) {
      const text = (a.innerText || a.textContent || "").trim().replace(/\s+/g, " ");
      if (!text || text.length > 80) continue;
      if (!/\b(newsletter|bulletin|weekly|parish news)\b/i.test(text)) continue;
      let href = "";
      try { href = new URL(a.getAttribute("href") || "", window.location.href).href; } catch (_e) { /* skip */ }
      navNewsletter.push({ text, href });
      if (navNewsletter.length >= 8) break;
    }
    const path = String(window.location?.pathname || "").toLowerCase();
    const onNewsPage = /newsletter|bulletin|\/news\b|weekly/i.test(path + " " + document.title);
    const bulletinOnPage = headings.some((h) => /\b(newsletter|bulletin)\b/i.test(h));
    return { headings, navNewsletter, onNewsPage, bulletinOnPage };
  };

  const adviseOnPage = ({ pageType = "unknown", brief = {}, best, pin }) => {
    const lines = [];
    if (brief.bulletinOnPage || (brief.onNewsPage && pageType === "wix_html")) {
      lines.push("✅ I see the bulletin on this page.");
      lines.push("→ Click 📰 Save page as PDF (best for Ardara-style HTML newsletters).");
      return lines.join("\n");
    }
    if (pageType === "wix_html" || pageType === "html") {
      lines.push("This looks like an HTML newsletter page.");
      lines.push("→ Use 📰 Save page as PDF after you reach the bulletin.");
    }
    if (brief.navNewsletter?.length === 1) {
      lines.push(`→ Click menu link "${brief.navNewsletter[0].text}" first, then Analyse again.`);
    } else if (brief.navNewsletter?.length > 1) {
      const pick = brief.navNewsletter.find((n) => !/archive|past|old/i.test(n.text)) || brief.navNewsletter[0];
      lines.push(`→ Try "${pick.text}" in the menu (not Archive unless you need an old week).`);
    }
    if (pin) lines.push("📌 Using your pinned link for this site.");
    if (best && !lines.length) return "";
    return lines.join("\n");
  };

  const advise = ({ pageType = "unknown", best, alternatives, pin, pageUrl = "", pageBrief = null }) => {
    const lines = [];
    const onPage = adviseOnPage({ pageType, brief: pageBrief || {}, best, pin });
    if (onPage) lines.push(onPage);
    if (pin && !onPage.includes("pinned")) {
      lines.push("📌 You pinned a link for this site — I'll prefer that.");
    }
    if (!best && !pageBrief?.bulletinOnPage) {
      if (!lines.length) {
        lines.push("I couldn't find bulletin links on this page.");
        lines.push("Try: open the newsletter menu, then click Analyse again.");
      }
      return lines.join("\n");
    }
    if (pageBrief?.bulletinOnPage && pageType !== "pdf_links") {
      return lines.join("\n");
    }
    if (best.pinBonus) {
      lines.push(`Use your pinned link: "${best.label || best.url}"`);
    } else if (best.phraseBonus >= 80) {
      lines.push(`Strong match — "${best.label || "link"}" looks like the current newsletter.`);
    } else if (best.hasFullDate) {
      lines.push(`Best dated link: "${best.label || best.url}" (${best.reason || "newest date"}).`);
    } else {
      lines.push(`Best guess: "${best.label || best.url}".`);
      lines.push("⚠️ Not 100% sure — use Highlight, then Record if it looks right.");
    }
    if (pageType === "parish_messenger") {
      lines.push("Tip: pick View Newsletter, not Gift Aid or Data Entry.");
    }
    if (alternatives.length) {
      lines.push(`Other options: ${alternatives.map((a) => a.label || a.url).slice(0, 2).join("; ")}`);
    }
    if (pageUrl) lines.push(`Page: ${pageUrl}`);
    return lines.join("\n");
  };

  const replyToChat = (userText, context) => {
    const q = String(userText || "").toLowerCase().trim();
    if (!q) return "Ask me anything about this page, or click Analyse page.";
    if (/pin|always|remember/.test(q)) {
      return "Click 📌 Pin after I find the right link — I'll remember it for this site.";
    }
    if (/wrong|bad|incorrect/.test(q)) {
      return "Use Highlight to check my pick. If wrong, click the right link yourself → 👍 Looks right, then 📌 Pin.";
    }
    if (/highlight|show|where/.test(q)) {
      return context?.best
        ? `I'll ring "${context.best.label || context.best.url}". Click Highlight.`
        : "Click Analyse page first.";
    }
    if (/record|save|train/.test(q)) {
      return context?.best
        ? `Click Record step to save "${context.best.label || "this link"}" into your recipe.`
        : "Analyse the page first, then Record step.";
    }
    if (/auto|click for me/.test(q)) {
      return "Click Click for me only when you're happy with the highlight. I'll click once and record it.";
    }
    return context?.advice || "Click Analyse page — I'll scan links and suggest the bulletin.";
  };

  const MEMORY_KEY = "ph_copilot_memory";

  const rememberIssue = (parishKey, payload) => {
    if (!parishKey || typeof chrome === "undefined" || !chrome.storage?.local) return;
    chrome.storage.local.get([MEMORY_KEY], (r) => {
      const mem = r?.[MEMORY_KEY] && typeof r[MEMORY_KEY] === "object" ? r[MEMORY_KEY] : {};
      mem[parishKey] = { ...mem[parishKey], ...payload, updatedAt: new Date().toISOString() };
      chrome.storage.local.set({ [MEMORY_KEY]: mem });
    });
  };

  const getMemory = (parishKey) => new Promise((resolve) => {
    if (!parishKey || typeof chrome === "undefined" || !chrome.storage?.local) {
      resolve(null);
      return;
    }
    chrome.storage.local.get([MEMORY_KEY], (r) => {
      const mem = r?.[MEMORY_KEY] && typeof r[MEMORY_KEY] === "object" ? r[MEMORY_KEY] : {};
      resolve(mem[parishKey] || null);
    });
  });

  window.ph_copilot = {
    PINS_KEY,
    MEMORY_KEY,
    scorePhrase,
    rankLinks,
    buildPageBrief,
    adviseOnPage,
    advise,
    replyToChat,
    rememberIssue,
    getMemory,
    matchesPin,
    normHost: _normHost,
  };
})();
