// Ссылка «Открыть материал» в окне-инфобоксе: путь сайта открывается окном рабочего стола, иначе обычным переходом.
(function () {
  "use strict";
  document.addEventListener("click", function (event) {
    const link = event.target.closest && event.target.closest("a[data-open]");
    if (!link) return;
    let desktop = null;
    try { desktop = window.parent !== window && window.parent.desktopAPI; } catch (error) { desktop = null; }
    const url = link.getAttribute("href");
    if (desktop && typeof desktop.openApp === "function" && url.startsWith("/")) {
      event.preventDefault();
      desktop.openApp("map-link-" + url, link.dataset.label || "link", url);
    } else if (!url.startsWith("/")) {
      event.preventDefault();
      window.open(url, "_blank", "noopener");
    }
  });
})();
