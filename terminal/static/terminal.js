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

        if (data.output) {
            appendLine(data.output, data.exit_code ? "terminal-error" : "");
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

    updatePrompt();
    input.focus();
})();