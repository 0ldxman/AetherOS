/* =========================================================
   AETHER.OS BOOT ENGINE
   ---------------------------------------------------------
   Этапы: подключение -> BIOS -> загрузчик -> ядро
          -> службы. Дальше работает login.js (событие
          aether:boot-complete): мини-загрузка, вход, рабочий стол

   Возможности:
   - пропуск по Esc / Space / Enter или клику по подсказке
   - короткая загрузка при повторных заходах: включается
     параметром shortBootOnRepeat в boot-config (по умолчанию выкл.)
   - данные узла можно передать из Django (boot-config)
   - ?boot=full в адресе принудительно включает полную версию
   ========================================================= */


/* =========================================================
   CONFIG
   ---------------------------------------------------------
   Значения по умолчанию. Из Django их можно переопределить:

   В шаблоне:
       {{ boot_config|json_script:"boot-config" }}

   Во view:
       boot_config = {
           "node": "NODE-02",
           "serial": "AE-0002-1180-A",
           "username": request.user.username,
           "clearance": {"level": "L3", "label": "RESTRICTED"},
           "redirectUrl": "/desktop/",
       }

   Вложенные объекты (clearance, lastLogin) передаются
   целиком, а не по частям.
   ========================================================= */

function loadConfig() {
    const defaults = {
        node: "NODE-07",
        domain: "AETHER",
        serial: "AE-0007-4471-C",
        memoryKB: 67108864,
        username: "operator",
        clearance: { level: "L3", label: "RESTRICTED" },
        lastLogin: {
            date: "2061-03-28 02:14",
            from: "NODE-02",
            anomaly: true
        },
        /*
         * Куда перейти после загрузки.
         * null = никуда не переходить, только отправить
         * событие "aether:boot-complete" (на него можно
         * повесить показ рабочего стола).
         */
        redirectUrl: null
    };

    const element = document.getElementById("boot-config");

    if (!element) {
        return defaults;
    }

    try {
        return { ...defaults, ...JSON.parse(element.textContent) };
    } catch (error) {
        console.warn("boot-config: не удалось разобрать JSON", error);
        return defaults;
    }
}

const CONFIG = loadConfig();


/* -----------------------------------------
   DOM
   ----------------------------------------- */

const output = document.getElementById("boot-output");
const screen = document.getElementById("boot-screen");


/* -----------------------------------------
   STATE
   ----------------------------------------- */

let currentLine = null;
let currentCursor = null;

/* Множитель времени: 1 = обычно, меньше = быстрее */
let speed = 1;

let aborted = false;
let abortCurrentSleep = null;
let finished = false;
let hintElement = null;

/*
 * Сигнал пропуска. Им "прерывается" любая ожидающая
 * анимация, он пролетает вверх по цепочке await
 * до runBoot(), где и ловится.
 */
class BootAbort extends Error {}


/* =========================================================
   BASIC UTILITIES
   ========================================================= */

/* Обычное ожидание, которое нельзя прервать */
function delay(ms) {
    return new Promise(resolve => {
        setTimeout(resolve, ms);
    });
}

/* Ожидание, которое прерывается пропуском */
function sleep(ms) {
    return new Promise((resolve, reject) => {

        if (aborted) {
            reject(new BootAbort());
            return;
        }

        const timer = setTimeout(() => {
            abortCurrentSleep = null;
            resolve();
        }, ms * speed);

        abortCurrentSleep = () => {
            clearTimeout(timer);
            abortCurrentSleep = null;
            reject(new BootAbort());
        };
    });
}

async function pause(ms) {
    await sleep(ms);
}

function random(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
}


/* =========================================================
   LINE MANAGEMENT
   ========================================================= */

function newLine() {
    const line = document.createElement("div");
    line.className = "boot-line";
    output.appendChild(line);
    currentLine = line;

    /* Прокрутка вниз, чтобы новые строки были видны */
    output.scrollTop = output.scrollHeight;

    return line;
}

function ensureLine() {
    if (!currentLine) {
        newLine();
    }
    return currentLine;
}

