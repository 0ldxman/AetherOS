<script lang="ts">
  import { untrack } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import DraftState from "../../lib/DraftState.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import Icon from "../../lib/Icon.svelte";
  import { SharedForm } from "../../lib/shared.svelte";
  import { tileUrl, WALL_MODES, WALL_PATTERNS, WALLPAPER_DEFAULT, type Wallpaper } from "../../lib/wallpaper";
  import WallpaperPicker from "./WallpaperPicker.svelte";

  type System = Schemas["SystemOut"];
  type Panel = { look?: string; show?: string; edge?: string; form?: string; start?: string[]; center?: string[]; end?: string[] };
  type Slot = "start" | "center" | "end";
  type Panel2 = { show?: string; edge?: string; form?: string; hide?: string; reserve?: string; start?: string[]; center?: string[]; end?: string[] };
  type Which = "panel" | "panel2";
  type Card = { key: string; corner: string };
  type Done = (data: System | undefined, error: unknown, text: string) => void;

  let { system, errors, done, onstate }: { system: System; errors: Record<string, string[]>; done: Done; onstate: (state: { dirty: boolean; share: typeof share; save: () => unknown } | null) => void } = $props();

  let look = $state({ style: "aether", tokens: {} as Record<string, string>, wallpaper: { ...WALLPAPER_DEFAULT } as Wallpaper, widgets: {} as Record<string, boolean>, places: {} as Record<string, string>, win: {} as Record<string, string>, panel: {} as Panel, panel2: {} as Panel2, parts: {} as Record<string, Record<string, string>>, cards: null as Card[] | null });
  let picking = $state(false);
  let lookSaved = $state("");
  let base = $state<typeof look | null>(null);                  // сохранённое: им наполняется общий черновик
  const share = new SharedForm({ room: () => `systems/${system.code}`, scope: () => "style", draft: () => look, base: () => base });
  const lookDirty = $derived(JSON.stringify(look) !== lookSaved);
  const TITLE_GROUP = "Заголовок окна";                                   // эти токены живут в разделе «Окна», под заголовком
  const titleTokens = $derived(system.token_info.filter((t) => t.group === TITLE_GROUP));
  const HEX6 = /^#[0-9a-fA-F]{6}$/;

  async function saveLook() {
    const body = { style: look.style, tokens: look.tokens, wallpaper: look.wallpaper, widgets: look.widgets, widget_places: look.places, window: look.win, panel: look.panel, panel2: look.panel2, parts: look.parts, cards: look.cards ?? undefined, cards_style: look.cards === null };
    const { data, error } = await api.PUT("/studio/api/systems/{code}/style", { params: { path: { code: system.code } }, body });
    if (data) share.markSaved();
    done(data, error, "Стиль сохранён.");
  }

  function setToken(name: string, value: string) {
    look.tokens = value.trim() ? { ...look.tokens, [name]: value } : Object.fromEntries(Object.entries(look.tokens).filter(([key]) => key !== name));
  }

  // предпросмотр: настоящий рабочий стол в рамке, адрес с несохранёнными стилем и токенами; перезагружается с паузой, чтобы не мигать
  const PV_KEY = "studio.styleDeskPreview";
  let deskPreview = $state((() => { try { return localStorage.getItem(PV_KEY) !== "off"; } catch { return true; } })());
  function toggleDeskPreview() {
    deskPreview = !deskPreview;
    try { localStorage.setItem(PV_KEY, deskPreview ? "on" : "off"); } catch { /* память браузера может быть закрыта */ }
  }
  let previewSrc = $state("");
  let previewWidth = $state(0);
  let deskTimer: ReturnType<typeof setTimeout>;
  const PREVIEW_W = 1100;
  const PREVIEW_H = 640;

  $effect(() => {
    if (!deskPreview) return;
    const url = `${system.preview_url}?preview_os=${encodeURIComponent(system.code)}&preview_style=${encodeURIComponent(look.style)}&preview_tokens=${encodeURIComponent(JSON.stringify(look.tokens))}&preview_wall=${encodeURIComponent(JSON.stringify(look.wallpaper))}&preview_widgets=${encodeURIComponent(JSON.stringify(look.widgets))}&preview_places=${encodeURIComponent(JSON.stringify(look.places))}&preview_parts=${encodeURIComponent(JSON.stringify({ window: look.win, panel: look.panel, panel2: look.panel2, ...look.parts, ...(look.cards ? { cards: look.cards } : {}) }))}&preview_scene=${scene.join(",")}`;
    clearTimeout(deskTimer);
    deskTimer = setTimeout(() => (previewSrc = url), 350);
    return () => clearTimeout(deskTimer);
  });

  // значения токенов у выбранного (а не сохранённого) стиля: у каждого стиля свои
  const styleDefaults = $derived(system.style_defaults[look.style] ?? {});
  const def = (token: Schemas["TokenInfo"]) => styleDefaults[token.name] ?? token.default;
  const pickerValue = (token: Schemas["TokenInfo"]) => (HEX6.test(look.tokens[token.name] ?? "") ? look.tokens[token.name] : HEX6.test(def(token)) ? def(token) : "#000000");
  // картинка рабочего стола: сотрудник видит и ещё не сохранённый файл (?file=)
  const wallUrl = (fileId: string) => `${(window as unknown as { STUDIO: { site: string } }).STUDIO.site}wallpaper/${encodeURIComponent(system.code)}/?file=${encodeURIComponent(fileId)}`;
  // сетка выбранного стиля: с неё начинается узор (шаг --cell и цвет --line-faint с учётом токенов ниже)
  const gridCell = $derived(Math.round(parseFloat(look.tokens["--cell"] ?? styleDefaults["--cell"] ?? "48")) || 48);
  const gridColor = $derived.by(() => { const value = look.tokens["--line-faint"] ?? styleDefaults["--line-faint"] ?? ""; return HEX6.test(value) ? value : "#212121"; });
  const desktopUrl = $derived(`${(window as unknown as { STUDIO: { site: string } }).STUDIO.site}?preview_os=${system.code}`);

  // сервер вернул ОС заново (после сохранения): берём значения оттуда
  $effect(() => {
    const data = system;
    untrack(() => {
      const next = { style: data.style, tokens: { ...data.style_tokens }, wallpaper: { ...WALLPAPER_DEFAULT, ...data.wallpaper }, widgets: { ...data.widgets }, places: { ...data.widget_places }, win: { ...data.window }, panel: Object.fromEntries(Object.entries(data.panel).filter(([, v]) => v !== null)) as Panel, panel2: Object.fromEntries(Object.entries(data.panel2).filter(([, v]) => v !== null)) as Panel2, parts: JSON.parse(JSON.stringify(data.parts)), cards: data.cards ? data.cards.map((c) => ({ ...c })) : null };
      if (!share.ready) look = { style: next.style, tokens: { ...next.tokens }, wallpaper: { ...next.wallpaper }, widgets: { ...next.widgets }, places: { ...next.places }, win: { ...next.win }, panel: JSON.parse(JSON.stringify(next.panel)), panel2: JSON.parse(JSON.stringify(next.panel2)), parts: JSON.parse(JSON.stringify(next.parts)), cards: next.cards ? next.cards.map((c) => ({ ...c })) : null };
      lookSaved = JSON.stringify(next);
      base = next;
    });
  });

  // кнопка «Сохранить» живёт в шапке ОС: вкладка сообщает ей своё состояние
  $effect(() => {
    onstate({ dirty: lookDirty, share, save: saveLook });
    return () => onstate(null);
  });

  guardUnsaved(() => !share.ready && lookSaved !== "" && lookDirty);

  // ---------- разделы: по тому, что видит игрок; токены лежат рядом с тем, что красят ----------
  const SECTION_KEY = "studio.styleSection";
  const SECTIONS = [
    { key: "base", label: "Основа", note: "Заготовка задаёт всё остальное по умолчанию. Здесь же видно, что у этой ОС изменено." },
    { key: "desk", label: "Стол", note: "Картинка и узор, сетка, значки на столе, бегущая строка и курсор." },
    { key: "windows", label: "Окна", note: "Заголовок, рамка и кнопки окна, их цвета." },
    { key: "panel", label: "Панели", note: "Основная занимает полосу стола; дополнительная висит поверх у любого края. Обе — полоса, док или острова из одних элементов; каждый элемент стоит только в одной." },
    { key: "notice", label: "Сообщения", note: "Всплывающие уведомления и окна ошибок: чей вид, где и как показывать." },
    { key: "fx", label: "Эффекты", note: "Развёртка, шум, свечение, пиксельная сетка и сбои кадра поверх всего стола." },
    { key: "colors", label: "Цвета и шрифты", note: "Общая палитра, линии, акценты, шрифты и форма. То, что красит одну часть, есть и в её разделе." },
    { key: "terminal", label: "Терминал", note: "Цвета и шрифт консоли терминала и экрана входа." },
  ];
  const COLOR_GROUPS = ["Цвета", "Линии", "Акценты", "Шрифты", "Форма"];
  const DESK_TOKENS = ["--bg", "--line-faint", "--cell"];
  const WINDOW_TOKENS = ["--window-border", "--border-w", "--tab-h"];
  const PANEL_TOKENS = ["--panel"];
  let section = $state((() => { try { return localStorage.getItem(SECTION_KEY) ?? "base"; } catch { return "base"; } })());
  const sections = SECTIONS.map((s) => s.key);
  const sectionOf = (key: string) => SECTIONS.find((s) => s.key === key) ?? SECTIONS[0];
  const tokenBy = (name: string) => system.token_info.find((t) => t.name === name);
  const tokensNamed = (names: string[]) => names.map(tokenBy).filter((t): t is Schemas["TokenInfo"] => !!t);

  // предпросмотр показывает то, что сейчас настраивается; кнопки над ним включают и выключают сцены вручную
  const SCENES = [{ key: "windows", label: "Окна" }, { key: "menu", label: "Меню" }, { key: "error", label: "Ошибка" }, { key: "toast", label: "Уведомление" }];
  const SCENE_OF: Record<string, string[]> = {
    base: ["windows", "toast", "error"], desk: [], windows: ["windows"], panel: ["windows", "menu"],
    notice: ["windows", "toast", "error"], fx: ["windows"], colors: ["windows", "toast", "error"], terminal: ["windows"],
  };
  let scene = $state<string[]>([]);
  $effect(() => { const key = section; untrack(() => (scene = [...(SCENE_OF[key] ?? [])])); });
  const toggleScene = (key: string) => (scene = scene.includes(key) ? scene.filter((s) => s !== key) : [...scene, key]);
  // ---------- док, сообщения, часы: параметры с вариантами, как у окон ----------
  const groupPreset = (group: string): Record<string, string> => {
    const by = system.part_presets[group] ?? {};
    const chosenLook = group === "notice" ? look.parts.notice?.look : undefined;       // чужой вид сообщений приходит со своим углом
    return by[chosenLook ?? look.style] ?? by[look.style] ?? {};
  };
  const partValue = (group: string, key: string) => look.parts[group]?.[key] ?? groupPreset(group)[key];
  function setPart(group: string, key: string, value: string) {
    const next = { ...(look.parts[group] ?? {}) };
    if (group === "notice" && key === "look") {                  // другой вид сообщений — угол снова его, пока не выбран свой
      delete next.corner;
      if (value === system.part_presets.notice?.[look.style]?.look) delete next.look; else next.look = value;
    } else if (value === groupPreset(group)[key]) delete next[key];
    else next[key] = value;
    look.parts = { ...look.parts, [group]: next };
  }
  const partOwn = (group: string) => Object.keys(look.parts[group] ?? {}).length;
  // что изменено у ОС, по разделам: для бейджей и сводки в «Основе»
  const tokOwn = (names: string[]) => names.filter((n) => look.tokens[n]).length;
  const groupTokOwn = (groups: string[]) => system.token_info.filter((t) => groups.includes(t.group) && look.tokens[t.name]).length;
  const sectionOwn = (key: string): number => ({
    base: 0,
    desk: (wallChanged ? 1 : 0) + widgetsOwn + partOwn("icons") + partOwn("cursor") + tokOwn(DESK_TOKENS) + (look.cards ? 1 : 0),
    windows: winOwn + tokOwn([...WINDOW_TOKENS, "--title-bg", "--title-fg", "--title-bg-active", "--title-fg-active"]),
    panel: panelOwn + partOwn("clock") + partOwn("apps") + tokOwn(PANEL_TOKENS),
    notice: partOwn("notice"),
    fx: partOwn("fx"),
    colors: groupTokOwn(COLOR_GROUPS),
    terminal: groupTokOwn(["Терминал"]),
  } as Record<string, number>)[key] ?? 0;
  const allOwn = $derived(SECTIONS.reduce((sum, s) => sum + sectionOwn(s.key), 0));
  const PART_NOTE: Record<string, string> = {
    "fx:glitch:on": "Дамп памяти на столе, порченые значки и окна, редкий рывок всего экрана. Это то, чем Glitched отличается от Aether.",
    "fx:noise:on": "Зерно сигнала шевелится; при «уменьшить движение» в системе игрока замирает.",
    "icons:look:ascii": "Вместо картинок — текстовый знак приложения, и в меню запуска тоже.",
    "icons:set:text": "Картинок нет ни на столе, ни в меню: только текстовые знаки.",
    "notice:errors:banner": "Ошибка встаёт полосой под панелью, Enter или OK её закрывает. Окна не открываются.",
    "notice:errors:screen": "Ошибка закрывает весь экран, как отказ прошивки; Enter или кнопка возвращают на стол.",
  };

  // ---------- панель: вид, край, форма и элементы в трёх слотах ----------
  const PI = $derived(system.panel_info);
  const SLOTS: Slot[] = ["start", "center", "end"];
  const styleLook = $derived(PI.look_of_style[look.style] ?? "aether");
  const curLook = $derived(look.panel.look ?? styleLook);
  const panelPreset = $derived(PI.presets[curLook]);
  const fixedEdge = $derived(PI.fixed_edge.includes(curLook));
  const curEdge = $derived(fixedEdge ? panelPreset.edge : look.panel.edge ?? panelPreset.edge);
  const curForm = $derived(look.panel.form ?? panelPreset.form);
  const panel2Preset = $derived(PI.presets2[curLook]);
  const mainOn = $derived((look.panel.show ?? "on") === "on");
  const mainList = (slot: Slot): string[] => look.panel[slot] ?? panelPreset[slot];
  const mainKeys = $derived(new Set(SLOTS.flatMap((s) => mainList(s))));
  // на дополнительной панели не стоит то, что уже на главной (так же считает сервер)
  const slotList = (w: Which, slot: Slot): string[] => w === "panel" ? mainList(slot) : (look.panel2[slot] ?? panel2Preset[slot]).filter((key) => !mainOn || !mainKeys.has(key));
  const p2 = (key: "show" | "edge" | "form" | "hide" | "reserve") => look.panel2[key] ?? panel2Preset[key];
  const placedKeys = $derived(new Set([...(mainOn ? mainKeys : []), ...(p2("show") === "on" ? SLOTS.flatMap((s) => slotList("panel2", s)) : [])]));
  const freeKeys = $derived(new Set([...(mainOn ? mainKeys : []), ...SLOTS.flatMap((s) => slotList("panel2", s))]));
  const elLabel = (key: string) => PI.elements.find((e) => e.key === key)?.label ?? key;
  const elHint = (key: string) => PI.elements.find((e) => e.key === key)?.hint ?? "";
  const panelOwn = $derived(Object.keys(look.panel).length + Object.keys(look.panel2).length);
  const noExit = $derived(!["tui", "phosphor"].includes(curLook) && !PI.exits.some((key) => placedKeys.has(key)));
  let panelTab = $state<Which>("panel");
  let adding = $state<Record<string, string>>({});
  function setLook(value: string) { look.panel = value === styleLook ? {} : { look: value }; }    // другой вид — его раскладка целиком
  function setPanel(key: "edge" | "form", value: string) {
    const next = { ...look.panel };
    if (value === panelPreset[key]) delete next[key]; else next[key] = value;
    look.panel = next;
  }
  function setPanel2(key: "show" | "edge" | "form" | "hide" | "reserve", value: string) {
    const next = { ...look.panel2 };
    if (value === panel2Preset[key]) delete next[key]; else next[key] = value;
    look.panel2 = next;
  }
  function setSlots(w: Which, lists: Record<Slot, string[]>) {
    const preset = w === "panel" ? panelPreset : panel2Preset;
    const next: Record<string, unknown> = { ...look[w] };
    const same = SLOTS.every((s) => JSON.stringify(lists[s]) === JSON.stringify(preset[s]));
    for (const s of SLOTS) { if (same) delete next[s]; else next[s] = lists[s]; }
    if (w === "panel") look.panel = next as Panel; else look.panel2 = next as Panel2;
  }
  function editSlots(w: Which, change: (lists: Record<Slot, string[]>) => void) {
    const lists = { start: [...slotList(w, "start")], center: [...slotList(w, "center")], end: [...slotList(w, "end")] };
    change(lists);
    setSlots(w, lists);
  }
  const moveIn = (w: Which, slot: Slot, i: number, dir: number) => editSlots(w, (l) => { const j = i + dir; if (j < 0 || j >= l[slot].length) return; [l[slot][i], l[slot][j]] = [l[slot][j], l[slot][i]]; });
  const moveTo = (w: Which, slot: Slot, i: number, dir: number) => editSlots(w, (l) => { const to = SLOTS[SLOTS.indexOf(slot) + dir]; if (!to) return; const [key] = l[slot].splice(i, 1); if (dir > 0) l[to].unshift(key); else l[to].push(key); });
  const removeEl = (w: Which, slot: Slot, i: number) => editSlots(w, (l) => { l[slot].splice(i, 1); });
  const addEl = (w: Which, slot: Slot, key: string) => { if (key) editSlots(w, (l) => { l[slot].push(key); }); adding = { ...adding, [w + slot]: "" }; };

  // ---------- окна: каждый параметр «как в стиле» или свой вариант ----------
  const preset = $derived(system.window_presets[look.style] ?? {});
  const winValue = (key: string) => look.win[key] ?? preset[key];
  function setWin(key: string, value: string) {
    const next = { ...look.win };
    if (value === preset[key]) delete next[key]; else next[key] = value;
    look.win = next;
  }
  const winOwn = $derived(Object.keys(look.win).length);
  const WIN_NOTE: Record<string, string> = {
    "title:full": "Окно занимает весь стол между панелями, видно только верхнее. Перетаскивать и менять размер нельзя, назад ведёт кнопка «закрыть».",
    "title:tab": "Вкладка стоит над рамкой, поэтому окна открываются на высоту вкладки ниже панели.",
    "frame:ascii": "Окна встают на сетку знакомест 8×16: положение и размер кратны клетке.",
    "set:close": "Свернуть и развернуть окно на этой ОС нельзя.",
  };

  // ---------- элементы стола: у каждого «как в стиле», «вкл», «выкл»; чего нет в оболочке стиля, то недоступно ----------
  const widgetGroups = $derived([...new Set(system.widget_info.filter((w) => !["date", "toasts"].includes(w.key)).map((w) => w.group))]);
  const native = (w: Schemas["WidgetInfo"]) => w.native.includes(look.style);
  const isOn = (w: Schemas["WidgetInfo"]) => look.widgets[w.key] ?? native(w);
  function setPlace(key: string, value: string) { look.places = { ...look.places, [key]: value }; }
  function setWidget(key: string, value: boolean | null) {
    const next = { ...look.widgets };
    if (value === null) delete next[key]; else next[key] = value;
    look.widgets = next;
  }
  const widgetsOwn = $derived(Object.keys(look.widgets).length);
  const widgetWarning = $derived.by(() => {
    if (["phosphor", "tui"].includes(curLook)) return "";
    const on = (key: string) => { const w = system.widget_info.find((x) => x.key === key); return !!w && isOn(w); };
    const inPanel = ["launcher", "search", "apps", "allapps"].some((key) => placedKeys.has(key));
    return !on("icons") && !inPanel ? "Нет ни значков, ни меню запуска или быстрого запуска на панелях: приложения на этой ОС открыть нечем, кроме ссылок и хуков." : "";
  });
  $effect(() => { if (!sections.includes(section)) section = "base"; });
  $effect(() => { const value = section; try { localStorage.setItem(SECTION_KEY, value); } catch { /* память браузера может быть закрыта */ } });
  let find = $state("");
  let onlyOwn = $state(false);

  const totalOwn = $derived(system.token_info.filter((t) => look.tokens[t.name]).length);
  const wallChanged = $derived(JSON.stringify({ ...look.wallpaper, file_name: "" }) !== JSON.stringify({ ...WALLPAPER_DEFAULT, file_name: "" }));
  // поиск по всем настройкам: токены редактируются прямо в результатах, параметры ведут в свой раздел
  const query = $derived(find.trim().toLowerCase());
  const tokensIn = (groups: string[]) => system.token_info.filter((t) => groups.includes(t.group) && (!onlyOwn || look.tokens[t.name]));
  const foundTokens = $derived(query ? system.token_info.filter((t) => `${t.label} ${t.name} ${t.hint}`.toLowerCase().includes(query)) : []);
  const foundParams = $derived.by(() => {
    if (!query) return [];
    const out: { label: string; section: string }[] = [];
    const add = (label: string, key: string) => { if (label.toLowerCase().includes(query)) out.push({ label, section: key }); };
    system.window_params.forEach((p) => add(p.label, "windows"));
    for (const [group, key] of [["notice", "notice"], ["fx", "fx"], ["icons", "desk"], ["cursor", "desk"], ["clock", "panel"], ["apps", "panel"]]) (system.part_params[group] ?? []).forEach((p) => add(p.label, key));
    ["Вид панели", "Край", "Форма", "Дополнительная панель", "Автоскрытие", "Что стоит на панели"].forEach((l) => add(l, "panel"));
    PI.elements.forEach((e) => add(e.label, "panel"));
    system.widget_info.forEach((w) => add(w.label, w.key === "toasts" ? "notice" : w.key === "date" ? "panel" : "desk"));
    ["Картинка", "Узор", "Курсор", "Значки"].forEach((l) => add(l, "desk"));
    return out;
  });
  const palette = (slug: string) => ["--bg", "--panel", "--accent"].map((name) => system.style_defaults[slug]?.[name] ?? "#000000");
  const colorOf = (token: Schemas["TokenInfo"]) => look.tokens[token.name] ?? def(token);
  const isColor = (value: string) => /^(#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\()/.test(value);
  let presetOpen = $state(false);
  let openEl = $state<string | null>(null);         // элемент панели с раскрытыми настройками (часы, быстрый запуск)
  const EL_SETTINGS: Record<string, string> = { clock: "clock", apps: "apps" };

  async function resetAll() {
    if (!(await ask("Вернуть всё к заготовке?", `Изменений: ${allOwn}. Токены, окна, панели, сообщения, эффекты, значки, картинка и узор вернутся к стилю «${system.styles.find((s) => s.slug === look.style)?.label}». Пока не нажато «Сохранить», это можно отменить.`, "Вернуть всё"))) return;
    look = { ...look, tokens: {}, wallpaper: { ...WALLPAPER_DEFAULT }, widgets: {}, places: {}, win: {}, panel: {}, panel2: {}, parts: {}, cards: null };
  }
  // карточки на столе: список по порядку; пока он не задан — карточки заготовки
  const CI = $derived(system.card_info);
  const cardList = $derived(look.cards ?? CI.presets[look.style] ?? []);
  const cardOf = (key: string) => cardList.find((c) => c.key === key);
  function setCard(key: string, corner: string) {
    const list = cardList.map((c) => ({ ...c }));
    const found = list.find((c) => c.key === key);
    if (corner === "") look.cards = list.filter((c) => c.key !== key);
    else if (found) { found.corner = corner; look.cards = list; }
    else look.cards = [...list, { key, corner }];
  }
  function moveCard(key: string, dir: number) {
    const list = cardList.map((c) => ({ ...c }));
    const i = list.findIndex((c) => c.key === key);
    const j = list.findIndex((c, n) => (dir < 0 ? n < i : n > i) && c.corner === list[i].corner && (dir < 0 ? !list.slice(n + 1, i).some((x) => x.corner === c.corner) : true));
    if (i < 0 || j < 0) return;
    [list[i], list[j]] = [list[j], list[i]];
    look.cards = list;
  }
  const sameCorner = (key: string) => { const c = cardOf(key); return c ? cardList.filter((x) => x.corner === c.corner) : []; };

  function setMain(value: string) {
    const next = { ...look.panel } as Record<string, unknown>;
    if (value === "on") delete next.show; else next.show = value;
    look.panel = next as Panel;
  }
</script>

{#snippet widgetRow(w: Schemas["WidgetInfo"])}
  {@const value = look.widgets[w.key]}
  {@const own = native(w)}
  <div class="wrow">
    <div class="wname">
      <b>{w.label}<span class="wkind" class:own>{own ? "родной в стиле" : "добавляется"}</span></b>
      <span class="muted small">{w.hint}</span>
    </div>
    <div class="wctl2">
      {#if !own && isOn(w) && w.places.length}
        <select class="field place" value={look.places[w.key] ?? w.places[0].value} onchange={(e) => setPlace(w.key, e.currentTarget.value)} aria-label="Где стоит: {w.label}">
          {#each w.places as p (p.value)}<option value={p.value}>{p.label}</option>{/each}
        </select>
      {/if}
      <div class="seg" role="radiogroup" aria-label={w.label}>
        <button type="button" role="radio" aria-checked={value === undefined} class:on={value === undefined} onclick={() => setWidget(w.key, null)} title="Как в стиле: {own ? 'есть' : 'нет'}">стиль · {own ? "вкл" : "выкл"}</button>
        <button type="button" role="radio" aria-checked={value === true} class:on={value === true} onclick={() => setWidget(w.key, true)}>вкл</button>
        <button type="button" role="radio" aria-checked={value === false} class:on={value === false} onclick={() => setWidget(w.key, false)}>выкл</button>
      </div>
    </div>
  </div>
{/snippet}

{#snippet pick(title: string, options: { value: string; label: string }[], current: string, preset: string, onpick: (value: string) => void, off: boolean)}
  <div class="wprow" class:muted={off}>
    <div class="wphead"><b>{title}</b>{#if current !== preset}<button class="btn ghost small" onclick={() => onpick(preset)}>вернуть как в стиле</button>{/if}</div>
    <div class="chips" role="radiogroup" aria-label={title}>
      {#each options as option (option.value)}
        <button type="button" role="radio" class="chip" disabled={off} aria-checked={current === option.value} class:on={current === option.value} onclick={() => onpick(option.value)}>
          {option.label}{#if option.value === preset}<span class="wkind own">стиль</span>{/if}
        </button>
      {/each}
    </div>
  </div>
{/snippet}

{#snippet slotEditor(w: Which)}
  {@const preset = w === "panel" ? panelPreset : panel2Preset}
  <div class="wprow">
    <div class="wphead"><b>Что стоит на панели</b>{#if look[w].start}<button class="btn ghost small" onclick={() => setSlots(w, { start: [...preset.start], center: [...preset.center], end: [...preset.end] })}>вернуть раскладку вида</button>{/if}</div>
    <div class="slotgrid">
      {#each SLOTS as slot, s (slot)}
        <div class="slotcol">
          <span class="wlabel">{PI.slots.find((x) => x.value === slot)?.label}</span>
          {#each slotList(w, slot) as key, i (key)}
            <div class="slotel" title={elHint(key)}>
              {#if EL_SETTINGS[key]}
                <button type="button" class="slotname slotopen" aria-expanded={openEl === key} onclick={() => (openEl = openEl === key ? null : key)}>{elLabel(key)} <span aria-hidden="true">{openEl === key ? "▴" : "▾"}</span></button>
              {:else}
                <span class="slotname">{elLabel(key)}</span>
              {/if}
              <span class="slotbtns">
                <button type="button" class="ib" disabled={i === 0} onclick={() => moveIn(w, slot, i, -1)} aria-label="Выше: {elLabel(key)}">↑</button>
                <button type="button" class="ib" disabled={i === slotList(w, slot).length - 1} onclick={() => moveIn(w, slot, i, 1)} aria-label="Ниже: {elLabel(key)}">↓</button>
                <button type="button" class="ib" disabled={s === 0} onclick={() => moveTo(w, slot, i, -1)} aria-label="В слот левее: {elLabel(key)}">←</button>
                <button type="button" class="ib" disabled={s === SLOTS.length - 1} onclick={() => moveTo(w, slot, i, 1)} aria-label="В слот правее: {elLabel(key)}">→</button>
                <button type="button" class="ib" onclick={() => removeEl(w, slot, i)} aria-label="Убрать: {elLabel(key)}">×</button>
              </span>
            </div>
            {#if openEl === key && EL_SETTINGS[key]}
              <div class="elset">
                {@render params(EL_SETTINGS[key])}
                {#if key === "clock"}{#each system.widget_info.filter((x) => x.key === "date") as wd (wd.key)}{@render widgetRow(wd)}{/each}{/if}
              </div>
            {/if}
          {:else}
            <p class="muted small slotempty">пусто</p>
          {/each}
          {#if PI.elements.some((e) => !freeKeys.has(e.key))}
            <select class="field addel" value={adding[w + slot] ?? ""} onchange={(e) => addEl(w, slot, e.currentTarget.value)} aria-label="Добавить в {PI.slots.find((x) => x.value === slot)?.label}">
              <option value="">+ добавить…</option>
              {#each PI.elements.filter((e) => !freeKeys.has(e.key)) as e (e.key)}<option value={e.key}>{e.label}</option>{/each}
            </select>
          {/if}
        </div>
      {/each}
    </div>
    <p class="muted small">{w === "panel" ? "Порядок сверху вниз — слева направо на панели. Центр стоит посередине панели поверх распорки." : "У боковой панели порядок сверху вниз. У острова слоты идут подряд, у полосы во всю длину они разнесены по краям и центру."}</p>
  </div>
{/snippet}

{#snippet params(group: string)}
  {#each system.part_params[group] ?? [] as param (param.key)}
    {@const value = partValue(group, param.key)}
    {@const preset = group === "notice" && param.key === "look" ? system.part_presets.notice?.[look.style]?.look : groupPreset(group)[param.key]}
    {@const off = false}
    {@const note = PART_NOTE[`${group}:${param.key}:${value}`]}
    <div class="wprow" class:muted={off}>
      <div class="wphead">
        <b>{param.label}</b>
        {#if look.parts[group]?.[param.key] !== undefined}<button class="btn ghost small" onclick={() => setPart(group, param.key, preset)}>вернуть как в стиле</button>{/if}
      </div>
      <div class="chips" role="radiogroup" aria-label={param.label}>
        {#each param.options as option (option.value)}
          <button type="button" role="radio" class="chip" disabled={off} aria-checked={value === option.value} class:on={value === option.value} onclick={() => setPart(group, param.key, option.value)}>
            {option.label}{#if option.value === preset}<span class="wkind own">стиль</span>{/if}
          </button>
        {/each}
      </div>
      {#if note && !off}<p class="muted small">{note}</p>{/if}
    </div>
  {/each}
{/snippet}

{#snippet tokenTile(token: Schemas["TokenInfo"])}
  <div class="tok" class:changed={look.tokens[token.name]}>
    <div class="thead">
      {#if token.kind === "color"}
        <label class="sw" title="Выбрать цвет">
          <span class="swfill" style:background={isColor(colorOf(token)) ? colorOf(token) : "transparent"}></span>
          <input type="color" value={pickerValue(token)} oninput={(e) => setToken(token.name, e.currentTarget.value)} aria-label="Цвет: {token.label}" />
        </label>
      {/if}
      <div class="tname"><b>{token.label}</b><code class="muted">{token.name}</code></div>
      <button class="btn ghost reset" disabled={!look.tokens[token.name]} onclick={() => setToken(token.name, "")} title="Вернуть значение стиля ({def(token)})" aria-label="Вернуть значение стиля: {token.label}">×</button>
    </div>
    <p class="thint muted small">{token.hint}</p>
    {#if token.kind === "font"}
      <select class="field" value={look.tokens[token.name] ?? ""} onchange={(e) => setToken(token.name, e.currentTarget.value)} aria-label={token.label}>
        <option value="">как в стиле ({def(token)})</option>
        {#each system.fonts as font}<option value={font.value}>{font.label}</option>{/each}
      </select>
    {:else}
      <input class="field mono" placeholder={def(token)} value={look.tokens[token.name] ?? ""} oninput={(e) => setToken(token.name, e.currentTarget.value)} class:bad={errors.style} aria-label={token.label} />
    {/if}
  </div>
{/snippet}

{#snippet tokenBlock(title: string, list: Schemas["TokenInfo"][])}
  {#if list.length}
    <h4 class="wgroup">{title}</h4>
    <div class="tokens">{#each list as token (token.name)}{@render tokenTile(token)}{/each}</div>
  {/if}
{/snippet}

<div class="stylepage" class:nopv={!deskPreview}>
  <header class="stylehead">
    <div class="presetpick">
      <button type="button" class="presetbtn" aria-expanded={presetOpen} onclick={() => (presetOpen = !presetOpen)}>
        <span class="dots" aria-hidden="true">{#each palette(look.style) as color}<i style:background={color}></i>{/each}</span>
        <span class="pname"><span class="muted small">Заготовка</span><b>{system.styles.find((x) => x.slug === look.style)?.label}</b></span>
        <span aria-hidden="true">▾</span>
      </button>
      {#if presetOpen}
        <div class="presetpop" role="radiogroup" aria-label="Заготовка стиля">
          {#each system.styles as item (item.slug)}
            <label class="stylecard" class:on={look.style === item.slug}>
              <input type="radio" name="style" value={item.slug} bind:group={look.style} onchange={() => (presetOpen = false)} />
              <span class="dots" aria-hidden="true">{#each palette(item.slug) as color}<i style:background={color}></i>{/each}</span>
              <b>{item.label}</b>
              <span class="muted small">{item.description}</span>
            </label>
          {/each}
        </div>
      {/if}
    </div>
    <span class="muted small headnote">{system.styles.find((x) => x.slug === look.style)?.description}</span>
    <span class="headtools">
      <span class="muted small">Изменено: <b>{allOwn}</b></span>
      <button class="btn ghost small" disabled={!allOwn} onclick={resetAll}>Вернуть всё к заготовке</button>
      <a class="more" href={desktopUrl} target="_blank" rel="noopener">на рабочем столе →</a>
      {#if !deskPreview}<button class="btn ghost small" onclick={toggleDeskPreview}>Показать предпросмотр</button>{/if}
    </span>
  </header>

  <div class="stylegrid">
    <nav class="snav" aria-label="Разделы стиля">
      <label class="find"><Icon name="search" size={14} /><input placeholder="Найти настройку" bind:value={find} aria-label="Поиск по настройкам стиля" /></label>
      {#each SECTIONS as s (s.key)}
        {@const own = sectionOwn(s.key)}
        <button class="snav-item" class:on={!query && section === s.key} aria-current={!query && section === s.key ? "page" : undefined} onclick={() => { section = s.key; find = ""; }}>
          <span>{s.label}</span>{#if own}<span class="badge" title="Изменено: {own}">{own}</span>{/if}
        </button>
      {/each}
    </nav>

    <section class="panelbox" aria-label={query ? "Поиск" : sectionOf(section).label}>
      <header class="phead">
        <div>
          <h3>{query ? `Поиск: «${find.trim()}»` : sectionOf(section).label}</h3>
          <p class="muted small">{query ? `Параметров: ${foundParams.length}, токенов: ${foundTokens.length}` : sectionOf(section).note}</p>
        </div>
        {#if !query && (section === "colors" || section === "terminal")}
          <label class="check small"><input type="checkbox" bind:checked={onlyOwn} /> только изменённые</label>
        {/if}
      </header>

      {#if query}
        {#if foundParams.length}
          <div class="found">
            {#each foundParams as item, i (i)}
              <button class="chip" onclick={() => { section = item.section; find = ""; }}>{item.label} <span class="muted small">→ {sectionOf(item.section).label}</span></button>
            {/each}
          </div>
        {/if}
        <div class="tokens">{#each foundTokens as token (token.name)}{@render tokenTile(token)}{/each}</div>
        {#if !foundParams.length && !foundTokens.length}<p class="muted small pad">Ничего не нашлось. Попробуйте слово попроще: «заголовок», «док», «шум».</p>{/if}

      {:else if section === "base"}
        <div class="winparams">
          <div class="styles" role="radiogroup" aria-label="Заготовка">
            {#each system.styles as item (item.slug)}
              <label class="stylecard" class:on={look.style === item.slug} title={item.description}>
                <input type="radio" name="style2" value={item.slug} bind:group={look.style} />
                <span class="dots" aria-hidden="true">{#each palette(item.slug) as color}<i style:background={color}></i>{/each}</span>
                <b>{item.label}</b>
              </label>
            {/each}
          </div>
          <p class="muted small">{system.styles.find((x) => x.slug === look.style)?.description} Всё, что ниже, берётся у заготовки, пока не выбрано своё.</p>
          <h4 class="wgroup">Что изменено у этой ОС</h4>
          <div class="summary">
            {#each SECTIONS.filter((s) => s.key !== "base") as s (s.key)}
              {@const own = sectionOwn(s.key)}
              <button class="sumrow" onclick={() => (section = s.key)}><span>{s.label}</span><span class:muted={!own}>{own ? `изменено: ${own}` : "как в заготовке"}</span></button>
            {/each}
          </div>
          {#if errors.style}{#each errors.style as text}<p class="warn small">{text}</p>{/each}{/if}
        </div>

      {:else if section === "desk"}
        <h4 class="wgroup">Картинка и узор</h4>
        <div class="wall">
          <div class="wallrow">
            <div class="wthumb" class:empty={!look.wallpaper.file_id}>
              {#if look.wallpaper.file_id}<img src={wallUrl(look.wallpaper.file_id)} alt="" />{:else}<span class="muted small">нет</span>{/if}
            </div>
            <div class="wmeta">
              <b>{look.wallpaper.file_id ? look.wallpaper.file_name || "Файл выбран" : "Картинка не выбрана"}</b>
              <span class="muted small">Файл из хранилища (Nextcloud, папка AETHER). Игрок видит его без проверки ключей.</span>
              <div class="wacts">
                <button class="btn" onclick={() => (picking = true)}>{look.wallpaper.file_id ? "Заменить…" : "Выбрать из Nextcloud…"}</button>
                {#if look.wallpaper.file_id}<button class="btn ghost" onclick={() => { look.wallpaper.file_id = ""; look.wallpaper.file_name = ""; }}>Убрать</button>{/if}
              </div>
            </div>
          </div>
          {#if look.wallpaper.file_id}
            <div class="wctl">
              <span class="wlabel">Режим</span>
              <div class="seg" role="radiogroup" aria-label="Режим картинки">
                {#each WALL_MODES as item (item.key)}
                  <button type="button" role="radio" aria-checked={look.wallpaper.mode === item.key} class:on={look.wallpaper.mode === item.key} title={item.hint} onclick={() => (look.wallpaper.mode = item.key)}>{item.label}</button>
                {/each}
              </div>
              <span class="wlabel">Прозрачность</span>
              <div class="range"><input type="range" min="0" max="100" step="5" bind:value={look.wallpaper.opacity} aria-label="Прозрачность картинки" /><output>{look.wallpaper.opacity}%</output></div>
            </div>
          {/if}
          <div class="wctl">
            <span class="wlabel">Узор</span>
            <div class="patterns" role="radiogroup" aria-label="Узор поверх картинки">
              {#each WALL_PATTERNS as item (item.key)}
                <button type="button" role="radio" aria-checked={look.wallpaper.pattern === item.key} class="pat" class:on={look.wallpaper.pattern === item.key} onclick={() => (look.wallpaper.pattern = item.key)}>
                  <span class="swatchpat" style:background-image={item.key === "none" ? "none" : `url("${tileUrl(item.key, "#b0b0b0", 16)}")`}></span>{item.label}
                </button>
              {/each}
            </div>
            {#if look.wallpaper.pattern !== "none"}
              <span class="wlabel">Цвет</span>
              <div class="range">
                <input class="picker" type="color" value={look.wallpaper.pattern_color || gridColor} oninput={(e) => (look.wallpaper.pattern_color = e.currentTarget.value)} aria-label="Цвет узора" />
                <output class="same">{look.wallpaper.pattern_color ? look.wallpaper.pattern_color : "как у сетки стиля"}</output>
                <button class="btn ghost" disabled={!look.wallpaper.pattern_color} onclick={() => (look.wallpaper.pattern_color = "")} title="Цвет сетки стиля">×</button>
              </div>
              <span class="wlabel">Шаг</span>
              <div class="range">
                <input type="range" min="8" max="120" step="2" value={look.wallpaper.pattern_size || gridCell} oninput={(e) => (look.wallpaper.pattern_size = +e.currentTarget.value)} aria-label="Шаг узора" />
                <output>{look.wallpaper.pattern_size || gridCell} px</output>
                <button class="btn ghost" disabled={!look.wallpaper.pattern_size} onclick={() => (look.wallpaper.pattern_size = 0)} title="Шаг сетки стиля">×</button>
              </div>
              <span class="wlabel">Прозрачность</span>
              <div class="range"><input type="range" min="0" max="100" step="5" bind:value={look.wallpaper.pattern_opacity} aria-label="Прозрачность узора" /><output>{look.wallpaper.pattern_opacity}%</output></div>
            {/if}
          </div>
          {#if errors.wallpaper}{#each errors.wallpaper as text}<p class="warn small">{text}</p>{/each}{/if}
        </div>
        {@render tokenBlock("Фон и сетка стола", tokensNamed(DESK_TOKENS))}
        <h4 class="wgroup">Значки</h4>
        {#if widgetWarning}<p class="warn small">{widgetWarning}</p>{/if}
        <div class="winparams">
          {#each system.widget_info.filter((w) => w.key === "icons") as w (w.key)}{@render widgetRow(w)}{/each}
          {@render params("icons")}
        </div>
        <h4 class="wgroup">Карточки на столе {#if look.cards}<button class="btn ghost small" onclick={() => (look.cards = null)}>вернуть как в стиле</button>{/if}</h4>
        <p class="muted small">Лежат на столе под окнами. В одном углу идут сверху вниз в порядке списка.</p>
        <div class="winparams">
          {#each CI.cards as card (card.key)}
            {@const on = cardOf(card.key)}
            {@const group = sameCorner(card.key)}
            <div class="wprow">
              <div class="wphead"><b>{card.label}</b>
                {#if on && group.length > 1}<span class="slotbtns">
                  <button type="button" class="ib" disabled={group[0].key === card.key} onclick={() => moveCard(card.key, -1)} aria-label="Выше: {card.label}">↑</button>
                  <button type="button" class="ib" disabled={group[group.length - 1].key === card.key} onclick={() => moveCard(card.key, 1)} aria-label="Ниже: {card.label}">↓</button>
                </span>{/if}
              </div>
              <span class="muted small">{card.hint}</span>
              <div class="chips" role="radiogroup" aria-label="Где: {card.label}">
                <button type="button" role="radio" class="chip" aria-checked={!on} class:on={!on} onclick={() => setCard(card.key, "")}>Нет</button>
                {#each CI.corners as corner (corner.value)}
                  <button type="button" role="radio" class="chip" aria-checked={on?.corner === corner.value} class:on={on?.corner === corner.value} onclick={() => setCard(card.key, corner.value)}>{corner.label}</button>
                {/each}
              </div>
            </div>
          {/each}
          {#if errors.cards}{#each errors.cards as text}<p class="warn small">{text}</p>{/each}{/if}
        </div>
        <h4 class="wgroup">На столе</h4>
        <div class="winparams">
          {#each system.widget_info.filter((w) => !["icons", "date", "toasts"].includes(w.key)) as w (w.key)}{@render widgetRow(w)}{/each}
          {@render params("cursor")}
        </div>

      {:else if section === "windows"}
        <div class="winparams">
          {#each system.window_params.filter((p) => p.key !== "hatch" || winValue("title") === "plaque") as param (param.key)}
            {@const value = winValue(param.key)}
            {@const note = WIN_NOTE[`${param.key}:${value}`]}
            <div class="wprow">
              <div class="wphead">
                <b>{param.label}</b>
                {#if look.win[param.key]}<button class="btn ghost small" onclick={() => setWin(param.key, preset[param.key])}>вернуть как в стиле</button>{/if}
              </div>
              <div class="chips" role="radiogroup" aria-label={param.label}>
                {#each param.options as option (option.value)}
                  <button type="button" role="radio" class="chip" aria-checked={value === option.value} class:on={value === option.value} onclick={() => setWin(param.key, option.value)}>
                    {option.label}{#if option.value === preset[param.key]}<span class="wkind own">стиль</span>{/if}
                  </button>
                {/each}
              </div>
              {#if note}<p class="muted small">{note}</p>{/if}
              {#if param.key === "title"}
                <div class="titlecolors">
                  {#each titleTokens as token (token.name)}
                    <div class="tc" class:changed={look.tokens[token.name]}>
                      <label class="sw" title="Выбрать цвет">
                        <span class="swfill" style:background={isColor(look.tokens[token.name] ?? "") ? look.tokens[token.name] : "transparent"}></span>
                        <input type="color" value={pickerValue(token)} oninput={(e) => setToken(token.name, e.currentTarget.value)} aria-label="Цвет: {token.label}" />
                      </label>
                      <div class="tname"><b>{token.label}</b>
                        <input class="field mono" placeholder={def(token) || "как у заголовка"} value={look.tokens[token.name] ?? ""} oninput={(e) => setToken(token.name, e.currentTarget.value)} aria-label={token.label} /></div>
                      <button class="btn ghost reset" disabled={!look.tokens[token.name]} onclick={() => setToken(token.name, "")} title="Как у заголовка" aria-label="Вернуть: {token.label}">×</button>
                    </div>
                  {/each}
                </div>
                <p class="muted small">Цвета подходят к любому заголовку; пусто — как задумано у выбранного. У заголовка из символов текст красит и символы рамки.</p>
              {/if}
            </div>
          {/each}
          {@render tokenBlock("Рамка и размеры", tokensNamed(WINDOW_TOKENS))}
          {#if errors.window}{#each errors.window as text}<p class="warn small">{text}</p>{/each}{/if}
        </div>

      {:else if section === "panel"}
        <div class="winparams">
          <div class="seg ptabs" role="tablist" aria-label="Какая панель">
            <button type="button" role="tab" aria-selected={panelTab === "panel"} class:on={panelTab === "panel"} onclick={() => (panelTab = "panel")}>Основная{#if !mainOn} · нет{/if}</button>
            <button type="button" role="tab" aria-selected={panelTab === "panel2"} class:on={panelTab === "panel2"} onclick={() => (panelTab = "panel2")}>Дополнительная{#if p2("show") === "on"} · есть{/if}</button>
          </div>
          {#if panelTab === "panel"}
            {@render pick("Основная панель", PI.shows, look.panel.show ?? "on", "on", setMain, false)}
            {#if !mainOn}<p class="muted small">Основной панели нет: её элементы можно поставить на дополнительную. Выход из сеанса должен остаться там.</p>{/if}
            <div class="wprow" class:muted={!mainOn}>
              <div class="wphead"><b>Вид панелей</b>{#if look.panel.look}<button class="btn ghost small" onclick={() => setLook(styleLook)}>вернуть как в стиле</button>{/if}</div>
              <div class="chips" role="radiogroup" aria-label="Вид панелей">
                {#each PI.looks as option (option.value)}
                  <button type="button" role="radio" class="chip" aria-checked={curLook === option.value} class:on={curLook === option.value} onclick={() => setLook(option.value)}>
                    {option.label}{#if option.value === styleLook}<span class="wkind own">стиль</span>{/if}
                  </button>
                {/each}
              </div>
              <p class="muted small">Оформление обеих панелей. Другой вид приходит со своей раскладкой; её можно поменять ниже.</p>
            </div>
            {#if mainOn}
              {@render pick("Край", PI.edges, curEdge, panelPreset.edge, (v) => setPanel("edge", v), fixedEdge)}
              {#if fixedEdge}<p class="muted small">У этого вида панель — строка состояния сверху, а снизу своя полоса клавиш: край не меняется.</p>{/if}
              {@render pick("Форма", PI.forms, curForm, panelPreset.form, (v) => setPanel("form", v), false)}
              {#if curForm === "islands"}<p class="muted small">Каждая колонка ниже — свой остров: начало слева, центр по центру, конец справа.</p>{/if}
              {@render slotEditor("panel")}
            {/if}
          {:else}
            {@render pick("Дополнительная панель", PI.shows, p2("show"), panel2Preset.show, (v) => setPanel2("show", v), false)}
            {#if p2("show") === "on"}
              {@render pick("Край", PI.edges2, p2("edge"), panel2Preset.edge, (v) => setPanel2("edge", v), false)}
              {@render pick("Форма", PI.forms2, p2("form"), panel2Preset.form, (v) => setPanel2("form", v), false)}
              {#if p2("form") === "islands"}<p class="muted small">Каждая колонка — свой остров; сбоку они идут сверху вниз.</p>{/if}
              {@render pick("Место", PI.reserves, p2("reserve"), panel2Preset.reserve, (v) => setPanel2("reserve", v), p2("hide") === "on")}
              {#if p2("reserve") === "on" && p2("hide") !== "on"}<p class="muted small">Развёрнутые окна встают рядом с панелью и не заходят под неё.</p>{/if}
              {@render pick("Автоскрытие", PI.hides, p2("hide"), panel2Preset.hide, (v) => setPanel2("hide", v), false)}
              {#if p2("hide") === "on"}<p class="muted small">У края остаётся тонкая полоска; панель выезжает, когда к ней подводят мышь или переходят клавишей Tab.</p>{/if}
              {@render slotEditor("panel2")}
            {/if}
            <p class="muted small">Её оформление берётся у вида панелей.</p>
          {/if}
          {@render tokenBlock("Цвет панелей", tokensNamed(PANEL_TOKENS))}
          {#if noExit}<p class="warn small">Игроку не выйти из сеанса: оставьте на одной из панелей меню запуска, «Сеанс» или «Кнопки сеанса».</p>{/if}
          {#if errors.panel}{#each errors.panel as text}<p class="warn small">{text}</p>{/each}{/if}
          {#if errors.panel2}{#each errors.panel2 as text}<p class="warn small">{text}</p>{/each}{/if}
          {#if errors.parts}{#each errors.parts as text}<p class="warn small">{text}</p>{/each}{/if}
        </div>

      {:else if section === "notice" || section === "fx"}
        <div class="winparams">
          {@render params(section)}
          {#if section === "notice"}{#each system.widget_info.filter((w) => w.key === "toasts") as w (w.key)}{@render widgetRow(w)}{/each}{/if}
          {#if errors.parts}{#each errors.parts as text}<p class="warn small">{text}</p>{/each}{/if}
        </div>

      {:else if section === "colors"}
        {#each COLOR_GROUPS as group (group)}
          {@render tokenBlock(group, tokensIn([group]))}
        {/each}
        {#if onlyOwn && !groupTokOwn(COLOR_GROUPS)}<p class="muted small pad">Здесь ничего не изменено.</p>{/if}

      {:else if section === "terminal"}
        <div class="tokens">{#each tokensIn(["Терминал"]) as token (token.name)}{@render tokenTile(token)}{/each}</div>
        {#if onlyOwn && !groupTokOwn(["Терминал"])}<p class="muted small pad">Здесь ничего не изменено.</p>{/if}
      {/if}
    </section>

    {#if deskPreview}
      <aside class="stylepreview">
        <div class="block">
          <h3>Предпросмотр <span class="muted small">с несохранёнными изменениями</span> <button class="btn ghost small hidepv" onclick={toggleDeskPreview}>Скрыть</button></h3>
          <div class="scenes" role="group" aria-label="Что показать в предпросмотре">
            {#each SCENES as s (s.key)}
              <button type="button" class="chip" aria-pressed={scene.includes(s.key)} class:on={scene.includes(s.key)} onclick={() => toggleScene(s.key)}>{s.label}</button>
            {/each}
          </div>
          <div class="pvframe" bind:clientWidth={previewWidth} style:height="{(previewWidth * PREVIEW_H) / PREVIEW_W}px">
            {#if previewSrc}
              <iframe title="Предпросмотр рабочего стола" src={previewSrc} style:width="{PREVIEW_W}px" style:height="{PREVIEW_H}px" style:transform="scale({previewWidth / PREVIEW_W})"></iframe>
            {/if}
          </div>
          <p class="muted small">Настоящий рабочий стол с тестовыми приложениями. Сцена подстраивается под раздел; внутри можно открывать меню и окна.</p>
        </div>
      </aside>
    {/if}
  </div>
</div>

{#if picking}
  <WallpaperPicker current={look.wallpaper.file_id} previewUrl={wallUrl} onclose={() => (picking = false)}
    onpick={(fileId, name) => { look.wallpaper.file_id = fileId; look.wallpaper.file_name = name; picking = false; }} />
{/if}

<style>
  .small { font-size: 12px; margin: 0; }
  .warn { color: var(--warn); margin: 0; }
  .more { margin-left: auto; font-size: 12px; text-transform: none; letter-spacing: 0; }
  .hidepv { margin-left: auto; text-transform: none; letter-spacing: 0; }
  .styles { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 8px; }
  .stylecard { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); cursor: pointer; }
  .stylecard:hover { border-color: var(--line); }
  .stylecard.on { border-color: var(--accent); background: var(--accent-soft); }
  .stylecard:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 1px; }
  .stylecard input { position: absolute; opacity: 0; pointer-events: none; }
  .dots { display: flex; }
  .dots i { width: 22px; height: 22px; border: 1px solid var(--line); margin-right: -6px; border-radius: 50%; }
  .badge { min-width: 18px; padding: 0 6px; border-radius: 999px; background: var(--accent); color: var(--bg); font-size: 11px; text-align: center; line-height: 18px; }
  .panelbox { display: flex; flex-direction: column; gap: 14px; min-width: 0; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .phead { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
  .phead h3 { margin: 0 0 2px; font-size: 15px; text-transform: none; letter-spacing: 0; }
  .find { display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { width: 150px; padding: 5px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .check { display: flex; align-items: center; gap: 6px; }
  .pad { padding: 8px; }
  .tokens { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }
  .tok { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .tok.changed { border-color: var(--accent); }
  .thead { display: flex; align-items: center; gap: 10px; }
  .sw { position: relative; flex: none; width: 34px; height: 34px; border: 1px solid var(--line-bright); border-radius: var(--radius-s); overflow: hidden; cursor: pointer; background: repeating-conic-gradient(var(--panel-2) 0 25%, var(--bg) 0 50%) 0 0 / 8px 8px; }
  .sw:focus-within { outline: 2px solid var(--accent); outline-offset: 1px; }
  .swfill { position: absolute; inset: 0; }
  .sw input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; }
  .tname { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .tname b { font-weight: 600; overflow-wrap: anywhere; }
  .tname code { font-size: 11px; }
  .reset { padding: 0 8px; height: 26px; }
  .thint { margin: 0; line-height: 1.4; }
  .tok .field { width: 100%; min-width: 0; }
  .stylepage { display: flex; flex-direction: column; gap: 12px; }
  .stylehead { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; padding: 10px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .presetpick { position: relative; }
  .presetbtn { display: flex; align-items: center; gap: 10px; padding: 6px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--text); font: inherit; cursor: pointer; }
  .presetbtn:hover, .presetbtn[aria-expanded="true"] { border-color: var(--accent); }
  .pname { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.2; }
  .presetpop { position: absolute; z-index: 20; top: calc(100% + 6px); left: 0; width: min(560px, 80vw); display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding: 10px;
               border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45); }
  .headnote { flex: 1; min-width: 220px; }
  .headtools { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .stylegrid { display: grid; grid-template-columns: 180px minmax(420px, 1fr) minmax(320px, 400px); gap: 16px; align-items: start; }
  .stylepage.nopv .stylegrid { grid-template-columns: 200px minmax(0, 1fr); }
  .snav { position: sticky; top: 8px; display: flex; flex-direction: column; gap: 2px; }
  .snav .find { margin-bottom: 8px; }
  .snav .find input { width: 100%; }
  .snav-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; text-align: left; cursor: pointer; }
  .snav-item:hover { background: var(--panel-2); color: var(--text); }
  .snav-item.on { background: var(--accent-soft); color: var(--text); }
  .snav-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .summary { display: flex; flex-direction: column; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .sumrow { display: flex; justify-content: space-between; gap: 8px; padding: 8px 12px; border: 0; border-bottom: 1px solid var(--line-soft); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .sumrow:last-child { border-bottom: 0; }
  .sumrow:hover { background: var(--panel-2); }
  .found { display: flex; flex-wrap: wrap; gap: 6px; }
  .scenes { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
  .slotopen { border: 0; background: none; padding: 0; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .slotopen:hover { color: var(--accent); }
  .elset { margin: -2px 0 4px; padding: 4px 10px 8px; border: 1px dashed var(--line-soft); border-radius: var(--radius-s); }
  @media (max-width: 1400px) { .stylegrid { grid-template-columns: 180px minmax(0, 1fr); } .stylepreview { grid-column: 1 / -1; position: static; } }
  @media (max-width: 760px) { .stylegrid { grid-template-columns: minmax(0, 1fr); } .snav { position: static; flex-direction: row; flex-wrap: wrap; } }
  .stylepreview { position: sticky; top: 8px; }
  .pvframe { position: relative; overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius-s); background: #000; }
  .pvframe iframe { position: absolute; top: 0; left: 0; border: 0; transform-origin: 0 0; }
  .picker { width: 34px; height: 32px; padding: 0; border: 1px solid var(--line); border-radius: var(--radius-s); background: none; cursor: pointer; }
  .field.bad { border-color: var(--danger); }
  .wall { display: flex; flex-direction: column; gap: 12px; }
  .wallrow { display: grid; grid-template-columns: auto 1fr; gap: 14px; align-items: center; }
  .wthumb { width: 120px; height: 76px; display: grid; place-items: center; overflow: hidden; border-radius: var(--radius-s); border: 1px solid var(--line-soft); background: repeating-conic-gradient(var(--panel-2) 0 25%, var(--bg) 0 50%) 0 0 / 14px 14px; }
  .wthumb.empty { border-style: dashed; }
  .wthumb img { max-width: 100%; max-height: 100%; object-fit: contain; }
  .wmeta { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .wmeta b { overflow-wrap: anywhere; }
  .wacts { display: flex; gap: 8px; margin-top: 4px; }
  .wctl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 8px 14px; align-items: center; }
  .wlabel { color: var(--muted); font-size: 12px; }
  .seg { display: inline-flex; width: max-content; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 4px 14px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .range { display: flex; align-items: center; gap: 10px; }
  .range input { flex: 1; max-width: 280px; accent-color: var(--accent); }
  .range input.picker { flex: none; max-width: none; width: 34px; }
  .range output.same { min-width: 0; }
  .range output { min-width: 52px; font-variant-numeric: tabular-nums; color: var(--muted); font-size: 12.5px; }
  .patterns { display: flex; gap: 8px; flex-wrap: wrap; }
  .pat { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 6px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
  .pat:hover { color: var(--text); border-color: var(--line); }
  .pat.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .swatchpat { width: 48px; height: 32px; border-radius: 4px; background-color: var(--bg); background-size: 16px 16px; border: 1px solid var(--line-soft); }

  .wgroup { margin: 10px 0 2px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .wrow { display: flex; flex-direction: column; gap: 6px; padding: 8px 4px; border-bottom: 1px solid var(--line-soft); }
  .wrow .seg { flex-shrink: 0; }
  .wrow .seg button { padding: 4px 10px; white-space: nowrap; }
  .wkind { margin-left: 6px; white-space: nowrap; padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 10.5px; font-weight: 500; }
  .wkind.own { color: var(--accent); }
  .wctl2 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .wname b { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 2px; }
  .wctl2 .place { width: auto; height: 26px; padding: 0 6px; font-size: 12px; }
  .wname { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .wrow .seg button:disabled { cursor: not-allowed; }
  .winparams { display: flex; flex-direction: column; gap: 4px; }
  .wprow { display: flex; flex-direction: column; gap: 8px; padding: 10px 4px; border-bottom: 1px solid var(--line-soft); }
  .wprow:last-of-type { border-bottom: 0; }
  .wphead { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-height: 26px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 5px 12px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .chip:hover { color: var(--text); border-color: var(--line); }
  .chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .chip:disabled { opacity: 0.45; cursor: not-allowed; }
  .ptabs { margin: 0 0 4px; }
  .ptabs button { padding: 6px 16px; }
  .titlecolors { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px; }
  .tc { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .tc.changed { border-color: var(--accent); }
  .tc .tname { gap: 4px; }
  .tc .tname b { font-size: 12.5px; font-weight: 500; }
  .tc .field { width: 100%; min-width: 0; height: 26px; font-size: 12px; }
  .slotgrid { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
  .slotcol { display: flex; flex-direction: column; gap: 6px; min-width: 0; padding: 8px; border: 1px dashed var(--line-soft); border-radius: var(--radius-s); }
  .slotel { display: flex; align-items: center; justify-content: space-between; gap: 6px; padding: 4px 4px 4px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .slotname { flex: 1; min-width: 60px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; }
  .slotbtns { display: inline-flex; flex: none; }
  .ib { width: 22px; height: 22px; padding: 0; border: 0; border-radius: 4px; background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
  .ib:hover:not(:disabled) { background: var(--panel-2); color: var(--text); }
  .ib:disabled { opacity: 0.3; cursor: default; }
  .ib:focus-visible { outline: 2px solid var(--accent); }
  .slotempty { padding: 4px 2px; }
  .addel { width: 100%; height: 28px; font-size: 12px; }
</style>
