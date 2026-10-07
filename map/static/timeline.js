// Таймлайн карты. Подключается после map.js.
// Дата хранится в адресе страницы как ?date=YYYY-MM-DD (бэкенд это уже понимает).
// Без параметра карта показывает последних владельцев, то есть «сейчас».
(() => {
  'use strict';

  const q = new URLSearchParams(location.search);
  // В редакторе территорий и в режиме выбора точки свой интерфейс - таймлайн не нужен
  if (q.has('edit') || q.has('pick')) return;
  if (typeof TIMELINE_URL === 'undefined') return;

  // true: карта обновляется без перезагрузки (loadProvinceColors и loadCountryLabels
  // из map.js сами берут дату из адреса). false: страница перезагружается.
  const LIVE_UPDATE = true;

  const DAY = 86400000;
  const APPLY_DELAY = LIVE_UPDATE ? 150 : 400;   // пауза после последнего изменения, мс
  const PAD = 6;             // половина ширины бегунка, чтобы засечки совпадали с ним

  // ---------- даты ----------
  const pad = (n, w) => String(n).padStart(w, '0');

  function ymdToDay(y, m, d) {
    const t = new Date(0);               // setUTCFullYear нужен для лет < 100
    t.setUTCFullYear(y, m - 1, d);
    return Math.round(t.getTime() / DAY);
  }
  function dayToYmd(n) {
    const t = new Date(n * DAY);
    return { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: t.getUTCDate() };
  }
  const dayToIso = (n) => {
    const { y, m, d } = dayToYmd(n);
    return `${pad(y, 4)}-${pad(m, 2)}-${pad(d, 2)}`;
  };
  function daysInMonth(y, m) {
    const t = new Date(0);
    t.setUTCFullYear(y, m, 0);           // нулевой день следующего месяца = последний день этого
    return t.getUTCDate();
  }
  function isoToDay(iso) {
    const m = /^(\d{1,4})-(\d{2})-(\d{2})$/.exec(iso || '');
    if (!m) return null;
    const y = +m[1], mo = +m[2], d = +m[3];
    if (y < 1 || mo < 1 || mo > 12 || d < 1 || d > daysInMonth(y, mo)) return null;
    return ymdToDay(y, mo, d);
  }

  // ---------- состояние ----------
  let events = [];                       // номера дней, в которые менялись границы
  let lo = 0, hi = 1;                    // границы ползунка
  const urlDay = isoToDay(q.get('date'));
  let appliedDay = urlDay;               // дата, которая сейчас показана на карте (null = «сейчас»)
  let current = urlDay;                  // дата в ползунке и в полях
  let timer = null;

  // ---------- разметка ----------
  const root = document.createElement('div');
  root.id = 'timeline';
  root.innerHTML = `
    <div class="tl-head"><span class="tl-title">map.timeline</span><span class="tl-hint"></span></div>
    <div class="tl-track">
      <div class="tl-line"></div>
      <div class="tl-ticks"></div>
      <input class="tl-range" type="range" step="1" aria-label="Дата на карте">
    </div>
    <div class="tl-labels"></div>
    <div class="tl-controls">
      <button type="button" class="tl-prev" title="Предыдущее изменение">&#9664;</button>
      <div class="tl-date">
        <input class="tl-y" maxlength="4" inputmode="numeric" aria-label="Год">-
        <input class="tl-m" maxlength="2" inputmode="numeric" aria-label="Месяц">-
        <input class="tl-d" maxlength="2" inputmode="numeric" aria-label="День">
      </div>
      <button type="button" class="tl-next" title="Следующее изменение">&#9654;</button>
      <button type="button" class="tl-latest" title="Показать последних владельцев">latest</button>
    </div>`;
  document.body.appendChild(root);

  const $ = (sel) => root.querySelector(sel);
  const range = $('.tl-range'), ticksEl = $('.tl-ticks'), labelsEl = $('.tl-labels');
  const hint = $('.tl-hint');
  const fy = $('.tl-y'), fm = $('.tl-m'), fd = $('.tl-d');
  const btnPrev = $('.tl-prev'), btnNext = $('.tl-next'), btnLatest = $('.tl-latest');

  const frac = (day) => (hi === lo ? 0 : Math.min(1, Math.max(0, (day - lo) / (hi - lo))));
  const leftFor = (day) => `calc(${PAD}px + (100% - ${PAD * 2}px) * ${frac(day)})`;

  // ---------- отрисовка ----------
  function renderTrack() {
    ticksEl.textContent = '';
    for (const day of events) {
      const t = document.createElement('div');
      t.className = 'tl-tick';
      t.style.left = leftFor(day);
      ticksEl.appendChild(t);
    }
    renderLabels();
  }

  // Подписи годов: у первой засечки каждого года, если хватает места
  function renderLabels() {
    labelsEl.textContent = '';
    const width = labelsEl.clientWidth - PAD * 2;
    let lastX = -Infinity;
    let lastYear = null;
    for (const day of events) {
      const { y } = dayToYmd(day);
      if (y === lastYear) continue;
      const x = PAD + width * frac(day);
      if (x - lastX < 44) continue;
      const el = document.createElement('div');
      el.className = 'tl-label';
      el.style.left = leftFor(day);
      el.textContent = y;
      labelsEl.appendChild(el);
      lastX = x;
      lastYear = y;
    }
  }

  function renderDate() {
    const { y, m, d } = dayToYmd(current);
    fy.value = pad(y, 4);
    fm.value = pad(m, 2);
    fd.value = pad(d, 2);
    [fy, fm, fd].forEach((f) => f.classList.remove('tl-bad'));
    range.value = Math.min(hi, Math.max(lo, current));

    const before = events.filter((e) => e <= current);
    hint.textContent = events.length === 0
      ? 'нет данных'
      : before.length
        ? `последнее изменение: ${dayToIso(before[before.length - 1])}`
        : 'до начала истории';
    btnPrev.disabled = !events.some((e) => e < current);
    btnNext.disabled = !events.some((e) => e > current);
    btnLatest.disabled = appliedDay === null && urlDay === null && current === events[events.length - 1];
  }

  // ---------- применение даты к карте ----------
  function applyDate(day) {
    clearTimeout(timer);
    if (day === appliedDay) return;
    appliedDay = day;

    const p = new URLSearchParams(location.search);
    if (day === null) p.delete('date'); else p.set('date', dayToIso(day));
    const url = `${location.pathname}?${p}${location.hash}`;

    if (LIVE_UPDATE) {
      history.replaceState(history.state, '', url);
      loadProvinceColors();
      loadCountryLabels();
    } else {
      location.replace(url);             // #hash сохраняет положение карты
    }
  }
  const scheduleApply = () => {
    clearTimeout(timer);
    timer = setTimeout(() => applyDate(current), APPLY_DELAY);
  };

  function setCurrent(day, { apply = 'later' } = {}) {
    current = day;
    renderDate();
    if (apply === 'now') applyDate(day);
    else if (apply === 'later') scheduleApply();
  }

  // ---------- события ----------
  // Ползунок: при живом обновлении карта следует за ним, иначе меняется после отпускания
  range.addEventListener('input', () =>
    setCurrent(+range.value, { apply: LIVE_UPDATE ? 'later' : 'none' }));
  range.addEventListener('change', () => setCurrent(+range.value, { apply: 'later' }));

  // Ручной ввод
  function commitFields() {
    const y = +fy.value, m = +fm.value, d = +fd.value;
    const ok = Number.isInteger(y) && Number.isInteger(m) && Number.isInteger(d)
      && y >= 1 && m >= 1 && m <= 12 && d >= 1 && d <= daysInMonth(y, m);
    if (!ok) {
      [fy, fm, fd].forEach((f) => f.classList.add('tl-bad'));
      return;
    }
    setCurrent(ymdToDay(y, m, d), { apply: 'later' });
  }
  function adjust(part, delta) {
    let { y, m, d } = dayToYmd(current);
    if (part === 'd') {
      setCurrent(current + delta);
      return;
    }
    if (part === 'y') y = Math.min(9999, Math.max(1, y + delta));
    if (part === 'm') {
      const total = y * 12 + (m - 1) + delta;
      y = Math.min(9999, Math.max(1, Math.floor(total / 12)));
      m = ((total % 12) + 12) % 12 + 1;
    }
    setCurrent(ymdToDay(y, m, Math.min(d, daysInMonth(y, m))));
  }
  [[fy, 'y'], [fm, 'm'], [fd, 'd']].forEach(([field, part]) => {
    field.addEventListener('focus', () => field.select());
    field.addEventListener('change', commitFields);
    field.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { field.blur(); commitFields(); }
      else if (e.key === 'ArrowUp')   { e.preventDefault(); adjust(part, 1); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); adjust(part, -1); }
    });
  });

  // Прыжки между датами изменений
  btnPrev.addEventListener('click', () => {
    const prev = [...events].reverse().find((e) => e < current);
    if (prev !== undefined) setCurrent(prev, { apply: 'now' });
  });
  btnNext.addEventListener('click', () => {
    const next = events.find((e) => e > current);
    if (next !== undefined) setCurrent(next, { apply: 'now' });
  });
  btnLatest.addEventListener('click', () => {
    if (events.length) current = events[events.length - 1];
    renderDate();
    applyDate(null);
  });

  window.addEventListener('resize', renderLabels);

  // ---------- старт ----------
  function init(days) {
    events = [...new Set(days)].sort((a, b) => a - b);
    const today = Math.floor(Date.now() / DAY);
    if (events.length) {
      lo = events[0];
      hi = events[events.length - 1];
      if (lo === hi) hi = lo + 365;      // одна дата: рисуем год, чтобы ползунок был живым
    } else {
      lo = today - 365;
      hi = today;
    }
    range.min = lo;
    range.max = hi;
    if (current === null) current = events.length ? events[events.length - 1] : today;
    renderTrack();
    renderDate();
  }

  init([]); // пустой каркас, пока грузятся даты
  fetch(TIMELINE_URL)
    .then((r) => r.json())
    .then((data) => init((data.dates || []).map(isoToDay).filter((x) => x !== null)))
    .catch(() => { hint.textContent = 'даты не загрузились'; });
})();