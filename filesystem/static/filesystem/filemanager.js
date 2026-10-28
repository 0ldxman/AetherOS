/* Файловый менеджер админки (том и машина). Дерево слева, список справа, панель кнопок, правая кнопка, F2/Delete/Ctrl+C/X/V,
   перетаскивание папок и файлов (в томе). Данные и операции идут по JSON, см. filesystem/admin_files.py. Всё содержимое рисуется
   через textContent, разметка из данных не строится. */
(function () {
    "use strict";

    const root = document.getElementById("fm");
    if (!root) {
        return;
    }
    const cfg = JSON.parse(document.getElementById("fm-config").textContent);
    const csrf = document.querySelector("input[name=csrfmiddlewaretoken]").value;
    const machine = cfg.mode === "machine";
    const ROOT = machine ? "/" : "";
    const formats = {};
    (cfg.formats || []).forEach(function (f) { formats[f.name] = f; });

    const els = {
        path: document.getElementById("fm-path"),
        tree: document.getElementById("fm-tree"),
        body: document.querySelector("#fm-list tbody"),
        empty: document.getElementById("fm-empty"),
        count: document.getElementById("fm-count"),
        msg: document.getElementById("fm-msg"),
        tools: document.getElementById("fm-tools"),
        search: document.getElementById("fm-search"),
        menu: document.getElementById("fm-menu"),
        dialog: document.getElementById("fm-dialog"),
        thObj: document.getElementById("fm-th-obj"),
    };
    els.thObj.textContent = machine ? "Том" : "Объект";

    const state = {byKey: new Map(), kids: new Map(), cwd: ROOT, sel: new Set(), last: null, history: [], clip: null, open: new Set([ROOT]), filter: "", drag: null};

    // ---------- данные ----------
    function dirname(path) {
        const cut = path.lastIndexOf("/");
        return cut <= 0 ? "/" : path.slice(0, cut);
    }

    function normalize(data) {
        state.byKey = new Map();
        state.kids = new Map();
        (data.rows || []).forEach(function (row) {
            let node;
            if (machine) {
                node = {key: row.path, parent: dirname(row.path), name: row.name, type: row.kind === "dir" ? "folder" : row.kind === "deleted" ? "deleted" : "file", row: row};
            } else {
                node = {key: String(row.id), parent: row.parent === null ? "" : String(row.parent), name: row.name, type: row.kind === "folder" ? "folder" : row.kind === "whiteout" ? "deleted" : "file", row: row};
            }
            state.byKey.set(node.key, node);
            if (!state.kids.has(node.parent)) {
                state.kids.set(node.parent, []);
            }
            state.kids.get(node.parent).push(node);
        });
        state.kids.forEach(function (list) {
            list.sort(function (a, b) {
                const rank = function (n) { return n.type === "folder" ? 0 : 1; };
                return rank(a) - rank(b) || a.name.localeCompare(b.name, undefined, {sensitivity: "base", numeric: true});
            });
        });
        if (state.cwd !== ROOT && !state.byKey.has(state.cwd)) {
            state.cwd = ROOT;
        }
        state.sel = new Set(Array.from(state.sel).filter(function (k) { return state.byKey.has(k); }));
    }

    async function load() {
        const response = await fetch(cfg.dataUrl, {credentials: "same-origin"});
        normalize(await response.json());
        render();
    }

    async function api(op, payload) {
        const response = await fetch(cfg.opUrl, {
            method: "POST", credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
            body: JSON.stringify(Object.assign({op: op}, payload || {})),
        });
        let data;
        try {
            data = await response.json();
        } catch (e) {
            data = {ok: false, error: "Сервер ответил ошибкой (" + response.status + ")."};
        }
        if (!data.ok) {
            say(data.error || "Не получилось.", true);
            return null;
        }
        await load();
        return data;
    }

    function say(text, error) {
        els.msg.textContent = text;
        els.msg.className = error ? "error" : "";
        clearTimeout(say.timer);
        say.timer = setTimeout(function () { els.msg.textContent = ""; els.msg.className = ""; }, 6000);
    }

    // ---------- вспомогательное ----------
    function el(tag, attrs, text) {
        const node = document.createElement(tag);
        Object.keys(attrs || {}).forEach(function (k) {
            if (k === "class") { node.className = attrs[k]; } else { node.setAttribute(k, attrs[k]); }
        });
        if (text !== undefined) { node.textContent = text; }
        return node;
    }

    function itemUrl(id) {
        return cfg.itemUrl.replace("__id__", id);
    }

    function size(bytes) {
        if (bytes === null || bytes === undefined) { return ""; }
        if (bytes < 1024) { return bytes + " Б"; }
        if (bytes < 1048576) { return (bytes / 1024).toFixed(1).replace(/\.0$/, "") + " КБ"; }
        return (bytes / 1048576).toFixed(1).replace(/\.0$/, "") + " МБ";
    }

    const SVG = "http://www.w3.org/2000/svg";
    function shape(tag, attrs) {
        const node = document.createElementNS(SVG, tag);
        Object.keys(attrs).forEach(function (k) { node.setAttribute(k, attrs[k]); });
        return node;
    }

    // значки рисуются здесь же: не зависят от шрифтов с эмодзи
    function svgIcon(kind) {
        const svg = shape("svg", {class: "fm-ico", width: "16", height: "16", viewBox: "0 0 16 16", "aria-hidden": "true"});
        if (kind === "folder") {
            svg.appendChild(shape("path", {d: "M1.5 3.5h4l1.5 1.5h7.5v8h-13z", fill: "#e0a93a", stroke: "#b9822a", "stroke-linejoin": "round"}));
        } else if (kind === "drive") {
            svg.appendChild(shape("rect", {x: "1.5", y: "4.5", width: "13", height: "7", rx: "1.2", fill: "#b8c2cc", stroke: "#6b7885"}));
            svg.appendChild(shape("circle", {cx: "12.3", cy: "8", r: "0.9", fill: "#3aa655"}));
        } else if (kind === "deleted") {
            svg.appendChild(shape("circle", {cx: "8", cy: "8", r: "6", fill: "none", stroke: "#ba2121", "stroke-width": "1.6"}));
            svg.appendChild(shape("path", {d: "M3.8 12.2L12.2 3.8", stroke: "#ba2121", "stroke-width": "1.6"}));
        } else {
            svg.appendChild(shape("path", {d: "M3.5 1.5h6l3 3v10h-9z", fill: "#fff", stroke: "#7a8a99", "stroke-linejoin": "round"}));
            svg.appendChild(shape("path", {d: "M9.5 1.5v3h3", fill: "none", stroke: "#7a8a99"}));
        }
        return svg;
    }

    function iconKind(node) {
        if (node.type === "deleted") { return "deleted"; }
        if (node.type === "folder") { return /^[A-Za-z]:$/.test(node.name) ? "drive" : "folder"; }
        return "file";
    }

    function typeLabel(node) {
        if (node.type === "folder") { return "Папка"; }
        if (node.type === "deleted") { return "Скрыто"; }
        const item = node.row.item;
        const f = item && formats[item.format];
        return f ? (f.title || f.name) : (item && item.format) || "Файл";
    }

    function selected() {
        return Array.from(state.sel).map(function (k) { return state.byKey.get(k); }).filter(Boolean);
    }

    function currentArg() {
        return machine ? state.cwd : (state.cwd === "" ? null : Number(state.cwd));
    }

    function ancestors(key) {
        const list = [];
        let node = state.byKey.get(key);
        while (node) { list.unshift(node); node = state.byKey.get(node.parent); }
        return list;
    }

    // ---------- отрисовка ----------
    function render() {
        renderPath();
        renderTree();
        renderList();
        renderTools();
    }

    function renderPath() {
        els.path.textContent = "";
        const rootLink = el("a", {});
        rootLink.appendChild(svgIcon("drive"));
        rootLink.appendChild(document.createTextNode(cfg.rootName));
        rootLink.addEventListener("click", function () { go(ROOT); });
        els.path.appendChild(rootLink);
        ancestors(state.cwd).forEach(function (node) {
            els.path.appendChild(el("span", {class: "sep"}, "›"));
            const link = el("a", {}, node.name);
            link.addEventListener("click", function () { go(node.key); });
            els.path.appendChild(link);
        });
    }

    function treeNode(key, label, depth, glyph) {
        const folders = (state.kids.get(key) || []).filter(function (n) { return n.type === "folder"; });
        const row = el("div", {class: "node" + (key === state.cwd ? " current" : "")});
        row.style.paddingLeft = (6 + depth * 14) + "px";
        const twist = el("span", {class: "twist"}, folders.length ? (state.open.has(key) ? "▾" : "▸") : "");
        twist.addEventListener("click", function (event) {
            event.stopPropagation();
            if (state.open.has(key)) { state.open.delete(key); } else { state.open.add(key); }
            renderTree();
        });
        row.appendChild(twist);
        row.appendChild(svgIcon(glyph));
        row.appendChild(el("span", {}, label));
        row.addEventListener("click", function () { go(key); });
        row.addEventListener("dragover", function (event) { if (state.drag) { event.preventDefault(); row.classList.add("drop"); } });
        row.addEventListener("dragleave", function () { row.classList.remove("drop"); });
        row.addEventListener("drop", function (event) { row.classList.remove("drop"); drop(event, key); });
        els.tree.appendChild(row);
        if (state.open.has(key)) {
            folders.forEach(function (n) { treeNode(n.key, n.name, depth + 1, iconKind(n)); });
        }
    }

    function renderTree() {
        els.tree.textContent = "";
        ancestors(state.cwd).forEach(function (n) { state.open.add(n.parent); });
        treeNode(ROOT, cfg.rootName, 0, "drive");
    }

    function noteTags(node) {
        const tags = [];
        const row = node.row;
        const add = function (text, cls) { tags.push(el("span", {class: "tag" + (cls ? " " + cls : "")}, text)); };
        if (machine) {
            if (row.mark === "override") { add("перекрыт", "override"); }
            else if (row.mark === "added") { add("добавлен", "added"); }
            else if (row.mark === "base") { add("образ"); }
            else if (row.mark === "deleted") { add("удалён", "deleted"); }
            if (node.type !== "deleted" && row.volume && !row.private) { add("общий том", "shared"); }
        } else {
            if (node.type === "deleted") { add("надгробие", "deleted"); }
            if (row.item && row.item.used > 1) { add("общий объект ×" + row.item.used, "shared"); }
            if (row.access && row.access !== "inherit") { add("доступ: " + (row.access === "none" ? "открыт" : "свой")); }
            if (row.state && row.state !== "inherit") { add("слои: " + (row.state === "none" ? "нет" : "свои")); }
        }
        if (row.mode) { add(row.mode + (row.owner ? " " + row.owner : "") + (row.group ? ":" + row.group : "")); }
        if (row.hidden) { add("скрытый"); }
        if (row.system) { add("системный"); }
        return tags;
    }

    function renderList() {
        const filter = state.filter.toLowerCase();
        const nodes = (state.kids.get(state.cwd) || []).filter(function (n) { return !filter || n.name.toLowerCase().indexOf(filter) >= 0; });
        els.body.textContent = "";
        nodes.forEach(function (node) {
            const tr = el("tr", {"data-key": node.key});
            if (state.sel.has(node.key)) { tr.classList.add("sel"); }
            if (node.row.hidden) { tr.classList.add("is-hidden"); }
            if (node.type === "deleted") { tr.classList.add("is-deleted"); }
            if (state.clip && state.clip.mode === "cut" && state.clip.keys.indexOf(node.key) >= 0) { tr.classList.add("is-cut"); }
            const name = el("td", {class: "c-name"});
            name.appendChild(svgIcon(iconKind(node)));
            name.appendChild(el("span", {}, node.name));
            tr.appendChild(name);
            tr.appendChild(el("td", {class: "c-type"}, typeLabel(node)));
            const third = el("td", {class: "c-obj"});
            if (machine) {
                third.textContent = node.row.volume || "";
            } else if (node.row.item) {
                const link = el("a", {href: itemUrl(node.row.item.id), target: "_blank", rel: "noopener"}, node.row.item.slug);
                link.addEventListener("click", function (event) { event.stopPropagation(); });
                link.addEventListener("dblclick", function (event) { event.stopPropagation(); });
                third.appendChild(link);
            }
            tr.appendChild(third);
            tr.appendChild(el("td", {class: "c-size"}, node.row.item ? size(node.row.item.size) : ""));
            const note = el("td", {class: "c-note"});
            noteTags(node).forEach(function (t) { note.appendChild(t); });
            tr.appendChild(note);

            tr.addEventListener("click", function (event) { event.stopPropagation(); pick(node, event); });
            tr.addEventListener("dblclick", function () { activate(node); });
            tr.addEventListener("contextmenu", function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (!state.sel.has(node.key)) { state.sel = new Set([node.key]); state.last = node.key; renderList(); renderTools(); }
                menu(event.clientX, event.clientY, true);
            });
            if (!machine && cfg.canChange) {
                tr.draggable = true;
                tr.addEventListener("dragstart", function (event) {
                    if (!state.sel.has(node.key)) { state.sel = new Set([node.key]); }
                    state.drag = Array.from(state.sel);
                    event.dataTransfer.effectAllowed = "copyMove";
                    event.dataTransfer.setData("text/plain", node.name);
                });
                tr.addEventListener("dragend", function () { state.drag = null; });
                if (node.type === "folder") {
                    tr.addEventListener("dragover", function (event) { if (state.drag && state.drag.indexOf(node.key) < 0) { event.preventDefault(); tr.classList.add("drop"); } });
                    tr.addEventListener("dragleave", function () { tr.classList.remove("drop"); });
                    tr.addEventListener("drop", function (event) { tr.classList.remove("drop"); drop(event, node.key); });
                }
            }
            els.body.appendChild(tr);
        });
        els.empty.hidden = nodes.length > 0;
        const picked = state.sel.size;
        els.count.textContent = nodes.length + " элем." + (picked ? " · выбрано: " + picked : "");
    }

    function can() {
        const sel = selected();
        const one = sel.length === 1 ? sel[0] : null;
        const edit = cfg.canChange;
        const live = sel.filter(function (n) { return n.type !== "deleted"; });
        return {
            new_folder: edit, new_file: edit, link: edit,
            edit: edit && !!one && one.type === "file" && !!one.row.item,
            open: !!one && (one.type === "folder" || !!one.row.item),
            rename: edit && !!one && one.type !== "deleted",
            cut: edit && live.length > 0, copy: edit && live.length > 0, paste: edit && !!state.clip,
            hidden: edit && !!one && one.type !== "deleted",
            rights: edit && !machine && !!one && one.type !== "deleted",
            reset: edit && !!one && (one.row.mark === "override" || (one.type === "folder" && one.row.private)),
            restore: edit && !!one && one.type === "deleted" && (machine ? one.row.private : true),
            delete: edit && (machine ? live.length > 0 : sel.length > 0),
        };
    }

    function renderTools() {
        const allowed = can();
        els.tools.querySelectorAll("button[data-act]").forEach(function (button) {
            button.disabled = !allowed[button.dataset.act];
        });
        const one = selected().length === 1 ? selected()[0] : null;
        const hiddenButton = els.tools.querySelector('[data-act="hidden"]');
        if (hiddenButton) { hiddenButton.textContent = one && one.row.hidden ? "Показать" : "Скрытый"; }
    }

    // ---------- навигация и выбор ----------
    function go(key, silent) {
        if (!silent && key !== state.cwd) { state.history.push(state.cwd); }
        state.cwd = key;
        state.sel = new Set();
        state.last = null;
        els.search.value = "";
        state.filter = "";
        render();
    }

    function pick(node, event) {
        if (event.shiftKey && state.last && state.byKey.has(state.last)) {
            const keys = (state.kids.get(state.cwd) || []).map(function (n) { return n.key; });
            const a = keys.indexOf(state.last), b = keys.indexOf(node.key);
            state.sel = new Set(keys.slice(Math.min(a, b), Math.max(a, b) + 1));
        } else if (event.ctrlKey || event.metaKey) {
            if (state.sel.has(node.key)) { state.sel.delete(node.key); } else { state.sel.add(node.key); }
            state.last = node.key;
        } else {
            state.sel = new Set([node.key]);
            state.last = node.key;
        }
        renderList();
        renderTools();
    }

    function activate(node) {
        if (node.type === "folder") { go(node.key); return; }
        if (node.type === "deleted") { return; }
        if (machine) { act("edit"); } else if (node.row.item) { window.open(itemUrl(node.row.item.id), "_blank"); }
    }

    // ---------- окна ----------
    function ask(options) {
        return new Promise(function (resolve) {
            const dialog = els.dialog;
            dialog.textContent = "";
            const form = el("form", {method: "dialog"});
            form.appendChild(el("h3", {}, options.title));
            const inputs = {};
            (options.fields || []).forEach(function (field) {
                form.appendChild(el("label", {}, field.label));
                let input;
                if (field.options) {
                    input = el("select");
                    field.options.forEach(function (option) {
                        const o = el("option", {value: option[0]}, option[1]);
                        if (option[0] === field.value) { o.selected = true; }
                        input.appendChild(o);
                    });
                } else {
                    input = el("input", {type: "text", autocomplete: "off"});
                    input.value = field.value || "";
                }
                inputs[field.name] = input;
                form.appendChild(input);
            });
            if (options.text) { form.appendChild(el("p", {}, options.text)); }
            const row = el("div", {class: "row"});
            const cancel = el("button", {type: "button"}, "Отмена");
            const ok = el("button", {type: "submit", class: "default"}, options.ok || "ОК");
            row.appendChild(cancel);
            row.appendChild(ok);
            form.appendChild(row);
            dialog.appendChild(form);
            let answered = false;
            const finish = function (value) {
                if (answered) { return; }
                answered = true;
                dialog.close();
                resolve(value);
            };
            cancel.addEventListener("click", function () { finish(null); });
            dialog.addEventListener("cancel", function () { finish(null); }, {once: true});
            form.addEventListener("submit", function (event) {
                event.preventDefault();
                const values = {};
                Object.keys(inputs).forEach(function (k) { values[k] = inputs[k].value; });
                finish(values);
            });
            dialog.showModal();
            const first = form.querySelector("input, select");
            if (first) { first.focus(); if (first.select) { first.select(); } }
        });
    }

    function pickObject() {
        return new Promise(function (resolve) {
            const dialog = els.dialog;
            dialog.textContent = "";
            dialog.appendChild(el("h3", {}, "Положить объект"));
            const input = el("input", {type: "text", placeholder: "Название или слаг объекта", autocomplete: "off"});
            const results = el("div", {class: "results"});
            dialog.appendChild(input);
            dialog.appendChild(results);
            const row = el("div", {class: "row"});
            const cancel = el("button", {type: "button"}, "Отмена");
            row.appendChild(cancel);
            dialog.appendChild(row);
            let answered = false;
            const finish = function (value) { if (!answered) { answered = true; dialog.close(); resolve(value); } };
            cancel.addEventListener("click", function () { finish(null); });
            dialog.addEventListener("cancel", function () { finish(null); }, {once: true});
            let timer = null;
            const search = async function () {
                const response = await fetch(cfg.objectsUrl + "?q=" + encodeURIComponent(input.value), {credentials: "same-origin"});
                const data = await response.json();
                results.textContent = "";
                data.items.forEach(function (item) {
                    const line = el("div", {});
                    line.appendChild(el("span", {}, item.name + " "));
                    line.appendChild(el("small", {}, item.slug + (item.format ? " · " + item.format : "")));
                    line.addEventListener("click", function () { finish(item); });
                    results.appendChild(line);
                });
                if (!data.items.length) { results.appendChild(el("div", {}, "Ничего не найдено.")); }
            };
            input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(search, 200); });
            dialog.showModal();
            input.focus();
            search();
        });
    }

    // ---------- действия ----------
    function formatOptions() {
        const list = [["", "— по расширению в имени —"]];
        (cfg.formats || []).forEach(function (f) { list.push([f.name, f.name + (f.extension ? " (" + f.extension + ")" : "") + (f.title ? " — " + f.title : "")]); });
        return list;
    }

    async function act(name) {
        const allowed = can();
        if (!allowed[name]) { return; }
        const sel = selected();
        const one = sel.length === 1 ? sel[0] : null;

        if (name === "new_folder") {
            const v = await ask({title: "Новая папка", fields: [{name: "name", label: "Имя", value: "Новая папка"}], ok: "Создать"});
            if (v && v.name.trim()) { await api("new_folder", {parent: currentArg(), name: v.name}); }
        } else if (name === "new_file") {
            const v = await ask({title: "Новый файл", fields: [
                {name: "name", label: "Имя (расширение выберет формат: notes.txt)", value: "Новый файл"},
                {name: "format", label: "Формат", value: "", options: formatOptions()},
            ], ok: "Создать"});
            if (v && v.name.trim()) {
                const result = await api("new_file", {parent: currentArg(), name: v.name, format: v.format});
                if (result && result.item) { say("Создано. Содержимое открылось в новой вкладке."); window.open(itemUrl(result.item), "_blank"); }
            }
        } else if (name === "link") {
            const item = await pickObject();
            if (item) { await api("link", {parent: currentArg(), item: item.id}); }
        } else if (name === "open") {
            if (one.type === "folder") { go(one.key); } else if (one.row.item) { window.open(itemUrl(one.row.item.id), "_blank"); }
        } else if (name === "edit") {
            const shared = !one.row.private && one.row.volume;
            const result = await api("override", {path: one.key});
            if (result && result.item) {
                say(shared ? "Для этой машины создана своя копия файла; общий образ не тронут." : "Файл открыт для правки.");
                window.open(itemUrl(result.item), "_blank");
            }
        } else if (name === "rename") {
            const v = await ask({title: "Переименовать", fields: [{name: "name", label: "Новое имя", value: one.name}], ok: "Переименовать"});
            if (v && v.name.trim() && v.name !== one.name) {
                await api("rename", machine ? {path: one.key, name: v.name} : {id: Number(one.key), name: v.name});
            }
        } else if (name === "delete") {
            const text = machine
                ? "Убрать из вида машины: " + sel.length + " элем.? Файлы общего образа не удаляются, а скрываются (их можно восстановить)."
                : "Удалить из тома: " + sel.length + " элем.? Папки уйдут со всем внутри; сами объекты останутся в библиотеке.";
            const v = await ask({title: "Удалить", text: text, ok: "Удалить"});
            if (v) {
                if (machine) {
                    for (const node of sel) { if (node.type !== "deleted") { await api("delete", {path: node.key}); } }
                } else {
                    await api("delete", {ids: sel.map(function (n) { return Number(n.key); })});
                }
            }
        } else if (name === "restore") {
            await api("restore", {path: one.key});
        } else if (name === "reset") {
            const v = await ask({title: "Сбросить к образу", text: "Правка этой машины для «" + one.name + "» будет убрана, вернётся файл из общего образа.", ok: "Сбросить"});
            if (v) { await api("reset", {path: one.key}); }
        } else if (name === "rights") {
            const v = await ask({title: "Права", text: "Режим из трёх цифр (640): владелец, группа, остальные; 4 читать, 2 писать, 1 входить. Пусто: права не заданы, открыто всем.",
                fields: [{name: "owner", label: "Владелец (логин)", value: one.row.owner || ""}, {name: "group", label: "Группа", value: one.row.group || ""}, {name: "mode", label: "Режим", value: one.row.mode || ""}], ok: "Задать"});
            if (v) { await api("rights", {id: Number(one.key), owner: v.owner, group: v.group, mode: v.mode}); }
        } else if (name === "hidden") {
            await api("set", {id: Number(one.key), hidden: !one.row.hidden});
        } else if (name === "cut" || name === "copy") {
            state.clip = {mode: name, keys: sel.filter(function (n) { return n.type !== "deleted"; }).map(function (n) { return n.key; })};
            say((name === "cut" ? "Вырезано: " : "Скопировано: ") + state.clip.keys.length);
            renderList();
            renderTools();
        } else if (name === "paste") {
            const ids = state.clip.keys.map(Number);
            const result = await api(state.clip.mode === "cut" ? "move" : "copy", {ids: ids, parent: currentArg()});
            if (result && state.clip.mode === "cut") { state.clip = null; }
        }
    }

    async function drop(event, targetKey) {
        event.preventDefault();
        if (!state.drag) { return; }
        const ids = state.drag.map(Number);
        const copy = event.ctrlKey || event.altKey;
        state.drag = null;
        await api(copy ? "copy" : "move", {ids: ids, parent: targetKey === "" ? null : Number(targetKey)});
    }

    // ---------- меню и клавиши ----------
    function menu(x, y, onRow) {
        const allowed = can();
        const entries = onRow
            ? [["open", "Открыть"], ["edit", "Изменить для этой машины"], ["restore", "Восстановить"], null, ["cut", "Вырезать"], ["copy", "Копировать"], ["paste", "Вставить"], null,
               ["rename", "Переименовать (F2)"], ["hidden", "Скрытый / показать"], ["rights", "Права…"], ["reset", "Сбросить к образу"], ["delete", "Удалить (Del)"]]
            : [["new_folder", "Новая папка"], ["new_file", "Новый файл"], ["link", "Положить объект"], null, ["paste", "Вставить"]];
        els.menu.textContent = "";
        entries.forEach(function (entry) {
            if (entry === null) { els.menu.appendChild(el("hr")); return; }
            const only = els.tools.querySelector('[data-act="' + entry[0] + '"]');
            if (only && only.dataset.only && only.dataset.only !== cfg.mode) { return; }
            const button = el("button", {type: "button"}, entry[1]);
            button.disabled = !allowed[entry[0]];
            button.addEventListener("click", function () { closeMenu(); act(entry[0]); });
            els.menu.appendChild(button);
        });
        els.menu.hidden = false;
        els.menu.style.left = Math.min(x, window.innerWidth - 220) + "px";
        els.menu.style.top = Math.min(y, window.innerHeight - els.menu.offsetHeight - 8) + "px";
    }

    function closeMenu() { els.menu.hidden = true; }

    document.addEventListener("click", closeMenu);
    document.addEventListener("scroll", closeMenu, true);
    root.querySelector(".fm-main").addEventListener("contextmenu", function (event) {
        event.preventDefault();
        state.sel = new Set();
        renderList();
        renderTools();
        menu(event.clientX, event.clientY, false);
    });
    root.querySelector(".fm-main").addEventListener("click", function () { state.sel = new Set(); renderList(); renderTools(); });

    els.tools.addEventListener("click", function (event) {
        const button = event.target.closest("button[data-act]");
        if (button) { act(button.dataset.act); }
    });
    root.querySelectorAll(".fm-nav").forEach(function (button) {
        button.addEventListener("click", function () {
            if (button.dataset.act === "up") { go(state.cwd === ROOT ? ROOT : (state.byKey.get(state.cwd) || {parent: ROOT}).parent); }
            else if (state.history.length) { go(state.history.pop(), true); }
        });
    });
    els.search.addEventListener("input", function () { state.filter = els.search.value; renderList(); });

    document.addEventListener("keydown", function (event) {
        if (els.dialog.open || /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) { return; }
        const key = event.key;
        if (key === "F2") { act("rename"); }
        else if (key === "Delete") { act("delete"); }
        else if (key === "Enter") { const sel = selected(); if (sel.length === 1) { activate(sel[0]); } }
        else if (key === "Backspace") { event.preventDefault(); root.querySelector('[data-act="up"]').click(); }
        else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "a") { event.preventDefault(); state.sel = new Set((state.kids.get(state.cwd) || []).map(function (n) { return n.key; })); renderList(); renderTools(); }
        else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "c") { act("copy"); }
        else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "x") { act("cut"); }
        else if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "v") { act("paste"); }
        else if (key === "Escape") { state.sel = new Set(); closeMenu(); renderList(); renderTools(); }
    });

    window.fileManager = {state: state, act: act, go: go, reload: load};     // для проверки и отладки
    load();
})();
