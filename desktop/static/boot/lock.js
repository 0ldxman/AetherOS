/* =========================================================
   AETHER.OS ENTRY
   ---------------------------------------------------------
   МАКЕТ экрана входа. Сценарий написан прямо здесь; когда вид
   будет утверждён, он переедет на движок консольных сцен.

   Игрок приходит на aether-main, там вход только через Discord.
   Через пару секунд в меню кто-то дописывает строку от первого
   лица: обходной путь внутрь, оставленный не игроком. Нажатие
   превращает aether-main в aether-null (для системы это две
   машины на одном железе: hid у них общий).

   Если сессия уже есть, экран показывает «Session restored» и
   идёт дальше. Допуски проверяются на сервере: этот файл только
   рисует и отправляет запросы. Тексты приходят из gateway.
   ========================================================= */

const CONFIG = JSON.parse(document.getElementById("boot-config").textContent);
const GATEWAY = CONFIG.gateway || {};
const BYPASS = GATEWAY.bypass || {};

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

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

let skipping = reducedMotion;   // любая клавиша во время анимации пропускает её
let animating = true;           // идёт ли ещё анимация, которую можно пропустить
let ready = false;              // показаны ли варианты входа (работают горячие клавиши)
let busy = false;
let cursor = null;
let hostEl = null;
let followupTimer = 0;


/* ---------- помощники ---------- */

const wait = ms => (skipping ? Promise.resolve() : new Promise(resolve => setTimeout(resolve, ms)));
const randomInt = (min, max) => Math.floor(min + Math.random() * (max - min + 1));
const pick = list => list[randomInt(0, list.length - 1)];

function el(tag, className = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    return node;
}

function hideCursor() {
    if (cursor) {
        cursor.remove();
        cursor = null;
    }
}

function showCursor(parent) {
    hideCursor();
    cursor = el("span", "boot-cursor");
    parent.appendChild(cursor);
}

/* parts: массив строк или [текст, стиль]; стили: success, warning, error, dim */
function addLine(parts = []) {
    hideCursor();

    const line = el("div", "boot-line");

    parts.forEach(part => {
        const [value, style] = Array.isArray(part) ? part : [part, ""];
        const span = el("span", style);
        span.textContent = value;
        line.appendChild(span);
    });

    output.appendChild(line);
    return line;
}

async function say(parts, delay = 70) {
    const line = addLine(parts);
    await wait(delay);
    return line;
}

/* «Метка ........ СТАТУС», точки набираются по одной */
async function dotted(label, status, style = "success", ms = 520) {
    const line = addLine([label]);
    const dots = el("span", "dim");
    line.appendChild(dots);

    const count = 14;
    for (let i = 0; i < count; i++) {
        dots.textContent += ".";
        await wait(ms / count);
    }

    const result = el("span", style);
    result.textContent = " " + status;
    line.appendChild(result);
    await wait(70);
}

/* Печать как у человека: неровный ритм, пауза в раздумье и одна опечатка,
   которую он замечает и стирает. Курсор стоит в конце набираемого текста. */
async function humanType(target, text, { typo = true } = {}) {
    const parent = target.parentElement;
    const hesitateAt = randomInt(2, Math.max(3, text.length - 3));
    const typoAt = typo && text.length > 10 ? randomInt(4, text.length - 4) : -1;

    for (let i = 0; i < text.length; i++) {
        if (skipping) {
            target.textContent = text;
            break;
        }

        if (i === hesitateAt) {
            showCursor(parent);
            await wait(randomInt(350, 700));
        }

        if (i === typoAt && /[a-z]/.test(text[i])) {
            const wrong = pick("abcdefghijklmnopqrstuvwxyz".replace(text[i], "").split(""));
            target.textContent += wrong;
            showCursor(parent);
            await wait(randomInt(420, 760));
            target.textContent = target.textContent.slice(0, -1);
            await wait(130);
        }

        target.textContent += text[i];
        showCursor(parent);
        await wait(randomInt(45, 130) + (text[i] === " " ? randomInt(30, 120) : 0));
    }

    hideCursor();
}

/* Текст «портится» и становится другим: меняющиеся символы сначала прыгают, потом встают на место */
async function glitchTo(target, to) {
    const noise = "#%&/\\?01<>=+*";
    const from = target.textContent;

    if (skipping) {
        target.textContent = to;
        return;
    }

    const length = Math.max(from.length, to.length);

    for (let frame = 0; frame < 14; frame++) {
        let shown = "";

        for (let i = 0; i < length; i++) {
            const settled = frame > 5 + i * 0.6;
            const target_char = to[i] || "";
            const original = from[i] || "";

            if (target_char === original || settled) {
                shown += target_char;
            } else {
                shown += pick(noise.split(""));
            }
        }

        target.textContent = shown;
        await wait(55);
    }

    target.textContent = to;
}

