// Поддержка у игрока: свои обращения слева, переписка или новое обращение справа. Вложения: до N файлов, картинки видны сразу.
(function () {
    "use strict";
    const { el, csrf, notice, size } = window.apps;
    const root = document.getElementById("support");
    const list = document.getElementById("support-list");
    const view = document.getElementById("support-view");
    const title = document.getElementById("support-title");
    const base = root.dataset.baseUrl;
    const maxFiles = +root.dataset.maxFiles;
    const maxSize = +root.dataset.maxSize;
    const STATUS = { new: "sent", open: "in progress", waiting: "answered", closed: "closed" };
    const TONE = { new: "", open: "accent", waiting: "ok", closed: "" };
    const CATEGORY = { bug: "bug", stuck: "stuck", other: "other" };
    let tickets = [];
    let current = null;

    if (root.dataset.guest) {
        document.getElementById("support-new").hidden = true;
        view.replaceChildren(el("p", "empty", "Sign in with your account to contact support."));
        return;
    }

    async function getJson(url) {
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) throw new Error(String(response.status));
        return response.json();
    }

    async function loadList() {
        try {
            tickets = (await getJson(base + "api/tickets/")).tickets;
        } catch (e) {
            return notice("support: could not load");
        }
        list.replaceChildren(...tickets.map((t) => {
            const card = el("li", "card" + (t.unread ? " unread" : "") + (current === t.id ? " selected" : ""));
            card.tabIndex = 0;
            const head = el("div", "card-head");
            head.append(el("span", "card-title", t.subject), el("span", "tag " + (TONE[t.status] || ""), STATUS[t.status] || t.status));
            card.append(head, el("span", "card-meta", "#" + t.id + " · " + (CATEGORY[t.category] || t.category) + " · " + t.when));
            card.addEventListener("click", () => openTicket(t.id));
            card.addEventListener("keydown", (e) => { if (e.key === "Enter") openTicket(t.id); });
            return card;
        }));
        if (!tickets.length) list.replaceChildren(el("li", "empty", "no requests yet"));
        const unread = tickets.filter((t) => t.unread).length;
        document.getElementById("support-count").textContent = unread ? unread + " new answers" : tickets.length + " requests";
    }

    // выбор файлов: чипы с размером и крестиком, проверка числа и размера до отправки
    function filePicker() {
        const picked = [];
        const input = el("input");
        input.type = "file";
        input.multiple = true;
        input.hidden = true;
        const chips = el("div", "picked");
        const button = el("button", "app-button", "attach files");
        button.type = "button";
        button.addEventListener("click", () => input.click());
        function draw() {
            chips.replaceChildren(...picked.map((file, i) => {
                const chip = el("span", "file", file.name + " · " + size(file.size));
                const x = el("button", "", "✕");
                x.type = "button";
                x.setAttribute("aria-label", "remove " + file.name);
                x.addEventListener("click", () => { picked.splice(i, 1); draw(); });
                chip.append(x);
                return chip;
            }));
            button.disabled = picked.length >= maxFiles;
        }
        input.addEventListener("change", () => {
            for (const file of input.files) {
                if (picked.length >= maxFiles) { notice("up to " + maxFiles + " files"); break; }
                if (file.size > maxSize) { notice(file.name + " is larger than " + size(maxSize)); continue; }
                picked.push(file);
            }
            input.value = "";
            draw();
        });
        const box = el("div", "row");
        box.append(button, input, chips);
        return { box, files: () => picked };
    }

    function showFiles(files) {
        const box = el("div", "files");
        for (const f of files) {
            if (f.image) {
                const img = el("img");
                img.src = f.url;
                img.alt = f.name;
                img.loading = "lazy";
                img.addEventListener("click", () => {
                    const shade = el("div", "lightbox");
                    const big = el("img");
                    big.src = f.url;
                    big.alt = f.name;
                    shade.append(big);
                    shade.addEventListener("click", () => shade.remove());
                    document.body.append(shade);
                });
                box.append(img);
            } else {
                const link = el("a", "file", "⎙ " + f.name + " · " + size(f.size));
                link.href = f.url;
                link.download = f.name;
                box.append(link);
            }
        }
        return box;
    }

    async function send(url, data, button) {
        button.disabled = true;
        try {
            const response = await fetch(url, { method: "POST", credentials: "same-origin", headers: { "X-CSRFToken": csrf() }, body: data });
            const answer = await response.json().catch(() => ({}));
            if (!response.ok) { notice(answer.error || "error " + response.status); return null; }
            return answer;
        } catch (e) {
            notice("support is unreachable");
            return null;
        } finally {
            button.disabled = false;
        }
    }

    let thread = null;
    let shown = 0;

    function drawThread(data) {
        shown = data.messages.length;
        thread.replaceChildren();
        for (const m of data.messages) {
            const box = el("div", "msg " + (m.staff ? "staff" : "mine"));
            const head = el("div", "msg-head");
            head.append(el("b", "", m.staff ? "Aether team" : "you"), el("span", "", m.when));
            box.append(head);
            if (m.text) box.append(el("div", "msg-text", m.text));
            if (m.files.length) box.append(showFiles(m.files));
            thread.append(box);
        }
    }

    // опрос: переписка перерисовывается, только если пришло новое; набранный ответ не трогается
    async function refresh() {
        if (!current || !thread) return loadList();
        try {
            const data = await getJson(base + "api/tickets/" + current + "/");
            if (data.messages.length !== shown) { drawThread(data); view.scrollTop = view.scrollHeight; }
        } catch (e) { /* в следующий раз */ }
        loadList();
    }

    async function openTicket(id) {
        current = id;
        let data;
        try {
            data = await getJson(base + "api/tickets/" + id + "/");
        } catch (e) {
            return notice("could not open the request");
        }
        title.textContent = "#" + data.id + " " + data.subject;
        thread = el("div", "thread");
        drawThread(data);
        const form = el("form", "form");
        const text = el("textarea", "field");
        text.placeholder = data.status === "closed" ? "write to reopen the request" : "your reply";
        text.setAttribute("aria-label", "reply");
        const picker = filePicker();
        const submit = el("button", "app-button primary", "send");
        submit.type = "submit";
        form.append(text, picker.box, submit);
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const body = new FormData();
            body.append("text", text.value);
            picker.files().forEach((f) => body.append("files", f));
            if (await send(base + "api/tickets/" + id + "/reply/", body, submit)) openTicket(id);
        });
        view.replaceChildren(thread, form);
        view.scrollTop = view.scrollHeight;
        loadList();
    }

    function newTicket() {
        current = null;
        thread = null;
        title.textContent = "new request";
        const form = el("form", "form");
        const subject = el("input", "field");
        subject.required = true;
        subject.maxLength = 200;
        const subjectLabel = el("label", "", "subject");
        subjectLabel.append(subject);
        const kinds = el("div", "choices");
        kinds.setAttribute("role", "radiogroup");
        for (const [value, label] of Object.entries({ bug: "something is broken", stuck: "I am stuck", other: "other" })) {
            const option = el("label");
            const radio = el("input");
            radio.type = "radio";
            radio.name = "category";
            radio.value = value;
            radio.checked = value === "bug";
            option.append(radio, label);
            kinds.append(option);
        }
        const text = el("textarea", "field");
        text.required = true;
        const textLabel = el("label", "", "what happened");
        textLabel.append(text);
        const picker = filePicker();
        const hint = el("p", "empty", "Your machine and account are attached automatically. Screenshots help a lot.");
        const submit = el("button", "app-button primary", "send request");
        submit.type = "submit";
        form.append(subjectLabel, kinds, textLabel, picker.box, hint, submit);
        form.addEventListener("submit", async (e) => {
            e.preventDefault();
            const body = new FormData();
            body.append("subject", subject.value);
            body.append("category", form.querySelector("input[name=category]:checked").value);
            body.append("text", text.value);
            picker.files().forEach((f) => body.append("files", f));
            const made = await send(root.dataset.createUrl, body, submit);
            if (made) { await loadList(); openTicket(made.id); }
        });
        view.replaceChildren(form);
        subject.focus();
        loadList();
    }

    document.getElementById("support-new").addEventListener("click", newTicket);
    loadList().then(() => {
        const first = tickets.find((t) => t.unread);
        if (first) openTicket(first.id);
        else if (!tickets.length) newTicket();
        else view.replaceChildren(el("p", "empty", "select a request or start a new one"));
    });
    setInterval(() => { if (!document.hidden) refresh(); }, 30000);
})();
