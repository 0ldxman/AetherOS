const clock = document.getElementById("clock");
const dateEl = document.getElementById("date");

function formatDate(now) {
  return now.toLocaleDateString("sv-SE");
}

function updateClock() {
  const now = new Date();
  clock.textContent = now.toTimeString().slice(0, 8);
  dateEl.textContent = formatDate(now);
}

updateClock();
setInterval(updateClock, 1000);


//PING
// Чисто декор: значение плавно дрейфует около базового, изредка скачет вверх.
const pingValue = document.getElementById('ping-value');

const PING_BASE = 42;
const PING_MIN = 15;
const PING_MAX = 180;
let ping = PING_BASE;

function randomBetween(min, max) {
    return min + Math.random() * (max - min);
}

function nextPing() {
    if (Math.random() < 0.03) {
        // редкий скачок
        return PING_BASE + randomBetween(70, 120);
    }

    // тянемся к базовому значению и чуть колеблемся
    const next = ping + (PING_BASE - ping) * 0.3 + randomBetween(-5, 5);
    return Math.min(PING_MAX, Math.max(PING_MIN, next));
}

function updatePing() {
    ping = nextPing();
    const value = Math.round(ping);

    pingValue.textContent = value;

    if (value <= 90) {
        document.documentElement.style.setProperty(
            '--ping-color',
            'var(--accent-green)'
        );
    } else if (value <= 150) {
        document.documentElement.style.setProperty(
            '--ping-color',
            'var(--accent-warn)'
        );
    } else {
        document.documentElement.style.setProperty(
            '--ping-color',
            'var(--accent-error)'
        );
    }
}

function schedulePing() {
    updatePing();

    const delay = randomBetween(2000, 4000);
    setTimeout(schedulePing, delay);
}

schedulePing();


const desktop = document.getElementById("desktop");
const template = document.getElementById("window-template");

// Окно терминала получает класс app-terminal: стиль может показывать его иначе (консоль рядом с приложением).
const terminalPath = desktop.dataset.terminalUrl ? new URL(desktop.dataset.terminalUrl, window.location.href).pathname : null;

function isTerminalUrl(url) {
  return Boolean(terminalPath) && new URL(url, window.location.href).pathname === terminalPath;
}
const openWindows = {};


/* ==================================================
   Запоминание раскладки
   Иконки и положение окон лежат в localStorage отдельно для каждой
   пары «игрок и машина» (ключ приходит с сервера). Список открытых
   окон лежит в sessionStorage и восстанавливается только после
   обычной перезагрузки страницы, но не после нового входа.
   ================================================== */

const layoutKey = desktop.dataset.layoutKey || "default";
const LAYOUT_STORE = "aether-desktop:v1:" + layoutKey;
const OPEN_STORE = "aether-desktop-open:v1:" + layoutKey;
const MAX_SAVED_WINDOWS = 40;

function readJson(storage, key, fallback) {
  try {
    const value = JSON.parse(storage.getItem(key));
    return value === null ? fallback : value;
  } catch (error) {
    return fallback;
  }
}

function writeJson(storage, key, value) {
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch (error) {
    // хранилище недоступно или переполнено: стол работает, просто ничего не запоминает
  }
}

function readLayout() {
  const layout = readJson(localStorage, LAYOUT_STORE, {});
  return {
    icons: layout.icons && typeof layout.icons === "object" ? layout.icons : {},
    windows: layout.windows && typeof layout.windows === "object" ? layout.windows : {},
  };
}

function updateLayout(change) {
  const layout = readLayout();
  change(layout);
  writeJson(localStorage, LAYOUT_STORE, layout);
}

function resetLayout() {
  try {
    localStorage.removeItem(LAYOUT_STORE);
    sessionStorage.removeItem(OPEN_STORE);
  } catch (error) {
    // см. writeJson
  }
}

// Окна документов, инфобоксов, ассетов и сессий открываются в большом числе:
// положение запоминается на вид окна, а не на каждое окно отдельно.
function geometryKey(id) {
  const kind = /^(doc|info|asset|session)-/.exec(String(id));
  return kind ? kind[1] : String(id);
}

const MIN_WINDOW_W = 200;
const MIN_WINDOW_H = 120;

// WinBox считает координаты от окна браузера, а не от стола.
// Заголовок окна нарисован над рамкой (высота вкладки и два пикселя рамки), поэтому
// выше этой границы окно не поднимается: иначе вкладка наезжает на панель задач
// и закрывает кнопку меню подключения.
const taskbar = document.getElementById("taskbar");
const TAB_HEIGHT =
  parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--tab-h")) || 26;
