// Форум: доска узла. Одна колонка: разделы (#/s/слаг), темы раздела (#/c/раздел), тема с ветками ответов (#/t/тема).
(function () {
    "use strict";
    const { el, csrf, markup, notice } = window.apps;
    const urls = document.getElementById("forum").dataset;
    const $ = (id) => document.getElementById(id);
    const INDENT = 4;                          // глубже ветки не сдвигаются вправо, чтобы текст не сжимался
    const FOLD_FROM = 3;                       // длинные ветки глубже этого свёрнуты сразу

    let spaces = [], space = null, player = false, node = "", callsign = "";

    const slot = (template, id) => template.replace(/0\/$/, id + "/");
    const ago = (text) => (!text ? "" : text === "just now" ? text : text + " ago");
    const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

    async function call(url, body) {
        const response = await fetch(url, body === undefined ? { credentials: "same-origin" } : {
            method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) { const error = new Error(data.error || (response.status === 404 ? "not found" : "no response")); error.status = response.status; throw error; }
        return data;
    }
    const fail = (error) => notice(error.message || String(error));
    function button(label, onclick, className) {
        const node = el("button", className || "app-button", label);
        node.type = "button";
        node.addEventListener("click", onclick);
        return node;
    }
    const link = (label, onclick, extra) => button(label, onclick, "fm-link" + (extra ? " " + extra : ""));
    function page() { const box = $("fm-page"); box.replaceChildren(); return box; }

    // ---------- шапка, путь, действия ----------
    function drawWho() {
        const who = $("fm-who");
        who.replaceChildren();
        if (callsign) who.append(el("b", "", callsign), " @ " + (node || "?"));
        else who.append("guest @ " + (node || "?") + " · read only");
    }
    function drawBar(crumbs, here, actions) {
        const bar = $("fm-crumbs");
        bar.replaceChildren();
        const home = el("a", "", space ? space.title : "forum");
        home.href = space ? "#/s/" + space.slug : "#/";
        bar.append(home);
        for (const item of crumbs || []) {
            bar.append(el("span", "fm-sep", "/"));
            const part = el("a", "", item.title);
            part.href = "#/c/" + item.id;
            bar.append(part);
        }
        if (here) bar.append(el("span", "fm-sep", "/"), el("span", "fm-here", here));
        $("fm-actions").replaceChildren(...(actions || []));
    }
    async function loadSpace(slug) {
        space = await call(urls.spaceUrl.replace("SLUG", slug));
        $("fm-space").textContent = space.title;
        return space;
    }
    const findNode = (nodes, id) => { for (const item of nodes) { if (item.id === id) return item; const found = findNode(item.children, id); if (found) return found; } return null; };

    // ---------- строки разделов ----------
    function boardRow(item, sub) {
        const row = el("a", "fm-board" + (sub ? " sub" : ""));
        row.href = "#/c/" + item.id;
        row.append(el("span", "fm-dot" + (item.new ? " on" : "")), el("span", "fm-board-title", item.title),
                   el("span", "fm-board-count", (item.new ? item.new + " new · " : "") + plural(item.topics, "topic", "topics")));
        if (item.about) row.append(el("span", "fm-board-about", item.about));
        const last = el("span", "fm-board-last");
        if (item.last) last.append("last: ", el("i", "", item.last.title), " · " + item.last.name + " · " + ago(item.last.ago));
        else last.append(item.can_write ? "empty — start the first topic" : "empty");
        row.append(last);
        if (!item.can_write) row.title = "read only";
        return row;
    }
    function boards(items, depth) {
        const box = el("div", "fm-boards");
        const walk = (nodes, level) => nodes.forEach((item) => { box.append(boardRow(item, level > 0)); if (level < 1) walk(item.children, level + 1); });
        walk(items, depth);
        return box;
    }

    // ---------- формы ----------
    function attachField() {
        const wrap = el("div", "fm-attach");
        const chosen = [];
        const chips = el("span", "fm-chips");
        const picker = el("div", "fm-picker");
        picker.hidden = true;
        const add = link("+ attach file", () => { picker.hidden = !picker.hidden; if (!picker.hidden) browse(""); });
        function drawChips() {
            chips.replaceChildren();
            for (const file of chosen) {
                const chip = el("span", "fm-chip", file.name + " ");
                chip.append(link("×", () => { chosen.splice(chosen.indexOf(file), 1); drawChips(); }));
                chips.append(chip);
            }
            add.hidden = chosen.length >= 2;
        }
        async function browse(path) {
            try {
                const data = await call(urls.filesUrl + (path ? "?path=" + encodeURIComponent(path) : ""));
                const list = el("div", "fm-picker-list");
                if (data.parent) list.append(link("../", () => browse(data.parent)));
                for (const row of data.entries) {
                    list.append(link(row.dir ? row.name + "/" : row.name, () => {
                        if (row.dir) return browse(row.path);
                        if (!chosen.some((file) => file.path === row.path)) chosen.push({ path: row.path, name: row.name });
                        picker.hidden = true;
                        drawChips();
                    }));
                }
                picker.replaceChildren(el("div", "fm-muted", data.path), list);
            } catch (error) { fail(error); picker.hidden = true; }
        }
        wrap.append(add, chips, picker);
        return { node: wrap, paths: () => chosen.map((file) => file.path) };
    }

    // форма: поля, вложения (у игрока), «Ctrl+Enter отправить, Esc отмена»
    function form({ fields, label, send, cancel, inline, files }) {
        const box = el("form", "fm-form" + (inline ? " inline" : ""));
        box.append(...fields);
        const attached = files && player ? attachField() : null;
        if (attached) box.append(attached.node);
        const submit = el("button", "app-button primary", label);
        submit.type = "submit";
        const foot = el("div", "fm-form-foot");
        foot.append(submit, button("Cancel", () => cancel(box)), el("span", "fm-hint", "ctrl+enter to send · esc to cancel"));
        box.append(foot);
        box.addEventListener("keydown", (event) => {
            if (event.key === "Escape") { event.preventDefault(); cancel(box); }
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); box.requestSubmit(); }
        });
        box.addEventListener("submit", async (event) => {
            event.preventDefault();
            submit.disabled = true;
            try { await send(attached ? attached.paths() : []); } catch (error) { fail(error); submit.disabled = false; }
        });
        return box;
    }
    function input(tag, placeholder, max, required) {
        const node = el(tag, "field");
        node.placeholder = placeholder;
        node.maxLength = max;
        node.required = required;
        return node;
    }

    function openTopicForm(sectionId) {
        const box = $("fm-page");
        if (box.querySelector(":scope > .fm-form")) return;
        const title = input("input", "subject", 160, true);
        const text = input("textarea", "what do you want to say?", 4000, true);
        const made = form({ fields: [title, text], label: "Post topic", files: true, cancel: (f) => f.remove(),
            send: async (files) => {
                const topic = await call(urls.newTopicUrl, { section: sectionId, title: title.value, text: text.value, attachments: files });
                location.hash = "#/t/" + topic.id;
            } });
        box.prepend(made);
        title.focus();
    }
    function openSectionForm(parentId) {
        const box = $("fm-page");
        if (box.querySelector(":scope > .fm-form")) return;
        const title = input("input", "section name", 120, true);
        const about = input("input", "what is it for (optional)", 240, false);
        const made = form({ fields: [title, about], label: "Create section", cancel: (f) => f.remove(),
            send: async () => {
                const section = await call(urls.newSectionUrl, { space: space.slug, parent: parentId, title: title.value, about: about.value });
                await loadSpace(space.slug);
                location.hash = "#/c/" + section.id;
            } });
        box.prepend(made);
        title.focus();
    }

    async function moderate(url, body) {
        try { await call(url, body); await route(); } catch (error) { fail(error); }
    }

    // ---------- главная пространства: разделы ----------
    async function showSpace(slug) {
        await loadSpace(slug);
        const actions = space.can_create ? [button("+ Section", () => openSectionForm(null))] : [];
        drawBar([], "", actions);
        const box = page();
        if (space.about) { const intro = el("div", "fm-intro"); intro.append(markup(space.about)); box.append(intro); }
        box.append(el("h2", "fm-cap", "SECTIONS"));
        if (space.tree.length) box.append(boards(space.tree, 0));
        else box.append(el("p", "fm-void", space.can_create ? "No sections yet. Create the first one." : "No sections yet."));
        if (spaces.length > 1) {
            box.append(el("h2", "fm-cap", "OTHER SPACES ON THIS NODE"));
            const list = el("div", "fm-boards");
            for (const item of spaces.filter((s) => s.slug !== space.slug)) {
                const row = el("a", "fm-board"); row.href = "#/s/" + item.slug;
                row.append(el("span", "fm-dot"), el("span", "fm-board-title", item.title), el("span", "fm-board-count", ""));
                if (item.about) row.append(el("span", "fm-board-about", item.about));
                list.append(row);
            }
            box.append(list);
        }
    }

    // ---------- раздел: подразделы и темы ----------
    function topicRow(t) {
        const fresh = t.unseen || t.new > 0;
        const row = el("a", "fm-topic" + (fresh ? "" : " read"));
        row.href = "#/t/" + t.id;
        const mark = el("span", "fm-mark");
        if (t.pinned) mark.textContent = "▲";
        else mark.append(el("span", "fm-dot" + (fresh ? " on" : "")));
        const title = el("span", "fm-topic-title", t.title);
        if (t.locked) title.append(el("span", "fm-closed", "closed"));
        row.append(mark, title, el("span", "fm-by kind-" + t.kind, t.name || "SYSTEM"));
        if (t.excerpt) row.append(el("span", "fm-excerpt", t.excerpt));
        const meta = el("span", "fm-topic-meta");
        const info = el("span", "", plural(t.replies, "reply", "replies") + (t.replies ? " · last " + t.last_name + " " + ago(t.last_ago) : " · " + ago(t.ago)));
        meta.append(info);
        if (t.unseen) meta.append(el("span", "fm-new", "new"));
        else if (t.new) meta.append(el("span", "fm-new", t.new + " new"));
        row.append(meta);
        return row;
    }

    async function showSection(id) {
        const data = await call(slot(urls.sectionUrl, id));
        await loadSpace(data.space);
        const actions = [];
        if (data.can_moderate) actions.push(button("Archive", async () => {
            if (!confirm("Archive this section? It leaves the lists; posts are kept.")) return;
            try {
                await call(urls.archiveUrl, { section: data.id });
                location.hash = data.crumbs.length > 1 ? "#/c/" + data.crumbs[data.crumbs.length - 2].id : "#/s/" + space.slug;
            } catch (error) { fail(error); }
        }));
        if (data.can_create) actions.push(button("+ Section", () => openSectionForm(data.id)));
        if (data.can_write) actions.push(button("+ Topic", () => openTopicForm(data.id), "app-button primary"));
        drawBar(data.crumbs.slice(0, -1), data.title, actions);
        const box = page();
        if (data.about) box.append(el("p", "fm-intro", data.about));
        const here = findNode(space.tree, data.id);
        if (here && here.children.length) {
            box.append(el("h2", "fm-cap", "SECTIONS"));
            box.append(boards(here.children, 0));
        }
        const pinned = data.topics.filter((t) => t.pinned);
        const rest = data.topics.filter((t) => !t.pinned);
        if (pinned.length) {
            box.append(el("h2", "fm-cap", "PINNED"));
            const list = el("div", "fm-topics"); pinned.forEach((t) => list.append(topicRow(t))); box.append(list);
        }
        box.append(el("h2", "fm-cap", "TOPICS"));
        if (rest.length) { const list = el("div", "fm-topics"); rest.forEach((t) => list.append(topicRow(t))); box.append(list); }
        else box.append(el("p", "fm-void", data.can_write ? "Nothing here yet. Start a topic." : "Nothing here yet."));
    }

    // ---------- тема ----------
    function filesOf(post) {
        const box = el("div", "fm-files");
        for (const file of post.files || []) {
            const row = el("span", "fm-file");
            row.append(el("b", "", file.name), file.size + " B");
            if (player) row.append(link("save to my disk", async () => {
                try { const saved = await call(urls.saveUrl, { attachment: file.id }); notice("saved to " + saved.path); } catch (error) { fail(error); }
            }));
            box.append(row);
        }
        return box;
    }
    function textOf(post, moderator) {
        if (post.hidden) {
            const gone = el("div", "fm-text");
            gone.append(el("p", "fm-gone", "message deleted"));
            if (moderator && post.text) gone.append(el("p", "fm-muted", post.text));
            return gone;
        }
        const text = el("div", "fm-text");
        text.append(markup(post.text));
        if (post.files && post.files.length) text.append(filesOf(post));
        return text;
    }

    async function showTopic(id) {
        const data = await call(slot(urls.topicUrl, id));
        await loadSpace(data.space);
        drawBar(data.crumbs, "", []);
        const box = page();
        const byId = new Map(data.posts.map((p) => [p.id, p]));
        const kids = new Map();
        for (const post of data.posts) { const key = post.parent || 0; if (!kids.has(key)) kids.set(key, []); kids.get(key).push(post); }
        const count = (post) => (kids.get(post.id) || []).reduce((n, child) => n + 1 + count(child), 0);
        const first = data.posts.find((p) => p.root) || data.posts[0];

        // первое сообщение: сама тема
        const op = el("article", "fm-op kind-" + first.kind);
        op.append(el("h2", "", data.title + (data.locked ? "  [closed]" : "")));
        const meta = el("div", "fm-meta");
        const when = el("span", "", ago(first.ago)); when.title = first.at;
        meta.append(el("span", "fm-name", first.name || "SYSTEM"), when);
        if (data.pinned) meta.append(el("span", "", "pinned"));
        op.append(meta, textOf(first, data.can_moderate));
        const tools = el("div", "fm-tools");
        if (data.can_reply) tools.append(link("reply", () => openReply(null)));
        if (data.can_moderate) {
            tools.append(link(data.pinned ? "unpin" : "pin", () => moderate(urls.flagsUrl, { topic: data.id, pinned: !data.pinned })),
                         link(data.locked ? "reopen" : "close", () => moderate(urls.flagsUrl, { topic: data.id, locked: !data.locked })),
                         link("delete topic", () => { if (confirm("Delete the whole topic?")) moderate(urls.hideUrl, { post: first.id }); }, "warn"));
        }
        if (tools.children.length) op.append(tools);
        box.append(op);

        const replies = data.posts.length - 1;
        box.append(el("h2", "fm-cap", replies ? plural(replies, "REPLY", "REPLIES") : "NO REPLIES YET"));

        const render = (post, depth) => {
            const item = el("div", "fm-c kind-" + post.kind + (post.new ? " fresh" : ""));
            item.id = "p" + post.id;
            const head = el("div", "fm-chead");
            const fold = el("button", "fm-fold", "[–]");
            fold.type = "button";
            fold.setAttribute("aria-expanded", "true");
            fold.title = "collapse";
            const when = el("span", "", ago(post.ago)); when.title = post.at;
            head.append(fold, el("span", "fm-name", post.name || "SYSTEM"), when);
            const parent = byId.get(post.parent);
            if (depth >= INDENT && parent && !parent.root) {
                const to = el("a", "fm-muted", "→ " + (parent.name || "SYSTEM"));
                to.href = "#p" + parent.id;
                to.addEventListener("click", (event) => { event.preventDefault(); const target = $("p" + parent.id); if (target) { target.scrollIntoView({ block: "center" }); target.classList.remove("fm-flash"); void target.offsetWidth; target.classList.add("fm-flash"); } });
                head.append(to);
            }
            item.append(head);
            const body = el("div", "fm-cbody");
            body.append(textOf(post, data.can_moderate));
            const actions = el("div", "fm-tools");
            if (data.can_reply && !post.hidden) actions.append(link("reply", () => openReply(post.id, body)));
            if (data.can_moderate) actions.append(post.hidden ? link("restore", () => moderate(urls.restoreUrl, { post: post.id }))
                                                              : link("delete", () => moderate(urls.hideUrl, { post: post.id }), "warn"));
            if (actions.children.length) body.append(actions);
            item.append(body);
            const children = kids.get(post.id) || [];
            if (children.length) {
                const nest = el("div", "fm-kids" + (depth + 1 >= INDENT ? " flat" : ""));
                children.forEach((child) => nest.append(render(child, depth + 1)));
                item.append(nest);
            }
            const total = count(post);
            const setFold = (folded) => {
                item.classList.toggle("folded", folded);
                fold.textContent = folded ? "[+" + (total + 1) + "]" : "[–]";
                fold.setAttribute("aria-expanded", String(!folded));
                fold.title = folded ? "expand" : "collapse";
            };
            fold.addEventListener("click", () => setFold(!item.classList.contains("folded")));
            if (depth >= FOLD_FROM && total > 3) setFold(true);
            return item;
        };
        const list = el("div", "fm-replies");
        (kids.get(first.id) || []).forEach((post) => list.append(render(post, 0)));
        box.append(list);

        // поле ответа в тему: свёрнуто в строку, раскрывается по щелчку
        function openReply(parentId, under) {
            const at = under || box;
            const existing = at.querySelector(":scope > .fm-form");
            if (existing) { existing.querySelector("textarea").focus(); return; }
            const text = input("textarea", parentId ? "reply to " + (byId.get(parentId).name || "SYSTEM") : "reply to the topic", 4000, true);
            const made = form({ fields: [text], label: "Reply", files: true, inline: !!parentId,
                cancel: (f) => { f.remove(); if (!parentId) drawReplyBox(); },
                send: async (files) => { await call(urls.newPostUrl, { topic: data.id, parent: parentId, text: text.value, attachments: files }); await route(); } });
            if (parentId) at.append(made);
            else { const stub = box.querySelector(":scope > .fm-replybox"); if (stub) stub.replaceWith(made); else box.append(made); }
            text.focus();
        }
        function drawReplyBox() {
            const stub = el("button", "fm-replybox", (callsign || "guest") + " — write a reply…");
            stub.type = "button";
            stub.addEventListener("click", () => openReply(null));
            box.append(stub);
        }
        if (data.can_reply) drawReplyBox();
        else box.append(el("p", "fm-void", data.locked ? "This topic is closed." : callsign ? "This board is read only." : "Sign in to reply."));
    }

    // ---------- старт ----------
    async function start() {
        const data = await call(urls.spacesUrl);
        spaces = data.spaces;
        node = data.node || "";
        callsign = data.callsign || "";
        player = !!callsign;
        drawWho();
        if (!spaces.length) {
            $("fm-space").textContent = "forum";
            drawBar([], "", []);
            page().append(el("p", "fm-void", "No boards are reachable from this node."));
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
            $("fm-page").parentElement.scrollTop = 0;
        } catch (error) { fail(error); }
    }
    window.addEventListener("hashchange", () => { route().then(() => { $("fm-page").parentElement.scrollTop = 0; }); });
    start().catch(fail);
})();
