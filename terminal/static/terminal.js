(() => {
    "use strict";

    const terminal = document.getElementById("terminal");
    const output = document.getElementById("terminal-output");
    const form = document.getElementById("terminal-form");
    const input = document.getElementById("terminal-input");
    const prompt = document.getElementById("terminal-prompt");

    const executeUrl = terminal.dataset.executeUrl;
    const hostname = terminal.dataset.hostname;
    const login = terminal.dataset.login;

    const csrfToken = document.querySelector(
        "[name=csrfmiddlewaretoken]"
    ).value;

    // Только для приглашения: настоящая папка хранится на сервере в сессии.
    let cwd = terminal.dataset.cwd || "/home";
    let busy = false;
    const history = [];
    let historyIndex = 0;

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
        // логин@машина:путь$, путь как в Linux: /home это ~, внутри него ~/папка (домашняя папка DEFAULT_CWD на сервере)
        const home = "/home";
        const shown = cwd === home ? "~" : cwd.startsWith(home + "/") ? "~" + cwd.slice(home.length) : cwd;
        prompt.textContent = `${login}@${hostname}:${shown}$`;
    }

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
        input.type = "password";
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
        } else if (effect.op === "switch") {
            if (api && api.reload) api.reload(); else window.location.reload();
        } else if (effect.op === "lock") {
            if (api && api.lock) api.lock(effect.url); else window.location.href = effect.url;
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
            // ответ на запрос пароля: строка запроса остаётся на экране, сам пароль нет
            appendLine(awaiting.text);
            endAnswer();
        } else {
            appendLine(`${prompt.textContent} ${command}`, "terminal-command");
            history.push(command);
            historyIndex = history.length;
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

            if (historyIndex > 0) {
                historyIndex--;
                input.value = history[historyIndex];
            }
        }

        if (event.key === "ArrowDown") {
            event.preventDefault();

            if (historyIndex < history.length - 1) {
                historyIndex++;
                input.value = history[historyIndex];
            } else {
                historyIndex = history.length;
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

    updatePrompt();
    input.focus();
    greet();
})();