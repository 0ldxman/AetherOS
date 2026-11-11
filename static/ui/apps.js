// Общие помощники простых приложений стола (news, support): элементы, CSRF, разметка текста, строка статуса.
(function () {
    "use strict";

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = text;
        return node;
    }

    function csrf() {
        const input = document.querySelector("input[name=csrfmiddlewaretoken]");
        if (input) return input.value;
        const found = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return found ? decodeURIComponent(found[1]) : "";
    }

    // строка: **жирный**, *курсив*, `код`, ссылки http(s); всё текстом, без HTML
    function inline(text) {
        const out = document.createDocumentFragment();
        const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|https?:\/\/[^\s)]+)/g;
        let last = 0;
        for (const found of text.matchAll(pattern)) {
            if (found.index > last) out.append(text.slice(last, found.index));
            const token = found[0];
            if (token.startsWith("**")) out.append(el("strong", "", token.slice(2, -2)));
            else if (token.startsWith("`")) out.append(el("code", "", token.slice(1, -1)));
            else if (token.startsWith("*")) out.append(el("em", "", token.slice(1, -1)));
            else {
                const link = el("a", "", token);
                link.href = token;
                link.target = "_blank";
                link.rel = "noopener noreferrer";
                out.append(link);
            }
            last = found.index + token.length;
        }
        if (last < text.length) out.append(text.slice(last));
        return out;
    }

    // блоки: # заголовок, - список, > цитата, пустая строка делит абзацы
    function markup(text) {
        const root = el("div", "markup");
        let list = null;
        let paragraph = [];
        const flush = () => {
            if (paragraph.length) {
                const p = el("p");
                paragraph.forEach((line, i) => { if (i) p.append(el("br")); p.append(inline(line)); });
                root.append(p);
            }
            paragraph = [];
        };
        for (const raw of (text || "").replace(/\r\n/g, "\n").split("\n")) {
            const line = raw.trimEnd();
            const heading = line.match(/^(#{1,3})\s+(.*)$/);
            const item = line.match(/^\s*[-*]\s+(.*)$/);
            if (!item) list = null;
            if (!line.trim()) { flush(); continue; }
            if (heading) { flush(); const h = el("h" + (heading[1].length + 1)); h.append(inline(heading[2])); root.append(h); continue; }
            if (item) {
                flush();
                if (!list) { list = el("ul"); root.append(list); }
                const li = el("li"); li.append(inline(item[1])); list.append(li);
                continue;
            }
            if (line.startsWith(">")) { flush(); const q = el("blockquote"); q.append(inline(line.replace(/^>\s?/, ""))); root.append(q); continue; }
            paragraph.push(line);
        }
        flush();
        return root;
    }

    let timer = null;
    function notice(text) {
        const status = document.querySelector(".status");
        if (!status) return;
        let box = status.querySelector(".notice");
        if (!box) { box = el("span", "notice"); status.prepend(box); }
        box.textContent = text;
        status.classList.add("is-warning");
        clearTimeout(timer);
        timer = setTimeout(() => { box.remove(); status.classList.remove("is-warning"); }, 4000);
    }

    function size(bytes) {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
        return (bytes / 1024 / 1024).toFixed(1) + " MB";
    }

    window.apps = { el, csrf, markup, notice, size };
})();
