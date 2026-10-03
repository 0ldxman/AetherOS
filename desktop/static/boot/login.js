/* =========================================================
   AETHER.OS LOGIN
   ---------------------------------------------------------
   Запускается событием "aether:boot-complete" от boot.js.

   Порядок: мини-загрузка -> (если сессия уже есть: "Session
   restored") или форма входа -> рабочий стол.

   ВАЖНО: подключать ПОСЛЕ boot.js. Использует его CONFIG
   и функции text, type, burst, spinner, newline,
   clearScreen, pause, sleep, flash и т.д.

   Допуски проверяются на сервере. Этот файл только рисует
   интерфейс и отправляет запросы.
   ========================================================= */


/* =========================================================
   SETTINGS
   ---------------------------------------------------------
   Можно переопределить из boot-config (Django):
   desktopUrl, urls, guestClearance
   ========================================================= */

const AUTH = {
    /*
     * Куда идти после входа. null = только событие "aether:auth-complete".
     *
     * Адреса ОТНОСИТЕЛЬНЫЕ (без ведущего "/"): они считаются от адреса
     * страницы входа. Если страница открыта как /proxy/8000/, запрос
     * пойдёт на /proxy/8000/auth/guest/, а при размещении в корне
     * сайта на /auth/guest/. Поэтому страница входа должна открываться
     * со слэшем в конце. Другие адреса можно передать через boot_config.
     */
    desktopUrl: CONFIG.desktopUrl !== undefined ? CONFIG.desktopUrl : "desktop/",

    urls: {
        login: "auth/login/",
        guest: "auth/guest/",
        discord: "accounts/discord/login/?process=login",
        ...(CONFIG.urls || {})
    },

    guestClearance: CONFIG.guestClearance || { level: "L0", label: "PUBLIC" }
};


/* -----------------------------------------
   STATE
   ----------------------------------------- */

let authBusy = false;
let hotkeyHandler = null;


/* =========================================================
   NETWORK
   ========================================================= */

function getCookie(name) {
    const prefix = name + "=";
    const row = document.cookie
        .split("; ")
        .find(item => item.startsWith(prefix));

    return row ? decodeURIComponent(row.slice(prefix.length)) : "";
}

/*
 * POST с JSON и CSRF-токеном Django.
 * Страница должна быть отдана через ensure_csrf_cookie,
 * иначе куки csrftoken не будет.
 */
async function postJson(url, payload = {}) {
    const response = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
        },
        body: JSON.stringify(payload)
    });

    let data = {};

    try {
        data = await response.json();
    } catch (error) {
        /* Ответ без JSON, оставляем пустой объект */
    }

    return { ok: response.ok, status: response.status, data };
}


/* =========================================================
   STAGE: SPLASH
   ---------------------------------------------------------
   Небольшой экран загрузки с полоской прогресса
   ========================================================= */

function renderBar(percent, width = 24) {
    const filled = Math.round(width * percent / 100);
    const bar = "#".repeat(filled) + "-".repeat(width - filled);

    return `[${bar}] ${String(percent).padStart(3)}%`;
}

async function stageSplash() {
    await clearScreen();
    hideCursor();

    const box = document.createElement("div");
    box.className = "splash";

    const logo = document.createElement("div");
    logo.className = "splash-logo";
    logo.textContent = "AETHER.OS";

    const bar = document.createElement("div");
    bar.className = "splash-bar";
    bar.textContent = renderBar(0);

    const status = document.createElement("div");
    status.className = "splash-status";

    box.append(logo, bar, status);
    output.appendChild(box);
    await fadeIn(500);

    const lastMessage = CONFIG.authenticated
        ? "Restoring session..."
        : "Awaiting credentials...";

    const phases = [
        ["Initializing session...", 30],
        ["Syncing archive index...", 70],
        [lastMessage, 100]
    ];

    let percent = 0;

    for (const [message, target] of phases) {
        status.textContent = message;

        while (percent < target) {
            percent = Math.min(percent + random(1, 4), target);
            bar.textContent = renderBar(percent);
            await sleep(random(25, 60));
        }
    }

    await pause(500);
}


