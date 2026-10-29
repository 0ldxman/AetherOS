/* Окно документа: инфобокс открывается рядом, отдельным окном рабочего стола. */
(function () {
    "use strict";

    const INFOBOX_WINDOW = { width: 320, height: 440 };
    const box = document.getElementById("auto-infobox");

    if (!box) return;

    let desktop = null;
    try {
        desktop = window.parent && window.parent !== window && window.parent.desktopAPI;
    } catch (error) {
        desktop = null;
    }

    if (desktop && typeof desktop.openApp === "function") {
        desktop.openApp("info-" + box.dataset.id, box.dataset.title + ".info", box.dataset.url, INFOBOX_WINDOW);
    }
})();
