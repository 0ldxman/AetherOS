/* ==================================================
   INTERCOM: список писем и чтение. Всё, что пришло с сервера, попадает на
   страницу через textContent, письма не могут внести разметку.
   ================================================== */

(function () {
    "use strict";

    const root = document.getElementById("mail");
    const list = document.getElementById("mail-list");
    const view = document.getElementById("mail-view");
    const count = document.getElementById("mail-count");
    const state = { messages: [], selected: null };

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


    /* ---------- список ---------- */

    function updateCount() {
        const unread = state.messages.filter(m => m.unread).length;
        count.textContent = `${state.messages.length} messages  ·  ${unread} unread`;
    }

    function renderList() {
        list.replaceChildren();

        if (!state.messages.length) {
            list.appendChild(el("li", "mail-meta", "no messages"));
        }

        state.messages.forEach(function (message) {
            const item = el("li");
            const row = el("button", "mail-row" + (message.unread ? " is-unread" : ""));

            row.type = "button";
            row.dataset.id = message.id;
            row.setAttribute("role", "option");
            row.setAttribute("aria-selected", String(message.id === state.selected));
            row.append(
                el("span", "mail-from", message.sender),
                el("span", "mail-subject", message.subject),
                el("span", "mail-meta", message.when + (message.attachments ? `  ·  ${message.attachments} attached` : "")),
                el("span", "mail-preview", message.preview)
            );
            row.addEventListener("click", () => open(message.id));

            item.appendChild(row);
            list.appendChild(item);
        });

        updateCount();
    }


    /* ---------- письмо ---------- */

    function renderMessage(data) {
        view.replaceChildren();

        const back = el("button", "mail-action mail-back", "‹ inbox");
        back.type = "button";
        back.addEventListener("click", () => root.classList.remove("is-reading"));

        const head = el("header", "mail-head");
        head.appendChild(el("h2", "", data.subject));

        const fields = el("dl");
        [["from", data.from], ["to", data.to], ["date", data.when]].forEach(function (pair) {
            fields.append(el("dt", "", pair[0]), el("dd", "", pair[1]));
        });
        head.appendChild(fields);

        const body = el("div", "mail-body", data.body);
        view.append(back, head, body);

        if (data.attachments.length) {
            const files = el("div", "mail-attachments");
            data.attachments.forEach(function (item) {
                const button = el("button", "mail-attachment", "+ " + item.label);
                button.type = "button";
                button.addEventListener("click", () => openAttachment(item));
                files.appendChild(button);
            });
            view.appendChild(files);
        }

        const actions = el("div", "mail-actions");
        const unread = el("button", "mail-action", "mark unread");
        unread.type = "button";
        unread.addEventListener("click", () => markUnread(data.id));
        actions.appendChild(unread);
        view.appendChild(actions);

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
            view.replaceChildren(el("p", "", "message not found"));
        }

        renderList();
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
        renderList();
    }


    /* ---------- клавиши ---------- */

    document.addEventListener("keydown", function (event) {
        if (event.ctrlKey || event.metaKey || event.altKey) return;

        const ids = state.messages.map(m => m.id);
        const index = ids.indexOf(state.selected);

        if (event.key === "ArrowDown" || event.key === "j") {
            event.preventDefault();
            open(ids[Math.min(ids.length - 1, index + 1)]);
        } else if (event.key === "ArrowUp" || event.key === "k") {
            event.preventDefault();
            open(ids[Math.max(0, index - 1)]);
        } else if (event.key === "u" && state.selected !== null) {
            markUnread(state.selected);
        } else if (event.key === "Escape") {
            root.classList.remove("is-reading");
        }
    });


    /* ---------- старт ---------- */

    getJson(root.dataset.listUrl)
        .then(function (data) {
            state.messages = data.messages;
            renderList();

            const first = state.messages.find(m => m.unread) || state.messages[0];
            if (first && window.matchMedia("(min-width: 721px)").matches) open(first.id);
        })
        .catch(function () {
            list.appendChild(el("li", "mail-meta", "inbox unavailable"));
        });
})();
