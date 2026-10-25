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
            api.openApp("mail-" + item.open, item.label, item.open);
        } else {
            window.open(item.open, "_blank", "noopener");
        }
    }

    // скачивание на ПК: заголовок ответа велит браузеру сохранить файл, а не показывать
    function downloadAttachment(item) {
        const link = document.createElement("a");
        link.href = item.download;
        link.rel = "noopener";
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    async function saveAttachment(item, button) {
        try {
            const response = await fetch(item.save, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-CSRFToken": csrf() }
            });
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                notice(data.error || `error ${response.status}`);
                return;
            }

            item.saved = true;
            button.textContent = `saved to ${data.path}`;
            button.disabled = true;
        } catch (error) {
            notice("could not reach the machine");
        }
    }

    function attachmentButtons(item) {
        const buttons = [];

        function make(text, action) {
            const button = el("button", "mail-button", text);
            button.type = "button";
            button.addEventListener("click", () => action(button));
            buttons.push(button);
            return button;
        }

        if (item.kind === "asset") {
            make(item.label, () => openAttachment(item));
            make("download", () => downloadAttachment(item));
        } else if (item.kind === "file") {
            const button = make(`${item.label}  ·  save to machine`, () => saveAttachment(item, button));
            if (item.saved) {
                button.textContent = `saved to ${item.path}`;
                button.disabled = true;
            }
        } else {
            make(item.label, () => openAttachment(item));
        }

        return buttons;
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
            folderRow("sent", "", "sent", inFolderCount("sent")),
            folderRow("trash", "", "trash", inFolderCount("trash"))
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


        renderBody(view, data.body);

        if (data.attachments.length) {
            const files = el("div", "mail-files");
            data.attachments.forEach(function (item) {
                attachmentButtons(item).forEach(button => files.appendChild(button));
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

    // строка состояния: короткое сообщение вместо подсказки клавиш
    function notice(text) {
        hint.textContent = text;
        status.classList.add("is-warning");
        clearTimeout(hintTimer);
        hintTimer = setTimeout(function () {
            hint.textContent = HINT;
            status.classList.remove("is-warning");
        }, 3500);
    }

    /* ---------- набор письма «от чужого имени» ---------- */

    // Целевой текст виден бледным слоем, набранное закрашивается, неверная буква получает красный фон.
    // Скрытые части ({{...}}) приходят только числом символов: про них браузер ничего не знает,
    // верность проверяет сервер при отправке.
    const composer = { task: null, typed: "", box: null, input: null, send: null };

    function totalLength(task) {
        return task.segments.reduce((sum, seg) => sum + (seg.text !== undefined ? Array.from(seg.text).length : seg.hidden), 0);
    }

    function typingChar(shown, state) {
        const node = el("span", "t-char " + state, shown);
        return node;
    }

    function paintTyping() {
        const task = composer.task;
        const typed = Array.from(composer.typed);
        let index = 0;
        let mistakes = 0;

        composer.box.replaceChildren();

        function put(expected, hidden) {
            const entered = index < typed.length;
            let state = "t-ghost";
            let shown = hidden ? "•" : expected;

            if (entered) {
                shown = typed[index];
                if (hidden) state = "t-done t-secret";
                else if (typed[index] === expected) state = "t-done";
                else {
                    state = "t-wrong";
                    mistakes += 1;
                }
            }

            if (index === typed.length) state += " t-caret";

            const isBreak = shown === "\n";
            composer.box.appendChild(typingChar(isBreak ? "↵" : shown, state));
            if (isBreak) composer.box.appendChild(document.createElement("br"));
            index += 1;
        }

        task.segments.forEach(function (seg) {
            if (seg.text !== undefined) Array.from(seg.text).forEach(ch => put(ch, false));
            else for (let n = 0; n < seg.hidden; n++) put("•", true);
        });

        composer.send.disabled = !(typed.length === totalLength(task) && mistakes === 0);
        composer.mistakes = mistakes;
    }

    function closeComposer() {
        composer.task = null;
        view.replaceChildren(el("p", "mail-empty", "select a message"));
        reader.querySelectorAll(".mail-toolbar").forEach(node => node.remove());
        root.classList.remove("is-reading");
    }

    async function sendComposed() {
        composer.send.disabled = true;

        try {
            const response = await fetch(composer.task.sendUrl, {
                method: "POST",
                credentials: "same-origin",
                headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" },
                body: JSON.stringify({ text: composer.typed })
            });
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                const left = data.attempts_left;
                notice((data.error || `error ${response.status}`) + (left === undefined || left === null ? "" : `  ·  ${left} attempts left`));
                paintTyping();
                return;
            }

            notice("message sent");
            closeComposer();
            await loadMessages();
            state.folder = { type: "sent", value: "" };
            renderAll();
        } catch (error) {
            notice("could not reach the machine");
            paintTyping();
        }
    }

    function openComposer(task, from) {
        const bar = el("div", "mail-toolbar");
        const cancel = el("button", "mail-button", "cancel");
        cancel.type = "button";
        cancel.addEventListener("click", closeComposer);
        bar.appendChild(cancel);
        reader.querySelectorAll(".mail-toolbar").forEach(node => node.remove());
        reader.appendChild(bar);

        const fields = el("dl", "mail-fields");
        [["from", from], ["to", task.to], ["subject", task.subject || "(no subject)"]].forEach(function (pair) {
            fields.append(el("dt", "", pair[0]), el("dd", "", pair[1]));
        });

        const wrap = el("div", "typing");
        const box = el("div", "typing-text");
        const input = el("textarea", "typing-input");
        input.setAttribute("aria-label", "type the message");
        input.spellcheck = false;
        input.autocomplete = "off";
        wrap.append(box, input);

        const send = el("button", "mail-button", "send");
        send.type = "button";
        send.disabled = true;
        send.addEventListener("click", sendComposed);

        view.replaceChildren(fields, wrap, el("div", "mail-actions"));
        view.lastChild.appendChild(send);

        Object.assign(composer, { task, typed: "", box, input, send });

        input.addEventListener("input", function () {
            composer.typed = Array.from(input.value.replace(/\r\n/g, "\n")).slice(0, totalLength(task)).join("");
            if (input.value !== composer.typed) input.value = composer.typed;
            paintTyping();
        });
        ["paste", "drop"].forEach(name => input.addEventListener(name, event => event.preventDefault()));
        wrap.addEventListener("click", () => input.focus());

        root.classList.add("is-reading");
        paintTyping();
        input.focus();
    }

    async function compose() {
        try {
            const response = await fetch(root.dataset.tasksUrl, { credentials: "same-origin" });
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                notice(data.error ? `compose: ${data.error}` : `error ${response.status}`);
                return;
            }

            if (!data.tasks.length) {
                notice("nothing to send from this mailbox");
                return;
            }

            const task = data.tasks[0];
            task.sendUrl = url(root.dataset.sendUrl, task.id);
            openComposer(task, data.from);
        } catch (error) {
            notice("could not reach the machine");
        }
    }

    document.getElementById("mail-compose").addEventListener("click", compose);


    /* ---------- клавиши ---------- */

    document.addEventListener("keydown", function (event) {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (document.activeElement && document.activeElement.tagName === "TEXTAREA") {
            if (event.key === "Escape") closeComposer();
            return;
        }

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

    async function loadMessages() {
        const data = await getJson(root.dataset.listUrl);
        state.messages = data.messages;
        if (data.address) document.getElementById("mail-address").textContent = data.address;
    }

    loadMessages()
        .then(function () {
            renderAll();

            const shown = visible();
            const first = shown.find(m => m.unread) || shown[0];
            if (first && window.matchMedia("(min-width: 761px)").matches) open(first.id);
        })
        .catch(function () {
            list.appendChild(el("li", "mail-empty", "inbox unavailable"));
        });
})();
