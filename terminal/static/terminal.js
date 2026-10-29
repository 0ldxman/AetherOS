(() => {
    "use strict";

    const terminal = document.getElementById("terminal");
    const output = document.getElementById("terminal-output");
    const form = document.getElementById("terminal-form");
    const input = document.getElementById("terminal-input");
    const prompt = document.getElementById("terminal-prompt");

    const executeUrl = terminal.dataset.executeUrl;
    let hostname = terminal.dataset.hostname;
    let login = terminal.dataset.login;

    const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]"
    ).value;

    // Только для приглашения: настоящая папка хранится на сервере в сессии.
    let cwd = terminal.dataset.cwd || "/home";
    let home = terminal.dataset.home || "/home";
    let busy = false;

    // У каждой вкладки своя лента вывода и своя история команд. Ленты неактивных вкладок лежат отдельно, пока терминал
    // на другой; вкладка без подключений одна и называется "0"
    const stores = new Map();
    let activeId = "0";

    function storeOf(id) {
        if (!stores.has(id)) {
            stores.set(id, { nodes: [], history: [], index: 0 });
        }

        return stores.get(id);
    }

    let tab = storeOf(activeId);

    // Сцены (анимация работы команды, приветствие) играет общий проигрыватель консоли: любая клавиша или клик
    // доигрывают сцену сразу. Строки команд и ответов лежат в том же контейнере.
    const scenes = window.Aether && window.Aether.console
        ? window.Aether.console.create(output, { flashTarget: terminal })
        : null;

    async function playScene(steps) {
        if (!scenes || !Array.isArray(steps) || !steps.length) {
            return;
        }

        await scenes.play(steps);
    }

    function appendLine(text, className = "") {
        const line = document.createElement("div");
        line.className = `terminal-line ${className}`.trim();
        line.textContent = text;
        output.appendChild(line);
    }

    function updatePrompt() {
        // логин@машина:путь$, путь как в Linux: домашняя папка это ~, внутри неё ~/папка (папку называет сервер)
        const shown = cwd === home ? "~" : cwd.startsWith(home + "/") ? "~" + cwd.slice(home.length) : cwd;
        prompt.textContent = `${login}@${hostname}:${shown}$`;
    }

    // Вкладки подключений: клик переносит терминал, рабочий стол остаётся; меню правой кнопкой меняет стол или закрывает
    const tabsBar = document.getElementById("terminal-tabs");
    const tabMenu = document.getElementById("terminal-tab-menu");
    let tabs = [];

    async function post(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
            body: JSON.stringify(body),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }
        return data;
    }

    function renderTabs(list) {
        tabs = list || [];
        tabsBar.textContent = "";
        tabsBar.hidden = tabs.length < 2;

        for (const entry of tabs) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "terminal-tab";
            button.setAttribute("role", "tab");
            button.setAttribute("aria-selected", entry.terminal ? "true" : "false");
            button.title = entry.desktop ? "desktop is here" : "";
            button.textContent = entry.label;

            if (entry.desktop) {
                const mark = document.createElement("span");
                mark.className = "terminal-tab-desk";
                button.prepend(mark);
            }

            button.addEventListener("click", () => focusTab(entry));
            button.addEventListener("contextmenu", (event) => {
                event.preventDefault();
                openTabMenu(entry, event.clientX, event.clientY);
            });
            tabsBar.appendChild(button);
        }

        scheduleLimits();
    }

    // Терминал переходит на вкладку, у которой стоит terminal: лента и история переключаются на её собственные
    function settleTabs() {
        const target = tabs.find((entry) => entry.terminal);
        const id = target ? target.id : "0";

        if (id !== activeId) {
            tab.nodes = Array.from(output.childNodes);
            tab.index = tab.history.length;
            tab = storeOf(id);
            activeId = id;
            output.replaceChildren(...tab.nodes);
            tab.nodes = [];
            input.value = "";
            scrollToBottom();
        }

        const alive = new Set(tabs.map((entry) => entry.id));
        alive.add("0");
        for (const key of Array.from(stores.keys())) {
            if (!alive.has(key) && key !== activeId) {
                stores.delete(key);                       // закрытое подключение уносит свою ленту
            }
        }
    }

    // Сроки подключений: за warn_at секунд до срока вкладка предупреждает в своей ленте, на сроке браузер просит сервер
    // закрыть вышедшее (сервер решает сам, браузер только вовремя стучится)
    let clockOffset = 0;
    let warnAt = [30, 10];
    let limitTimers = [];

    function syncClock(data) {
        if (data.now) clockOffset = data.now * 1000 - Date.now();
        if (data.warn_at) warnAt = data.warn_at;
    }

    function appendLineTo(id, text, className) {
        if (id === activeId) {
            appendLine(text, className);
            return;
        }

        const line = document.createElement("div");
        line.className = `terminal-line ${className}`.trim();
        line.textContent = text;
        storeOf(id).nodes.push(line);
    }

    function scheduleLimits() {
        limitTimers.forEach(clearTimeout);
        limitTimers = [];
        const now = Date.now() + clockOffset;

        for (const entry of tabs) {
            if (!entry.deadline) continue;
            const at = entry.deadline * 1000;

            for (const left of warnAt) {
                if (at - left * 1000 > now) {
                    limitTimers.push(setTimeout(() => {
                        appendLineTo(entry.id, (entry.warn || "").replace("{n}", left), "terminal-warning");
                    }, at - left * 1000 - now));
                }
            }

            limitTimers.push(setTimeout(tickNow, Math.max(0, at - now) + 400));
        }
    }

    async function tickNow() {
        try {
            applyShell(await post(terminal.dataset.tickUrl, {}));
        } catch {
            // сеть моргнула: следующая команда всё равно проверит срок на сервере
        }
    }

    // Что случилось с подключениями по сроку: выброс с рабочего стола показывает рабочий стол (чёрный экран), выход
    // из оболочки терминал пишет сам
    function handleKicks(kicks) {
        const api = window.parent && window.parent !== window ? window.parent.desktopAPI : null;

        for (const kick of kicks || []) {
            if (kick.desktop && api && api.blackout) {
                api.blackout(kick.blackout);
            } else {
                appendLine(`connection to ${kick.host} closed: ${kick.message.split("\n")[0]}`, "terminal-error");
            }
        }
    }

    function applyShell(data) {
        syncClock(data);
        cwd = data.cwd || cwd;
        home = data.home || home;
        hostname = data.hostname || hostname;
        login = data.login || login;
        renderTabs(data.tabs);
        settleTabs();
        handleKicks(data.kicks);              // сообщение выброшенной вкладки пишется туда, где терминал оказался
        updatePrompt();
    }

    async function focusTab(entry) {
        if (busy || entry.terminal) {
            return;
        }

        try {
            if (awaiting) {
                endAnswer();
            }
            const data = await post(terminal.dataset.tabFocusUrl, { node: entry.id });
            applyShell(data);
        } catch (error) {
            appendLine(`terminal: ${error.message}`, "terminal-error");
        }
        input.focus();
    }

    function closeTabMenu() {
        tabMenu.hidden = true;
    }

    function openTabMenu(entry, x, y) {
        tabMenu.textContent = "";

        const items = [
            ["Switch desktop here", !entry.desktop, async () => {
                const data = await post(terminal.dataset.tabDesktopUrl, { node: entry.id });
                applyShell(data);
                for (const effect of data.effects || []) runEffect(effect);
            }],
            ["Close connection", entry.parent !== null, async () => {
                const data = await post(terminal.dataset.tabCloseUrl, { node: entry.id });
                await playScene(data.scene);
                applyShell(data);
                for (const effect of data.effects || []) runEffect(effect);
            }],
        ];

        for (const [label, enabled, action] of items) {
            const item = document.createElement("li");
            item.setAttribute("role", "menuitem");
            item.setAttribute("aria-disabled", enabled ? "false" : "true");
            item.textContent = label;
            item.addEventListener("click", async () => {
                closeTabMenu();
                if (!enabled || busy) return;
                try {
                    await action();
                } catch (error) {
                    appendLine(`terminal: ${error.message}`, "terminal-error");
                }
                input.focus();
            });
            tabMenu.appendChild(item);
        }

        tabMenu.style.left = `${Math.min(x, window.innerWidth - 200)}px`;
        tabMenu.style.top = `${y}px`;
        tabMenu.hidden = false;
    }

    document.addEventListener("click", closeTabMenu);
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeTabMenu();
    });

    function scrollToBottom() {
        terminal.scrollTop = terminal.scrollHeight;
    }

    function openWindow(win) {
        const desktop = window.parent && window.parent.desktopAPI;

        if (!desktop || typeof desktop.openApp !== "function") {
            appendLine("terminal: cannot open window", "terminal-error");
            return;
        }

        desktop.openApp(win.id, win.title, win.url);
    }

    // запрос на ввод пароля (мост): пока он открыт, строка ввода скрыта звёздочками, а ответ уходит отдельно
    let awaiting = null;

    function awaitAnswer(request) {
        awaiting = request;
        input.type = request.kind === "confirm" ? "text" : "password";
        prompt.textContent = request.text;
    }

    function endAnswer() {
        awaiting = null;
        input.type = "text";
        updatePrompt();
    }

    // Эффекты ответа: сцена после текста, смена рабочего стола, экран входа, окна ошибок
    async function runEffect(effect) {
        const desktop = window.parent && window.parent !== window ? window.parent : null;
        const api = desktop && desktop.desktopAPI;

        if (effect.op === "play") {
            await playScene(effect.scene);
        } else if (effect.op === "blackout") {
            if (api && api.blackout) api.blackout(effect); else window.location.reload();
        } else if (effect.op === "switch") {
            if (api && api.reload) api.reload(); else window.location.reload();
        } else if (effect.op === "lock") {
            if (api && api.lock) api.lock(effect.url); else window.location.href = effect.url;
        } else if (effect.op === "open" && api && api.openApp) {
            api.openApp(effect.id, effect.title, effect.url);
        } else if (effect.op === "alert" && api && api.error) {
            for (let i = 0; i < effect.count; i++) {
                api.error(effect.message, { object: `0x${(4096 + Math.floor(Math.random() * 61000)).toString(16)}` }, { stack: true });
                await new Promise((resolve) => setTimeout(resolve, effect.gap * (0.6 + Math.random() * 0.8)));
            }
        }
    }

    async function send(body) {
        const response = await fetch(executeUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify(body),
        });

        let data;

        try {
            data = await response.json();
        } catch {
            throw new Error(`HTTP ${response.status}`);
        }

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        cwd = data.cwd || cwd;
        home = data.home || home;
        hostname = data.hostname || hostname;     // rshell меняет машину и логин оболочки
        login = data.login || login;
        syncClock(data);
        if (data.tabs) renderTabs(data.tabs);
        updatePrompt();

        if (data.clear) {
            output.textContent = "";
        }

        // сначала работа команды, потом её ответ
        await playScene(data.scene);

        if (data.output) {
            appendLine(data.output, data.exit_code ? "terminal-error" : "");
        }

        if (data.window) {
            openWindow(data.window);
        }

        if (data.prompt) {
            awaitAnswer(data.prompt);
        }

        settleTabs();            // команда доиграла в ленте своей вкладки, дальше терминал на той, что указал сервер
        handleKicks(data.kicks);

        // effects после текста: смена рабочего стола ждёт, пока доиграет последняя сцена
        for (const effect of data.effects || []) {
            if (effect.op === "play") {
                await runEffect(effect);
            } else {
                runEffect(effect);
            }
        }
    }

    function executeCommand(command) {
        return send({ command });
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (busy) {
            return;
        }

        const answering = awaiting !== null;
        const command = answering ? input.value : input.value.trim();

        if (!command && !answering) {
            return;
        }

        if (answering) {
            // ответ на запрос пароля: строка запроса остаётся на экране, сам пароль нет (ответ на y/n остаётся)
            appendLine(awaiting.kind === "confirm" ? awaiting.text + command : awaiting.text);
            endAnswer();
        } else {
            appendLine(`${prompt.textContent} ${command}`, "terminal-command");
            tab.history.push(command);
            tab.index = tab.history.length;
        }

        input.value = "";
        busy = true;
        input.disabled = true;

        try {
            await (answering ? send({ answer: command }) : executeCommand(command));
        } catch (error) {
            appendLine(`terminal: ${error.message}`, "terminal-error");
        } finally {
            busy = false;
            input.disabled = false;
            input.focus();
            scrollToBottom();
        }
    });

    input.addEventListener("keydown", (event) => {
        // Esc или Ctrl+C отменяют запрос пароля
        if (awaiting && (event.key === "Escape" || (event.ctrlKey && event.key === "c"))) {
            event.preventDefault();
            appendLine(`${awaiting.text}^C`);
            endAnswer();
            input.value = "";
            fetch(executeUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
                body: JSON.stringify({ cancel: true }),
            });
            return;
        }

        if (awaiting) {
            return;
        }

        if (event.key === "ArrowUp") {
            event.preventDefault();

            if (tab.index > 0) {
                tab.index--;
                input.value = tab.history[tab.index];
            }
        }

        if (event.key === "ArrowDown") {
            event.preventDefault();

            if (tab.index < tab.history.length - 1) {
                tab.index++;
                input.value = tab.history[tab.index];
            } else {
                tab.index = tab.history.length;
                input.value = "";
            }
        }
    });

    // прокрутка вниз при любом изменении вывода, в том числе пока играет сцена
    new MutationObserver(scrollToBottom).observe(output, {
        childList: true,
        subtree: true,
        characterData: true,
    });

    async function greet() {
        let greeting = null;

        try {
            greeting = JSON.parse(document.getElementById("terminal-greeting").textContent);
        } catch {
            greeting = null;
        }

        if (!greeting) {
            return;
        }

        busy = true;
        input.disabled = true;

        try {
            await playScene(greeting);
        } finally {
            busy = false;
            input.disabled = false;
            input.focus();
        }
    }

    try {
        const boot = JSON.parse(document.getElementById("terminal-boot").textContent);
        syncClock(boot);
        renderTabs(JSON.parse(document.getElementById("terminal-tabs-data").textContent));
        settleTabs();
        handleKicks(boot.kicks);
    } catch {
        renderTabs([]);
    }

    updatePrompt();
    input.focus();
    greet();
})();