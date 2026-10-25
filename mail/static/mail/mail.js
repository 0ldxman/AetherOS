/* ==================================================
   INTERCOM: почта узла. Папки и метки слева, карточки писем в
   середине, письмо справа. Всё, что пришло с сервера, попадает на страницу
   через textContent (в том числе текст писем): разметку внести нельзя.
   ================================================== */

(function () {
    "use strict";

    const root = document.getElementById("mail");
    const list = document.getElementById("mail-list");
    const view = document.getElementById("mail-view");
    const reader = document.getElementById("mail-reader");
    const folders = document.getElementById("mail-folders");
    const labels = document.getElementById("mail-labels");
    const folderTitle = document.getElementById("mail-folder-title");
    const count = document.getElementById("mail-count");
    const hint = document.getElementById("mail-hint");
    const status = document.getElementById("mail-status");
    const HINT = hint.textContent;

    const state = { messages: [], selected: null, folder: { type: "inbox", value: "" } };

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    }

    function url(template, id) {
        return template.replace("/0/", "/" + id + "/");
    }

    function csrf() {
        const input = document.querySelector("input[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    async function getJson(address) {
        const response = await fetch(address, { credentials: "same-origin" });
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
    }

    function desktop() {
        try {
            return window.parent && window.parent.desktopAPI;
        } catch (error) {
            return null;
        }
    }

    function openAttachment(item) {
        const api = desktop();
        if (api && typeof api.openApp === "function") {
            api.openApp("mail-" + item.url, item.label, item.url);
        } else {
            window.open(item.url, "_blank", "noopener");
        }
    }


    /* ---------- простая разметка письма: # заголовки, - списки, > цитаты, **жирный**, *курсив*, `код` ---------- */

    function inline(parent, text) {
        const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
        let last = 0;
        let match;

        while ((match = pattern.exec(text)) !== null) {
            if (match.index > last) parent.appendChild(document.createTextNode(text.slice(last, match.index)));

            const token = match[0];
            if (token.startsWith("**")) parent.appendChild(el("span", "md-strong", token.slice(2, -2)));
            else if (token.startsWith("`")) parent.appendChild(el("span", "md-code", token.slice(1, -1)));
            else parent.appendChild(el("span", "md-em", token.slice(1, -1)));

            last = match.index + token.length;
        }

        if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
    }

    function block(parent, tag, className, lines) {
        const node = el(tag, className);
        if (tag === "ul") {
            lines.forEach(function (line) {
                const item = el("li");
                inline(item, line);
                node.appendChild(item);
            });
        } else {
            inline(node, lines.join("\n"));
        }
        parent.appendChild(node);
    }

    function renderBody(parent, text) {
        const lines = text.replace(/\r/g, "").split("\n");
        let group = null;   // {kind, lines}

        function flush() {
            if (!group) return;
            if (group.kind === "list") block(parent, "ul", "md-list", group.lines);
            else if (group.kind === "quote") block(parent, "blockquote", "md-quote", group.lines);
            else block(parent, "p", "md-p", group.lines);
            group = null;
        }

        function add(kind, line) {
            if (!group || group.kind !== kind) {
                flush();
                group = { kind, lines: [] };
            }
            group.lines.push(line);
        }

        lines.forEach(function (line) {
            const heading = /^(#{1,3})\s+(.*)$/.exec(line);

            if (!line.trim()) flush();
            else if (heading) {
                flush();
                block(parent, "p", "md-h" + heading[1].length, [heading[2]]);
            } else if (/^[-*]\s+/.test(line)) add("list", line.replace(/^[-*]\s+/, ""));
            else if (/^>\s?/.test(line)) add("quote", line.replace(/^>\s?/, ""));
            else add("p", line);
        });

        flush();
    }


    /* ---------- папки и метки ---------- */

    function inFolder(message) {
        const folder = state.folder;
        if (folder.type === "label") return message.label === folder.value;
        if (folder.type === "unread") return message.folder === "inbox" && message.unread;
        return message.folder === folder.type;
    }

    function inFolderCount(name) {
        return state.messages.filter(m => m.folder === name).length;
    }

    function visible() {
        return state.messages.filter(inFolder);
    }

    function folderRow(type, value, title, number) {
        const item = el("li");
        const button = el("button", "folder");
        const selected = state.folder.type === type && state.folder.value === value;

        button.type = "button";
        button.setAttribute("role", "option");
        button.setAttribute("aria-selected", String(selected));
        button.append(el("span", "", title), el("span", "folder-count", String(number)));
        button.addEventListener("click", function () {
            state.folder = { type, value };
            renderAll();
        });

        item.appendChild(button);
        return item;
    }

    function renderFolders() {
        const unread = state.messages.filter(m => m.unread).length;
        folders.replaceChildren(
            folderRow("inbox", "", "inbox", inFolderCount("inbox")),
            folderRow("unread", "", "unread", unread),
            folderRow("drafts", "", "drafts", inFolderCount("drafts")),
            folderRow("sent", "", "sent", inFolderCount("sent"))
        );

        const counts = {};
        state.messages.forEach(function (message) {
            if (message.label) counts[message.label] = (counts[message.label] || 0) + 1;
        });

        labels.replaceChildren(
            ...Object.keys(counts).sort().map(name => folderRow("label", name, name, counts[name]))
        );

        const folder = state.folder;
        folderTitle.textContent = folder.type === "label" ? folder.value : folder.type;
    }


    /* ---------- карточки ---------- */

    function renderCards() {
        list.replaceChildren();
        const shown = visible();

        if (!shown.length) {
            list.appendChild(el("li", "mail-empty", "no messages"));
        }

        shown.forEach(function (message) {
            const item = el("li");
            const card = el("button", "card" + (message.unread ? " is-unread" : ""));

            card.type = "button";
            card.dataset.id = message.id;
            card.setAttribute("aria-selected", String(message.id === state.selected));
            card.append(
                el("span", "card-from", message.sender),
                el("span", "card-subject", message.subject),
                el("span", "card-body", message.preview),
                el("span", "card-date", message.when)
            );

            if (message.label) card.appendChild(el("span", "card-label tone-" + message.tone, message.label));

            card.addEventListener("click", () => open(message.id));
            item.appendChild(card);
            list.appendChild(item);
        });
    }

    function renderStatus() {
        const unread = state.messages.filter(m => m.unread).length;
        count.textContent = `${visible().length} of ${state.messages.length}  ·  ${unread} unread`;
    }

    function renderAll() {
        renderFolders();
        renderCards();
        renderStatus();
    }


    /* ---------- письмо ---------- */

    function toolbar(data) {
        reader.querySelectorAll(".mail-toolbar").forEach(node => node.remove());

        const bar = el("div", "mail-toolbar");
        const back = el("button", "mail-button mail-back", "‹ inbox");
        back.type = "button";
        back.addEventListener("click", () => root.classList.remove("is-reading"));

        const unread = el("button", "mail-button", "mark unread");
        unread.type = "button";
        unread.addEventListener("click", () => markUnread(data.id));

        bar.append(unread);
        reader.appendChild(bar);
        return back;
    }

    function renderMessage(data) {
        const back = toolbar(data);
        view.replaceChildren(back);

        view.appendChild(el("h2", "mail-title", data.subject));

        const fields = el("dl", "mail-fields");
        [["from", data.from], ["to", data.to], ["date", data.when]].forEach(function (pair) {
            fields.append(el("dt", "", pair[0]), el("dd", "", pair[1]));
        });
        view.appendChild(fields);

        if (data.note) view.appendChild(el("p", "mail-note", data.note));

        renderBody(view, data.body);

        if (data.attachments.length) {
            const files = el("div", "mail-files");
            data.attachments.forEach(function (item) {
                const button = el("button", "mail-button", item.label);
                button.type = "button";
                button.addEventListener("click", () => openAttachment(item));
                files.appendChild(button);
            });
            view.appendChild(files);
        }

        view.scrollTop = 0;
    }

    async function open(id) {
        state.selected = id;

        try {
            const data = await getJson(url(root.dataset.messageUrl, id));
            const row = state.messages.find(m => m.id === id);
            if (row) row.unread = false;
            renderMessage(data);
            root.classList.add("is-reading");
        } catch (error) {
            view.replaceChildren(el("p", "mail-empty", "message not found"));
        }

        renderAll();
    }

    async function markUnread(id) {
        await fetch(url(root.dataset.unreadUrl, id), {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrf() }
        });

        const row = state.messages.find(m => m.id === id);
        if (row) row.unread = true;
        root.classList.remove("is-reading");
        renderAll();
    }


    /* ---------- «compose»: узел не может отправлять, пока молчит центр ---------- */

    let hintTimer = null;

    function compose() {
        hint.textContent = "transmit: core unreachable, outgoing mail is disabled";
        status.classList.add("is-warning");
        clearTimeout(hintTimer);
        hintTimer = setTimeout(function () {
            hint.textContent = HINT;
            status.classList.remove("is-warning");
        }, 3500);
    }

    document.getElementById("mail-compose").addEventListener("click", compose);


    /* ---------- клавиши ---------- */

    document.addEventListener("keydown", function (event) {
        if (event.ctrlKey || event.metaKey || event.altKey) return;

        const ids = visible().map(m => m.id);
        const index = ids.indexOf(state.selected);

        if (event.key === "ArrowDown" || event.key === "j") {
            event.preventDefault();
            if (ids.length) open(ids[Math.min(ids.length - 1, index + 1)]);
        } else if (event.key === "ArrowUp" || event.key === "k") {
            event.preventDefault();
            if (ids.length) open(ids[Math.max(0, index - 1)]);
        } else if (event.key === "u" && state.selected !== null) {
            markUnread(state.selected);
        } else if (event.key === "c") {
            compose();
        } else if (event.key === "Escape") {
            root.classList.remove("is-reading");
        }
    });


    /* ---------- старт ---------- */

    getJson(root.dataset.listUrl)
        .then(function (data) {
            state.messages = data.messages;
            if (data.address) document.getElementById("mail-address").textContent = data.address;
            renderAll();

            const shown = visible();
            const first = shown.find(m => m.unread) || shown[0];
            if (first && window.matchMedia("(min-width: 761px)").matches) open(first.id);
        })
        .catch(function () {
            list.appendChild(el("li", "mail-empty", "inbox unavailable"));
        });
})();
