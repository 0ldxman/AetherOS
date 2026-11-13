// Форум: пространство машины, дерево разделов слева, темы раздела или дерево ответов темы справа. Адрес в хеше: #/s/слаг, #/c/раздел, #/t/тема.
(function () {
    "use strict";
    const { el, csrf, markup, notice } = window.apps;
    const root = document.getElementById("forum");
    const urls = root.dataset;
    const $ = (id) => document.getElementById(id);
    const MAX_FOLD = 3;                       // ветки глубже этого сворачиваются, если ответов много

    let spaces = [], space = null, player = false;

    const addr = (template, key, value) => template.replace(key, value);
    const sectionUrl = (id) => urls.sectionUrl.replace(/0\/$/, id + "/");
    const topicUrl = (id) => urls.topicUrl.replace(/0\/$/, id + "/");

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

    // ---------- вложения: выбор файла из своей машины ----------
    function attachField() {
        const wrap = el("div", "fm-attach");
        const chosen = [];
        const chips = el("span", "fm-chips");
        const add = el("button", "fm-link", "attach file"); add.type = "button";
        const picker = el("div", "fm-picker"); picker.hidden = true;
        const MAX = 2;

        function drawChips() {
            chips.replaceChildren();
            for (const file of chosen) {
                const chip = el("span", "fm-chip", file.name + " ");
                const drop = el("button", "fm-link", "×"); drop.type = "button"; drop.title = "remove";
                drop.addEventListener("click", () => { chosen.splice(chosen.indexOf(file), 1); drawChips(); });
                chip.append(drop);
                chips.append(chip);
            }
            add.hidden = chosen.length >= MAX;
        }
        async function browse(path) {
            try {
                const data = await call(urls.filesUrl + (path ? "?path=" + encodeURIComponent(path) : ""));
                picker.replaceChildren(el("div", "fm-dim", data.path));
                const list = el("div", "fm-files-list");
                if (data.parent) {
                    const up = el("button", "fm-link", ".."); up.type = "button";
                    up.addEventListener("click", () => browse(data.parent));
                    list.append(up);
                }
                for (const row of data.entries) {
                    const item = el("button", "fm-link", row.dir ? row.name + "/" : row.name); item.type = "button";
                    item.addEventListener("click", () => {
                        if (row.dir) return browse(row.path);
                        if (!chosen.some((file) => file.path === row.path)) chosen.push({ path: row.path, name: row.name });
                        picker.hidden = true;
                        drawChips();
                    });
                    list.append(item);
                }
                picker.append(list);
            } catch (error) { fail(error); picker.hidden = true; }
        }
        add.addEventListener("click", () => { picker.hidden = !picker.hidden; if (!picker.hidden) browse(""); });
        wrap.append(add, chips, picker);
        return { node: wrap, paths: () => chosen.map((file) => file.path) };
    }

    function fileLinks(post) {
        const box = el("div", "fm-files");
        for (const file of post.files || []) {
            const row = el("span", "fm-file", "[" + file.name + "] " + file.size + " B ");
            if (player) {
                const save = el("button", "fm-link", "save to my disk"); save.type = "button";
                save.addEventListener("click", async () => {
                    try { const saved = await call(urls.saveUrl, { attachment: file.id }); notice("saved: " + saved.path); } catch (error) { fail(error); }
                });
                row.append(save);
            }
            box.append(row);
        }
        return box;
    }

    // ---------- шапка и дерево ----------
    function crumbs(items) {
        const bar = $("fm-crumbs");
        bar.replaceChildren();
        const home = el("a", "", space ? space.title : "forum");
        home.href = space ? "#/s/" + space.slug : "#/";
        bar.append(home);
        for (const item of items || []) {
            bar.append(el("span", "fm-sep", " / "));
            const link = el("a", "", item.title);
            link.href = "#/c/" + item.id;
            bar.append(link);
        }
    }

    function drawTree(nodes, current) {
        const box = $("fm-tree");
        box.replaceChildren();
        if (!nodes.length) { box.append(el("p", "fm-dim", "no sections")); return; }
        const list = (items, depth) => {
            const ul = el("ul", "fm-list");
            for (const node of items) {
                const li = el("li");
                const link = el("a", "fm-node" + (node.id === current ? " on" : ""), node.title);
                link.href = "#/c/" + node.id;
                link.style.paddingLeft = (8 + depth * 12) + "px";
                if (node.about) link.title = node.about;
                li.append(link);
                if (node.children.length) li.append(list(node.children, depth + 1));
                ul.append(li);
            }
            return ul;
        };
        box.append(list(nodes, 0));
    }

    async function loadSpace(slug) {
        space = await call(addr(urls.spaceUrl, "SLUG", slug));
        $("fm-space").textContent = space.title;
        return space;
    }

    // ---------- раздел: список тем и форма новой темы ----------
    async function showSection(id) {
        const data = await call(sectionUrl(id));
        if (!space || space.slug !== data.space) await loadSpace(data.space);
        drawTree(space.tree, data.id);
        crumbs(data.crumbs);
        const main = $("fm-main");
        main.replaceChildren();
        const head = el("div", "fm-sechead");
        head.append(el("h2", "", data.title));
        if (data.about) head.append(el("p", "fm-dim", data.about));
        main.append(head);
        const tools = el("div", "fm-actions fm-tools");
        if (data.can_write) tools.append(tool("New topic", () => composeTopic(main, data.id)));
        if (data.can_create) tools.append(tool("New section", () => composeSection(main, data.id)));
        if (data.can_moderate) tools.append(tool("Archive section", async () => {
            if (!confirm("Archive this section? It disappears from the lists; posts are kept.")) return;
            try {
                await call(urls.archiveUrl, { section: data.id });
                await loadSpace(space.slug);
                const up = data.crumbs.length > 1 ? "#/c/" + data.crumbs[data.crumbs.length - 2].id : "#/s/" + space.slug;
                if (location.hash === up) await route(); else location.hash = up;
            } catch (error) { fail(error); }
        }));
        if (tools.children.length) main.append(tools);
        if (!data.topics.length) main.append(el("p", "fm-dim", "no topics yet"));
        const table = el("div", "fm-topics");
        for (const t of data.topics) {
            const row = el("a", "fm-topic");
            row.href = "#/t/" + t.id;
            const title = el("span", "fm-ttitle", (t.pinned ? "▲ " : "") + t.title + (t.locked ? " [closed]" : ""));
            const meta = el("span", "fm-meta", t.name + " · " + t.at + " · " + t.replies + (t.replies === 1 ? " reply" : " replies") + " · last " + t.last);
            row.append(title, meta);
            table.append(row);
        }
        main.append(table);
    }

    function tool(label, onclick) {
        const button = el("button", "app-button", label);
        button.type = "button";
        button.addEventListener("click", onclick);
        return button;
    }

    function composeSection(main, parentId) {
        if (main.querySelector(".fm-form")) return;
        const form = el("form", "fm-form");
        const title = el("input", "field");
        title.placeholder = "section name"; title.maxLength = 120; title.required = true;
        const about = el("input", "field");
        about.placeholder = "what is it for (optional)"; about.maxLength = 240;
        const send = el("button", "app-button primary", "Create"); send.type = "submit";
        const cancel = el("button", "app-button", "Cancel"); cancel.type = "button";
        cancel.addEventListener("click", () => form.remove());
        const acts = el("div", "fm-actions");
        acts.append(send, cancel);
        form.append(title, about, acts);
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            send.disabled = true;
            try {
                const made = await call(urls.newSectionUrl, { space: space.slug, parent: parentId, title: title.value, about: about.value });
                await loadSpace(space.slug);
                location.hash = "#/c/" + made.id;
            } catch (error) { fail(error); send.disabled = false; }
        });
        main.querySelector(".fm-sechead").after(form);
        title.focus();
    }

    function composeTopic(main, sectionId) {
        if (main.querySelector(".fm-form")) return;
        const form = el("form", "fm-form");
        const title = el("input", "field");
        title.placeholder = "title"; title.maxLength = 160; title.required = true;
        const text = el("textarea", "field");
        text.placeholder = "text"; text.maxLength = 4000; text.required = true;
        const send = el("button", "app-button primary", "Post"); send.type = "submit";
        const cancel = el("button", "app-button", "Cancel"); cancel.type = "button";
        cancel.addEventListener("click", () => form.remove());
        const topicFiles = player ? attachField() : null;
        form.append(title, text);
        if (topicFiles) form.append(topicFiles.node);
        form.append(el("div", "fm-actions"));
        form.lastChild.append(send, cancel);
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            send.disabled = true;
            try {
                const made = await call(urls.newTopicUrl, { section: sectionId, title: title.value, text: text.value, attachments: topicFiles ? topicFiles.paths() : [] });
                location.hash = "#/t/" + made.id;
            } catch (error) { fail(error); send.disabled = false; }
        });
        main.querySelector(".fm-sechead").after(form);
        title.focus();
    }

    // ---------- тема: дерево ответов ----------
    async function showTopic(id) {
        const data = await call(topicUrl(id));
        if (!space || space.slug !== data.space) await loadSpace(data.space);
        drawTree(space.tree, data.section);
        crumbs(data.crumbs);
        const main = $("fm-main");
        main.replaceChildren();
        const head = el("div", "fm-sechead");
        head.append(el("h2", "", (data.pinned ? "▲ " : "") + data.title + (data.locked ? " [closed]" : "")));
        main.append(head);
        if (data.can_moderate) {
            const bar = el("div", "fm-actions fm-tools");
            bar.append(tool(data.pinned ? "Unpin" : "Pin", () => moderate(urls.flagsUrl, { topic: data.id, pinned: !data.pinned })),
                       tool(data.locked ? "Open" : "Close", () => moderate(urls.flagsUrl, { topic: data.id, locked: !data.locked })));
            main.append(bar);
        }
        const children = new Map();
        for (const post of data.posts) {
            const key = post.parent || 0;
            if (!children.has(key)) children.set(key, []);
            children.get(key).push(post);
        }
        const count = (post) => (children.get(post.id) || []).reduce((n, child) => n + 1 + count(child), 0);
        const render = (post, depth) => {
            const box = el("div", "fm-post kind-" + post.kind + (post.root ? " root" : ""));
            const bar = el("div", "fm-postbar");
            bar.append(el("span", "fm-name", post.name || "system"), el("span", "fm-meta", post.at));
            box.append(bar);
            if (post.hidden) {
                box.append(el("p", "fm-dim", "[deleted]"));
                if (data.can_moderate && post.text) box.append(el("p", "fm-dim fm-gone", post.text));
            } else {
                box.append(markup(post.text));
                if (post.files && post.files.length) box.append(fileLinks(post));
            }
            const acts = el("div", "fm-actions");
            if (data.can_reply && !post.hidden) {
                const reply = el("button", "fm-link", "reply"); reply.type = "button";
                reply.addEventListener("click", () => composeReply(box, data.id, post.id));
                acts.append(reply);
            }
            if (data.can_moderate) {
                const act = el("button", "fm-link", post.hidden ? "restore" : (post.root ? "delete topic" : "delete")); act.type = "button";
                act.addEventListener("click", () => {
                    if (post.root && !post.hidden && !confirm("Delete the whole topic?")) return;
                    moderate(post.hidden ? urls.restoreUrl : urls.hideUrl, { post: post.id });
                });
                acts.append(act);
            }
            const kids = children.get(post.id) || [];
            let nest = null;
            if (kids.length) {
                nest = el("div", "fm-nest");
                kids.forEach((child) => nest.append(render(child, depth + 1)));
                const fold = el("button", "fm-link", "hide " + count(post));
                fold.type = "button";
                fold.addEventListener("click", () => {
                    nest.hidden = !nest.hidden;
                    fold.textContent = nest.hidden ? "show " + count(post) : "hide " + count(post);
                });
                if (depth >= MAX_FOLD && count(post) > 3) { nest.hidden = true; fold.textContent = "show " + count(post); }
                acts.append(fold);
            }
            box.append(acts);
            if (nest) box.append(nest);
            return box;
        };
        const roots = children.get(0) || [];
        roots.forEach((post) => main.append(render(post, 0)));
        if (!data.can_reply) main.append(el("p", "fm-dim", data.locked ? "this topic is closed" : "read only"));
    }

    async function moderate(url, body) {
        try {
            await call(url, body);
            await route();
        } catch (error) { fail(error); }
    }

    function composeReply(box, topicId, parentId) {
        if (box.querySelector(":scope > .fm-form")) return;
        const form = el("form", "fm-form");
        const text = el("textarea", "field");
        text.placeholder = "reply"; text.maxLength = 4000; text.required = true;
        const send = el("button", "app-button primary", "Reply"); send.type = "submit";
        const cancel = el("button", "app-button", "Cancel"); cancel.type = "button";
        cancel.addEventListener("click", () => form.remove());
        const acts = el("div", "fm-actions");
        acts.append(send, cancel);
        const replyFiles = player ? attachField() : null;
        form.append(text);
        if (replyFiles) form.append(replyFiles.node);
        form.append(acts);
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            send.disabled = true;
            try {
                await call(urls.newPostUrl, { topic: topicId, parent: parentId, text: text.value, attachments: replyFiles ? replyFiles.paths() : [] });
                await route();
            } catch (error) { fail(error); send.disabled = false; }
        });
        box.querySelector(":scope > .fm-actions").after(form);
        text.focus();
    }

    // ---------- старт и маршрутизация ----------
    async function start() {
        const data = await call(urls.spacesUrl);
        spaces = data.spaces;
        $("fm-call").textContent = data.callsign || "guest";
        player = !!data.callsign;
        if (!spaces.length) {
            $("fm-space").textContent = "forum";
            $("fm-main").append(el("p", "fm-dim", "no spaces on this machine"));
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
            await loadSpace(slug);
            drawTree(space.tree, null);
            crumbs([]);
            const main = $("fm-main");
            main.replaceChildren();
            const head = el("div", "fm-sechead");
            head.append(el("h2", "", space.title));
            if (space.about) head.append(markup(space.about));
            main.append(head);
            if (space.can_create) {
                const bar = el("div", "fm-actions fm-tools");
                bar.append(tool("New section", () => composeSection(main, null)));
                main.append(bar);
            }
            if (spaces.length > 1) {
                const list = el("div", "fm-topics");
                for (const item of spaces) {
                    const row = el("a", "fm-topic"); row.href = "#/s/" + item.slug;
                    row.append(el("span", "fm-ttitle", item.title), el("span", "fm-meta", item.about));
                    list.append(row);
                }
                main.append(el("h3", "", "spaces"), list);
            }
        } catch (error) { fail(error); }
    }

    window.addEventListener("hashchange", route);
    start().catch(fail);
})();