/* Создаёт span с нужным стилем и добавляет в текущую строку */
function createSpan(style = null) {
    const line = ensureLine();
    const span = document.createElement("span");

    if (style) {
        span.classList.add(style);
    }

    line.appendChild(span);
    return span;
}


/* =========================================================
   CURSOR
   ========================================================= */

function showCursor() {
    hideCursor();
    const line = ensureLine();
    currentCursor = document.createElement("span");
    currentCursor.className = "boot-cursor";
    line.appendChild(currentCursor);
}

function hideCursor() {
    if (currentCursor) {
        currentCursor.remove();
        currentCursor = null;
    }
}


/* =========================================================
   TEXT
   ========================================================= */

async function text(value, style = null) {
    hideCursor();
    const span = createSpan(style);
    span.textContent = value;
    showCursor();
}


/* =========================================================
   TYPEWRITER
   ========================================================= */

async function type(value, speedMs = 20, style = null) {
    hideCursor();
    const span = createSpan(style);

    for (const character of value) {
        span.textContent += character;
        await sleep(speedMs);
    }

    showCursor();
}


/* =========================================================
   BURST
   ---------------------------------------------------------
   Текст появляется кусками случайного размера
   ========================================================= */

async function burst(value, min = 2, max = 5, delayMin = 20, delayMax = 60, style = null) {
    hideCursor();
    const span = createSpan(style);

    let position = 0;

    while (position < value.length) {
        const size = random(min, max);

        span.textContent += value.slice(position, position + size);
        position += size;

        await sleep(random(delayMin, delayMax));
    }

    showCursor();
}


/* =========================================================
   SPINNER
   ========================================================= */

async function spinner(duration, interval = 100) {
    hideCursor();
    const element = createSpan("boot-spinner");

    const frames = ["|", "/", "-", "\\"];
    let frame = 0;

    element.textContent = frames[0];

    const timer = setInterval(() => {
        frame = (frame + 1) % frames.length;
        element.textContent = frames[frame];
    }, interval);

    try {
        await sleep(duration);
    } finally {
        /* Выполнится и при пропуске, таймер не останется висеть */
        clearInterval(timer);
        element.remove();
    }

    showCursor();
}


/* =========================================================
   MEMORY COUNTER
   ---------------------------------------------------------
   Число растёт от 0 до total, как в настоящем POST
   ========================================================= */

async function memoryCounter(total, duration = 1400) {
    hideCursor();
    const span = createSpan();

    const steps = 28;

    for (let i = 1; i <= steps; i++) {
        span.textContent = `${Math.floor(total * i / steps)}K`;
        await sleep(duration / steps);
    }

    showCursor();
}


/* =========================================================
   COUNTDOWN
   ---------------------------------------------------------
   "Auto-boot in 3s..." -> 2s -> 1s
   ========================================================= */

async function countdown(seconds) {
    hideCursor();
    const span = createSpan();

    for (let s = seconds; s > 0; s--) {
        span.textContent = `Auto-boot in ${s}s...`;
        await sleep(1000);
    }

    showCursor();
}


/* =========================================================
   ERASE
   ========================================================= */

/* Стирание по одному символу с задержкой (эффект Backspace) */
async function erase(count, speedMs = 30) {
    const line = ensureLine();
    hideCursor();

    for (let i = 0; i < count; i++) {
        const element = line.lastElementChild;

        if (!element) {
            break;
        }

        const content = element.textContent;

        if (!content.length) {
            element.remove();
            continue;
        }

        element.textContent = content.slice(0, -1);
        await sleep(speedMs);
    }

    showCursor();
}

/* Мгновенное стирание N символов */
async function eraseInstant(count) {
    const line = ensureLine();
    hideCursor();

    for (let i = 0; i < count; i++) {
        const element = line.lastElementChild;

        if (!element) {
            break;
        }

        const content = element.textContent;

        if (!content.length) {
            element.remove();
            continue;
        }

        element.textContent = content.slice(0, -1);
    }

    showCursor();
}

/* Очищает всю текущую строку целиком, считать символы не нужно */
function clearLine() {
    hideCursor();
    ensureLine().innerHTML = "";
    showCursor();
}


/* =========================================================
   NEW LINE / CLEAR
   ========================================================= */

