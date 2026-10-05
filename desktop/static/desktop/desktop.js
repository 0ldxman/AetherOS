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
const pingValue = document.getElementById('ping-value');

function updatePing() {
    const ping = Math.floor(Math.random() * (200 - 20 + 1)) + 20;

    pingValue.textContent = ping;

    if (ping <= 90) {
        document.documentElement.style.setProperty(
            '--ping-color',
            'var(--accent-green)'
        );
    } else if (ping <= 150) {
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

    const delay = Math.random() * 2000 + 1000;
    setTimeout(schedulePing, delay);
}

schedulePing();


const desktop = document.getElementById("desktop");
const template = document.getElementById("window-template");
const openWindows = {};

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

function openApp(id, label, url, options = {}) {
  const existing = openWindows[id];

  if (existing) {
    if (existing.min) existing.restore();
    existing.focus();
    return;
  }

  const offset = Object.keys(openWindows).length * 30;

  const win = new WinBox(label, {
    id: "win-" + id,

    top: 28,
    root: desktop,

    class: ["aether", "no-full"],

    x: 120 + offset,
    y: 40 + offset,

    width: 480,
    height: 320,

    url: url,

    ...options,

    onclose: () => {
      if (win._minObserver) win._minObserver.disconnect();
      delete openWindows[id];
    },
  });

  openWindows[id] = win;

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

window.desktopAPI = {
  openApp
};

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

document.querySelectorAll("#icons li").forEach((li, i) => {
  const perColumn = Math.max(1, Math.floor(desktop.clientHeight / cellH));
  li.style.left = Math.floor(i / perColumn) * cellW + "px";
  li.style.top = (i % perColumn) * cellH + "px";
  makeDraggable(li, li, null, snapToGrid);
});

document.querySelectorAll(".icon").forEach((icon) => {
  icon.addEventListener("dblclick", () => {
    openApp(
      icon.dataset.app,
      icon.querySelector(".icon-label").textContent,
      icon.dataset.url
    );
  });
});