async function flash() {
    if (skipping) return;

    for (let i = 0; i < 2; i++) {
        screen.classList.add("is-flash");
        await wait(70);
        screen.classList.remove("is-flash");
        await wait(70);
    }
}


/* ---------- сеть ---------- */

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

async function leave() {
    screen.classList.add("is-leaving");
    await wait(700);
    window.location.href = URLS.desktop;
}

function clearanceText(clearance) {
    return clearance ? `${clearance.level} (${clearance.label})` : "L? (UNKNOWN)";
}


/* ---------- шапка машины ---------- */

/* Шапка: система, организация, имя машины. Имя машины отдельным элементом,
   потому что при обходе оно меняется прямо на месте. */
function addHeader(host) {
    const line = addLine([
        `${GATEWAY.system || "AETHER"}  ·  ${GATEWAY.org || ""}  ·  `
    ]);

    hostEl = el("span", "lock-host");
    hostEl.textContent = host;
    line.appendChild(hostEl);

    const rest = el("span");
    rest.textContent = "  ·  tty1";
    line.appendChild(rest);

    return line;
}


/* ---------- сессия уже есть ---------- */

async function restored() {
    const guest = Boolean(CONFIG.guest);

    addHeader(guest ? (BYPASS.host || "aether-null") : (GATEWAY.host || "aether-main"));
    addLine([["hid: " + (GATEWAY.hid || ""), "dim"]]);
    addLine();
    await say([["Session restored.", "success"]], 160);
    await say(["User: ", [CONFIG.username || "unknown", guest ? "dim" : "success"]]);
    await say(["Clearance level: ", [clearanceText(CONFIG.clearance), guest ? "warning" : "success"]]);

    if (guest) {
        await say([["Unregistered session: not on this node's account list.", "warning"]]);
    }

    addLine();
    await say(["Loading workspace"], 200);
    await leave();
}


/* ---------- варианты входа ---------- */

function setBusy(value) {
    busy = value;
    output.querySelectorAll(".lock-option").forEach(button => { button.disabled = value; });
}

function stopFollowup() {
    clearTimeout(followupTimer);
}

/* Приглашение всегда одно и стоит последним; когда появляется обходной вариант, в нём появляется «?» */
let promptLine = null;

function showPrompt() {
    if (promptLine) promptLine.remove();

    const keys = output.querySelector("[data-action=bypass]") ? "D/?" : "D";
    promptLine = addLine([`Select [${keys}] `]);
    showCursor(promptLine);
}

function option(action, key, name, tag) {
    const button = el("button", "auth-btn lock-option");
    button.type = "button";
    button.dataset.action = action;

    const main = el("span", "lock-option-main");
    main.textContent = `${key}  ${name}`;

    if (tag) {
        main.textContent = `${key}  ${name.padEnd(22)}`;
        const label = el("span", "lock-option-tag");
        label.textContent = tag;
        main.appendChild(label);
    }

    button.appendChild(main);
    return button;
}

async function connectExternal() {
    setBusy(true);
    stopFollowup();
    hideCursor();
    addLine();
    await say(["> requesting external authority: ", [(GATEWAY.external || {}).label || "DISCORD", "dim"]], 200);
    await say(["Redirecting ..."], 300);

    /* вернёмся на эту же страницу: сессия уже будет, сработает «Session restored» */
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `${URLS.discord}&next=${next}`;
}

async function connectBypass() {
    setBusy(true);
    stopFollowup();
    hideCursor();
    addLine();

    /* запрос идёт параллельно с анимацией, результат проверяем в конце */
    const request = postJson(URLS.guest).catch(() => ({ ok: false, status: 0, data: {} }));
    const from = GATEWAY.host || "aether-main";
    const to = BYPASS.host || "aether-null";

    await flash();
    await say([[`> ${from} ... connection reset`, "warning"]], 220);
    await say(["> hid: ", [GATEWAY.hid || "", "dim"]], 200);

    /* то же железо, другое имя: меняем его прямо в шапке */
    await glitchTo(hostEl, to);
    await say(["> hostname: ", [to, "success"]], 220);
    await say([["> no credentials requested", "dim"]], 200);

    const result = await request;

    if (!result.ok) {
        const code = result.status ? `HTTP ${result.status}` : "no response";
        await glitchTo(hostEl, from);
        await say([[`ERROR: connection refused (${code})`, "error"]]);
        addLine();
        setBusy(false);
        showPrompt();
        return;
    }

    addLine();
    await say(["User: ", [result.data.username || "guest", "dim"]]);
    await say(["Clearance level: ", [clearanceText(result.data.clearance || BYPASS.clearance), "warning"]]);
    await say([["WARNING: session is not registered on this node", "warning"]], 200);
    addLine();
    await say(["Loading workspace"], 200);
    await leave();
}