/* =========================================================
   STAGE: ACCESS GRANTED
   ---------------------------------------------------------
   Финальные строки после успешного входа
   ========================================================= */

async function stageGranted({
    username,
    clearance = { level: "L?", label: "UNKNOWN" },
    guest = false,
    restored = false
}) {
    await fadeOut(300);
    await clearScreen();
    await fadeIn(300);
    await pause(200);

    if (restored) {
        await text("Session restored.", "success");
    } else {
        await text("Verifying credentials");
        await burst("......", 1, 2, 60, 120);
        await spinner(700);
        await text(" OK", "success");
    }
    await newline();

    await text("User: ");
    await text(username, guest ? "dim" : "success");
    await newline();

    await text("Clearance level: ");
    await text(`${clearance.level} (${clearance.label})`, guest ? "warning" : "success");
    await newline();
    await pause(400);

    await text("Loading workspace");
    await burst("...", 1, 1, 200, 350);
    await pause(900);

    await enterDesktop();
}

async function enterDesktop() {
    await fadeOut(500);

    if (AUTH.desktopUrl) {
        window.location.href = AUTH.desktopUrl;
    } else {
        document.dispatchEvent(new CustomEvent("aether:auth-complete"));
    }
}


/* =========================================================
   FORM
   ========================================================= */

function buildForm() {
    const form = document.createElement("form");
    form.className = "auth";
    form.noValidate = true;

    form.innerHTML = `
        <label class="auth-row">
            <span class="auth-label">login:</span>
            <input class="auth-input" name="username" type="text"
                   autocomplete="username" autocapitalize="off"
                   autocorrect="off" spellcheck="false">
        </label>
        <label class="auth-row">
            <span class="auth-label">password:</span>
            <input class="auth-input" name="password" type="password"
                   autocomplete="current-password">
        </label>
        <div class="auth-message" role="alert" aria-live="polite"></div>
        <div class="auth-actions">
            <button type="submit" class="auth-btn">[ ENTER ] Sign in</button>
            <button type="button" class="auth-btn" data-action="discord">[ D ] Authenticate via DISCORD</button>
            <button type="button" class="auth-btn" data-action="guest"></button>
        </div>
    `;

    const guestButton = form.querySelector('[data-action="guest"]');
    guestButton.textContent =
        `[ G ] Continue as GUEST (clearance ${AUTH.guestClearance.level})`;

    return form;
}

function showMessage(form, message, style = null) {
    const element = form.querySelector(".auth-message");
    element.className = style ? `auth-message ${style}` : "auth-message";
    element.textContent = message;
}

function setBusy(form, value) {
    authBusy = value;

    form.querySelectorAll("input, button").forEach(element => {
        element.disabled = value;
    });
}

function shake(form) {
    form.classList.remove("shake");
    void form.offsetWidth; /* перезапуск CSS-анимации */
    form.classList.add("shake");
}


/* =========================================================
   ACTIONS
   ========================================================= */

async function handleSubmit(form) {
    if (authBusy) {
        return;
    }

    const username = form.elements.username.value.trim();
    const password = form.elements.password.value;

    if (!username || !password) {
        showMessage(form, "ERROR: login and password required", "warning");
        return;
    }

    setBusy(form, true);
    showMessage(form, "Verifying credentials ...", "dim");

    let result;

    try {
        result = await postJson(AUTH.urls.login, { username, password });
    } catch (error) {
        showMessage(form, "ERROR: uplink failure, retry", "error");
        setBusy(form, false);
        return;
    }

    if (result.ok) {
        detachHotkeys();
        await stageGranted({
            username: result.data.username,
            clearance: result.data.clearance
        });
        return;
    }

    if (result.status === 429) {
        showMessage(form, "ACCESS DENIED: terminal locked. Try again later.", "error");
    } else if (result.data.attempts_left === undefined) {
        /* Неверный пароль всегда приходит с attempts_left, значит это не он */
        console.warn("login: сервер отклонил запрос", result);
        showMessage(form, `ERROR: server rejected request (HTTP ${result.status})`, "error");
    } else {
        showMessage(form, `ACCESS DENIED (${result.data.attempts_left} attempts left)`, "error");
    }

    shake(form);
    form.elements.password.value = "";
    setBusy(form, false);
    form.elements.password.focus();
}

