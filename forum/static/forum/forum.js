// Форум: журнал узла. Пространство машины, дерево разделов слева, темы строками таблицы или записи журнала с номерами справа.
// Адрес в хеше: #/s/слаг, #/c/раздел, #/t/тема.
(function () {
    "use strict";
    const { el, csrf, markup, notice } = window.apps;
    const root = document.getElementById("forum");
    const urls = root.dataset;
    const $ = (id) => document.getElementById(id);
    const FOLD_FROM = 3;                       // ветки глубже этого сворачиваются, если ответов много

    let spaces = [], space = null, player = false, node = "", callsign = "";

    const ref = (id) => "#" + String(id).padStart(4, "0");
    const slot = (template, id) => template.replace(/0\/$/, id + "/");

    async function call(url, body) {
        const response = await fetch(url, body === undefined ? { credentials: "same-origin" } : {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { const error = new Error(data.error || (response.status === 404 ? "not found" : "no response")); error.status = response.status; throw error; }
        return data;
    }
    function fail(error) { notice(error.message || String(error)); }
    function hint(text) { $("fm-hint").textContent = text || ""; }
    const button = (label, onclick, className) => {
        const node = el("button", className || "app-button", label);
        node.type = "button";
        node.addEventListener("click", onclick);
        return node;
    };
    const link = (label, onclick, className) => button(label, onclick, "fm-link " + (className || ""));

    // ---------- шапка и путь ----------
    function drawHead() {
        $("fm-node").textContent = node || "-";
        $("fm-call").textContent = callsign || "guest";
        const mode = $("fm-mode");
        mode.textContent = player ? "RW" : "RO · GUEST";
        mode.className = "fm-mode" + (player ? " rw" : "");
        if (space) {
            const flat = flatten(space.tree);
            $("fm-sections").textContent = String(flat.length);
            $("fm-topics").textContent = String(flat.reduce((sum, item) => sum + item.topics, 0));
        } else {
            $("fm-sections").textContent = "-";
            $("fm-topics").textContent = "-";
        }
    }
    function flatten(nodes) { return nodes.flatMap((item) => [item, ...flatten(item.children)]); }

    // путь вида relay:/General/Ciphers/#0003
    function drawPath(crumbs, last) {
        const bar = $("fm-path");
        bar.replaceChildren();
        const home = el("a", "", space ? space.slug + ":" : "forum:");
        home.href = space ? "#/s/" + space.slug : "#/";
        bar.append(home, "/");
        (crumbs || []).forEach((item, index) => {
            const part = el("a", "", item.title);
            part.href = "#/c/" + item.id;
            bar.append(part);
            if (index < crumbs.length - 1 || last) bar.append("/");
        });
        if (last) bar.append(el("span", "fm-here", last));
    }

    // ---------- дерево разделов с ветками ----------
    function drawTree(current) {
        const box = $("fm-tree");
        box.replaceChildren();
        if (!space || !space.tree.length) { box.append(el("p", "fm-dim fm-cap", "no sections")); return; }
        const walk = (nodes, trail) => {
            nodes.forEach((item, index) => {
                const last = index === nodes.length - 1;
                const row = el("a", "fm-node");
                row.href = "#/c/" + item.id;
                if (item.id === current) row.setAttribute("aria-current", "page");
                if (item.about) row.title = item.about;
                const branch = trail.length ? trail.join("") + (last ? "└─ " : "├─ ") : "";
                row.append(el("span", "fm-branch", branch), el("span", "fm-label", item.title));
                if (item.mine) row.append(el("span", "fm-flag mine", "mod"));
                else if (!item.can_write) row.append(el("span", "fm-flag", "ro"));
                row.append(el("span", "fm-count", String(item.topics)));
                box.append(row);
                walk(item.children, trail.concat([last ? "   " : "│  "]));
            });
        };
        walk(space.tree, []);
    }

    async function loadSpace(slug) {
        space = await call(urls.spaceUrl.replace("SLUG", slug));
        $("fm-space").textContent = space.title;
        drawHead();
        return space;
    }

    // ---------- формы ввода ----------
    function field(tag, placeholder, max) {
        const input = el(tag, "field");
        input.placeholder = placeholder;
        input.maxLength = max;
        input.required = tag !== "input" || placeholder !== "about";
        return input;
    }
    function prompt(label) {
        const row = el("div", "fm-prompt");
        row.append(el("span", "fm-ps", (callsign || "guest") + "@" + (node || "relay") + " ›"));
        row.append(label);
        return row;
    }
    function actions(...nodes) { const bar = el("div", "fm-actions"); bar.append(...nodes); return bar; }
    function submitter(label) { const send = el("button", "app-button primary", label); send.type = "submit"; return send; }

    // выбор файла со своей машины
    function attachField() {
        const wrap = el("div", "fm-attach");
        const chosen = [];
        const chips = el("span", "fm-chips");
        const add = link("attach file", () => { picker.hidden = !picker.hidden; if (!picker.hidden) browse(""); });
        const picker = el("div", "fm-picker");
        picker.hidden = true;
        const MAX = 2;
        function drawChips() {
            chips.replaceChildren();
            for (const file of chosen) {
                const chip = el("span", "fm-chip", file.name + " ");
                chip.append(link("×", () => { chosen.splice(chosen.indexOf(file), 1); drawChips(); }));
                chips.append(chip);
            }
            add.hidden = chosen.length >= MAX;
        }
        async function browse(path) {
            try {
                const data = await call(urls.filesUrl + (path ? "?path=" + encodeURIComponent(path) : ""));
                picker.replaceChildren(el("div", "fm-dim", data.path));
                const list = el("div", "fm-picker-list");
                if (data.parent) list.append(link("..", () => browse(data.parent)));
                for (const row of data.entries) {
                    list.append(link(row.dir ? row.name + "/" : row.name, () => {
                        if (row.dir) return browse(row.path);
                        if (!chosen.some((file) => file.path === row.path)) chosen.push({ path: row.path, name: row.name });
                        picker.hidden = true;
                        drawChips();
                    }));
                }
                picker.append(list);
            } catch (error) { fail(error); picker.hidden = true; }
        }
        wrap.append(add, chips, picker);
        return { node: wrap, paths: () => chosen.map((file) => file.path) };
    }

    function composeTopic(main, sectionId) {
        if (main.querySelector(".fm-form")) return;
        const form = el("form", "fm-form");
        const title = field("input", "subject", 160);
        const text = field("textarea", "message", 4000);
        const files = player ? attachField() : null;
        const send = submitter("POST");
        form.append(prompt(title), text);
        if (files) form.append(files.node);
        form.append(actions(send, button("Cancel", () => form.remove())));
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            send.disabled = true;
            try {
                const made = await call(urls.newTopicUrl, { section: sectionId, title: title.value, text: text.value, attachments: files ? files.paths() : [] });
                location.hash = "#/t/" + made.id;
            } catch (error) { fail(error); send.disabled = false; }
        });
        main.querySelector(".fm-tools").after(form);
        title.focus();
    }

    function composeSection(main, parentId) {
        if (main.querySelector(".fm-form")) return;
        const form = el("form", "fm-form");
        const title = field("input", "section name", 120);
        const about = field("input", "about", 240);
        about.placeholder = "what is it for (optional)";
        const send = submitter("CREATE");
        form.append(prompt(title), about, actions(send, button("Cancel", () => form.remove())));
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            send.disabled = true;
            try {
                const made = await call(urls.newSectionUrl, { space: space.slug, parent: parentId, title: title.value, about: about.value });
                await loadSpace(space.slug);
                location.hash = "#/c/" + made.id;
            } catch (error) { fail(error); send.disabled = false; }
        });
        main.querySelector(".fm-tools").after(form);
        title.focus();
    }

    function composeReply(topicId, parentId, className) {
        const form = el("form", "fm-form " + (className || ""));
        const text = field("textarea", "message", 4000);
        const files = player ? attachField() : null;
        const send = submitter("POST");
        form.append(prompt(text));
        if (files) form.append(files.node);
        form.append(actions(send, ...(parentId ? [button("Cancel", () => form.remove())] : [])));
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            send.disabled = true;
            try {
                await call(urls.newPostUrl, { topic: topicId, parent: parentId, text: text.value, attachments: files ? files.paths() : [] });
                await route();
            } catch (error) { fail(error); send.disabled = false; }
        });
        return { form, focus: () => text.focus() };
    }

    async function moderate(url, body) {
        try { await call(url, body); await route(); } catch (error) { fail(error); }
    }

    // ---------- страница пространства ----------
    async function showSpace(slug) {
        await loadSpace(slug);
        drawTree(null);
        drawPath([], "");
        const main = $("fm-main");
        main.replaceChildren();
        const head = el("div", "fm-sechead");
        head.append(el("h2", "", space.title));
        if (space.about) head.append(markup(space.about));
        main.append(head);
        const tools = el("div", "fm-tools");
        if (space.can_create) tools.append(button("+ SECTION", () => composeSection(main, null)));
        main.append(tools);
        if (spaces.length > 1) {
            main.append(el("h3", "fm-cap", "SPACES"));
            const table = el("div", "fm-table");
            for (const item of spaces) {
                const row = el("a", "fm-row"); row.href = "#/s/" + item.slug;
                row.style.gridTemplateColumns = "minmax(0, 1fr)";
                row.append(el("span", "fm-subject", item.title));
                table.append(row);
            }
            main.append(table);
        } else if (!space.tree.length) {
            main.append(el("p", "fm-void", "-- no sections yet --"));
        }
        hint(space.slug.toUpperCase());
    }

    // ---------- раздел: темы строками ----------
    async function showSection(id) {
        const data = await call(slot(urls.sectionUrl, id));
        if (!space || space.slug !== data.space) await loadSpace(data.space);
        drawTree(data.id);
        drawPath(data.crumbs, "");
        const main = $("fm-main");
        main.replaceChildren();
        const head = el("div", "fm-sechead");
        head.append(el("h2", "", data.title));
        if (data.about) head.append(el("p", "", data.about));
        main.append(head);
        const tools = el("div", "fm-tools");
        if (data.can_write) tools.append(button("+ POST", () => composeTopic(main, data.id)));
        if (data.can_create) tools.append(button("+ SECTION", () => composeSection(main, data.id)));
        if (data.can_moderate) tools.append(button("ARCHIVE", async () => {
            if (!confirm("Archive this section? It disappears from the lists; posts are kept.")) return;
            try {
                await call(urls.archiveUrl, { section: data.id });
                await loadSpace(space.slug);
                const up = data.crumbs.length > 1 ? "#/c/" + data.crumbs[data.crumbs.length - 2].id : "#/s/" + space.slug;
                if (location.hash === up) await route(); else location.hash = up;
            } catch (error) { fail(error); }
        }));
        main.append(tools);
        if (!data.topics.length) {
            main.append(el("p", "fm-void", "-- no entries on this board --"));
        } else {
            const table = el("div", "fm-table");
            const header = el("div", "fm-row head");
            ["NO.", "SUBJECT", "FROM", "RE", "LAST"].forEach((label) => header.append(el("span", "", label)));
            table.append(header);
            for (const t of data.topics) {
                const row = el("a", "fm-row");
                row.href = "#/t/" + t.id;
                const subject = el("span", "fm-subject");
                if (t.pinned) subject.append(el("span", "fm-pin", "▲"));
                subject.append(t.title);
                if (t.locked) subject.append(el("span", "fm-closed", "[closed]"));
                row.append(el("span", "fm-no", ref(t.id)), subject, el("span", "fm-from kind-" + t.kind, t.name || "SYSTEM"),
                           el("span", "fm-re", String(t.replies)), el("span", "fm-last", t.last));
                table.append(row);
            }
            main.append(table);
        }
        hint(data.topics.length + (data.topics.length === 1 ? " topic" : " topics"));
    }

    // ---------- тема: записи журнала ----------
    async function showTopic(id) {
        const data = await call(slot(urls.topicUrl, id));
        if (!space || space.slug !== data.space) await loadSpace(data.space);
        drawTree(data.section);
        drawPath(data.crumbs, ref(data.id));
        const main = $("fm-main");
        main.replaceChildren();
        const head = el("div", "fm-topichead");
        head.append(el("h2", "", (data.pinned ? "▲ " : "") + data.title + (data.locked ? " [closed]" : "")));
        if (data.can_moderate) {
            head.append(link(data.pinned ? "unpin" : "pin", () => moderate(urls.flagsUrl, { topic: data.id, pinned: !data.pinned })),
                        link(data.locked ? "open" : "close", () => moderate(urls.flagsUrl, { topic: data.id, locked: !data.locked })));
        }
        main.append(head);

        const children = new Map();
        for (const post of data.posts) {
            const key = post.parent || 0;
            if (!children.has(key)) children.set(key, []);
            children.get(key).push(post);
        }
        const count = (post) => (children.get(post.id) || []).reduce((n, child) => n + 1 + count(child), 0);

        const render = (post, depth) => {
            const entry = el("article", "fm-entry kind-" + post.kind + (post.root ? " root" : ""));
            entry.id = "p" + post.id;
            const top = el("header", "fm-entryhead");
            top.append(el("span", "fm-ref", ref(post.id)), el("span", "fm-name", post.name || "SYSTEM"), el("span", "fm-ref", post.at));
            if (post.parent && !post.root) {
                const parent = data.posts.find((p) => p.id === post.parent);
                if (parent && !parent.root) {
                    const to = el("a", "fm-refto", "re " + ref(parent.id));
                    to.href = "#/t/" + data.id;
                    to.addEventListener("click", (event) => {
                        event.preventDefault();
                        const target = document.getElementById("p" + parent.id);
                        if (target) { target.scrollIntoView({ block: "center" }); target.classList.remove("flash"); void target.offsetWidth; target.classList.add("flash"); }
                    });
                    top.append(to);
                }
            }
            entry.append(top);
            if (post.hidden) {
                entry.append(el("p", "fm-gone", "[deleted]"));
                if (data.can_moderate && post.text) entry.append(el("p", "fm-dim", post.text));
            } else {
                entry.append(markup(post.text));
                if (post.files && post.files.length) {
                    const files = el("div", "fm-files");
                    for (const file of post.files) {
                        const row = el("span", "fm-file", "[" + file.name + "] " + file.size + " B ");
                        if (player) row.append(link("save to my disk", async () => {
                            try { const saved = await call(urls.saveUrl, { attachment: file.id }); notice("saved: " + saved.path); } catch (error) { fail(error); }
                        }));
                        files.append(row);
                    }
                    entry.append(files);
                }
            }
            const foot = el("div", "fm-entryfoot");
            if (data.can_reply && !post.hidden && !post.root) {
                foot.append(link("reply", () => {
                    if (entry.querySelector(":scope > .fm-form")) return;
                    const composer = composeReply(data.id, post.id, "reply");
                    foot.after(composer.form);
                    composer.focus();
                }));
            }
            if (data.can_moderate) {
                foot.append(link(post.hidden ? "restore" : (post.root ? "delete topic" : "delete"), () => {
                    if (post.root && !post.hidden && !confirm("Delete the whole topic?")) return;
                    moderate(post.hidden ? urls.restoreUrl : urls.hideUrl, { post: post.id });
                }, post.hidden ? "" : "warn"));
            }
            const kids = children.get(post.id) || [];
            let nest = null;
            if (kids.length && !post.root) {
                nest = el("div", "fm-replies");
                kids.forEach((child) => nest.append(render(child, depth + 1)));
                const total = count(post);
                const fold = link("hide " + total, () => {
                    nest.hidden = !nest.hidden;
                    fold.textContent = (nest.hidden ? "show " : "hide ") + total;
                });
                if (depth >= FOLD_FROM && total > 3) { nest.hidden = true; fold.textContent = "show " + total; }
                foot.append(fold);
            }
            if (foot.children.length) entry.append(foot);
            if (nest) entry.append(nest);
            return entry;
        };

        const thread = el("div", "fm-thread");
        const rootPosts = children.get(0) || [];
        for (const first of rootPosts) {
            thread.append(render(first, 0));
            // ответы на тему идут на одном уровне под ней
            const replies = children.get(first.id) || [];
            const wrap = el("div", "fm-replies");
            replies.forEach((reply) => wrap.append(render(reply, 1)));
            if (replies.length) thread.append(wrap);
        }
        main.append(thread);

        if (data.can_reply) {
            main.append(el("h3", "fm-cap", "REPLY"));
            main.append(composeReply(data.id, null).form);
        } else {
            main.append(el("p", "fm-void", data.locked ? "-- topic closed --" : "-- read only --"));
        }
        const total = data.posts.length - 1;
        hint(total + (total === 1 ? " reply" : " replies"));
    }

    // ---------- старт и маршрутизация ----------
    async function start() {
        const data = await call(urls.spacesUrl);
        spaces = data.spaces;
        node = data.node || "";
        callsign = data.callsign || "";
        player = !!data.callsign;
        drawHead();
        if (!spaces.length) {
            $("fm-space").textContent = "forum";
            $("fm-main").append(el("p", "fm-void", "-- no spaces on this node --"));
            return;
        }
        await route();
    }

    async function route() {
        const hash = location.hash;
        try {
            let found;
            if ((found = hash.match(/^#\/t\/(\d+)$/))) return await showTopic(found[1]);
            if ((found = hash.match(/^#\/c\/(\d+)$/))) return await showSection(found[1]);
            const slug = (found = hash.match(/^#\/s\/([\w-]+)$/)) ? found[1] : spaces[0].slug;
            await showSpace(slug);
        } catch (error) { fail(error); }
    }

    window.addEventListener("hashchange", route);
    start().catch(fail);
})();
