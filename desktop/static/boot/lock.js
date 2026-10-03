const CONFIG = JSON.parse(document.getElementById("boot-config").textContent);

/* Адреса относительные от lock/ (поэтому "../"), как и раньше:
   страница должна открываться со слэшем в конце */
const URLS = {
    guest: "../auth/guest/",
    discord: "../accounts/discord/login/?process=login",
    desktop: "../desktop/"
};

const lock = document.getElementById("lock");
const message = lock.querySelector(".lock-message");
let busy = false;

const wait = ms => new Promise(resolve => setTimeout(resolve, ms));

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

function say(text, style = "") {
    message.className = style ? `lock-message ${style}` : "lock-message";
    message.textContent = text;
}

function setBusy(value) {
    busy = value;
    lock.classList.toggle("is-busy", value);
}

/* ---------- часы (пока реальное время) ---------- */

function tick() {
    const now = new Date();
    document.getElementById("lock-time").textContent =
        now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
    document.getElementById("lock-date").textContent =
        now.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });
}

/* ---------- разблокировка ---------- */

async function unlock({ username, clearance, tile = null }) {
    setBusy(true);
    lock.classList.add("is-unlocking");
    if (tile) tile.classList.add("is-chosen");

    say(`Welcome, ${username} · ${clearance.level} (${clearance.label})`);
    await wait(1400);

    lock.classList.add("is-leaving");
    await wait(700);

    window.location.href = URLS.desktop;
}

/* ---------- действия ---------- */

async function chooseGuest(tile) {
    setBusy(true);
    say("Requesting guest session ...");

    let result;
    try {
        result = await postJson(URLS.guest);
    } catch (error) {
        result = { ok: false, status: 0, data: {} };
    }

    if (!result.ok) {
        const code = result.status ? `HTTP ${result.status}` : "no response";
        say(`ERROR: guest access unavailable (${code})`, "error");
        setBusy(false);
        return;
    }

    await unlock({ username: result.data.username, clearance: result.data.clearance, tile });
}

async function chooseDiscord() {
    setBusy(true);
    say("Redirecting to DISCORD authority ...");
    await wait(600);

    /* вернёмся на эту же страницу: сессия уже будет, сработает автоматическая разблокировка */
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `${URLS.discord}&next=${next}`;
}

lock.addEventListener("click", event => {
    const tile = event.target.closest("[data-action]");
    if (!tile || busy) return;

    if (tile.dataset.action === "guest") chooseGuest(tile);
    else if (tile.dataset.action === "discord") chooseDiscord();
});

/* ---------- запуск ---------- */

tick();
setInterval(tick, 1000);
requestAnimationFrame(() => lock.classList.add("is-ready"));

if (CONFIG.authenticated) {
    unlock({ username: CONFIG.username, clearance: CONFIG.clearance });
} else {
    lock.querySelector(".user-tile").focus();
}