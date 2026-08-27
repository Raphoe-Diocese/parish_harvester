/**
 * Back-compat loader. Older pages reference this file.
 * The real viewer is pdf-inpage-viewer.js (PDF.js in-page render).
 */
(function () {
  if (window.__parishPressPdfInpage) return;
  var s = document.createElement("script");
  s.src = "/assets/pdf-inpage-viewer.js?v=20260827c";
  s.defer = true;
  document.head.appendChild(s);
})();
