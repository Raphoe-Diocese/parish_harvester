// ── Click Chain Tracking (Multi-page Click Sequences) ────────────────────────

(() => {
  if (globalThis.__phClickChainInstalled) {
    return;
  }
  globalThis.__phClickChainInstalled = true;

  let clickChainState = {
    active: false,
    steps: [],
    currentPageUrl: "",
    navigationDetectTimeout: null,
  };

  const startClickChainMode = (onComplete, showStatus) => {
    clickChainState.active = true;
    clickChainState.steps = [];
    clickChainState.currentPageUrl = window.location.href;

    if (showStatus) {
      showStatus(
        "🔗 Click chain mode active. Click links to build a sequence. Press Escape to finish, or continue clicking for multi-page chains.",
        "info"
      );
    }

    const originalHref = window.location.href;
    const navigationMonitor = setInterval(() => {
      if (window.location.href !== originalHref && clickChainState.active) {
        clickChainState.currentPageUrl = window.location.href;
        if (showStatus) {
          showStatus(
            `✅ Navigated to new page (${clickChainState.steps.length} clicks recorded). Click more or press Escape to finish.`,
            "info"
          );
        }
      }
    }, 500);

    clickChainState.navigationDetectTimeout = navigationMonitor;

    const handleChainClick = (e) => {
      if (!clickChainState.active) return;

      const el = e.target instanceof Element
        ? e.target.closest('a,button,[role="button"],[role="link"],input[type="submit"],input[type="button"]')
        : null;

      if (!el) return;

      e.preventDefault();
      e.stopImmediatePropagation();

      const text = (el.innerText || el.textContent || "").trim().slice(0, 100);
      const selector = _buildClickSelector(el, text);

      clickChainState.steps.push({
        selector,
        text,
        url: window.location.href,
        timestamp: new Date().toISOString(),
      });

      if (showStatus) {
        showStatus(
          `✅ Click ${clickChainState.steps.length} recorded: "${text || selector.slice(0, 30)}..."`,
          "success"
        );
      }

      e.target.click?.();
    };

    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        stopClickChainMode();
        onComplete(clickChainState.steps);
      }
    };

    setTimeout(() => {
      if (!clickChainState.active) return;
      document.addEventListener("click", handleChainClick, true);
      document.addEventListener("keydown", handleKeyDown, true);
    }, 0);
  };

  const stopClickChainMode = () => {
    clickChainState.active = false;

    if (clickChainState.navigationDetectTimeout) {
      clearInterval(clickChainState.navigationDetectTimeout);
      clickChainState.navigationDetectTimeout = null;
    }
  };

  const _buildClickSelector = (el, text) => {
    if (text && text.length >= 3 && text.length <= 60) {
      return `${(el.tagName || "").toLowerCase()}:has-text("${text.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}")`;
    }

    const parts = [];
    let current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE && parts.length < 6) {
      let selector = current.tagName.toLowerCase();

      if (current.id) {
        selector += `#${current.id}`;
        parts.unshift(selector);
        break;
      }

      const parent = current.parentElement;
      if (parent) {
        const siblings = Array.from(parent.children).filter((c) => c.tagName === current.tagName);
        if (siblings.length > 1) {
          selector += `:nth-of-type(${siblings.indexOf(current) + 1})`;
        }
      }

      parts.unshift(selector);
      current = current.parentElement;
    }

    return parts.join(" > ");
  };

  const convertClickChainToRecipeSteps = (clickChain) => {
    if (!Array.isArray(clickChain) || clickChain.length === 0) return [];

    const steps = [];
    let previousUrl = null;

    for (const clickStep of clickChain) {
      if (clickStep.url !== previousUrl) {
        steps.push({
          action: "goto",
          url: clickStep.url,
        });
        previousUrl = clickStep.url;
      }

      const clickRecipeStep = {
        action: "click",
        selector: clickStep.selector,
      };

      if (clickStep.text) {
        clickRecipeStep.fallback_selectors = [`button:has-text("${clickStep.text.replace(/"/g, '\\"')}")`];
      }

      steps.push(clickRecipeStep);
    }

    return steps;
  };

  window.ph_clickChain = {
    start: startClickChainMode,
    stop: stopClickChainMode,
    convert: convertClickChainToRecipeSteps,
    getState: () => ({ ...clickChainState }),
  };
})();
