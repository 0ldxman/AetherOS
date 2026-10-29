/* =========================================================
   AETHER.OS ENTRY
   Экран входа: игрок подключается к удалённой машине. Что и как
   показывать, решают консольные сцены (scenes/gateway.py); здесь
   только то, что нельзя вынести в сцену: запросы к серверу и
   переходы между страницами. Допуски проверяются на сервере.
   ========================================================= */

(function () {
    "use strict";

    const CONFIG = JSON.parse(document.getElementById("boot-config").textContent);
    const SCENES = CONFIG.scenes || {};

    /* Адреса относительные от lock/ (поэтому "../"): страница должна открываться
       со слэшем в конце */
    const URLS = {
        guest: "../auth/guest/",
        discord: "../accounts/discord/login/?process=login",
        desktop: "../desktop/"
    };

    const screen = document.getElementById("boot-screen");
    const output = document.getElementById("boot-output");
    const hint = document.getElementById("lock-hint");

    const term = Aether.console.create(output, {
        flashTarget: screen,
        onChoice: () => {
            hint.hidden = true;
            remembered(store => store.setItem(KNOWN_KEY, "1"));   // узел добавлен в контакты, дальше без вопроса
        }
    });

    const KNOWN_KEY = "aether_entry_known";

    function remembered(action) {
        try { return action(window.localStorage); } catch (error) { return null; }   // может быть недоступно
    }

    const known = Boolean(remembered(store => store.getItem(KNOWN_KEY)));
    hint.hidden = !known;   // подсказка про пропуск нужна тем, кто здесь уже был

    function getCookie(name) {
        const prefix = name + "=";
        const row = document.cookie.split("; ").find(item => item.startsWith(prefix));
        return row ? decodeURIComponent(row.slice(prefix.length)) : "";
    }

    async function postJson(url) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCookie("csrftoken")
            },
            body: "{}"
        });

        let data = {};
        try { data = await response.json(); } catch (error) { /* не JSON */ }

        return { ok: response.ok, status: response.status, data };
    }

    const READ_PAUSE_MS = 900;   // последние строки успевают прочитать, потом экран гаснет

    function leave() {
        setTimeout(() => {
            screen.classList.add("is-leaving");
            setTimeout(() => { window.location.href = URLS.desktop; }, 700);
        }, READ_PAUSE_MS);
    }

    async function connectExternal() {
        await term.play(SCENES.discord);

        /* вернёмся на эту же страницу: сессия уже будет, сработает сцена restored */
        const next = encodeURIComponent(window.location.pathname);
        window.location.href = `${URLS.discord}&next=${next}`;
    }

    async function connectBypass() {
        /* запрос идёт параллельно со сценой подключения; «session established» играем
           только если сервер действительно открыл сессию */
        const request = postJson(URLS.guest).catch(() => ({ ok: false, status: 0, data: {} }));

        await term.play(SCENES.bypass);
        const result = await request;

        if (result.ok) {
            await term.play(SCENES.established);
            leave();
            return;
        }

        const code = result.status ? `HTTP ${result.status}` : "no response";
        await term.play(SCENES.error, { vars: { code } });
        await choose(SCENES.menu);
    }

    async function choose(scene, options) {
        const result = await term.play(scene, options);

        if (result.choice === "discord") await connectExternal();
        else if (result.choice === "bypass") await connectBypass();
    }

    async function run() {
        try {
            if (SCENES.restored) {
                hint.hidden = true;
                await term.play(SCENES.restored);
                leave();
                return;
            }

            const intro = known ? SCENES.intro_known : SCENES.intro;
            await choose(intro, known ? { speed: 0.6 } : {});
        } catch (error) {
            console.error(error);
        }
    }

    run();
})();
