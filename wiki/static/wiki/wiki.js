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

            /* расширение зависит от типа записи: .doc, .snapshot */
            const windowTitle = title + (row.dataset.ext || ".doc");

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


        /* ================================================== */
        /* Table: сортировка по клику на заголовок             */
        /* ================================================== */

        /*
         * Сортируем только уже отрисованные строки, а они
         * приходят с сервера отфильтрованными по ключам.
         */
        const headers = table.querySelectorAll("thead th");
        const collator = new Intl.Collator(undefined, {
            numeric: true,
            sensitivity: "base",
        });

        function sortValue(cell) {
            return cell.dataset.sort || cell.textContent.trim();
        }

        headers.forEach(function (th, index) {
            th.addEventListener("click", function () {
                const asc = th.getAttribute("aria-sort") !== "ascending";

                headers.forEach(function (h) {
                    h.removeAttribute("aria-sort");
                });

                th.setAttribute(
                    "aria-sort",
                    asc ? "ascending" : "descending"
                );

                const tbody = table.tBodies[0];
                const rows = Array.from(tbody.rows);

                rows.sort(function (a, b) {
                    /* data-sort нужен там, где в ячейке есть лишнее (название + расширение) */
                    const x = sortValue(a.cells[index]);
                    const y = sortValue(b.cells[index]);

                    return asc
                        ? collator.compare(x, y)
                        : collator.compare(y, x);
                });

                rows.forEach(function (row) {
                    tbody.appendChild(row);
                });
            });
        });
    }
})();