(() => {
  if (globalThis.__phIsolatedBridgeInstalled) {
    return;
  }
  globalThis.__phIsolatedBridgeInstalled = true;

  // Legacy fallback: if any code still posts from the page main world, route to the extension.
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (event.data && event.data.direction === "from-main") {
      const reqId = event.data.reqId || null;
      if (reqId) {
        chrome.runtime.sendMessage(event.data.message, (response) => {
          const lastErr = chrome.runtime.lastError;
          window.postMessage(
            {
              direction: "from-isolated-response",
              reqId,
              response: response || null,
              error: lastErr ? lastErr.message : null,
            },
            "*"
          );
        });
      } else {
        chrome.runtime.sendMessage(event.data.message);
      }
    }
  });
})();