// Стиль ОС может поставить панель снизу (--tab-outside: 0 — заголовок внутри окна): тогда сверху отступа нет.
const rootStyle = getComputedStyle(document.documentElement);
const TAB_OUTSIDE = rootStyle.getPropertyValue("--tab-outside").trim() !== "0";
const BAR_TOP = taskbar.getBoundingClientRect().top < 1 ? taskbar.offsetHeight : 0;
// Развёрнутое окно не заходит на панель снизу: либо это сама панель задач, либо отдельная полоса оболочки с data-reserve-bottom.
const reserveBottom = document.querySelector("[data-reserve-bottom]");
// Сетка знакомест (стиль ОС может задать --grid-x и --grid-y в пикселях): положение и размер окон кратны клетке.
const GRID_X = parseFloat(rootStyle.getPropertyValue("--grid-x")) || 0;
const GRID_Y = parseFloat(rootStyle.getPropertyValue("--grid-y")) || 0;

function snapTo(value, grid) {
  return grid ? Math.round(value / grid) * grid : value;
}

function snapGeometry(g) {
  return { x: snapTo(g.x, GRID_X), y: snapTo(g.y, GRID_Y), width: snapTo(g.width, GRID_X), height: snapTo(g.height, GRID_Y) };
}

const WINDOW_BOTTOM = taskbar.getBoundingClientRect().top < 1 ? (reserveBottom ? reserveBottom.offsetHeight : 0) : taskbar.offsetHeight;
const WINDOW_TOP = BAR_TOP + (TAB_OUTSIDE ? TAB_HEIGHT + 2 : 0);

// Размер стола мог измениться с прошлого раза: окно не должно оказаться за краем
function clampGeometry(g) {
  const maxW = desktop.clientWidth;
  const bottom = BAR_TOP + desktop.clientHeight; // нижний край стола в координатах окна браузера
  const maxH = bottom - WINDOW_TOP;

  const width = Math.min(Math.max(g.width, MIN_WINDOW_W), maxW);
  const height = Math.min(Math.max(g.height, MIN_WINDOW_H), maxH);

  return snapGeometry({
    width,
    height,
    x: Math.min(Math.max(g.x, 0), Math.max(0, maxW - width)),
    y: Math.min(Math.max(g.y, WINDOW_TOP), Math.max(WINDOW_TOP, bottom - height)),
  });
}

function isNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function savedGeometry(id) {
  const saved = readLayout().windows[geometryKey(id)];

  if (!saved || ![saved.x, saved.y, saved.w, saved.h].every(isNumber)) {
    return null;
  }

  return clampGeometry({ x: saved.x, y: saved.y, width: saved.w, height: saved.h });
}

const saveTimers = {};

// Сохраняем после паузы: при перетаскивании события идут десятками в секунду
function scheduleGeometrySave(win, id) {
  const key = geometryKey(id);

  clearTimeout(saveTimers[key]);
  saveTimers[key] = setTimeout(() => {
    // свёрнутое и развёрнутое окно своего «обычного» положения не показывает
    if (win.min || win.max) return;

    updateLayout((layout) => {
      layout.windows[key] = {
        x: Math.round(win.x),
        y: Math.round(win.y),
        w: Math.round(win.width),
        h: Math.round(win.height),
        t: Date.now(),
      };

      const keys = Object.keys(layout.windows);
      if (keys.length > MAX_SAVED_WINDOWS) {
        keys
          .sort((a, b) => layout.windows[a].t - layout.windows[b].t)
          .slice(0, keys.length - MAX_SAVED_WINDOWS)
          .forEach((old) => delete layout.windows[old]);
      }
    });
  }, 300);
}

// Открытые окна в порядке фокуса: последнее в списке было сверху
const openMeta = {};
let focusOrder = [];

function saveOpenWindows() {
  writeJson(
    sessionStorage,
    OPEN_STORE,
    focusOrder.filter((id) => openMeta[id]).map((id) => openMeta[id])
  );
}

// Оболочка (shell.js) перерисовывает список окон и док по этому событию.
function announceWindows() {
  document.dispatchEvent(new CustomEvent("desktop:windows"));
}

function noteFocus(id) {
  focusOrder = focusOrder.filter((other) => other !== id);
  focusOrder.push(id);
  saveOpenWindows();
  announceWindows();
}

