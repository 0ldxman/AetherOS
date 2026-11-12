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
  type Done = (data: System | undefined, error: unknown, text: string) => void;

  let { system, errors, done, onstate }: { system: System; errors: Record<string, string[]>; done: Done; onstate: (state: { dirty: boolean; share: typeof share; save: () => unknown } | null) => void } = $props();

  let look = $state({ style: "aether", tokens: {} as Record<string, string>, wallpaper: { ...WALLPAPER_DEFAULT } as Wallpaper, widgets: {} as Record<string, boolean>, places: {} as Record<string, string> });
  let picking = $state(false);
  let lookSaved = $state("");
  let base = $state<typeof look | null>(null);                  // сохранённое: им наполняется общий черновик
  const share = new SharedForm({ room: () => `systems/${system.code}`, scope: () => "style", draft: () => look, base: () => base });
  const lookDirty = $derived(JSON.stringify(look) !== lookSaved);
  const groups = $derived([...new Set(system.token_info.map((t) => t.group))]);
  const HEX6 = /^#[0-9a-fA-F]{6}$/;

  async function saveLook() {
    const body = { style: look.style, tokens: look.tokens, wallpaper: look.wallpaper, widgets: look.widgets, widget_places: look.places };
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
    const url = `${system.preview_url}?preview_os=${encodeURIComponent(system.code)}&preview_style=${encodeURIComponent(look.style)}&preview_tokens=${encodeURIComponent(JSON.stringify(look.tokens))}&preview_wall=${encodeURIComponent(JSON.stringify(look.wallpaper))}&preview_widgets=${encodeURIComponent(JSON.stringify(look.widgets))}&preview_places=${encodeURIComponent(JSON.stringify(look.places))}`;
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
      const next = { style: data.style, tokens: { ...data.style_tokens }, wallpaper: { ...WALLPAPER_DEFAULT, ...data.wallpaper }, widgets: { ...data.widgets }, places: { ...data.widget_places } };
      if (!share.ready) look = { style: next.style, tokens: { ...next.tokens }, wallpaper: { ...next.wallpaper }, widgets: { ...next.widgets }, places: { ...next.places } };
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

  // ---------- разделы: «Картинка и узор» и группы токенов, по одному на экране ----------
  const SECTION_KEY = "studio.styleSection";
  const GROUP_NOTE: Record<string, string> = {
    "Цвета": "Основная палитра стола: фон, панели и четыре вида текста.",
    "Линии": "Разделители, рамки и сетка рабочего стола.",
    "Акценты": "Цвет интерфейса и статусов: выбранное, успех, предупреждение, ошибка.",
    "Терминал": "Цвета консоли терминала и экрана входа.",
    "Шрифты": "Гарнитуры и размер букв.",
    "Форма": "Скругление, толщина рамок и размеры элементов.",
  };
  let section = $state((() => { try { return localStorage.getItem(SECTION_KEY) ?? "wall"; } catch { return "wall"; } })());
  const sections = $derived(["wall", "widgets", ...groups]);

  // ---------- элементы стола: у каждого «как в стиле», «вкл», «выкл»; чего нет в оболочке стиля, то недоступно ----------
  const widgetGroups = $derived([...new Set(system.widget_info.map((w) => w.group))]);
  const native = (w: Schemas["WidgetInfo"]) => w.native.includes(look.style);
  const locked = (w: Schemas["WidgetInfo"]) => w.locked.includes(look.style);
  const isOn = (w: Schemas["WidgetInfo"]) => locked(w) || (look.widgets[w.key] ?? native(w));
  function setPlace(key: string, value: string) { look.places = { ...look.places, [key]: value }; }
  function setWidget(key: string, value: boolean | null) {
    const next = { ...look.widgets };
    if (value === null) delete next[key]; else next[key] = value;
    look.widgets = next;
  }
  const widgetsOwn = $derived(Object.keys(look.widgets).length);
  const widgetWarning = $derived.by(() => {
    if (look.style === "phosphor") return "";
    const on = (key: string) => { const w = system.widget_info.find((x) => x.key === key); return !!w && isOn(w); };
    return !on("icons") && !on("launcher") && !on("dock") ? "Выключены и значки, и меню запуска, и док: приложения на этой ОС открыть нечем, кроме ссылок и хуков." : "";
  });
  $effect(() => { if (!sections.includes(section)) section = "wall"; });
  $effect(() => { const value = section; try { localStorage.setItem(SECTION_KEY, value); } catch { /* память браузера может быть закрыта */ } });
  let find = $state("");
  let onlyOwn = $state(false);

  const ownIn = (group: string) => system.token_info.filter((t) => t.group === group && look.tokens[t.name]).length;
  const totalOwn = $derived(system.token_info.filter((t) => look.tokens[t.name]).length);
  const wallChanged = $derived(JSON.stringify({ ...look.wallpaper, file_name: "" }) !== JSON.stringify({ ...WALLPAPER_DEFAULT, file_name: "" }));
  // токены на экране: при поиске по всем группам, иначе выбранная группа; «только изменённые» оставляет переопределённые
  const query = $derived(find.trim().toLowerCase());
  const shown = $derived(system.token_info.filter((t) =>
    (query ? `${t.label} ${t.name} ${t.hint}`.toLowerCase().includes(query) : t.group === section) && (!onlyOwn || look.tokens[t.name])));
  const palette = (slug: string) => ["--bg", "--panel", "--accent"].map((name) => system.style_defaults[slug]?.[name] ?? "#000000");
  const colorOf = (token: Schemas["TokenInfo"]) => look.tokens[token.name] ?? def(token);
  const isColor = (value: string) => /^(#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\()/.test(value);

  async function resetAll() {
    if (!(await ask("Вернуть все токены к стилю?", `Переопределённых токенов: ${totalOwn}. Картинка и узор не меняются. Пока не нажато «Сохранить», это можно отменить.`, "Вернуть"))) return;
    look.tokens = {};
  }
</script>

  <div class="stylegrid" class:nopv={!deskPreview}>
  <div class="stylemain">
  <div class="block">
    <h3>Стиль рабочего стола и окон <a class="more" href={desktopUrl} target="_blank" rel="noopener">посмотреть на рабочем столе →</a>
      {#if !deskPreview}<button class="btn ghost small" onclick={toggleDeskPreview}>Показать предпросмотр</button>{/if}</h3>
    <div class="styles" role="radiogroup" aria-label="Стиль">
      {#each system.styles as item (item.slug)}
        <label class="stylecard" class:on={look.style === item.slug} title={item.description}>
          <input type="radio" name="style" value={item.slug} bind:group={look.style} />
          <span class="dots" aria-hidden="true">{#each palette(item.slug) as color}<i style:background={color}></i>{/each}</span>
          <b>{item.label}</b>
        </label>
      {/each}
    </div>
    <p class="muted small desc">{system.styles.find((x) => x.slug === look.style)?.description} Стиль задаёт раскладку и вид элементов, токены ниже переназначают цвета, шрифты и форму поверх него.</p>
  </div>

  <div class="settings">
    <nav class="rail" aria-label="Разделы настроек">
      {#each sections as key (key)}
        {@const own = key === "wall" ? (wallChanged ? 1 : 0) : key === "widgets" ? widgetsOwn : ownIn(key)}
        <button class="rail-item" class:on={!query && section === key} aria-current={!query && section === key ? "true" : undefined} onclick={() => { section = key; find = ""; }}>
          <span>{key === "wall" ? "Картинка и узор" : key === "widgets" ? "Элементы стола" : key}</span>
          {#if own}<span class="badge" title={key === "wall" ? "Картинка или узор заданы" : key === "widgets" ? `Изменено элементов: ${own}` : `Изменено токенов: ${own}`}>{key === "wall" ? "●" : own}</span>{/if}
        </button>
      {/each}
      <div class="rail-foot">
        <span class="muted small">Изменено токенов: <b>{totalOwn}</b></span>
        <button class="btn ghost small" disabled={!totalOwn} onclick={resetAll}>Сбросить всё к стилю</button>
      </div>
    </nav>

    <section class="panelbox" aria-label={section === "wall" ? "Картинка и узор" : section === "widgets" ? "Элементы стола" : section}>
      <header class="phead">
        <div>
          <h3>{query ? "Поиск по токенам" : section === "wall" ? "Картинка и узор" : section === "widgets" ? "Элементы стола" : section}</h3>
          <p class="muted small">{query ? `Найдено: ${shown.length}` : section === "widgets" ? "Что показывает оболочка стиля на этой ОС. Вид у каждого элемента от стиля; две ОС с одним стилем могут показывать разное." : section === "wall" ? "Лежат под окнами и значками, не зависят от выбранного стиля. Цвет под ними это токен «Фон рабочего стола» в разделе «Цвета»." : GROUP_NOTE[section]}</p>
        </div>
        <div class="tools">
          {#if (section !== "wall" && section !== "widgets") || query}
            <label class="find"><Icon name="search" size={14} /><input placeholder="Найти токен" bind:value={find} aria-label="Поиск токена" /></label>
            <label class="check small"><input type="checkbox" bind:checked={onlyOwn} /> только изменённые</label>
          {/if}
        </div>
      </header>

      {#if section === "wall" && !query}
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
          <span class="wlabel"></span>
          <p class="muted small">Пока цвет и шаг не заданы, узор повторяет сетку выбранного стиля ({gridCell} px), и замена получается незаметной.</p>
        {/if}
      </div>
      {#if errors.wallpaper}{#each errors.wallpaper as text}<p class="warn small">{text}</p>{/each}{/if}
    </div>
      {:else if section === "widgets" && !query}
        <div class="widgets">
          {#if widgetWarning}<p class="warn small">{widgetWarning}</p>{/if}
          {#each widgetGroups as group (group)}
            <h4 class="wgroup">{group === "Панель" ? "На панелях оболочки" : "На самом столе"}</h4>
            {#each system.widget_info.filter((w) => w.group === group) as w (w.key)}
              {@const value = look.widgets[w.key]}
              {@const own = native(w)}
              <div class="wrow">
                <div class="wname">
                  <b>{w.label}<span class="wkind" class:own>{own ? "родной в стиле" : "добавляется"}</span></b>
                  <span class="muted small">{locked(w) ? "Здесь выход из сессии: в этом стиле не выключается." : w.hint}</span>
                </div>
                <div class="wctl2">
                  {#if !own && isOn(w) && w.places.length}
                    <select class="field place" value={look.places[w.key] ?? w.places[0].value} onchange={(e) => setPlace(w.key, e.currentTarget.value)} aria-label="Где стоит: {w.label}">
                      {#each w.places as p (p.value)}<option value={p.value}>{p.label}</option>{/each}
                    </select>
                  {/if}
                  <div class="seg" role="radiogroup" aria-label={w.label}>
                    <button type="button" role="radio" aria-checked={value === undefined} disabled={locked(w)} class:on={value === undefined && !locked(w)} onclick={() => setWidget(w.key, null)} title="Как в стиле: {own ? 'есть' : 'нет'}">стиль · {own ? "вкл" : "выкл"}</button>
                    <button type="button" role="radio" aria-checked={value === true || locked(w)} class:on={value === true || locked(w)} onclick={() => setWidget(w.key, true)}>вкл</button>
                    <button type="button" role="radio" aria-checked={value === false} disabled={locked(w)} class:on={value === false} onclick={() => setWidget(w.key, false)}>выкл</button>
                  </div>
                </div>
              </div>
            {/each}
          {/each}
        </div>
      {:else}
        <div class="tokens">
          {#each shown as token (token.name)}
            <div class="tok" class:changed={look.tokens[token.name]}>
              <div class="thead">
                {#if token.kind === "color"}
                  <label class="sw" title="Выбрать цвет">
                    <span class="swfill" style:background={isColor(colorOf(token)) ? colorOf(token) : "transparent"}></span>
                    <input type="color" value={pickerValue(token)} oninput={(e) => setToken(token.name, e.currentTarget.value)} aria-label="Цвет: {token.label}" />
                  </label>
                {/if}
                <div class="tname"><b>{token.label}</b><code class="muted">{token.name}</code></div>
                <button class="btn ghost reset" disabled={!look.tokens[token.name]} onclick={() => setToken(token.name, "")} title="Вернуть значение стиля ({def(token)})" aria-label="Вернуть значение стиля">×</button>
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
          {:else}
            <p class="muted small pad">{onlyOwn ? "Здесь ничего не изменено." : "Ничего не нашлось."}</p>
          {/each}
        </div>
      {/if}
    </section>
  </div>
  {#if errors.style}{#each errors.style as text}<p class="warn small">{text}</p>{/each}{/if}
  </div>
  {#if deskPreview}
  <aside class="stylepreview">
    <div class="block">
      <h3>Предпросмотр <span class="muted small">с несохранёнными изменениями</span> <button class="btn ghost small hidepv" onclick={toggleDeskPreview}>Скрыть</button></h3>
      <div class="pvframe" bind:clientWidth={previewWidth} style:height="{(previewWidth * PREVIEW_H) / PREVIEW_W}px">
        {#if previewSrc}
          <iframe title="Предпросмотр рабочего стола" src={previewSrc} style:width="{PREVIEW_W}px" style:height="{PREVIEW_H}px" style:transform="scale({previewWidth / PREVIEW_W})"></iframe>
        {/if}
      </div>
      <p class="muted small">Настоящий рабочий стол с тестовыми приложениями. Внутри можно пользоваться меню и открывать окна.</p>
    </div>
  </aside>
  {/if}
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
  .desc { margin-top: 8px; }
  .settings { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
  .rail { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; padding-bottom: 8px; border-bottom: 1px solid var(--line-soft); }
  .rail-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; text-align: left; cursor: pointer; }
  .rail-item:hover { background: var(--panel-2); color: var(--text); }
  .rail-item.on { background: var(--accent-soft); color: var(--text); }
  .rail-item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .badge { min-width: 18px; padding: 0 6px; border-radius: 999px; background: var(--accent); color: var(--bg); font-size: 11px; text-align: center; line-height: 18px; }
  .rail-foot { display: flex; align-items: center; gap: 8px; margin-left: auto; }
  .panelbox { display: flex; flex-direction: column; gap: 14px; min-width: 0; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .phead { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
  .phead h3 { margin: 0 0 2px; font-size: 15px; text-transform: none; letter-spacing: 0; }
  .tools { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
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
  .stylegrid.nopv { grid-template-columns: minmax(0, 1fr); }
  .stylegrid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 520px); gap: 16px; align-items: start; }
  .stylemain { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
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
  @media (max-width: 1280px) { .stylegrid { grid-template-columns: minmax(0, 1fr); } .stylepreview { position: static; } }
  .widgets { display: flex; flex-direction: column; gap: 4px; }
  .wgroup { margin: 10px 0 2px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .wrow { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 6px 4px; border-bottom: 1px solid var(--line-soft); }
  .wrow .seg { flex-shrink: 0; }
  .wrow .seg button { padding: 4px 10px; white-space: nowrap; }
  .wkind { margin-left: 8px; padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 10.5px; font-weight: 500; }
  .wkind.own { color: var(--accent); }
  .wctl2 { display: flex; align-items: center; gap: 6px; }
  .wctl2 .place { width: auto; height: 26px; padding: 0 6px; font-size: 12px; }
  .wname { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .wrow .seg button:disabled { cursor: not-allowed; }
</style>
