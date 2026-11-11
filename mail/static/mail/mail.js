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

    // круглый спиннер (static/ui/spinner.css), пока данные едут с сервера
    function loading() {
        const box = el("div", "mail-loading");
        const spinner = el("div", "spinner");
        spinner.setAttribute("role", "status");
        spinner.setAttribute("aria-label", "loading");
        box.appendChild(spinner);
        return box;
    }

    // письмо называется своим путём на машине (/var/mail/ivan/inbox/door.msg)
    function url(template, id) {
        return template + "?path=" + encodeURIComponent(id);
    }

    async function postJson(address, body) {
        const response = await fetch(address, {
            method: "POST",
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || String(response.status));
        return data;
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

    // файл машины: сервер решает, открывается ли он (слои), и отдаёт адрес вьювера
    async function openFile(item) {
        const api = desktop();

        try {
            const response = await fetch(item.open, { credentials: "same-origin" });
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                if (api && typeof api.error === "function") {
                    api.error(data.error || "failed");
                } else {
                    notice(data.error || `error ${response.status}`);
                }
                return;
            }

            if (api && typeof api.openApp === "function") {
                api.openApp(data.id, data.title, data.url);
            } else {
                window.open(data.url, "_blank", "noopener");
            }
        } catch (error) {
            notice("could not reach the machine");
        }
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
            make(item.label, () => openFile(item));

            const button = make("save to machine", () => saveAttachment(item, button));
            if (item.saved) {
                button.textContent = `saved to ${item.path}`;
                button.disabled = true;
            }
        } else if (item.kind === "member") {
            make(item.label, () => notice(`attachment ${item.label}: open ${item.path} from the terminal`));
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

        const trash = el("button", "mail-button", data.folder === "trash" ? "restore" : "delete");
        trash.type = "button";
        trash.addEventListener("click", () => moveToTrash(data.id));

        const answer = el("button", "mail-button", "reply");
        answer.type = "button";
        answer.addEventListener("click", () => openComposer("reply", data));

        const forward = el("button", "mail-button", "forward");
        forward.type = "button";
        forward.addEventListener("click", () => openComposer("forward", data));

        if (data.folder === "inbox") bar.append(answer);
        if (data.folder !== "trash") bar.append(forward);
        bar.append(unread, trash);
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
        view.replaceChildren(loading());

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

    // в корзину и обратно: письмо переезжает в другую папку ящика (у других игроков оно на месте)
    async function moveToTrash(id) {
        try {
            await postJson(root.dataset.trashUrl, { path: id });
        } catch (error) {
            notice(error.message === "403" ? "sign in to manage mail" : `delete: ${error.message}`);
            return;
        }
        state.selected = null;
        view.replaceChildren(el("p", "mail-empty", "select a message"));
        root.classList.remove("is-reading");
        await loadMessages();
        renderAll();
    }

    async function markUnread(id) {
        await postJson(root.dataset.unreadUrl, { path: id }).catch(() => null);

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

    /* ---------- письмо игрока: ответ, новое письмо, пересылка ---------- */

    // Игрок не пишет что угодно: он выбирает вариант ответа и набирает его. Целевой текст виден бледным слоем,
    // набранное закрашивается, неверная буква получает красный фон. Секрет ({{...}}) приходит только длиной,
    // выбор слова ([[a|b]]) показан вариантами, пока игрок не начал его набирать. Верность проверяет сервер.
    // Если персонажу ответить нечего (адрес не его или вариантов нет), письмо пишется свободно: его просто отправят.
    const composer = { mode: "", segments: null, typed: "", box: null, input: null, send: null, offers: [], variant: null,
                       attachment: "", reply: "", forward: "", to: "", subject: "" };

    function layout(segments, typedText) {
        const typed = Array.from(typedText);
        const tokens = [];
        let index = 0;
        let mistakes = 0;
        let complete = true;

        function char(expected, hidden) {
            let shown = hidden ? "•" : expected;
            let stateName = "t-ghost";
            if (index < typed.length) {
                shown = typed[index];
                if (hidden) stateName = "t-done t-secret";
                else if (typed[index] === expected) stateName = "t-done";
                else { stateName = "t-wrong"; mistakes += 1; }
            } else {
                complete = false;
            }
            tokens.push({ shown, state: stateName + (index === typed.length ? " t-caret" : "") });
            index += 1;
        }

        segments.forEach(function (seg) {
            if (seg.text !== undefined) {
                Array.from(seg.text).forEach(ch => char(ch, false));
            } else if (seg.hidden !== undefined) {
                for (let n = 0; n < seg.hidden; n++) char("•", true);
            } else {
                const rest = typed.slice(index);
                const options = seg.choices.map(option => Array.from(option));
                const done = options.filter(o => o.length <= rest.length && o.every((c, k) => c === rest[k])).sort((a, b) => b.length - a.length)[0];
                const partial = options.filter(o => rest.length < o.length && rest.every((c, k) => c === o[k]));
                if (!rest.length) {
                    // ещё не начато: варианты слова видны все сразу
                    tokens.push({ choice: seg.choices, state: index === typed.length ? "t-caret" : "" });
                    complete = false;
                    index += Math.max(...options.map(o => o.length));
                } else if (done) {
                    done.forEach(ch => char(ch, false));
                } else if (partial.length) {
                    partial[0].forEach(ch => char(ch, false));
                    const others = seg.choices.filter(option => option !== partial[0].join(""));
                    if (others.length) tokens.push({ hint: others });
                } else {
                    options[0].forEach(ch => char(ch, false));
                }
            }
        });
        if (typed.length > index) {
            mistakes += typed.length - index;
            typed.slice(index).forEach(ch => tokens.push({ shown: ch, state: "t-wrong" }));
        }
        return { tokens, mistakes, complete: complete && mistakes === 0 && typed.length >= index };
    }

    function paintTyping() {
        if (!composer.segments) {
            composer.send.disabled = !composer.typed.trim();
            return;
        }
        const plan = layout(composer.segments, composer.typed);
        composer.box.replaceChildren();
        plan.tokens.forEach(function (token) {
            if (token.choice) {
                const chip = el("span", "t-choice " + token.state, token.choice.join(" / "));
                composer.box.appendChild(chip);
            } else if (token.hint) {
                composer.box.appendChild(el("span", "t-hint", " (или " + token.hint.join(", ") + ")"));
            } else {
                const isBreak = token.shown === "\n";
                composer.box.appendChild(el("span", "t-char " + token.state, isBreak ? "↵" : token.shown));
                if (isBreak) composer.box.appendChild(document.createElement("br"));
            }
        });
        composer.send.disabled = !(plan.complete && (!composer.variant || !composer.variant.attach || composer.attachment));
    }

    function closeComposer() {
        composer.mode = "";
        view.replaceChildren(el("p", "mail-empty", "select a message"));
        reader.querySelectorAll(".mail-toolbar").forEach(node => node.remove());
        root.classList.remove("is-reading");
    }

    function runEffects(effects) {
        const api = desktop();
        (effects || []).forEach(async function (effect) {
            if (effect.op === "open" && api && api.openApp) {
                api.openApp(effect.id, effect.title, effect.url);
            } else if (effect.op === "alert" && api && api.error) {
                for (let i = 0; i < effect.count; i++) {
                    api.error(effect.message, { object: `0x${(4096 + Math.floor(Math.random() * 61000)).toString(16)}` }, { stack: true });
                    await new Promise(resolve => setTimeout(resolve, effect.gap * (0.6 + Math.random() * 0.8)));
                }
            }
        });
    }

    const RESULT = {
        ok: "message sent", sent: "message sent", wrong: "message sent", exhausted: "message sent",
        bounced: "message returned: recipient unknown"
    };

    async function sendComposed() {
        composer.send.disabled = true;
        const body = {
            to: composer.to, subject: composer.subject, text: composer.typed, variant: composer.variant ? composer.variant.id : null,
            attachment: composer.attachment, reply: composer.reply, forward: composer.forward
        };
        try {
            const data = await postJson(root.dataset.sendUrl, body);
            notice(RESULT[data.kind] || "message sent");
            runEffects(data.effects);
            closeComposer();
            await loadMessages();
            renderAll();
        } catch (error) {
            notice(`send: ${error.message}`);
            paintTyping();
        }
    }

    // выбор файла для вложения: папки машины, которые игрок вправе читать
    async function pickAttachment(target, path) {
        let data;
        try {
            data = await getJson(root.dataset.filesUrl + (path ? "?path=" + encodeURIComponent(path) : ""));
        } catch (error) {
            notice("could not list files");
            return;
        }
        const list = el("ul", "picker");
        list.appendChild(el("li", "picker-path", data.path));
        if (data.parent) {
            const up = el("button", "picker-row", "..");
            up.type = "button";
            up.addEventListener("click", () => pickAttachment(target, data.parent));
            list.appendChild(el("li")).appendChild(up);
        }
        data.entries.forEach(function (entry) {
            const row = el("button", "picker-row" + (entry.dir ? " is-dir" : ""), entry.dir ? entry.name + "/" : entry.name);
            row.type = "button";
            row.addEventListener("click", function () {
                if (entry.dir) return pickAttachment(target, entry.path);
                composer.attachment = entry.path;
                target.replaceChildren(el("span", "picked", "attached: " + entry.path));
                paintTyping();
            });
            list.appendChild(el("li")).appendChild(row);
        });
        target.replaceChildren(list);
    }

    function chooseVariant(offer, area) {
        composer.variant = offer;
        composer.segments = offer.segments.length ? offer.segments : [];
        composer.typed = "";
        composer.attachment = "";
        area.replaceChildren();

        const wrap = el("div", "typing");
        const box = el("div", "typing-text");
        const input = el("textarea", "typing-input");
        input.setAttribute("aria-label", "type the message");
        input.spellcheck = false;
        input.autocomplete = "off";
        wrap.append(box, input);
        area.appendChild(wrap);
        Object.assign(composer, { box, input });

        if (offer.attach) {
            const files = el("div", "attach");
            const button = el("button", "mail-button", "attach a file");
            button.type = "button";
            button.addEventListener("click", () => pickAttachment(files));
            files.appendChild(button);
            area.appendChild(files);
        }

        input.addEventListener("input", function () {
            composer.typed = input.value.replace(/\r\n/g, "\n").slice(0, 4000);
            if (input.value !== composer.typed) input.value = composer.typed;
            paintTyping();
        });
        ["paste", "drop"].forEach(name => input.addEventListener(name, event => event.preventDefault()));
        wrap.addEventListener("click", () => input.focus());
        paintTyping();
        input.focus();
    }

    function freeText(area) {
        composer.variant = null;
        composer.segments = null;
        composer.typed = "";
        const input = el("textarea", "free-input");
        input.setAttribute("aria-label", "message");
        input.rows = 6;
        input.addEventListener("input", function () {
            composer.typed = input.value.slice(0, 4000);
            paintTyping();
        });
        area.replaceChildren(input);
        composer.input = input;
        paintTyping();
    }

    function renderOffers(data, place) {
        const area = el("div", "compose-area");
        place.replaceChildren();
        composer.offers = data.offers;
        if (data.offers.length) {
            const list = el("ul", "offers");
            data.offers.forEach(function (offer) {
                const button = el("button", "offer" + (offer.open ? "" : " is-closed"), offer.title);
                button.type = "button";
                button.disabled = !offer.open;
                if (!offer.open) button.title = "not available yet";
                button.addEventListener("click", function () {
                    list.querySelectorAll(".offer").forEach(node => node.classList.remove("is-chosen"));
                    button.classList.add("is-chosen");
                    chooseVariant(offer, area);
                });
                list.appendChild(el("li")).appendChild(button);
            });
            place.append(el("p", "compose-note", "choose what to answer"), list, area);
        } else {
            place.append(el("p", "compose-note", data.persona ? "nothing to answer for now" : "write your message"), area);
            if (!data.persona || composer.mode === "new") freeText(area);
        }
    }

    async function loadOffers(place) {
        const params = new URLSearchParams();
        if (composer.reply) params.set("reply", composer.reply);
        if (composer.forward) params.set("forward", composer.forward);
        if (composer.to) params.set("to", composer.to);
        try {
            const data = await getJson(root.dataset.composeUrl + "?" + params.toString());
            if (!composer.to) composer.to = data.to;
            if (data.subject && !composer.subject) composer.subject = data.subject;
            renderOffers(data, place);
            return data;
        } catch (error) {
            notice(error.message === "403" ? "sign in to send mail" : "could not prepare the message");
            return null;
        }
    }

    // mode: reply (на письмо), forward (переслать письмо), new (новое письмо)
    async function openComposer(mode, letter) {
        Object.assign(composer, { mode, reply: mode === "reply" ? letter.id : "", forward: mode === "forward" ? letter.id : "",
                                  to: mode === "reply" ? letter.from : "", subject: "", variant: null, segments: null, typed: "", attachment: "" });

        const bar = el("div", "mail-toolbar");
        const cancel = el("button", "mail-button", "cancel");
        cancel.type = "button";
        cancel.addEventListener("click", closeComposer);
        bar.appendChild(cancel);
        reader.querySelectorAll(".mail-toolbar").forEach(node => node.remove());
        reader.appendChild(bar);

        const fields = el("dl", "mail-fields");
        const toField = el("dd");
        const subjectField = el("dd");
        fields.append(el("dt", "", "from"), el("dd", "", document.getElementById("mail-address").textContent),
                      el("dt", "", "to"), toField, el("dt", "", "subject"), subjectField);

        const place = el("div", "compose-place");
        const send = el("button", "mail-button", "send");
        send.type = "button";
        send.disabled = true;
        send.addEventListener("click", sendComposed);
        composer.send = send;

        view.replaceChildren(el("h2", "mail-title", mode === "new" ? "new message" : mode === "forward" ? "forward" : "reply"), fields, place,
                             el("div", "mail-actions"));
        view.lastChild.appendChild(send);
        root.classList.add("is-reading");

        if (mode === "reply") {
            toField.textContent = letter.from;
            const data = await loadOffers(place);
            subjectField.textContent = composer.subject || (data && data.subject) || "";
            return;
        }
        // новое письмо и пересылка: адрес вводит игрок, варианты появляются для найденного адреса
        const to = el("input", "compose-input");
        to.placeholder = "address@host";
        to.setAttribute("aria-label", "recipient");
        toField.appendChild(to);
        if (mode === "new") {
            const subject = el("input", "compose-input");
            subject.setAttribute("aria-label", "subject");
            subject.addEventListener("input", () => (composer.subject = subject.value));
            subjectField.appendChild(subject);
        } else {
            subjectField.textContent = "Fwd: " + letter.subject;
            composer.subject = "Fwd: " + letter.subject;
        }
        // варианты перечитываются, только если адрес правда сменился: уход фокуса с поля тоже шлёт change
        let checked = "";
        const check = async function () {
            composer.to = to.value.trim();
            if (!composer.to.includes("@") || composer.to === checked) return;
            checked = composer.to;
            await loadOffers(place);
        };
        to.addEventListener("change", check);
        to.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); check(); } });
        place.appendChild(el("p", "compose-note", "type the address and press Enter"));
        to.focus();
    }

    function compose() {
        openComposer("new", null);
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

    list.replaceChildren(loading());

    loadMessages()
        .then(function () {
            renderAll();

            // письмо, открытое из терминала (cnt) или с рабочего стола, сразу на экране
            if (root.dataset.file) {
                open(root.dataset.file);
                return;
            }
            const shown = visible();
            const first = shown.find(m => m.unread) || shown[0];
            if (first && window.matchMedia("(min-width: 761px)").matches) open(first.id);
        })
        .catch(function () {
            list.replaceChildren(el("li", "mail-empty", "inbox unavailable"));
        });
})();