async function newline() {
    hideCursor();
    newLine();
    showCursor();
}

async function clearScreen() {
    hideCursor();
    output.innerHTML = "";
    currentLine = null;
}


/* =========================================================
   COMMAND
   ---------------------------------------------------------
   Строка, которую "вводит" игрок
   ========================================================= */

async function command(value, speedMs = 30) {
    await text("> ");
    await type(value, speedMs);
}


/* =========================================================
   SCREEN FLASH
   ---------------------------------------------------------
   Использует delay, а не sleep, чтобы работать
   и после пропуска загрузки
   ========================================================= */

async function flash(duration = 80) {
    screen.style.filter = "brightness(2)";
    await delay(duration);
    screen.style.filter = "";
}


/* =========================================================
   FADE
   ---------------------------------------------------------
   Плавное появление и исчезновение текста терминала.
   Используют delay, поэтому работают и после пропуска.
   ========================================================= */

async function fadeOut(ms = 400) {
    output.style.transition = `opacity ${ms}ms ease`;
    output.style.opacity = "0";
    await delay(ms);
}

async function fadeIn(ms = 400) {
    output.style.transition = `opacity ${ms}ms ease`;
    output.style.opacity = "1";
    await delay(ms);
}


/* =========================================================
   HELPERS FOR BOOT SCREENS
   ========================================================= */

/* Выравнивание подписей в BIOS: "Chipset:         ..." */
function field(label) {
    return label.padEnd(17);
}

/*
 * "..............", спиннер, результат.
 * Используется для проверок в BIOS.
 */
async function probe(ms, result, style = "success") {
    await type("..............", 15);
    await spinner(ms);
    await text(` ${result}`, style);
}

/* Метка времени ядра: [    0.004211]. null = неизвестное время */
function stamp(time) {
    const value = time === null ? "X.XXXXXX" : time.toFixed(6);
    return `[${value.padStart(12)}]`;
}

/* Текущее "время ядра", от него считаются паузы между строками */
let kernelTime = 0;

/* Обычная строка ядра, пауза равна разнице времён */
async function kernelLine(time, message, style = null) {
    await pause((time - kernelTime) * 1000);
    kernelTime = time;
    await text(`${stamp(time)} ${message}`, style);
    await newline();
}

/*
 * Строка ядра с ожиданием: сначала появляется с неизвестным
 * временем (X.XXXXXX), спиннер крутится ровно столько,
 * сколько "длилась" операция, потом строка подменяется
 * настоящей.
 */
async function kernelTask(time, message, result = "OK") {
    const wait = (time - kernelTime) * 1000;

    await text(`${stamp(null)} ${message} `);
    await spinner(wait);
    kernelTime = time;

    clearLine();
    await text(`${stamp(time)} ${message} `);
    await text(result, "success");
    await newline();
}

/*
 * Служба systemd: [ WAIT ] -> [  OK  ] / [ WARN ] / [FAILED]
 *   wait  - текст во время запуска
 *   done  - текст после запуска
 *   state - "ok" | "warn" | "fail"
 *   note  - приглушённая приписка в конце (необязательно)
 */
async function service({ wait, done, state = "ok", note = null, ms = null }) {
    await text(`[ WAIT ] ${wait}`, "dim");
    await spinner(ms ?? random(300, 700));
    clearLine();

    if (state === "ok") {
        await text("[  OK  ] ", "success");
        await text(done);
    } else if (state === "warn") {
        await text("[ WARN ] ", "warning");
        await text(done, "warning");
    } else {
        await text("[FAILED] ", "error");
        await text(done, "error");
    }

    if (note) {
        await text(note, "dim");
    }

    await newline();
}


/* =========================================================
   STAGE 0: CONNECT
   ========================================================= */

async function stageConnect() {
    showCursor();

    await command(`CONNECT ${CONFIG.node}.${CONFIG.domain}`);
    await pause(400);
    await newline();

    await type("Establishing secure channel", 15, "dim");
    await pause(300);
    await burst("................", 2, 4, 20, 50, "dim");
    await text(" OK", "success");
    await pause(300);
    await newline();

    await type("Serial-over-LAN session opened. Escape sequence: ~.", 15, "dim");
    await pause(300);
    await newline();

    await text("Waiting for remote console", "dim");
    await type("..............", 15, "dim");
    await spinner(1800);
}