async function handleGuest(form) {
    if (authBusy) {
        return;
    }

    setBusy(form, true);
    showMessage(form, "Requesting guest session ...", "dim");

    let result;

    try {
        result = await postJson(AUTH.urls.guest);
    } catch (error) {
        console.warn("guest: запрос не дошёл до сервера", error);
        result = { ok: false, status: 0, data: {} };
    }

    if (!result.ok) {
        console.warn("guest: сервер ответил ошибкой", result);
        const code = result.status ? `HTTP ${result.status}` : "no response";
        showMessage(form, `ERROR: guest access unavailable (${code})`, "error");
        setBusy(form, false);
        return;
    }

    detachHotkeys();
    await stageGranted({
        username: result.data.username || "guest",
        clearance: result.data.clearance || AUTH.guestClearance,
        guest: true
    });
}

async function handleDiscord(form) {
    if (authBusy) {
        return;
    }

    setBusy(form, true);
    showMessage(form, "Redirecting to DISCORD authority ...", "dim");
    await pause(700);

    /*
     * После входа вернёмся на эту же страницу: загрузка
     * пройдёт в короткой версии, и сработает "Session restored".
     */
    const next = encodeURIComponent(window.location.pathname);
    const separator = AUTH.urls.discord.includes("?") ? "&" : "?";

    window.location.href = `${AUTH.urls.discord}${separator}next=${next}`;
}


/* =========================================================
   HOTKEYS
   ---------------------------------------------------------
   D = Discord, G = гость. Работают, только когда фокус
   не в поле ввода. event.code не зависит от раскладки.
   ========================================================= */

function attachHotkeys(form) {
    hotkeyHandler = event => {
        if (event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }

        const tag = event.target.tagName;

        if (tag === "INPUT" || tag === "TEXTAREA") {
            return;
        }

        if (event.code === "KeyD") {
            event.preventDefault();
            handleDiscord(form);
        } else if (event.code === "KeyG") {
            event.preventDefault();
            handleGuest(form);
        }
    };

    document.addEventListener("keydown", hotkeyHandler);
}

function detachHotkeys() {
    if (hotkeyHandler) {
        document.removeEventListener("keydown", hotkeyHandler);
        hotkeyHandler = null;
    }
}


/* =========================================================
   STAGE: AUTH
   ========================================================= */

async function stageAuth() {
    await fadeOut(400);
    await clearScreen();

    await text(`AETHER OS 9.1 (Halcyon)  ${CONFIG.node}  tty1`);
    await newline();
    await newline();

    const last = CONFIG.lastLogin;

    if (last) {
        await text(`Last login: ${last.date} from ${last.from}`, "dim");

        if (last.anomaly) {
            await text("   [ANOMALY: session not closed]", "warning");
        }

        await newline();
        await newline();
    }

    await text("Authentication required.");
    hideCursor();

    const form = buildForm();
    output.appendChild(form);

    form.addEventListener("submit", event => {
        event.preventDefault();
        handleSubmit(form);
    });

    form.addEventListener("click", event => {
        const button = event.target.closest("[data-action]");

        if (!button) {
            return;
        }

        if (button.dataset.action === "discord") {
            handleDiscord(form);
        } else if (button.dataset.action === "guest") {
            handleGuest(form);
        }
    });

    attachHotkeys(form);
    await fadeIn(400);
    form.elements.username.focus();
}


/* =========================================================
   RUN
   ========================================================= */

async function runAuth() {
    try {
        await stageSplash();

        if (CONFIG.authenticated) {
            await stageGranted({
                username: CONFIG.username,
                clearance: CONFIG.clearance,
                guest: Boolean(CONFIG.guest),
                restored: true
            });
        } else {
            await stageAuth();
        }
    } catch (error) {
        console.error(error);
    }
}

document.addEventListener("aether:boot-complete", runAuth);