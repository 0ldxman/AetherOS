// Форум: доски узла. Слева доски пространства (как каналы), справа лист: обзор (#/s/слаг), раздел (#/c/id), тема (#/t/id).
(function () {
    "use strict";
    const { el, csrf, markup, notice } = window.apps;
    const urls = document.getElementById("forum").dataset;
    const $ = (id) => document.getElementById(id);
    const INDENT = 4;                          // глубже ветки не сдвигаются: ответ встаёт рядом и подписан «→ имя»
    const FOLD_FROM = 3;                       // длинные ветки глубже этого свёрнуты сразу

    let spaces = [], space = null, player = false, node = "", callsign = "", current = null;

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
    const page = () => { const box = $("fm-page"); box.replaceChildren(); return box; };
    const cap = (text, extra) => { const h = el("h2", "fm-cap", text); if (extra) h.append(extra); return h; };

    // код отправителя, как в заголовках узловой почты: три знака (MAPT → MAP, OPERATOR-7 → OP7), у системы SYS; свой цвет у каждого
    function plate(name, kind, face) {
        if (kind === "system" || !name) return el("span", "fm-plate sys", "SYS");
        if (face && face.code) { const own = el("span", "fm-plate c" + (face.color || 0), face.code); own.setAttribute("aria-hidden", "true"); return own; }
        let hash = 0;
        for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
        const clean = name.toUpperCase().replace(/[^A-Z0-9]/g, "");
        const digit = clean.slice(2).match(/[0-9]/);
        const box = el("span", "fm-plate c" + (hash % 4), digit ? clean.slice(0, 2) + digit[0] : clean.slice(0, 3) || "???");
        box.setAttribute("aria-hidden", "true");
        return box;
    }
    const nameTag = (name, kind) => el("span", "fm-name kind-" + kind, name || "SYSTEM");

    // ---------- шапка, доски слева, строка места ----------
    function drawWho() {
        const who = $("fm-who");
        who.replaceChildren();
        if (callsign) who.append(plate(callsign, "player"), el("b", "", callsign));
        else who.append("guest · read only");
    }
    function drawRail() {
        const rail = $("fm-rail");
        rail.replaceChildren();
        if (!space) return;
        const item = (href, label, active, extra, level) => {
            const row = el("a", "fm-railitem" + (level ? " sub" : "") + (extra && extra.fresh ? " fresh" : ""));
            row.href = href;
            if (level) row.style.paddingLeft = (16 + level * 16) + "px";
            if (active) row.setAttribute("aria-current", "page");
            row.append(el("span", "fm-name-cut", label));
            if (extra && extra.fresh) row.append(el("span", "fm-pill", String(extra.fresh)));
            else if (extra && extra.count !== undefined) row.append(el("span", "fm-railcount", String(extra.count)));
            return row;
        };
        rail.append(item("#/s/" + space.slug, "Overview", current === "space"));
        rail.append(el("div", "fm-railcap", "BOARDS"));
        const walk = (nodes, level) => nodes.forEach((n) => {
            rail.append(item("#/c/" + n.id, n.title, current === n.id, { fresh: n.new, count: n.topics }, level));
            walk(n.children, level + 1);
        });
        walk(space.tree, 0);
        if (space.can_create) rail.append(link("+ new board", () => { location.hash = "#/s/" + space.slug; setTimeout(() => openSectionForm(null), 0); }, "fm-railadd strong"));
        if (spaces.length > 1) {
            rail.append(el("div", "fm-railcap", "SPACES"));
            spaces.forEach((s) => rail.append(item("#/s/" + s.slug, s.title, false)));
        }
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
        $("fm-addr").textContent = space.slug + "@" + (node || "?");
        return space;
    }
    const findNode = (nodes, id) => { for (const n of nodes) { if (n.id === id) return n; const f = findNode(n.children, id); if (f) return f; } return null; };
    const allNodes = (nodes) => nodes.flatMap((n) => [n, ...allNodes(n.children)]);

    // ---------- строки списков ----------
    function boardRow(n) {
        const row = el("a", "fm-row" + (n.new ? "" : " read"));
        row.href = "#/c/" + n.id;
        row.append(el("span", "fm-ico" + (n.new ? " on" : ""), n.new ? "●" : "#"));
        const main = el("div", "fm-row-main");
        main.append(el("div", "fm-row-title", n.title));
        if (n.about) main.append(el("div", "fm-row-sub", n.about));
        const meta = el("div", "fm-row-meta");
        if (n.last) meta.append("last: ", el("i", "", n.last.title), " · " + n.last.name + " · " + ago(n.last.ago));
        else meta.append(n.can_write ? "no topics yet — be the first" : "no topics yet");
        main.append(meta);
        const side = el("div", "fm-row-side");
        side.append(el("span", "fm-big", String(n.topics)), el("span", "", n.topics === 1 ? "topic" : "topics"));
        if (n.new) side.append(el("span", "fm-new", n.new + " new"));
        row.append(main, side);
        return row;
    }
    // пометки темы: закреплена, том, закрыта или в архиве, скоро закроется
    function tags(title, t) {
        if (t.pinned) title.append(el("span", "fm-pinned", "pinned"));
        if (t.volume) title.append(el("span", "fm-closed", "vol. " + t.volume));
        if (t.archived) title.append(el("span", "fm-closed", "archived"));
        else if (t.locked) title.append(el("span", "fm-closed", "closed"));
        else if (t.closing) title.append(el("span", "fm-closed warn", "closing"));
    }
    function topicRow(t, withSection) {
        const fresh = t.unseen || t.new > 0;
        const row = el("a", "fm-row" + (fresh ? "" : " read"));
        row.href = "#/t/" + t.id;
        row.append(plate(t.name, t.kind, t));
        const main = el("div", "fm-row-main");
        const title = el("div", "fm-row-title", t.title);
        tags(title, t);
        main.append(title);
        if (t.excerpt) main.append(el("div", "fm-row-sub", t.excerpt));
        const meta = el("div", "fm-row-meta");
        meta.append(el("i", "", t.name || "SYSTEM"), " · " + ago(t.ago));
        if (withSection) meta.append(" · in ", el("i", "", t.section_title));
        if (t.replies) meta.append(" · last reply " + t.last_name + " " + ago(t.last_ago));
        main.append(meta);
        const side = el("div", "fm-row-side");
        side.append(el("span", "fm-big", String(t.replies)), el("span", "", t.replies === 1 ? "reply" : "replies"));
        if (t.unseen) side.append(el("span", "fm-new", "new"));
        else if (t.new) side.append(el("span", "fm-new", t.new + " new"));
        row.append(main, side);
        return row;
    }
    function list(rows) { const box = el("div", "fm-list"); box.append(...rows); return box; }

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
                const items = el("div", "fm-picker-list");
                if (data.parent) items.append(link("../", () => browse(data.parent)));
                for (const row of data.entries) {
                    items.append(link(row.dir ? row.name + "/" : row.name, () => {
                        if (row.dir) return browse(row.path);
                        if (!chosen.some((file) => file.path === row.path)) chosen.push({ path: row.path, name: row.name });
                        picker.hidden = true;
                        drawChips();
                    }));
                }
                picker.replaceChildren(el("div", "fm-muted", data.path), items);
            } catch (error) { fail(error); picker.hidden = true; }
        }
        wrap.append(add, chips, picker);
        return { node: wrap, paths: () => chosen.map((file) => file.path) };
    }
    function form({ heading, fields, label, send, cancel, inline, files }) {
        const box = el("form", "fm-form" + (inline ? " inline" : ""));
        if (heading) box.append(el("div", "fm-form-title", heading));
        box.append(...fields);
        const attached = files && player ? attachField() : null;
        if (attached) box.append(attached.node);
        const submit = el("button", "app-button primary", label);
        submit.type = "submit";
        const foot = el("div", "fm-form-foot");
        foot.append(submit, button("Cancel", () => cancel(box)), el("span", "fm-hint", "ctrl+enter send · esc cancel"));
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
    function placeForm(made, focus) {
        const box = $("fm-page");
        const old = box.querySelector(":scope > .fm-form");
        if (old) old.remove();
        const hero = box.querySelector(":scope > .fm-hero");
        if (hero) hero.after(made); else box.prepend(made);
        made.scrollIntoView({ block: "nearest" });
        focus.focus();
    }
    function openTopicForm(sectionId, sectionTitle) {
        const title = input("input", "subject", 160, true);
        const text = input("textarea", "what do you want to say?", 4000, true);
        placeForm(form({ heading: "NEW TOPIC IN " + (sectionTitle || "").toUpperCase(), fields: [title, text], label: "Post topic", files: true, cancel: (f) => f.remove(),
            send: async (files) => {
                const topic = await call(urls.newTopicUrl, { section: sectionId, title: title.value, text: text.value, attachments: files });
                location.hash = "#/t/" + topic.id;
            } }), title);
    }
    function openSectionForm(parentId) {
        const title = input("input", "board name", 120, true);
        const about = input("input", "what is it for (optional)", 240, false);
        placeForm(form({ heading: parentId ? "NEW SUB-BOARD" : "NEW BOARD", fields: [title, about], label: "Create board", cancel: (f) => f.remove(),
            send: async () => {
                const section = await call(urls.newSectionUrl, { space: space.slug, parent: parentId, title: title.value, about: about.value });
                await loadSpace(space.slug);
                location.hash = "#/c/" + section.id;
            } }), title);
    }
    async function moderate(url, body) {
        try { await call(url, body); await route(); } catch (error) { fail(error); }
    }

    // ---------- обзор пространства ----------
    async function showSpace(slug) {
        await loadSpace(slug);
        current = "space";
        drawRail();
        drawBar([], "", space.can_create ? [button("+ Board", () => openSectionForm(null))] : []);
        const box = page();
        const nodes = allNodes(space.tree);
        const hero = el("div", "fm-hero");
        hero.append(el("h2", "", space.title));
        if (space.about) { const about = el("div", "fm-about"); about.append(markup(space.about)); hero.append(about); }
        const stats = el("div", "fm-stats");
        const stat = (n, label) => { const s = el("span"); s.append(el("b", "", String(n)), " " + label); return s; };
        const fresh = nodes.reduce((sum, n) => sum + n.new, 0);
        stats.append(stat(nodes.length, nodes.length === 1 ? "board" : "boards"), stat(nodes.reduce((sum, n) => sum + n.topics, 0), "topics"));
        if (fresh) stats.append(stat(fresh, "with new posts"));
        hero.append(stats);
        box.append(hero);

        box.append(cap("BOARDS"));
        if (space.tree.length) box.append(list(space.tree.map(boardRow)));
        else {
            const empty = el("div", "fm-void", "No boards yet.");
            if (space.can_create) empty.append(el("br"), button("+ Create the first board", () => openSectionForm(null), "app-button primary"));
            box.append(empty);
        }
        if (space.recent && space.recent.length) {
            box.append(cap("RECENT ACTIVITY"));
            box.append(list(space.recent.map((t) => topicRow(t, true))));
        }
    }

    // ---------- раздел ----------
    async function showSection(id, archive) {
        const data = await call(slot(urls.sectionUrl, id) + (archive ? "?archive=1" : ""));
        await loadSpace(data.space);
        current = data.id;
        drawRail();
        const actions = [];
        if (data.can_moderate) actions.push(button("Archive", async () => {
            if (!confirm("Archive this board? It leaves the lists; posts are kept.")) return;
            try {
                await call(urls.archiveUrl, { section: data.id });
                location.hash = data.crumbs.length > 1 ? "#/c/" + data.crumbs[data.crumbs.length - 2].id : "#/s/" + space.slug;
            } catch (error) { fail(error); }
        }));
        if (data.can_create) actions.push(button("+ Sub-board", () => openSectionForm(data.id)));
        if (data.can_write) actions.push(button("+ New topic", () => openTopicForm(data.id, data.title), "app-button primary"));
        if (data.archive) {
            drawBar(data.crumbs, "archive", []);
            const box = page();
            const back = el("a", "fm-back", "← back to " + data.title);
            back.href = "#/c/" + data.id;
            const hero = el("div", "fm-hero");
            hero.append(el("h2", "", data.title + " · archive"), el("p", "fm-about", "Closed topics moved here after a while. Read only."));
            box.append(back, hero, cap("ARCHIVED TOPICS"));
            box.append(data.topics.length ? list(data.topics.map((t) => topicRow(t))) : el("div", "fm-void", "The archive is empty."));
            return;
        }
        drawBar(data.crumbs.slice(0, -1), data.title, actions);
        const box = page();
        const hero = el("div", "fm-hero");
        hero.append(el("h2", "", data.title));
        if (data.about) hero.append(el("p", "fm-about", data.about));
        const stats = el("div", "fm-stats");
        const replies = data.topics.reduce((sum, t) => sum + t.replies, 0);
        const fresh = data.topics.filter((t) => t.unseen || t.new).length;
        const stat = (n, label) => { const s = el("span"); s.append(el("b", "", String(n)), " " + label); return s; };
        stats.append(stat(data.topics.length, data.topics.length === 1 ? "topic" : "topics"), stat(replies, replies === 1 ? "reply" : "replies"));
        if (fresh) stats.append(stat(fresh, "with new posts"));
        if (!data.can_write) stats.append(el("span", "", callsign ? "read only" : "sign in to post"));
        hero.append(stats);
        box.append(hero);

        const here = findNode(space.tree, data.id);
        if (here && here.children.length) { box.append(cap("SUB-BOARDS")); box.append(list(here.children.map(boardRow))); }
        const pinned = data.topics.filter((t) => t.pinned);
        const rest = data.topics.filter((t) => !t.pinned);
        if (pinned.length) { box.append(cap("PINNED")); box.append(list(pinned.map((t) => topicRow(t)))); }
        box.append(cap("TOPICS"));
        if (rest.length) box.append(list(rest.map((t) => topicRow(t))));
        else {
            const empty = el("div", "fm-void", "No topics on this board yet.");
            if (data.can_write) empty.append(el("br"), button("+ Start the first topic", () => openTopicForm(data.id, data.title), "app-button primary"));
            box.append(empty);
        }
        if (data.archived) {
            const more = el("a", "fm-archive-link", "Archive · " + plural(data.archived, "topic", "topics") + " →");
            more.href = "#/c/" + data.id + "/archive";
            box.append(more);
        }
    }

    // ---------- тема ----------
    function filesOf(post) {
        const box = el("div", "fm-files");
        for (const file of post.files || []) {
            const row = el("span", "fm-file");
            row.append(el("b", "", file.name), file.size + " B");
            if (player) row.append(link("save to my disk", async () => {
                try { const saved = await call(urls.saveUrl, { attachment: file.id }); notice("saved to " + saved.path); } catch (error) { fail(error); }
            }, "strong"));
            box.append(row);
        }
        return box;
    }
    function textOf(post, moderator) {
        const text = el("div", "fm-text");
        if (post.hidden) {
            text.append(el("p", "fm-gone", "message deleted"));
            if (moderator && post.text) text.append(el("p", "fm-muted", post.text));
            return text;
        }
        text.append(markup(post.text));
        if (post.files && post.files.length) text.append(filesOf(post));
        return text;
    }

    async function showTopic(id) {
        const data = await call(slot(urls.topicUrl, id));
        await loadSpace(data.space);
        current = data.section;
        drawRail();
        const section = data.crumbs[data.crumbs.length - 1];
        drawBar(data.crumbs, "", data.can_reply ? [button("Reply", () => openReply(null), "app-button primary")] : []);
        const box = page();
        const byId = new Map(data.posts.map((p) => [p.id, p]));
        const kids = new Map();
        for (const post of data.posts) { const key = post.parent || 0; if (!kids.has(key)) kids.set(key, []); kids.get(key).push(post); }
        const count = (post) => (kids.get(post.id) || []).reduce((n, child) => n + 1 + count(child), 0);
        const first = data.posts.find((p) => p.root) || data.posts[0];
        const isStarter = (post) => post.starter || (post.kind !== "player" && post.name === first.name && post.kind === first.kind);

        const back = el("a", "fm-back", "← back to " + (section ? section.title : "board"));
        back.href = section ? "#/c/" + section.id : "#/s/" + space.slug;
        box.append(back);

        // первое сообщение: карточка с заголовком, автором, текстом и действиями
        const op = el("article", "fm-op");
        const head = el("header", "fm-op-head");
        const title = el("h2", "", data.title);
        tags(title, data);
        const author = el("div", "fm-author");
        const who = el("div", "fm-who-line");
        const when = el("span", "", ago(first.ago)); when.title = first.at;
        who.append(nameTag(first.name, first.kind), el("span", "fm-badge op", "TS"), when, el("span", "", "in " + (section ? section.title : "")));
        author.append(plate(first.name, first.kind, first), who);
        head.append(title, author);
        if (data.prev || data.next) {
            const vols = el("div", "fm-volumes");
            if (data.prev) { const a = el("a", "", "← volume " + (data.volume - 1)); a.href = "#/t/" + data.prev; vols.append(a); }
            if (data.next) { const a = el("a", "", "volume " + (data.volume + 1) + " →"); a.href = "#/t/" + data.next; vols.append(a); }
            head.append(vols);
        }
        const body = el("div", "fm-op-body");
        body.append(textOf(first, data.can_moderate));
        op.append(head, body);
        const foot = el("footer", "fm-op-foot");
        if (data.can_reply) foot.append(link("reply", () => openReply(null), "strong"));
        if (data.can_moderate) {
            foot.append(link(data.pinned ? "unpin" : "pin", () => moderate(urls.flagsUrl, { topic: data.id, pinned: !data.pinned })),
                        link(data.locked ? "reopen" : "close", () => moderate(urls.flagsUrl, { topic: data.id, locked: !data.locked })),
                        link("delete topic", () => { if (confirm("Delete the whole topic?")) moderate(urls.hideUrl, { post: first.id }); }, "warn"));
        }
        if (foot.children.length) op.append(foot);
        box.append(op);

        if (data.closing) box.append(el("p", "fm-banner", "No recent activity: this topic will be closed unless someone posts."));
        const replies = data.posts.length - 1;
        if (data.compressed) {
            box.append(cap(plural(data.compressed, "RECORD", "RECORDS") + " COMPRESSED"));
            box.append(el("p", "fm-void", "[" + plural(data.compressed, "record", "records") + " compressed] Only the opening post is kept in the archive."));
            return;
        }
        box.append(cap(replies ? plural(replies, "REPLY", "REPLIES") : "NO REPLIES YET"));

        const render = (post, depth, container) => {
            const item = el("div", "fm-c" + (post.new ? " fresh" : "") + (post.useful && !post.hidden ? " useful" : "") + (post.name === callsign && post.kind === "player" ? " mine" : ""));
            item.id = "p" + post.id;
            const main = el("div", "fm-cmain");
            const line = el("div", "fm-who-line");
            const when = el("span", "", ago(post.ago)); when.title = post.at;
            line.append(nameTag(post.name, post.kind));
            if (isStarter(post)) line.append(el("span", "fm-badge op", "TS"));
            if (post.useful) line.append(el("span", "fm-badge useful", "✓ useful"));
            line.append(when);
            const parent = byId.get(post.parent);
            if (depth >= INDENT && parent && !parent.root) {
                const to = el("a", "", "→ " + (parent.name || "SYSTEM"));
                to.href = "#p" + parent.id;
                to.addEventListener("click", (event) => { event.preventDefault(); const target = $("p" + parent.id); if (target) { target.scrollIntoView({ block: "center" }); target.classList.remove("fm-flash"); void target.offsetWidth; target.classList.add("fm-flash"); } });
                line.append(to);
            }
            if (post.new) line.append(el("span", "fm-new", "new"));
            const note = el("span", "fm-folded-note");
            line.append(note);
            const cbox = el("div", "fm-cbox");
            cbox.append(line, textOf(post, data.can_moderate));
            const tools = el("div", "fm-ctools");
            if (data.can_reply && !post.hidden) tools.append(link("reply", () => openReply(post.id, main)));
            if (data.can_mark && !post.hidden && !post.starter && post.kind !== "system") tools.append(link(post.useful ? "unmark useful" : "mark useful", () => moderate(urls.usefulUrl, { post: post.id, on: !post.useful })));
            if (data.can_moderate) tools.append(post.hidden ? link("restore", () => moderate(urls.restoreUrl, { post: post.id }))
                                                            : link("delete", () => moderate(urls.hideUrl, { post: post.id }), "warn"));
            if (tools.children.length) cbox.append(tools);
            main.append(cbox);
            item.append(plate(post.name, post.kind, post), main);
            container.append(item);

            const children = kids.get(post.id) || [];
            if (!children.length) return;
            if (depth + 1 >= INDENT) { children.forEach((child) => render(child, depth + 1, container)); return; }
            const rail = el("button", "fm-line");
            rail.type = "button";
            rail.setAttribute("aria-label", "collapse thread");
            const nest = el("div", "fm-kids");
            item.append(rail, nest);
            children.forEach((child) => render(child, depth + 1, nest));
            const total = count(post);
            const setFold = (folded) => {
                item.classList.toggle("folded", folded);
                note.replaceChildren();
                if (folded) note.append(link("+ " + plural(total, "reply", "replies") + " hidden", () => setFold(false), "strong"));
            };
            rail.addEventListener("click", () => setFold(true));
            if (depth >= FOLD_FROM && total > 3) setFold(true);
        };
        const thread = el("div", "fm-replies");
        (kids.get(first.id) || []).forEach((post) => render(post, 0, thread));
        box.append(thread);

        function openReply(parentId, under) {
            const at = under || box;
            const existing = at.querySelector(":scope > .fm-form");
            if (existing) { existing.querySelector("textarea").focus(); existing.scrollIntoView({ block: "nearest" }); return; }
            const target = parentId ? byId.get(parentId) : null;
            const text = input("textarea", target ? "reply to " + (target.name || "SYSTEM") : "reply to the topic", 4000, true);
            const made = form({ heading: target ? "REPLY TO " + (target.name || "SYSTEM") : "REPLY TO TOPIC", fields: [text], label: "Post reply", files: true, inline: !!parentId,
                cancel: (f) => { f.remove(); if (!parentId) drawReplyBox(); },
                send: async (files) => { await call(urls.newPostUrl, { topic: data.id, parent: parentId, text: text.value, attachments: files }); await route(); } });
            if (parentId) at.append(made);
            else { const stub = box.querySelector(":scope > .fm-replybox"); if (stub) stub.replaceWith(made); else box.append(made); }
            made.scrollIntoView({ block: "nearest" });
            text.focus();
        }
        function drawReplyBox() {
            const stub = el("button", "fm-replybox");
            stub.type = "button";
            stub.append(plate(callsign, "player"), "Write a reply…");
            stub.addEventListener("click", () => openReply(null));
            box.append(stub);
        }
        if (data.can_reply) drawReplyBox();
        else {
            const end = el("p", "fm-void", closedText(data));
            if (data.next) { const a = el("a", "", "Open volume " + (data.volume + 1) + " →"); a.href = "#/t/" + data.next; end.append(el("br"), a); }
            box.append(end);
        }
    }
    function closedText(data) {
        if (data.archived) return "Moved to archive. Read only.";
        if (data.locked && data.closed_reason === "volume") return data.next ? "This volume is full. The thread continues in volume " + (data.volume + 1) + "." : "This volume is full.";
        if (data.locked && data.closed_reason === "idle") return "Closed for inactivity.";
        if (data.locked) return "This topic is closed.";
        return callsign ? "This board is read only." : "Sign in to reply.";
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
            if ((found = hash.match(/^#\/t\/(\d+)$/))) return await showTopic(+found[1]);
            if ((found = hash.match(/^#\/c\/(\d+)(\/archive)?$/))) return await showSection(+found[1], !!found[2]);
            const slug = (found = hash.match(/^#\/s\/([\w-]+)$/)) ? found[1] : spaces[0].slug;
            await showSpace(slug);
        } catch (error) { fail(error); }
    }
    window.addEventListener("hashchange", () => route().then(() => { $("fm-page").parentElement.scrollTop = 0; }));
    start().catch(fail);
})();
