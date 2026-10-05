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

    /*
     * Открытие по клику на строку. Работает и для таблицы
     * документов раздела, и для таблицы результатов поиска.
     */
    const INFOBOX_WINDOW = { width: 320, height: 440 };
    function bindOpen(table) {
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
                    row.dataset.infoboxUrl,
                    INFOBOX_WINDOW
                );
            }

            desktop.openApp(
                "doc-" + id,
                windowTitle,
                row.dataset.url
            );
        });
    }


    /* ================================================== */
    /* Table: сортировка по клику на заголовок             */
    /* ================================================== */

    const collator = new Intl.Collator(undefined, {
        numeric: true,
        sensitivity: "base",
    });

    function sortValue(cell) {
        return cell.dataset.sort || cell.textContent.trim();
    }

    /*
     * Сортируем только уже отрисованные строки, а они
     * приходят с сервера отфильтрованными по ключам.
     */
    function bindSort(table) {
        const headers = table.querySelectorAll("thead th");

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

    const docsTable = document.getElementById("docs");

    if (docsTable) {
        bindOpen(docsTable);
        bindSort(docsTable);
    }


    /* ================================================== */
    /* Search: запрос к «базе», выдача подменяет список    */
    /* ================================================== */

    const layout = document.getElementById("layout");
    const input = document.getElementById("search");
    const typed = document.getElementById("typed");
    const typedWrap = document.getElementById("typed-wrap");
    const browse = document.getElementById("browse");
    const results = document.getElementById("results");
    const pathText = document.getElementById("path-text");
    const records = document.getElementById("records");

    /*
     * Запрос на языке архива. Он только показывается в шапке:
     * настоящий поиск делает сервер.
     *
     *     locate @technologies/weapon "first" --in name,text
     *
     * Адрес — раздел, из которого ищет игрок (корень: ~).
     * Кавычки и обратная косая в слове экранируются.
     */
    function buildQuery(word) {
        const address = layout.dataset.scope || "~";

        const escaped = word
            .replace(/\\/g, "\\\\")
            .replace(/"/g, '\\"');

        return "locate @" + address + ' "' + escaped + '" --in name,text';
    }

    /*
     * Запрос к серверу. Возвращает список строк:
     *
     *     {
     *         id, title, ext, open, url, infobox_url,
     *         path: "~/Technologies/Weapon/"
     *     }
     *
     * Что можно показывать игроку, решает сервер (ключи, видимость,
     * закрытые разделы), интерфейс показывает всё, что пришло.
     */
    async function fetchResults(word) {
        const url = new URL(layout.dataset.searchUrl, window.location.href);

        url.searchParams.set("q", word);
        url.searchParams.set("ns", layout.dataset.nsId || "");

        const response = await fetch(url, {
            credentials: "same-origin",
            headers: { Accept: "application/json" },
        });

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        const data = await response.json();

        return data.rows || [];
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);

        if (className) {
            node.className = className;
        }

        if (text !== undefined) {
            node.textContent = text;
        }

        return node;
    }

    function buildResultsTable(rows) {
        const table = el("table", "grid");

        const headRow = el("tr");

        ["name", "path", "access"].forEach(function (label) {
            headRow.appendChild(el("th", null, label));
        });

        table.appendChild(el("thead")).appendChild(headRow);

        const body = el("tbody");

        rows.forEach(function (item) {
            const tr = el("tr", item.open ? "" : "locked");

            tr.dataset.docId = item.id;
            tr.dataset.title = item.title;
            tr.dataset.ext = item.ext || "";
            tr.dataset.url = item.url;

            if (item.infobox_url) {
                tr.dataset.infoboxUrl = item.infobox_url;
            }

            /* название + приглушённое расширение */
            const nameCell = el("td");
            nameCell.dataset.sort = item.title;

            const link = el("a", null, item.title);
            link.href = item.url;
            link.appendChild(el("span", "ext", item.ext || ""));
            nameCell.appendChild(link);

            const pathCell = el("td", null, item.path || "");

            const accessCell = el(
                "td",
                item.open ? "state-open" : "",
                item.open ? "OPEN" : "LOCKED"
            );

            tr.append(nameCell, pathCell, accessCell);
            body.appendChild(tr);
        });

        table.appendChild(body);

        bindOpen(table);
        bindSort(table);

        return table;
    }

    if (
        layout && input && typed && typedWrap &&
        browse && results && pathText && records
    ) {

        /* то, что показывалось до поиска: к нему возвращаемся */
        const basePath = pathText.textContent;
        const baseRecords = records.textContent;

        let requestId = 0;
        let searching = false;

        /*
         * Настоящий <input> прозрачный и лежит поверх строки,
         * а видимый текст и блочный курсор рисуем сами.
         * Курсор всегда стоит в конце строки.
         */
        function syncTyped() {
            typed.textContent = input.value;
            typedWrap.scrollLeft = typedWrap.scrollWidth;
        }

        function setMode(value) {
            searching = value;

            browse.hidden = value;
            results.hidden = !value;
            layout.classList.toggle("searching", value);
        }

        async function run(word) {
            const id = ++requestId;

            records.textContent = "executing...";

            let rows = [];
            let failed = false;

            try {
                rows = await fetchResults(word);
            } catch (error) {
                console.warn("search failed:", error);
                failed = true;
            }

            /* пока ждали, запрос мог быть отменён или заменён новым */
            if (id !== requestId) {
                return;
            }

            pathText.textContent = buildQuery(word);

            results.replaceChildren();

            if (failed) {
                records.textContent = "(error)";
                results.appendChild(el("p", "empty", "> error: query failed"));
            } else {
                records.textContent =
                    "(" + rows.length + (rows.length === 1 ? " record)" : " records)");

                if (rows.length) {
                    results.appendChild(buildResultsTable(rows));
                } else {
                    results.appendChild(el("p", "empty", "> no records found"));
                }
            }

            setMode(true);
        }

        function leave() {
            requestId++;

            setMode(false);

            pathText.textContent = basePath;
            records.textContent = baseRecords;
        }

        input.addEventListener("input", syncTyped);
        input.addEventListener("focus", syncTyped);

        input.addEventListener("keydown", function (event) {
            if (event.isComposing) {
                return;
            }

            if (event.key === "Enter") {
                event.preventDefault();

                const word = input.value.trim();

                if (word) {
                    run(word);
                } else if (searching) {
                    leave();
                }

                return;
            }

            if (event.key === "Escape" && (input.value || searching)) {
                event.preventDefault();

                input.value = "";
                syncTyped();
                leave();
            }
        });

        syncTyped();
    }
})();