function noteClosed(id) {
  focusOrder = focusOrder.filter((other) => other !== id);
  delete openMeta[id];
  saveOpenWindows();
  announceWindows();
}

function makeDraggable(el, handle, ignore, onDrop) {
  handle.addEventListener("pointerdown", (e) => {
    if (ignore && e.target.closest(ignore)) return;

    const startX = e.clientX;
    const startY = e.clientY;
    const baseLeft = el.offsetLeft;
    const baseTop = el.offsetTop;
    let dragging = false;

    function onMove(ev) {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;

      if (!dragging) {
        if (Math.hypot(dx, dy) < 4) return;
        dragging = true;
        handle.setPointerCapture(e.pointerId);
      }

      const maxX = desktop.clientWidth - el.offsetWidth;
      const maxY = desktop.clientHeight - el.offsetHeight;

      el.style.left =
        Math.min(Math.max(0, baseLeft + dx), maxX) + "px";

      el.style.top =
        Math.min(Math.max(0, baseTop + dy), maxY) + "px";
    }

    function onUp() {
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onUp);
      if (dragging && onDrop) onDrop(el);
    }

    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
  });
}


// корневой элемент окна: свойство WinBox, а если его нет, поиск по id
function getWinRoot(win, id) {
  return win.dom || win.window || document.getElementById("win-" + id);
}

function getHeaderMinWidth(root) {
  const header = root.querySelector(".wb-header");
  if (!header) return 0;

  // способ 1: реальная ширина содержимого заголовка
  const byScroll = header.scrollWidth;

  // способ 2: сумма натуральных ширин детей (текст меряем через Range)
  let byChildren = 0;
  for (const child of header.children) {
    if (child.classList.contains("wb-title")) {
      const range = document.createRange();
      range.selectNodeContents(child);
      byChildren += range.getBoundingClientRect().width;
    } else {
      byChildren += child.offsetWidth;
    }
  }

  const result = Math.ceil(Math.max(byScroll, byChildren) + 24);

  console.log("[minwidth]", { byScroll, byChildren, result });
  return result;
}

function applyHeaderMinWidth(win, root) {
  const minWidth = getHeaderMinWidth(root);
  if (!minWidth) return;

  win.minwidth = minWidth;
  root.style.minWidth = minWidth + "px";

  if (win.width < minWidth) {
    win.resize(minWidth, win.height);
  }

  // страховка: если WinBox всё равно дал сузить окно, возвращаем обратно
  if (!win._minObserver) {
    win._minObserver = new ResizeObserver(() => {
      if (root.offsetWidth < minWidth) {
        win.resize(minWidth, win.height);
      }
    });
    win._minObserver.observe(root);
  }
}

/*
 * Пока приложение грузится (и при переходах внутри окна), поверх него
 * лежит заслон с круглым спиннером: игрок не видит пустой документ и
 * неоформленный HTML. Если страница так и не сообщила о загрузке,
 * заслон снимается сам через LOAD_TIMEOUT_MS.
 */
const LOAD_TIMEOUT_MS = 15000;

function attachLoader(win, label) {
  const body = win.body;
  const frame = body && body.querySelector("iframe");

  if (!frame) return;

  const veil = document.createElement("div");
  veil.className = "loading-veil";

  const spinner = document.createElement("div");
  spinner.className = "spinner";
  spinner.setAttribute("role", "status");
  spinner.setAttribute("aria-label", "loading");

  const caption = document.createElement("div");
  caption.className = "loading-label";
  caption.textContent = "loading " + label;

  veil.append(spinner, caption);
  body.appendChild(veil);

  let timer = null;

  const hide = () => {
    clearTimeout(timer);
    veil.hidden = true;
  };

  const show = () => {
    veil.hidden = false;
    clearTimeout(timer);
    timer = setTimeout(hide, LOAD_TIMEOUT_MS);
  };

  frame.addEventListener("load", () => {
    hide();

    // переход внутри окна (ссылка в вики и т.п.): снова показываем заслон
    try {
      frame.contentWindow.addEventListener("beforeunload", show);
    } catch (error) {
      /* страница с другого адреса: следить за уходом нельзя */
    }
  });

  show();
}

function snapWindow(win) {
  if ((!GRID_X && !GRID_Y) || win.max || win.min || win.hidden) return;

  const g = snapGeometry({ x: win.x, y: win.y, width: win.width, height: win.height });

  if (g.x !== win.x || g.y !== win.y) win.move(g.x, g.y);
  if (g.width !== win.width || g.height !== win.height) win.resize(g.width, g.height);
}

