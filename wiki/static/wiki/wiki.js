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
     * Строка выбирается кликом: внизу показываются свойства объекта.
     * Открывается запись двойным кликом, по названию или кнопкой open.
     * Работает и для таблицы раздела, и для таблицы результатов поиска.
     */
    const INFOBOX_WINDOW = { width: 320, height: 440 };

    const props = document.getElementById("props");
    const propsEmpty = document.getElementById("props-empty");
    const propsList = document.getElementById("props-list");
    const propsOpen = document.getElementById("props-open");

    let selected = null;

    function openRow(row) {
        const desktop = getDesktop();

        /* вне рабочего стола работают обычные ссылки */
        if (!desktop) {
            window.location.href = row.dataset.url;
            return;
        }

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
    }

    function showProps(row) {
        const fields = [
            ["key", row.dataset.key],
            ["class", row.dataset.class],
            ["size", row.dataset.size],
            ["etag", row.dataset.etag],
            ["access", row.dataset.access],
        ];

        if (row.dataset.infoboxUrl) {
            fields.push(["infobox", "yes"]);
        }

        propsList.replaceChildren();

        fields.forEach(function (pair) {
            if (pair[1] === undefined) {
                return;
            }

            const term = document.createElement("dt");
            const value = document.createElement("dd");

            term.textContent = pair[0];
            value.textContent = pair[1];
            propsList.append(term, value);
        });

        propsEmpty.hidden = true;
        propsList.hidden = false;
        propsOpen.hidden = !row.dataset.url;
    }

    function select(row) {
        if (selected) {
            selected.classList.remove("selected");
        }

        selected = row;
        row.classList.add("selected");
        showProps(row);
    }

    function bindOpen(table) {
        table.addEventListener("click", function (event) {
            const row = event.target.closest("tr[data-key]");

            if (!row) {
                return;
            }

            select(row);

            /* название раздела ведёт по ссылке, название записи открывает её */
            if (event.target.closest("a") && row.dataset.url) {
                event.preventDefault();
                openRow(row);
            }
        });

        table.addEventListener("dblclick", function (event) {
            const row = event.target.closest("tr[data-key]");

            if (!row) {
                return;
            }

            if (row.dataset.url) {
                openRow(row);
                return;
            }

            const link = row.querySelector("a");

            if (link) {
                window.location.href = link.href;
            }
        });
    }

    if (propsOpen) {
        propsOpen.addEventListener("click", function () {
            if (selected && selected.dataset.url) {
                openRow(selected);
            }
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
    /* Document: инфобокс открывается вместе с документом  */
    /* ================================================== */

    const autoInfobox = document.getElementById("auto-infobox");

    if (autoInfobox) {
        const desktop = getDesktop();

        if (desktop) {
            desktop.openApp(
                "info-" + autoInfobox.dataset.id,
                autoInfobox.dataset.title + ".info",
                autoInfobox.dataset.url,
                INFOBOX_WINDOW
            );
        }
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
    const typedHint = document.getElementById("typed-hint");

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

        ["key", "class", "size", "etag", "access"].forEach(function (label) {
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
            tr.dataset.key = item.key;
            tr.dataset.class = item.kind;
            tr.dataset.size = item.size || "-";
            tr.dataset.etag = item.etag || "-";
            tr.dataset.access = item.open ? "open" : "locked";

            if (item.infobox_url) {
                tr.dataset.infoboxUrl = item.infobox_url;
            }

            /* название + приглушённое расширение */
            const nameCell = el("td");
            nameCell.dataset.sort = item.title;

            const link = el("a", null);
            link.href = item.url;
            link.appendChild(el("span", "ext", item.path || ""));
            link.appendChild(document.createTextNode(item.title));
            link.appendChild(el("span", "ext", item.ext || ""));
            nameCell.appendChild(link);

            const classCell = el("td", null, item.kind);
            const sizeCell = el("td", null, item.size || "-");
            sizeCell.dataset.sort = item.bytes;
            const etagCell = el("td", null, item.etag || "-");

            const accessCell = el(
                "td",
                item.open ? "state-open" : "",
                item.open ? "OPEN" : "LOCKED"
            );

            tr.append(nameCell, classCell, sizeCell, etagCell, accessCell);
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

            if (typedHint) {
                typedHint.hidden = input.value !== "";
            }

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
                    "(" + rows.length + (rows.length === 1 ? " object)" : " objects)");

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


document.addEventListener("click", (e) => {
  const link = e.target.closest("[data-asset-viewer]");
  if (!link) return;

  // страница вики лежит в iframe окна, а desktopAPI живёт у родителя
  const api = window.parent && window.parent.desktopAPI;
  if (!api) return; // нет рабочего стола: сработает обычная ссылка

  e.preventDefault();

  const url = link.dataset.assetViewer;
  api.openApp(
    "asset-" + url.replace(/\W+/g, "-"),
    link.dataset.assetTitle || "Asset",
    url,
    { width: 640, height: 480 }
  );
});