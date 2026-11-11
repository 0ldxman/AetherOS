// Лента новостей команды: список слева, новость справа. Открытая новость отмечается прочитанной.
(function () {
    "use strict";
    const { el, csrf, markup, notice } = window.apps;
    const root = document.getElementById("news");
    const list = document.getElementById("news-list");
    const view = document.getElementById("news-view");
    const allButton = document.getElementById("news-all");
    let posts = [];
    let current = null;

    async function load() {
        const response = await fetch(root.dataset.postsUrl, { credentials: "same-origin" });
        if (!response.ok) return notice("news: could not load");
        const data = await response.json();
        posts = data.posts;
        render();
        if (current === null && posts.length) open(posts.find((p) => p.unread && p.important) || posts[0]);
    }

    function render() {
        list.replaceChildren(...posts.map((post) => {
            const card = el("li", "card" + (post.unread ? " unread" : "") + (current === post.id ? " selected" : ""));
            card.tabIndex = 0;
            card.dataset.id = post.id;
            const head = el("div", "card-head");
            head.append(el("span", "card-title", post.title));
            if (post.pinned) head.append(el("span", "tag", "pinned"));
            if (post.important) head.append(el("span", "tag warn", "important"));
            card.append(head, el("span", "card-meta", post.when + (post.author ? " · " + post.author : "")));
            card.addEventListener("click", () => open(post));
            card.addEventListener("keydown", (e) => { if (e.key === "Enter") open(post); });
            return card;
        }));
        if (!posts.length) list.replaceChildren(el("li", "empty", "no news yet"));
        const unread = posts.filter((p) => p.unread).length;
        document.getElementById("news-count").textContent = unread ? unread + " unread" : posts.length + " posts";
        allButton.hidden = !unread;
    }

    async function markRead(ids) {
        if (!ids.length) return;
        await fetch(root.dataset.readUrl, { method: "POST", credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ ids }) });
        posts.forEach((p) => { if (ids.includes(p.id)) p.unread = false; });
        render();
    }

    function open(post) {
        current = post.id;
        const head = el("header", "reader-head");
        head.append(el("h1", "", post.title), el("p", "meta", post.when + (post.author ? " · " + post.author : "")));
        view.replaceChildren(head, markup(post.body));
        render();
        if (post.unread) markRead([post.id]);
    }

    function move(by) {
        const index = posts.findIndex((p) => p.id === current);
        const next = posts[Math.min(posts.length - 1, Math.max(0, index + by))];
        if (next) open(next);
    }

    allButton.addEventListener("click", () => markRead(posts.filter((p) => p.unread).map((p) => p.id)));
    document.addEventListener("keydown", (e) => {
        if (e.target.closest("input, textarea")) return;
        if (e.key === "j") move(1);
        if (e.key === "k") move(-1);
    });
    load();
    setInterval(() => { if (!document.hidden) load(); }, 60000);
})();