// после перетаскивания и изменения размера окно встаёт на сетку
if (GRID_X || GRID_Y) {
  for (const type of ["pointerup", "mouseup"]) {
    window.addEventListener(type, () => setTimeout(() => Object.values(openWindows).forEach(snapWindow), 0), true);
  }
}

// Пустой элемент под телом окна: стиль может нарисовать им нижнюю кромку рамки (у основного стиля скрыт).
// Не div: у WinBox все div после тела считаются ручками размера.
function addFoot(win) {
  const root = win.dom || win.window;
  if (root) root.appendChild(document.createElement("i")).className = "wb-foot";
}

function openApp(id, label, url, options = {}) {
  const existing = openWindows[id];

  if (existing) {
    if (existing.min) existing.restore();
    existing.focus();
    return;
  }

  const offset = Object.keys(openWindows).length * 30;

  // Запомненное положение важнее и умолчаний, и размеров от вызывающего.
  // Окна одного вида (документы и т.п.) каскадом, чтобы не ложились точно друг на друга.
  let geometry = {};
  const saved = savedGeometry(id);

  if (saved) {
    const sameKind = Object.keys(openWindows).filter(
      (other) => geometryKey(other) === geometryKey(id)
    ).length;

    geometry = clampGeometry({
      x: saved.x + sameKind * 30,
      y: saved.y + sameKind * 30,
      width: saved.width,
      height: saved.height,
    });
  }

  let win = null;

  win = new WinBox(label, {
    id: "win-" + id,

    top: WINDOW_TOP,
    bottom: WINDOW_BOTTOM,
    root: desktop,

    class: ["aether", "no-full", ...(isTerminalUrl(url) ? ["app-terminal"] : [])],

    ...snapGeometry({ x: 120 + offset, y: WINDOW_TOP + offset, width: 480, height: 320 }),

    url: url,

    ...options,
    ...geometry,

    onmove: () => {
      if (win) scheduleGeometrySave(win, id);
    },

    onresize: () => {
      if (win) scheduleGeometrySave(win, id);
    },

    onfocus: () => noteFocus(id),
    onblur: announceWindows,
    onminimize: announceWindows,
    onrestore: announceWindows,

    onclose: () => {
      if (win && win._minObserver) win._minObserver.disconnect();
      delete openWindows[id];
      noteClosed(id);
      // окно-туннель закрыли: все мосты закрываются, и мы возвращаемся на исходную машину
      if (options.tunnel) closeBridge();
    },
  });

  addFoot(win);
  openWindows[id] = win;
  openMeta[id] = { id, label, url, options };
  noteFocus(id);
  attachLoader(win, label);

  const root = getWinRoot(win, id);

  if (!root) {
    console.warn("[minwidth] не нашёл корень окна", win);
    return;
  }

  const titleEl = root.querySelector(".wb-title");
  const fontSpec = titleEl
    ? getComputedStyle(titleEl).font
    : "1em sans-serif";

  const measure = () => {
    // окно могли закрыть, пока грузился шрифт
    if (openWindows[id] !== win) return;
    applyHeaderMinWidth(win, root);
  };

  document.fonts.load(fontSpec, label).then(measure, measure);

  // повторный замер после раскладки, на случай если стили докатились позже
  requestAnimationFrame(() => requestAnimationFrame(measure));
}

/* ---------- сообщения системы: окна ошибок и уведомления ---------- */

// каталог своей операционной системы: коды и формулировки зависят от неё (desktop/messages.py)
const SYSTEM_MESSAGES = (function () {
  const node = document.getElementById("system-messages");

  try {
    return node ? JSON.parse(node.textContent) : {};
  } catch (error) {
    return {};
  }
})();

const FALLBACK_MESSAGE = { kind: "error", code: "", title: "Error", text: "" };
const MESSAGE_GLYPH = { error: "!", warning: "!", info: "i" };
const TOAST_MS = 4500;
const openDialogs = {};
let dialogCount = 0;

// spec: ключ из каталога или готовое {kind, code, title, text}; {name} в тексте заполняется из params
function resolveMessage(spec, params) {
  const base = typeof spec === "string"
    ? SYSTEM_MESSAGES[spec] || SYSTEM_MESSAGES.failed || FALLBACK_MESSAGE
    : spec;

  const fill = (text) => String(text || "").replace(/\{(\w+)\}/g, (match, name) =>
    params && params[name] !== undefined ? String(params[name]) : ""
  );

  return {
    kind: base.kind || "error",
    code: base.code || "",
    title: fill(base.title),
    text: fill(base.text),
  };
}