/* =========================================================
   STAGE 1: BIOS / POST
   ========================================================= */

async function stageBios() {
    await clearScreen();
    await pause(300);

    await text("AETHER-BIOS v4.12.0  (C) 2061 Aether Dynamics Consortium");
    await newline();
    await text(`Node: ${CONFIG.node}   Serial: ${CONFIG.serial}`);
    await newline();
    await text("Build: 2061-03-14 / secure-boot chain v3");
    await newline();
    await pause(300);
    await newline();

    await text("CPU0: AETHER QX-9 Quantum-Assisted   8 cores   3.80 GHz");
    await pause(300);
    await newline();

    await text(field("Memory Testing:"));
    await memoryCounter(CONFIG.memoryKB);
    await text(" OK", "success");
    await text("  (ECC, quad channel)", "dim");
    await pause(300);
    await newline();

    await text(field("Chipset:") + "AETHER Nexus-Q2");
    await pause(300);
    await newline();

    await text(field("Crypto module:") + "TPM-X 3.0");
    await probe(1800, "PRESENT");
    await pause(300);
    await newline();

    await text(field("Tamper seal:"));
    await spinner(1800);
    await text("INTACT", "success");
    await pause(300);
    await newline();
    await newline();

    await text("Primary Storage Master:  AETHER-VAULT 4TB (encrypted)");
    await pause(300);
    await newline();
    await text("Primary Storage Slave:   ");
    await text("None", "dim");
    await pause(300);
    await newline();
    await text("Network uplink:          ETH0 UP 10Gbps   ETH1 NO CARRIER");
    await pause(300);
    await newline();
    await newline();

    await text("Verifying firmware signature");
    await probe(1800, "OK");
    await newline();
    await newline();

    await text("Press <DEL> for SETUP, <F12> for boot menu", "dim");
    await pause(1000);
}


/* =========================================================
   STAGE 2: BOOT MANAGER
   ========================================================= */

async function stageBootManager() {
    await clearScreen();

    await text("AETHER BOOT MANAGER 2.12");
    await newline();
    await pause(1000);
    await newline();

    await text("> AETHER OS 9.1 (Halcyon)");
    await newline();
    await text("  AETHER OS 9.1 (Halcyon) - recovery mode      ", "dim");
    await text("[CLEARANCE L5 REQUIRED]", "error");
    await newline();
    await text("  AETHER OS 8.4 (legacy)", "dim");
    await newline();
    await text("  Memory diagnostic", "dim");
    await newline();
    await newline();

    await countdown(3);
    await flash();
}


/* =========================================================
   STAGE 3: KERNEL
   ========================================================= */

async function stageKernel() {
    await clearScreen();
    kernelTime = 0;

    await kernelLine(0.000000, "Aether kernel 9.1.4-hal (builder@forge-03) #1 SMP 2061-03-02");
    await kernelLine(0.000000, "Command line: root=/dev/vault0 ro console=ttyS0 quiet_level=2");
    await kernelLine(0.004211, "CPU: detected AETHER QX-9, 8 cores, quantum coprocessor online");
    await kernelLine(0.312874, "tamper: chassis seal intact");
    await kernelTask(0.801544, "vault: unlocking /dev/vault0 using TPM-bound key ...");
    await kernelTask(1.120377, "integrity: verifying system image .......");
    await kernelLine(1.204910, "AEFS (vault0): mounted, journal clean");
    await kernelLine(1.377002, "netfilter: default policy DROP (inbound)");
    await kernelLine(1.402118, `audit: logging enabled, sink=NODE-00.${CONFIG.domain}`);
    await newline();
}


/* =========================================================
   STAGE 4: SERVICES
   ---------------------------------------------------------
   Весь сюжет этого этапа лежит в этом списке.
   Добавить службу = добавить один объект.
   ========================================================= */