/* Кто-то дописывает в меню свою строку */
async function appendBypassOption(box) {
    const button = option("bypass", "[ ? ]", "", "");
    const main = button.querySelector(".lock-option-main");
    const label = main.textContent;   // «[ ? ]  »
    main.textContent = label;

    const typed = el("span");
    main.appendChild(typed);
    box.appendChild(button);

    hideCursor();
    await humanType(typed, pick(BYPASS.lines || ["come in"]));

    if (!busy) {
        showPrompt();
    }

    scheduleFollowup(button);
}

/* Если игрок всё ещё ничего не сделал, строка дописывается ещё раз */
function scheduleFollowup(button) {
    const [min, max] = BYPASS.again_after_ms || [20000, 30000];
    const lines = BYPASS.again_lines || [];

    if (!lines.length) return;

    followupTimer = setTimeout(async () => {
        if (busy) return;

        const note = el("span", "lock-option-note");
        button.appendChild(note);

        hideCursor();
        await humanType(note, pick(lines), { typo: false });
        showPrompt();
    }, randomInt(min, max));
}

function buildOptions() {
    const box = el("div", "auth-actions lock-options");

    box.appendChild(option("discord", "[ D ]", "external authority", (GATEWAY.external || {}).label || "DISCORD"));

    box.addEventListener("click", event => {
        const button = event.target.closest("[data-action]");

        if (!button || busy) return;

        if (button.dataset.action === "bypass") connectBypass();
        else if (button.dataset.action === "discord") connectExternal();
    });

    return box;
}

function moveFocus(step) {
    const buttons = Array.from(output.querySelectorAll(".lock-option"));
    const index = buttons.indexOf(document.activeElement);
    const next = (index + step + buttons.length) % buttons.length;
    buttons[next].focus();
}

document.addEventListener("keydown", event => {
    if (event.ctrlKey || event.altKey || event.metaKey) return;

    /* пока идёт анимация, лишняя клавиша пропускает её (но горячие клавиши работают) */
    const isHotkey = ["KeyD", "ArrowUp", "ArrowDown"].includes(event.code) || event.key === "?" || event.key === "/";

    if (animating && !isHotkey) {
        skipping = true;
        return;
    }

    if (!ready || busy) return;

    if (event.code === "KeyD") {
        event.preventDefault();
        connectExternal();
    } else if ((event.key === "?" || event.key === "/") && output.querySelector("[data-action=bypass]")) {
        event.preventDefault();
        connectBypass();
    } else if (event.code === "ArrowDown") {
        event.preventDefault();
        moveFocus(1);
    } else if (event.code === "ArrowUp") {
        event.preventDefault();
        moveFocus(-1);
    }
});

document.addEventListener("pointerdown", () => {
    if (animating) skipping = true;
});


/* ---------- запуск ---------- */

async function intro() {
    const host = GATEWAY.host || "aether-main";

    await dotted(`connecting to ${host} `, "OK", "success", 600);
    addLine();

    addHeader(host);
    await say([["hid: " + (GATEWAY.hid || ""), "dim"]], 160);
    addLine();

    await say([["*** NOTICE ***", "warning"]], 100);
    for (const row of GATEWAY.notice || []) {
        await say([[row, "dim"]], 90);
    }
    addLine();

    await say(["Authentication required."], 160);
    addLine();
}

async function run() {
    try {
        if (CONFIG.authenticated) {
            animating = false;
            await restored();
            return;
        }

        await intro();

        const box = buildOptions();
        output.appendChild(box);
        showPrompt();
        box.querySelector(".lock-option").focus();
        ready = true;
        hint.hidden = true;

        /* через пару секунд кто-то дописывает строку */
        await wait(BYPASS.delay_ms || 2200);
        await appendBypassOption(box);
        animating = false;
    } catch (error) {
        console.error(error);
    }
}

run();