function el(tag, className, text) {
  const node = document.createElement(tag);

  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;

  return node;
}

// окно ошибки как в обычной системе: заголовок, значок, текст, код и кнопка OK
function showDialog(spec, params = {}, options = {}) {
  const msg = resolveMessage(spec, params);
  // stack: окна одного сообщения не склеиваются в одно и ложатся в случайные места (хук alert)
  const dedupe = options.stack
    ? "stack-" + (dialogCount + 1)
    : msg.kind + "|" + msg.title + "|" + msg.text;

  if (openDialogs[dedupe]) {
    openDialogs[dedupe].focus();
    return;
  }

  const body = el("div", "dialog dialog--" + msg.kind);
  const main = el("div", "dialog-main");
  const foot = el("div", "dialog-foot");
  const ok = el("button", "dialog-ok", "OK");

  ok.type = "button";
  foot.append(el("span", "dialog-code", msg.code ? "code " + msg.code : ""), ok);
  main.append(
    el("span", "dialog-glyph", MESSAGE_GLYPH[msg.kind] || "!"),
    el("p", "dialog-message", msg.text)
  );
  body.append(main, foot);

  dialogCount += 1;

  const win = new WinBox(msg.title, {
    id: "dialog-" + dialogCount,
    root: desktop,
    top: WINDOW_TOP,
    bottom: WINDOW_BOTTOM,
    class: [
      "aether",
      "no-full",
      "no-max",
      "no-min",
      "no-resize",
      "dialog-window",
      "dialog-window--" + msg.kind,
    ],
    x: options.stack ? Math.max(0, Math.round(Math.random() * (desktop.clientWidth - 400))) : "center",
    y: options.stack ? WINDOW_TOP + Math.round(Math.random() * Math.max(0, desktop.clientHeight - 170 - WINDOW_TOP)) : "center",
    width: 400,
    height: 170,
    mount: body,
    onclose: () => {
      delete openDialogs[dedupe];
    },
  });

  addFoot(win);
  openDialogs[dedupe] = win;

  ok.addEventListener("click", () => win.close());
  body.addEventListener("keydown", (event) => {
    if (event.key === "Escape" || event.key === "Enter") {
      event.preventDefault();
      win.close();
    }
  });

  ok.focus();
}

// короткое уведомление в углу; исчезает само
function showToast(spec, params = {}, onClick = null, ms = TOAST_MS) {
  const msg = resolveMessage(spec, params);
  let stack = document.getElementById("toasts");

  if (!stack) {
    stack = el("div");
    stack.id = "toasts";
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
  }

  const toast = el("div", "toast toast--" + msg.kind);

  toast.append(el("strong", "toast-title", msg.title));
  if (msg.text) toast.append(el("span", "toast-text", msg.text));

  const close = () => toast.remove();

  toast.addEventListener("click", () => {
    close();
    if (onClick) onClick();
  });
  if (onClick) toast.classList.add("toast--action");
  stack.appendChild(toast);
  setTimeout(close, ms);

  // оболочка копит историю уведомлений (центр уведомлений)
  document.dispatchEvent(new CustomEvent("desktop:notice", { detail: { kind: msg.kind, title: msg.title, text: msg.text || "", onClick } }));
}


/* ==================================================
   Новая почта: бейдж на иконке интеркома и уведомление
   ================================================== */

const MAIL_POLL_MS = 10000;
const MAIL_POLL_MAX_MS = 60000;
let mailFailures = 0;
const MAIL_TOAST_MS = 9000;
const mailUrl = desktop.dataset.mailUrl;
const mailPulseUrl = desktop.dataset.mailPulseUrl;
const knownMail = new Set();
let mailSeeded = false;

function mailIcon() {
  const path = new URL(mailUrl, window.location.href).pathname;

  return Array.from(document.querySelectorAll(".icon")).find(
    (item) => new URL(item.dataset.url, window.location.href).pathname === path
  );
}

function openMail() {
  const icon = mailIcon();

  if (icon) {
    openApp(icon.dataset.app, icon.querySelector(".icon-label").textContent, icon.dataset.url);
  }
}

