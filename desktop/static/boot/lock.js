/* =========================================================
   AETHER.OS GATEWAY
   ---------------------------------------------------------
   Экран входа после загрузки. Узел подаёт себя как удалённую
   машину: показывает своё состояние и баннер, а вход предлагает
   двумя способами.

     [ G ] гость: не логин, а дыра. На aether-null оставили
           открытым сервис, и кто-то сделал это намеренно, но не
           игрок. Текст про дыру приходит с сервера (gateway).
     [ D ] внешний авторитет (Discord).

   Если сессия уже есть, экран просто показывает «Session restored»
   и идёт дальше. Допуски проверяются на сервере: этот файл только
   рисует и отправляет запросы.
   ========================================================= */

const CONFIG = JSON.parse(document.getElementById("boot-config").textContent);
const GATEWAY = CONFIG.gateway || {};

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

const LABEL_WIDTH = 18;

let skipping = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let typing = true;
let busy = false;
let cursor = null;


/* ---------- вывод строк (тот же вид, что у загрузки) ---------- */

const wait = ms => (skipping ? Promise.resolve() : new Promise(resolve => setTimeout(resolve, ms)));

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

function showCursor(line) {
    hideCursor();
    cursor = el("span", "boot-cursor");
    line.appendChild(cursor);
}

/* parts: строка или массив [текст, стиль]; стили: success, warning, error, dim */
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
    addLine(parts);
    await wait(delay);
}

const field = label => label.padEnd(LABEL_WIDTH);

/* «Метка: ........ СТАТУС», точки набираются по одной */
async function probe(label, status, style = "success", ms = 520) {
    const line = addLine([field(label)]);
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


/* ---------- переходы ---------- */

async function leave() {
    screen.classList.add("is-leaving");
    await wait(700);
    window.location.href = URLS.desktop;
}

function clearanceText(clearance) {
    return clearance ? `${clearance.level} (${clearance.label})` : "L? (UNKNOWN)";
}

/* Сессия уже есть: показываем, кто и с каким допуском, и идём на стол */
async function restored() {
    const guest = Boolean(CONFIG.guest);

    await say(["AETHER OS 9.1 (Halcyon)  " + CONFIG.node + "  tty1"], 120);
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


/* ---------- выбор способа входа ---------- */

function setBusy(value) {
    busy = value;
    output.querySelectorAll(".lock-option").forEach(button => { button.disabled = value; });
}

async function connectGuest() {
    const guest = GATEWAY.guest || {};
    const machine = guest.machine || "aether-null";

    setBusy(true);
    hideCursor();
    addLine();

    /* запрос идёт параллельно с анимацией, результат проверяем в конце */
    const request = postJson(URLS.guest).catch(() => ({ ok: false, status: 0, data: {} }));

    await say(["> connecting to ", [machine, "dim"]], 140);
    await probe("> " + (guest.service || "service"), "ACCEPTED", "warning", 700);
    await say([["> no credentials requested", "dim"]], 160);

    const result = await request;

    if (!result.ok) {
        const code = result.status ? `HTTP ${result.status}` : "no response";
        await say([[`ERROR: connection refused (${code})`, "error"]]);
        addLine();
        setBusy(false);
        focusFirstOption();
        showPrompt();
        return;
    }

    addLine();
    await say(["User: ", [(result.data.username || "guest"), "dim"]]);
    await say(["Clearance level: ", [clearanceText(result.data.clearance || guest.clearance), "warning"]]);
    await say([["WARNING: session is not registered on this node", "warning"]], 200);
    addLine();
    await say(["Loading workspace"], 200);
    await leave();
}

async function connectExternal() {
    const external = GATEWAY.external || {};

    setBusy(true);
    hideCursor();
    addLine();
    await say(["> requesting external authority: ", [external.label || "DISCORD", "dim"]], 200);
    await say(["Redirecting ..."], 300);

    /* вернёмся на эту же страницу: сессия уже будет, сработает «Session restored» */
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `${URLS.discord}&next=${next}`;
}

function option(action, key, name, tag, notes) {
    const button = el("button", "auth-btn lock-option");
    button.type = "button";
    button.dataset.action = action;

    const main = el("span", "lock-option-main");
    main.textContent = `${key}  ${name.padEnd(22)}`;

    /* метка допуска отдельным элементом: на узком экране она переносится на свою строку */
    const label = el("span", "lock-option-tag");
    label.textContent = tag;
    main.appendChild(label);

    button.appendChild(main);

    notes.forEach(([value, style]) => {
        const note = el("span", `lock-option-note ${style}`);
        note.textContent = value;
        button.appendChild(note);
    });

    return button;
}

function buildOptions() {
    const guest = GATEWAY.guest || {};
    const external = GATEWAY.external || {};
    const box = el("div", "auth-actions lock-options");

    box.appendChild(option("guest", "[ G ]", "guest", `clearance ${clearanceText(guest.clearance)}`, [
        [`! unauthenticated ${guest.service || "service"} on ${guest.machine || "node"} accepts connections`, "warning"],
        [`  enabled ${guest.opened || "?"} by: ${guest.by || "unknown"}`, "dim"]
    ]));

    box.appendChild(option("discord", "[ D ]", "external authority", external.label || "DISCORD", []));

    box.addEventListener("click", event => {
        const button = event.target.closest("[data-action]");

        if (!button || busy) return;

        if (button.dataset.action === "guest") connectGuest();
        else if (button.dataset.action === "discord") connectExternal();
    });

    return box;
}

function focusFirstOption() {
    const first = output.querySelector(".lock-option");
    if (first) first.focus();
}

function showPrompt() {
    const line = addLine(["Select [G/D] "]);
    showCursor(line);
}

function moveFocus(step) {
    const buttons = Array.from(output.querySelectorAll(".lock-option"));
    const index = buttons.indexOf(document.activeElement);
    const next = (index + step + buttons.length) % buttons.length;
    buttons[next].focus();
}

document.addEventListener("keydown", event => {
    /* пока идёт печать, любая клавиша пропускает анимацию */
    if (typing) {
        skipping = true;
        return;
    }

    if (busy || event.ctrlKey || event.altKey || event.metaKey) return;

    if (event.code === "KeyG") {
        event.preventDefault();
        connectGuest();
    } else if (event.code === "KeyD") {
        event.preventDefault();
        connectExternal();
    } else if (event.code === "ArrowDown") {
        event.preventDefault();
        moveFocus(1);
    } else if (event.code === "ArrowUp") {
        event.preventDefault();
        moveFocus(-1);
    }
});

document.addEventListener("pointerdown", () => {
    if (typing) skipping = true;
});


/* ---------- запуск ---------- */

async function intro() {
    await say(["AETHER OS 9.1 (Halcyon)  " + CONFIG.node + "  tty1"], 140);
    addLine();

    await say([field("Remote console:") + "SOL attached"]);
    await say([field("Network uplink:") + "ETH0 UP 10Gbps"]);
    await probe("Tamper seal:", "INTACT");
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
            typing = false;
            await restored();
            return;
        }

        await intro();
        typing = false;
        hint.hidden = true;

        output.appendChild(buildOptions());
        showPrompt();
        focusFirstOption();
    } catch (error) {
        console.error(error);
    }
}

run();
