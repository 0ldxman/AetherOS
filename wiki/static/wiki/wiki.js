(function () {
    "use strict";

    /* ================================================== */
    /* Tree: запоминаем раскрытые узлы между страницами    */
    /* ================================================== */

    const STORAGE_KEY = "wiki:tree:open";
    const nodes = document.querySelectorAll(".tree details[data-ns]");

    function readOpen() {
        try {
            return new Set(
                JSON.parse(
                    sessionStorage.getItem(STORAGE_KEY) || "[]"
                )
            );
        } catch (error) {
            return new Set();
        }
    }

    function saveOpen() {
        const open = [];

        nodes.forEach(function (node) {
            if (node.open) {
                open.push(node.dataset.ns);
            }
        });

        try {
            sessionStorage.setItem(
                STORAGE_KEY,
                JSON.stringify(open)
            );
        } catch (error) {
            /* sessionStorage может быть недоступен — это не страшно */
        }
    }

    const saved = readOpen();

    nodes.forEach(function (node) {
        if (saved.has(node.dataset.ns)) {
            node.open = true;
        }
    });

    nodes.forEach(function (node) {
        node.addEventListener("toggle", saveOpen);
    });


    /* ================================================== */
    /* Documents: открытие в окнах рабочего стола          */
    /* ================================================== */

    function getDesktop() {
        try {
            const api =
                window.parent &&
                window.parent !== window &&
                window.parent.desktopAPI;

            return api && typeof api.openApp === "function"
                ? api
                : null;
        } catch (error) {
            return null;
        }
    }

    const table = document.getElementById("docs");

    if (table) {
        table.addEventListener("click", function (event) {
            const row = event.target.closest("tr[data-url]");

            if (!row) {
                return;
            }

            const desktop = getDesktop();

            /* Вне рабочего стола работают обычные ссылки */
            if (!desktop) {
                if (!event.target.closest("a")) {
                    window.location.href = row.dataset.url;
                }

                return;
            }

            event.preventDefault();

            const id = row.dataset.docId;
            const title = row.dataset.title;

            /*
             * Пока все документы имеют тип .doc.
             */
            const windowTitle = title + ".doc";

            /*
             * Сначала инфобокс, потом документ:
             * окно документа открывается последним
             * и остаётся сверху.
             */
            if (row.dataset.infoboxUrl) {
                desktop.openApp(
                    "info-" + id,
                    title + ".info",
                    row.dataset.infoboxUrl
                );
            }

            desktop.openApp(
                "doc-" + id,
                windowTitle,
                row.dataset.url
            );
        });
    }
})();