function setMailBadge(count) {
  const icon = mailIcon();

  if (!icon) return;

  let badge = icon.querySelector(".icon-badge");

  if (!count) {
    if (badge) badge.remove();
    announceWindows();
    return;
  }

  if (!badge) {
    badge = el("span", "icon-badge");
    icon.querySelector(".icon-glyph").appendChild(badge);
  }

  badge.textContent = count > 9 ? "9+" : String(count);
  announceWindows();
}

async function pollMail() {
  if (document.hidden) return;

  let data;

  try {
    const response = await fetch(mailPulseUrl, { credentials: "same-origin" });
    if (!response.ok) {
      mailFailures += 1;
      return;
    }
    data = await response.json();
  } catch (error) {
    mailFailures += 1;
    return;     // сеть недоступна: попробуем в следующий раз
  }

  mailFailures = 0;

  setMailBadge(data.unread);

  const fresh = data.messages.filter((item) => !knownMail.has(item.id));
  data.messages.forEach((item) => knownMail.add(item.id));

  // первый опрос только запоминает уже лежащие письма: о них игрок знает по бейджу
  if (!mailSeeded) {
    mailSeeded = true;
    return;
  }

  if (fresh.length === 1) {
    showToast("mail_new", { sender: fresh[0].sender, subject: fresh[0].subject }, openMail, MAIL_TOAST_MS);
  } else if (fresh.length > 1) {
    showToast("mail_new", { sender: fresh.length + " messages", subject: "see the intercom" }, openMail, MAIL_TOAST_MS);
  }
}

// интервал с разбросом, чтобы окна не бились в сервер одновременно, и с отступом при ошибках
function scheduleMailPoll() {
  const base = Math.min(MAIL_POLL_MS * 2 ** mailFailures, MAIL_POLL_MAX_MS);
  setTimeout(async () => {
    await pollMail();
    scheduleMailPoll();
  }, base + Math.random() * 3000);
}

if (mailUrl && mailPulseUrl) {
  pollMail();
  scheduleMailPoll();
  document.addEventListener("visibilitychange", pollMail);
}

// Чёрный экран при смене рабочего стола (подключение, закрытие подключения, обрыв по сроку): чёрная накладка, посреди неё окно
// под консоль с текстом, потом страница перезагружается и стол оказывается на нужной машине. Оформление и тексты приходят с сервера:
// {title, text, tone, delay, speed, hold}
let blackoutRunning = false;

function blackout(shown) {
  if (blackoutRunning) return;
  blackoutRunning = true;

  const cover = document.createElement("div");
  cover.className = `blackout blackout--${shown.tone || "error"}`;
  const box = document.createElement("div");
  box.className = "blackout-window";
  const title = document.createElement("div");
  title.className = "blackout-title";
  title.textContent = shown.title || "connection closed";
  const body = document.createElement("pre");
  body.className = "blackout-body";
  const cursor = document.createElement("span");
  cursor.className = "blackout-cursor";
  box.append(title, body);
  cover.append(box);
  document.body.append(cover);
  requestAnimationFrame(() => cover.classList.add("blackout--on"));

  const text = shown.text || "";
  const speed = shown.speed ?? 32;
  let count = 0;

  function type() {
    body.textContent = text.slice(0, count);
    body.append(cursor);
    if (count < text.length) {
      count += 1;
      setTimeout(type, text[count - 1] === "\n" ? speed * 12 : speed);
    } else {
      setTimeout(() => window.location.reload(), shown.hold ?? 2600);
    }
  }

  setTimeout(() => {
    box.classList.add("blackout-window--on");
    type();
  }, shown.delay ?? 1500);
}

function handleKicks(kicks) {
  const hit = (kicks || []).find((kick) => kick.desktop);
  if (hit) blackout(hit.blackout);
}

// Срок подключения, на котором открыт этот стол: в нужный момент просим сервер закрыть вышедшее
function watchLimit() {
  let limit = null;
  try {
    limit = JSON.parse(document.getElementById("desktop-limit").textContent);
  } catch {
    return;
  }
  if (!limit) return;

  const wait = limit.deadline * 1000 - (limit.now * 1000 + 0) + 400;
  setTimeout(async () => {
    try {
      const response = await fetch(limit.tick_url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        body: "{}",
      });
      handleKicks((await response.json()).kicks);
    } catch {
      // следующий запрос к серверу всё равно проверит срок
    }
  }, Math.max(0, wait - (Date.now() - pageLoadedAt)));
}

const pageLoadedAt = Date.now();

