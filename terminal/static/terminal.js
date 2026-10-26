(() => {
    "use strict";

    const terminal = document.getElementById("terminal");
    const output = document.getElementById("terminal-output");
    const form = document.getElementById("terminal-form");
    const input = document.getElementById("terminal-input");
    const prompt = document.getElementById("terminal-prompt");

    const executeUrl = terminal.dataset.executeUrl;
    const hostname = terminal.dataset.hostname;

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
        prompt.textContent = `${hostname}:${cwd}$`;
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

    async function executeCommand(command) {
        const response = await fetch(executeUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({ command }),
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

        // сначала работа команды, потом её ответ
        await playScene(data.scene);

        if (data.output) {
            appendLine(data.output, data.exit_code ? "terminal-error" : "");
        }

        if (data.window) {
            openWindow(data.window);
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (busy) {
            return;
        }

        const command = input.value.trim();

        if (!command) {
            return;
        }

        appendLine(`${prompt.textContent} ${command}`, "terminal-command");
        input.value = "";

        history.push(command);
        historyIndex = history.length;

        busy = true;
        input.disabled = true;

        try {
            await executeCommand(command);
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