const SERVICES = [
    {
        wait: "Starting Secure Key Agent...",
        done: "Started Secure Key Agent."
    },
    {
        wait: "Starting Clearance Daemon (aetherd-auth)...",
        done: "Started Clearance Daemon (aetherd-auth)."
    },
    {
        wait: "Mounting /archive...",
        done: "Mounted /archive",
        note: " (read-only)."
    },
    {
        wait: `Starting Uplink to NODE-00.${CONFIG.domain}...`,
        done: `Started Uplink to NODE-00.${CONFIG.domain}.`
    },
    {
        wait: "Checking sector telemetry...",
        done: "Sector 12 telemetry: no response, skipping.",
        state: "warn"
    },
    {
        wait: "Starting Message Relay...",
        done: "Started Message Relay."
    },
    {
        wait: "Starting Archive Service...",
        done: "Started Archive Service."
    },
    {
        wait: "Starting Legacy Watcher...",
        done: "Failed to start Legacy Watcher (code 0x0F).",
        state: "fail"
    },
    {
        wait: "Reaching target Aether Desktop...",
        done: "Reached target Aether Desktop."
    }
];

async function stageServices() {
    for (const item of SERVICES) {
        await service(item);
    }
    await pause(1200);
}


/* =========================================================
   SKIP / SEEN
   ========================================================= */

function seenKey() {
    return `aether_boot_seen:${CONFIG.node}`;
}

function hasSeenBoot() {
    try {
        return sessionStorage.getItem(seenKey()) === "1";
    } catch (error) {
        return false;
    }
}

function markSeen() {
    try {
        sessionStorage.setItem(seenKey(), "1");
    } catch (error) {
        /* sessionStorage может быть недоступен, это не страшно */
    }
}

function forceFullBoot() {
    return new URLSearchParams(window.location.search).get("boot") === "full";
}

function abortBoot() {
    aborted = true;

    if (abortCurrentSleep) {
        abortCurrentSleep();
    }
}

function onSkipKey(event) {
    if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
    }

    if (event.code === "Escape" || event.code === "Space" || event.code === "Enter") {
        event.preventDefault();
        abortBoot();
    }
}

function attachSkip() {
    document.addEventListener("keydown", onSkipKey);

    hintElement = document.createElement("div");
    hintElement.className = "boot-hint";
    hintElement.textContent = "[ ESC ] skip boot";
    hintElement.style.pointerEvents = "auto";
    hintElement.style.cursor = "pointer";
    hintElement.addEventListener("click", abortBoot);
    screen.appendChild(hintElement);
}

function detachSkip() {
    document.removeEventListener("keydown", onSkipKey);

    if (hintElement) {
        hintElement.remove();
        hintElement = null;
    }
}


/* =========================================================
   FINISH
   ========================================================= */

async function finishBoot() {
    if (finished) {
        return;
    }
    finished = true;

    detachSkip();
    hideCursor();

    /* Сбрасываем пропуск, иначе sleep() в login.js будет сразу падать */
    aborted = false;
    abortCurrentSleep = null;

    await fadeOut(500);

    if (CONFIG.redirectUrl) {
        window.location.href = CONFIG.redirectUrl;
    } else {
        document.dispatchEvent(new CustomEvent("aether:boot-complete"));
    }
}


/* =========================================================
   RUN
   ========================================================= */

async function runBoot() {
    const short = CONFIG.shortBootOnRepeat === true && hasSeenBoot() && !forceFullBoot();

    /* Повторный заход: только подключение и службы, вдвое быстрее */
    speed = short ? 0.5 : 1;

    attachSkip();

    try {
        await stageConnect();

        if (!short) {
            await stageBios();
            await stageBootManager();
            await stageKernel();
        }

        await stageServices();
        markSeen(); /* только если загрузка дошла до конца */
    } catch (error) {
        /* Пропуск это не ошибка, а остальное покажем в консоли */
        if (!(error instanceof BootAbort)) {
            console.error(error);
        }
    } finally {
        await finishBoot();
    }
}


/* =========================================================
   START
   ========================================================= */

document.addEventListener("DOMContentLoaded", () => {
    runBoot();
});

document.addEventListener("aether:boot-complete", async () => {
    await fadeOut(400);
    window.location.href = "lock/";
});