try {
  handleKicks(JSON.parse(document.getElementById("desktop-kicks").textContent));
} catch {
  // обрывов нет
}
watchLimit();

window.desktopAPI = {
  blackout,
  openApp,
  error: showDialog,
  notify: showToast,
  reload: () => window.location.reload(),
  lock: (url) => { window.location.href = url; },
};

// Мост: окно-туннель с терминалом открыто на столе чужой машины сразу. Его закрытие закрывает все мосты.
const tunnelUrl = desktop.dataset.tunnelUrl;

function closeBridge() {
  fetch(desktop.dataset.tunnelCloseUrl, {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRFToken": getCookie("csrftoken") },
  }).finally(() => window.location.reload());
}

if (tunnelUrl) {
  openApp("tunnel", desktop.dataset.tunnelLabel || "bridge", tunnelUrl, {
    tunnel: true,
    x: 80,
    y: WINDOW_TOP + 30,
    width: 760,
    height: 460,
  });
}

// размер клетки берём из CSS, чтобы он совпадал с фоном
const CELL = parseFloat(
  getComputedStyle(document.documentElement).getPropertyValue("--cell")
);
const CELLS_W = 3; // ширина ячейки иконки в клетках фона
const CELLS_H = 2; // высота ячейки иконки в клетках фона
const cellW = CELL * CELLS_W;
const cellH = CELL * CELLS_H;

// примагничивание иконки к ближайшей свободной ячейке
function snapToGrid(el) {
  const cols = Math.floor(desktop.clientWidth / cellW);
  const rows = Math.floor(desktop.clientHeight / cellH);

  const rawCol = el.offsetLeft / cellW;
  const rawRow = el.offsetTop / cellH;

  const taken = new Set();
  document.querySelectorAll("#icons li").forEach((other) => {
    if (other === el) return;
    const c = Math.round(other.offsetLeft / cellW);
    const r = Math.round(other.offsetTop / cellH);
    taken.add(c + "," + r);
  });

  let bestCol = null;
  let bestRow = null;
  let bestDist = Infinity;
  for (let c = 0; c < cols; c++) {
    for (let r = 0; r < rows; r++) {
      if (taken.has(c + "," + r)) continue;
      const dist = Math.hypot(c - rawCol, r - rawRow);
      if (dist < bestDist) {
        bestDist = dist;
        bestCol = c;
        bestRow = r;
      }
    }
  }

  if (bestCol === null) return;

  el.style.left = bestCol * cellW + "px";
  el.style.top = bestRow * cellH + "px";
}

/* ==================================================
   Иконки: расстановка и запоминание
   В хранилище лежат клетки сетки (колонка, ряд), а не пиксели:
   так расстановка переживает смену размера окна браузера.
   ================================================== */

const iconItems = Array.from(document.querySelectorAll("#icons li"));

function iconId(li) {
  return li.querySelector(".icon").dataset.app;
}

function placeIcon(li, col, row) {
  li.style.left = col * cellW + "px";
  li.style.top = row * cellH + "px";
}

function iconCell(li) {
  return [Math.round(li.offsetLeft / cellW), Math.round(li.offsetTop / cellH)];
}

function placeIcons() {
  const cols = Math.max(1, Math.floor(desktop.clientWidth / cellW));
  const rows = Math.max(1, Math.floor(desktop.clientHeight / cellH));
  const saved = readLayout().icons;

  const taken = new Set();
  const unplaced = [];

  iconItems.forEach((li) => {
    const cell = saved[iconId(li)];
    const fits =
      Array.isArray(cell) &&
      Number.isInteger(cell[0]) &&
      Number.isInteger(cell[1]) &&
      cell[0] >= 0 && cell[0] < cols &&
      cell[1] >= 0 && cell[1] < rows &&
      !taken.has(cell[0] + "," + cell[1]);

    if (fits) {
      placeIcon(li, cell[0], cell[1]);
      taken.add(cell[0] + "," + cell[1]);
    } else {
      unplaced.push(li);
    }
  });

  // остальные (новые, не помещающиеся) по порядку в свободные клетки, колонка за колонкой
  let col = 0;
  let row = 0;

  unplaced.forEach((li) => {
    while (taken.has(col + "," + row)) {
      row += 1;
      if (row >= rows) {
        row = 0;
        col += 1;
      }
    }

    placeIcon(li, col, row);
    taken.add(col + "," + row);
  });
}

function saveIcons() {
  updateLayout((layout) => {
    iconItems.forEach((li) => {
      layout.icons[iconId(li)] = iconCell(li);
    });
  });
}

placeIcons();

iconItems.forEach((li) => {
  makeDraggable(li, li, null, (el) => {
    snapToGrid(el);
    saveIcons();
  });
});

document.querySelectorAll(".icon").forEach((icon) => {
  icon.addEventListener("dblclick", () => {
    if (!icon.dataset.url) return; // файл закрыт слоями: пока они не сняты, окна нет
    openApp(
      icon.dataset.app,
      icon.querySelector(".icon-label").textContent,
      icon.dataset.url
    );
  });
});


/* ==================================================
   Открытые окна после перезагрузки
   Только при обычной перезагрузке страницы (F5). Новый вход или
   переход на стол всегда начинается с чистого стола.
   ================================================== */

function restoreOpenWindows() {
  const navigation = performance.getEntriesByType("navigation")[0];
  const stored = readJson(sessionStorage, OPEN_STORE, []);

  if (!navigation || navigation.type !== "reload" || !Array.isArray(stored)) {
    try {
      sessionStorage.removeItem(OPEN_STORE);
    } catch (error) {
      // см. writeJson
    }
    return;
  }

  // порядок в списке: от нижнего окна к верхнему, поэтому верхнее открывается последним
  stored.forEach((win) => {
    if (win && win.id !== undefined && win.url) {
      openApp(String(win.id), String(win.label || ""), String(win.url), win.options || {});
    }
  });
}

restoreOpenWindows();


/* ==================================================
   Меню подключения (слева на панели)
   ================================================== */

const menuButton = document.getElementById("session-menu-button");
const menu = document.getElementById("session-menu");

// В некоторых оболочках меню подключения нет (его действия лежат в меню лаунчера): тогда элементов может не быть.
function setMenu(open) {
  if (!menu) return;
  menu.hidden = !open;
  if (menuButton) menuButton.setAttribute("aria-expanded", open ? "true" : "false");
}

function getCookie(name) {
  const prefix = name + "=";
  const row = document.cookie.split("; ").find((item) => item.startsWith(prefix));
  return row ? decodeURIComponent(row.slice(prefix.length)) : "";
}

// «sessions»: если на столе уже есть иконка этого приложения, открываем её окно,
// чтобы не получить два окна с одним и тем же адресом
function openSessions(button) {
  const path = new URL(button.dataset.url, window.location.href).pathname;

  const icon = Array.from(document.querySelectorAll(".icon")).find(
    (item) => new URL(item.dataset.url, window.location.href).pathname === path
  );

  if (icon) {
    openApp(icon.dataset.app, icon.querySelector(".icon-label").textContent, icon.dataset.url);
  } else {
    openApp("sessions", button.textContent.trim(), button.dataset.url);
  }
}

async function disconnect(button) {
  // на чужой машине (мост) «disconnect» закрывает мосты и возвращает на исходную машину, а не выходит из учётной записи игрока
  if (tunnelUrl) {
    closeBridge();
    return;
  }

  try {
    await fetch(button.dataset.logoutUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: "{}",
    });
  } finally {
    // даже если запрос не прошёл, экран входа покажет, в каком состоянии сессия
    window.location.href = button.dataset.lockUrl;
  }
}

if (menuButton && menu) {
  menuButton.addEventListener("click", () => {
    setMenu(menu.hidden);
  });
}

// Действия сессии (sessions, reset layout, disconnect) лежат в любом блоке с data-actions: в меню подключения или в меню лаунчера.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-actions] button[data-action]");

  if (!button) return;

  setMenu(false);
  document.dispatchEvent(new CustomEvent("shell:close"));

  if (button.dataset.action === "sessions") {
    openSessions(button);
  } else if (button.dataset.action === "reset-layout") {
    if (window.confirm("Reset icon layout and window positions?")) {
      resetLayout();
      window.location.reload();
    }
  } else if (button.dataset.action === "disconnect") {
    disconnect(button);
  }
});

document.addEventListener("pointerdown", (event) => {
  if (menu && !menu.hidden && !menu.contains(event.target) && !(menuButton && menuButton.contains(event.target))) {
    setMenu(false);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && menu && !menu.hidden) {
    setMenu(false);
    if (menuButton) menuButton.focus();
  }
});

// клик внутри окна приложения (iframe) до этого документа не доходит, но снимает с него фокус
window.addEventListener("blur", () => setMenu(false));
