<script lang="ts">
  // Территории: карта на выбранную дату. Режимы: просмотр, покраска страной, выбор кликами, рамка, страна целиком, ластик.
  // Выделение можно передать стране, убрать (записи этой даты) или выделить в новую страну; страну можно передать целиком.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import Icon from "../../lib/Icon.svelte";
  import MapView from "../../lib/MapView.svelte";
  import { LOOKS, RIGHTS, VIEWS, type MapView as View, type Rights } from "../../lib/mapLooks";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, NO_COLOR, showDate, today, type Country } from "./shared";

  type Mode = "inspect" | "paint" | "select" | "box" | "country" | "erase";
  const MODES: { key: Mode; label: string; hint: string; icon: string; hotkey: string }[] = [
    { key: "inspect", label: "Просмотр", icon: "cursor", hotkey: "v", hint: "Клик по провинции показывает её владельца и историю. Ничего не меняет." },
    { key: "paint", label: "Покраска", icon: "brush", hotkey: "b", hint: "Выберите страну слева и кликайте по провинциям: каждая сразу переходит стране с выбранной даты." },
    { key: "select", label: "Выбор", icon: "listcheck", hotkey: "s", hint: "Клик добавляет провинцию в выделение или убирает её. Потом выделение передают стране справа." },
    { key: "box", label: "Рамка", icon: "boxselect", hotkey: "r", hint: "Тяните рамку по карте: всё под ней попадает в выделение. С Alt рамка убирает из выделения." },
    { key: "country", label: "Страна", icon: "flag", hotkey: "c", hint: "Клик выделяет все провинции страны, которой принадлежит эта. С Shift добавляет к выделению." },
    { key: "erase", label: "Ластик", icon: "eraser", hotkey: "e", hint: "Клик убирает запись владения, начатую ровно в выбранную дату: провинция возвращается к прежнему владельцу." },
  ];

  const LOOK_KEY = "studio.mapLook";
  function remembered(): { look: string; view: View; rights: Rights } {
    try {
      const raw = JSON.parse(localStorage.getItem(LOOK_KEY) ?? "{}");
      return {
        look: raw.look in LOOKS ? raw.look : "dark",
        view: VIEWS.some((v) => v.key === raw.view) ? raw.view : "political",
        rights: RIGHTS.some((r) => r.key === raw.rights) ? raw.rights : "all",
      };
    } catch { return { look: "dark", view: "political", rights: "all" }; }
  }
  const saved = remembered();
  let look = $state(saved.look);
  let view = $state<View>(saved.view);
  let rights = $state<Rights>(saved.rights);
  $effect(() => {
    const value = JSON.stringify({ look, view, rights });
    try { localStorage.setItem(LOOK_KEY, value); } catch { /* память браузера может быть закрыта */ }
  });
  let tab = $state<"countries" | "provinces">("countries");
  let pq = $state("");
  let found = $state<Schemas["MapProvincePage"]>({ total: 0, rows: [] });
  let mapView: { zoomBy(d: number): void; reset(): void; fitBounds(b: [number, number, number, number]): void; flash(code: string): void } | undefined = $state();

  let dates = $state<string[]>([]);
  let date = $state("");
  let owners = $state<Record<string, Schemas["MapOwnerOnDate"]>>({});
  let countries = $state<Country[]>([]);
  let filter = $state("");
  let mode = $state<Mode>("inspect");
  let active = $state<number | null>(null);          // страна для покраски и передачи
  let selection = $state<string[]>([]);
  let jure = $state(true);
  let facto = $state(true);
  let province = $state<Schemas["MapProvinceOut"] | null>(null);
  let hover = $state<string | null>(null);
  let busy = $state(false);
  let dialog = $state<null | "split" | "transfer">(null);
  let draft = $state({ code: "", name: "", color: "#c8372d" });
  let errors = $state<Record<string, string[]>>({});
  let move = $state({ source: 0, target: 0 });

  // что закрашено: все владения или только по праву / только по контролю
  const colors = $derived(Object.fromEntries(Object.entries(owners)
    .filter(([, own]) => rights === "all" || (rights === "jure" ? own.de_jure : own.de_facto))
    .map(([code, own]) => [code, own.color])));
  // карта в её приложении (просмотрщик игры): та же дата, режим и стиль, что выбраны здесь
  const viewerUrl = $derived.by(() => {
    const root = window.STUDIO.api.replace(/studio\/api\/?$/, "");
    const query = new URLSearchParams({ mode: view, theme: look });
    if (date) query.set("date", date);
    return `${new URL("apps/map/", new URL(root, location.href)).pathname}?${query}`;
  });
  const dateIndex = $derived(Math.max(0, dates.findLastIndex((d) => d <= date)));
  const byId = $derived(new Map(countries.map((c) => [c.id, c])));
  const shown = $derived(countries.filter((c) => !filter.trim() || `${c.name} ${c.code}`.toLowerCase().includes(filter.trim().toLowerCase())));
  const activeCountry = $derived(active === null ? null : byId.get(active) ?? null);
  const hoverOwner = $derived(hover && owners[hover] ? byId.get(owners[hover].country) : null);
  const mayPaint = $derived(mode === "paint" && activeCountry !== null);

  // поиск провинции: по названию и коду, владелец на выбранную дату
  let findTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const text = pq.trim();
    const on = date;
    clearTimeout(findTimer);
    if (tab !== "provinces") return;
    if (!text) { found = { total: 0, rows: [] }; return; }
    findTimer = setTimeout(async () => {
      found = (await api.GET("/studio/api/map/provinces", { params: { query: { q: text, on, limit: 40 } } })).data ?? { total: 0, rows: [] };
    }, 200);
  });
  // показать провинцию из списка: камера на неё, обводка на пару секунд и карточка с историей
  function focusProvince(row: Schemas["MapProvinceRow"]) {
    if (row.bounds) mapView?.fitBounds(row.bounds as [number, number, number, number]);
    mapView?.flash(row.source_code);
    inspect(row.source_code);
  }

  async function loadCountries() {
    countries = (await api.GET("/studio/api/map/countries")).data ?? [];
  }
  async function loadDates() {
    dates = (await api.GET("/studio/api/map/territory/dates")).data ?? [];
  }
  async function loadOwners() {
    if (!date) return;
    owners = (await api.GET("/studio/api/map/territory/owners", { params: { query: { date } } })).data ?? {};
  }

  onMount(async () => {
    await Promise.all([loadCountries(), loadDates()]);
    date = dates.at(-1) ?? today();
  });
  $effect(() => { date; loadOwners(); });

  function step(direction: -1 | 1) {
    const found = direction < 0 ? [...dates].reverse().find((d) => d < date) : dates.find((d) => d > date);
    if (found) date = found;
  }

  async function inspect(code: string) {
    const { data } = await api.GET("/studio/api/map/provinces/by-code/{source_code}", { params: { path: { source_code: code }, query: { on: date } } });
    province = data ?? null;
  }

  function summary(out: Schemas["MapApplyOut"]): string {
    const parts = [out.created && `новых ${out.created}`, out.updated && `изменено ${out.updated}`, out.unchanged && `без изменений ${out.unchanged}`];
    const note = [out.later && `позже есть записи у ${out.later}`, out.missing.length && `нет в базе: ${out.missing.length}`];
    return [parts.filter(Boolean).join(", ") || "ничего не изменилось", ...note.filter(Boolean)].join("; ");
  }

  async function apply(codes: string[], country: Country | null = activeCountry) {
    if (!country || !codes.length || busy) return false;
    busy = true;
    const { data, error } = await api.POST("/studio/api/map/territory/apply", { body: { codes, country: country.id, date, de_jure: jure, de_facto: facto } });
    busy = false;
    if (error || !data) { toast(problem(error, "Не удалось передать."), "error"); return false; }
    toast(`${country.name} с ${showDate(date)}: ${summary(data)}.`);
    await loadOwners();
    if (province && codes.includes(province.source_code)) inspect(province.source_code);
    if (!dates.includes(date)) loadDates();
    return true;
  }

  async function erase(codes: string[]) {
    if (!codes.length || busy) return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/map/territory/erase", { body: { codes, date } });
    busy = false;
    if (error || !data) return toast(problem(error, "Не удалось убрать."), "error");
    toast(data.deleted ? `Убрано записей: ${data.deleted}. Провинции вернулись к прежним владельцам.` : `На ${showDate(date)} записей у этих провинций нет.`, data.deleted ? "ok" : "error");
    await loadOwners();
    if (province) inspect(province.source_code);
  }

  async function pick(code: string | null, event: { shift: boolean }) {
    if (!code) return;
    if (mode === "inspect") return inspect(code);
    if (mode === "paint") {
      if (!activeCountry) return toast("Сначала выберите страну в списке слева.", "error");
      return apply([code]);
    }
    if (mode === "erase") return erase([code]);
    if (mode === "select") {
      selection = selection.includes(code) ? selection.filter((c) => c !== code) : [...selection, code];
      return;
    }
    if (mode === "country") {
      const own = owners[code];
      if (!own) return toast("У этой провинции на выбранную дату нет владельца.", "error");
      const { data } = await api.GET("/studio/api/map/territory/country/{country_id}", { params: { path: { country_id: own.country }, query: { date } } });
      const codes = data ?? [];
      selection = event.shift ? [...new Set([...selection, ...codes])] : codes;
      active = active ?? null;
    }
  }

  function onbox(codes: string[], remove: boolean) {
    selection = remove ? selection.filter((c) => !codes.includes(c)) : [...new Set([...selection, ...codes])];
  }

  async function give() {
    if (await apply(selection)) selection = [];
  }

  function openSplit() {
    draft = { code: "", name: "", color: "#c8372d" };
    errors = {};
    dialog = "split";
  }
  async function split() {
    errors = {};
    const { data, error } = await api.POST("/studio/api/map/countries", { body: { ...draft, valid_from: date, wiki_url: "" } });
    if (error || !data) { errors = fieldErrors(error); return toast(problem(error, "Страна не создалась."), "error"); }
    await loadCountries();
    const made = byId.get(data.id);
    if (made && (await apply(selection, made))) selection = [];
    active = data.id;
    dialog = null;
  }

  function openTransfer() {
    move = { source: active ?? countries[0]?.id ?? 0, target: 0 };
    dialog = "transfer";
  }
  async function transfer() {
    const { data, error } = await api.POST("/studio/api/map/territory/transfer", { body: { ...move, date, de_jure: jure, de_facto: facto } });
    if (error || !data) return toast(problem(error, "Не удалось передать."), "error");
    toast(`Передано провинций: ${data.moved}. ${summary(data)}.`);
    dialog = null;
    await loadOwners();
    if (!dates.includes(date)) loadDates();
  }

  const flagsOk = $derived(jure || facto);

  // горячие клавиши инструментов; в полях ввода и открытых окнах не работают
  function hotkey(event: KeyboardEvent) {
    if (event.ctrlKey || event.metaKey || event.altKey || dialog) return;
    const target = event.target as HTMLElement | null;
    if (target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable)) return;
    if (event.key === "Escape") { selection = []; return; }
    const found = MODES.find((item) => item.hotkey === event.key.toLowerCase());
    if (found) mode = found.key;
  }
</script>

<svelte:window onkeydown={hotkey} />

<div class="terr">
  <div class="mapbox">
    <MapView bind:this={mapView} {colors} selected={selection} boxMode={mode === "box"} look={look} view={view} onpick={pick} onhover={(c) => (hover = c)} {onbox} />
  </div>

  <div class="overlay">
    <section class="panel top" aria-label="Дата и вид карты">
      <div class="row">
        <div class="when">
          <button class="icon" onclick={() => step(-1)} disabled={!dates.some((d) => d < date)} aria-label="Предыдущее изменение границ" title="Предыдущее изменение границ"><Icon name="chevron" size={16} /></button>
          <input class="field date" type="date" bind:value={date} aria-label="Дата" />
          <button class="icon next" onclick={() => step(1)} disabled={!dates.some((d) => d > date)} aria-label="Следующее изменение границ" title="Следующее изменение границ"><Icon name="chevron" size={16} /></button>
          <button class="ghost" onclick={() => { if (dates.length) date = dates[dates.length - 1]; }} disabled={!dates.length || date === dates.at(-1)} title="Перейти к последнему изменению границ">К последней</button>
        </div>
        <div class="line">
          <input type="range" min="0" max={Math.max(0, dates.length - 1)} step="1" value={dateIndex} disabled={dates.length < 2} oninput={(e) => (date = dates[+e.currentTarget.value] ?? date)}
                 aria-label="Изменения границ по порядку" />
          <span class="muted small">{#if dates.length}{dateIndex + 1} из {dates.length}{:else}изменений нет{/if}</span>
        </div>
        <Hint text="Карта показывает владения на эту дату. Правки действуют с неё: более поздние записи не трогаются. Ползунок переключает даты, когда менялись границы." />
      </div>
      <div class="row looks">
        <div class="seg" role="radiogroup" aria-label="Стиль карты">
          <span class="seglabel"><Icon name="layers" size={14} />Стиль</span>
          {#each Object.entries(LOOKS) as [key, item] (key)}
            <button role="radio" aria-checked={look === key} class:on={look === key} title={item.hint} onclick={() => (look = key)}>{item.label}</button>
          {/each}
        </div>
        <div class="seg" role="radiogroup" aria-label="Режим карты">
          {#each VIEWS as item (item.key)}
            <button role="radio" aria-checked={view === item.key} class:on={view === item.key} title={item.hint} onclick={() => (view = item.key)}>{item.label}</button>
          {/each}
        </div>
        <label class="rights" title={RIGHTS.find((r) => r.key === rights)?.hint}>
          <span class="muted small">Владения</span>
          <select class="field" bind:value={rights} aria-label="Чьи владения показывать">
            {#each RIGHTS as item (item.key)}<option value={item.key}>{item.label}</option>{/each}
          </select>
        </label>
        <a class="ghost view" href={viewerUrl} target="_blank" rel="noopener" title="Открыть карту в приложении игры: на выбранную дату, в этом режиме и стиле"><Icon name="play" size={14} />Посмотреть</a>
      </div>
    </section>

    <div class="tools panel" role="radiogroup" aria-label="Инструмент">
      {#each MODES as item (item.key)}
        <button class="tool" class:on={mode === item.key} role="radio" aria-checked={mode === item.key} title="{item.label} ({item.hotkey.toUpperCase()}): {item.hint}" onclick={() => (mode = item.key)}>
          <Icon name={item.icon} size={18} /><kbd>{item.hotkey.toUpperCase()}</kbd>
        </button>
      {/each}
    </div>

    <aside class="side">
      <section class="panel dock" aria-label="Страны и провинции">
        <div class="tabs" role="tablist">
          <button role="tab" aria-selected={tab === "countries"} class:on={tab === "countries"} onclick={() => (tab = "countries")}>Страны<span class="n">{countries.length}</span></button>
          <button role="tab" aria-selected={tab === "provinces"} class:on={tab === "provinces"} onclick={() => (tab = "provinces")}>Провинции</button>
        </div>
        <label class="find"><Icon name="search" size={14} />
          {#if tab === "countries"}<input placeholder="Найти страну" bind:value={filter} aria-label="Поиск страны" />
          {:else}<input placeholder="Название или код провинции" bind:value={pq} aria-label="Поиск провинции" />{/if}
        </label>

        {#if tab === "countries"}
          <ul class="list">
            {#each shown as c (c.id)}
              <li>
                <button class="row-btn" class:on={c.id === active} aria-pressed={c.id === active} onclick={() => (active = c.id === active ? null : c.id)}>
                  <i style="background:{c.color}"></i><span>{c.name}</span><code>{c.code}</code>
                </button>
              </li>
            {:else}
              <li class="muted small pad">{countries.length ? "Ничего не нашлось." : "Стран нет. Создайте их на вкладке «Страны»."}</li>
            {/each}
          </ul>
          {#if mode === "paint" || mode === "country"}
            <div class="checks" aria-label="Права владения">
              <span class="muted small">Права:</span>
              <label class="check"><input type="checkbox" bind:checked={jure} /> де-юре<Hint text="Страна владеет провинцией по праву (признанные границы)." /></label>
              <label class="check"><input type="checkbox" bind:checked={facto} /> де-факто<Hint text="Страна реально контролирует провинцию. Нужно отметить хотя бы одно из двух." /></label>
            </div>
          {/if}
          <button class="btn" onclick={openTransfer} disabled={countries.length < 2}>Передать страну целиком…</button>
        {:else}
          <ul class="list">
            {#each found.rows as row (row.id)}
              <li>
                <button class="row-btn" onclick={() => focusProvince(row)} title="Показать на карте">
                  <i style="background:{row.owner?.color || NO_COLOR}"></i>
                  <span class="two"><b>{row.name}</b><small class="muted">{row.owner ? row.owner.country_name : "без владельца"}</small></span>
                  <code>{row.code}</code>
                </button>
              </li>
            {:else}
              <li class="muted small pad">{pq.trim() ? "Ничего не нашлось." : "Введите название или код провинции: она подсветится на карте, а справа откроется её история."}</li>
            {/each}
          </ul>
          {#if found.total > found.rows.length}<p class="muted small more">Показано {found.rows.length} из {found.total}: уточните запрос.</p>{/if}
        {/if}
      </section>

      {#if selection.length}
        <section class="panel card">
          <h3>Выделение <span class="chip">{selection.length}</span><span class="spacer"></span>
            <button class="btn ghost small" onclick={() => (selection = [])}>Очистить</button></h3>
          <div class="checks">
            <label class="check"><input type="checkbox" bind:checked={jure} /> де-юре</label>
            <label class="check"><input type="checkbox" bind:checked={facto} /> де-факто</label>
          </div>
          <button class="btn primary" onclick={give} disabled={!activeCountry || !flagsOk || busy}>
            {activeCountry ? `Передать «${activeCountry.name}» с ${showDate(date)}` : "Выберите страну во вкладке «Страны»"}
          </button>
          <button class="btn" onclick={openSplit} disabled={busy}>В новую страну…</button>
          <button class="btn danger" onclick={() => erase(selection)} disabled={busy}>Убрать записи этой даты</button>
        </section>
      {/if}

      {#if province}
        <section class="panel card">
          <h3>Провинция<span class="spacer"></span><button class="x" onclick={() => (province = null)} aria-label="Закрыть карточку провинции"><Icon name="close" size={14} /></button></h3>
          <div class="who"><b>{province.name}</b> <code>{province.code}</code></div>
          <div class="owner">
            {#if province.owner}<i style="background:{province.owner.color || NO_COLOR}"></i>{province.owner.country_name}
              <span class="muted small">с {showDate(province.owner.since)}</span>
            {:else}<span class="muted">на {showDate(date)} владельца нет</span>{/if}
          </div>
          <ul class="history">
            {#each province.history as row (row.id)}
              <li class:now={row.current}>
                <i style="background:{row.color}"></i><span>{showDate(row.date_from)}</span><b>{row.country_code}</b>
                <small class="muted">{row.de_jure && row.de_facto ? "юре+факто" : row.de_jure ? "юре" : "факто"}</small>
              </li>
            {/each}
          </ul>
          <a class="small" href="#/map/provinces/{province.id}">Открыть в таблице</a>
        </section>
      {/if}
    </aside>

    <div class="foot">
      <div class="tag" aria-live="polite">
        {#if hover}
          <b>{hover}</b>
          {#if hoverOwner}<span><i style="background:{hoverOwner.color}"></i>{hoverOwner.name}</span>{:else}<span class="muted">без владельца на {showDate(date)}</span>{/if}
        {:else}
          <span class="muted">{mayPaint ? `Красим: ${activeCountry?.name}` : `${MODES.find((m) => m.key === mode)?.label}: наведите на провинцию`}</span>
        {/if}
      </div>
      <div class="zoom panel">
        <button class="icon" onclick={() => mapView?.zoomBy(1)} aria-label="Приблизить" title="Приблизить"><Icon name="plus" size={16} /></button>
        <button class="icon" onclick={() => mapView?.zoomBy(-1)} aria-label="Отдалить" title="Отдалить"><Icon name="minus" size={16} /></button>
        <button class="icon" onclick={() => mapView?.reset()} aria-label="Вернуть вид" title="Вернуть вид"><Icon name="home" size={16} /></button>
      </div>
    </div>
  </div>
</div>

{#if dialog === "split"}
  <Dialog title="Новая страна из выделения" confirm="Создать и передать" busy={busy} onsubmit={split} onclose={() => (dialog = null)}
          disabled={!draft.code.trim() || !draft.name.trim()}>
    <p class="muted small">Страна появится с {showDate(date)}, и все {selection.length} выделенных провинций перейдут ей с этой даты.</p>
    <label><span class="label">Код</span><input class="field" class:bad={errors.code} bind:value={draft.code} placeholder="NEW" />
      {#if errors.code}<span class="err">{errors.code.join(" ")}</span>{/if}</label>
    <label><span class="label">Название</span><input class="field" bind:value={draft.name} /></label>
    <label><span class="label">Цвет</span><input class="field color" type="color" bind:value={draft.color} /></label>
  </Dialog>
{:else if dialog === "transfer"}
  <Dialog title="Передать страну целиком" confirm="Передать" onsubmit={transfer} onclose={() => (dialog = null)} disabled={!move.target || move.source === move.target || !flagsOk}>
    <p class="muted small">Всё, чем «источник» владеет на {showDate(date)}, перейдёт другой стране с этой даты: присоединение, наследование, раздел.</p>
    <label><span class="label">Кто отдаёт</span>
      <select class="field" bind:value={move.source}>{#each countries as c (c.id)}<option value={c.id}>{c.name} ({c.code})</option>{/each}</select></label>
    <label><span class="label">Кто получает</span>
      <select class="field" bind:value={move.target}>
        <option value={0}>— выберите —</option>
        {#each countries as c (c.id)}<option value={c.id}>{c.name} ({c.code})</option>{/each}
      </select></label>
    <label class="check"><input type="checkbox" bind:checked={jure} /> де-юре</label>
    <label class="check"><input type="checkbox" bind:checked={facto} /> де-факто</label>
  </Dialog>
{/if}

<style>
  .terr { position: relative; height: 100%; min-height: 0; overflow: hidden; }
  .mapbox { position: absolute; inset: 0; }
  .overlay { position: absolute; inset: 0; display: grid; grid-template-columns: auto minmax(0, 1fr) 320px; grid-template-rows: auto minmax(0, 1fr) auto; gap: 10px; padding: 12px; pointer-events: none; }
  .overlay > * { pointer-events: auto; }
  .panel { padding: 10px 12px; border: 1px solid var(--line); border-radius: var(--radius); background: color-mix(in srgb, var(--panel) 95%, transparent); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3); }
  .top { grid-column: 1 / 3; grid-row: 1; display: flex; flex-direction: column; gap: 8px; justify-self: start; max-width: 100%; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; }
  .when { display: flex; align-items: center; gap: 4px; }
  .date { width: 150px; height: 30px; padding: 2px 8px; }
  .icon { display: grid; place-items: center; width: 30px; height: 30px; padding: 0; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); color: var(--text); cursor: pointer; }
  .icon:hover:not(:disabled) { border-color: var(--line); background: var(--raise); }
  .icon:disabled { opacity: 0.4; cursor: default; }
  .icon :global(svg) { transform: rotate(90deg); }
  .icon.next :global(svg) { transform: rotate(-90deg); }
  .zoom .icon :global(svg) { transform: none; }
  .ghost { height: 30px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .ghost:hover:not(:disabled) { color: var(--text); border-color: var(--line); }
  .ghost:disabled { opacity: 0.4; cursor: default; }
  .view { display: inline-flex; align-items: center; gap: 6px; margin-left: auto; padding-top: 0; text-decoration: none; line-height: 28px; }
  .view:hover { text-decoration: none; }
  .line { display: flex; align-items: center; gap: 8px; min-width: 200px; flex: 1; }
  .line input[type="range"] { flex: 1; min-width: 120px; accent-color: var(--accent); }
  .looks { padding-top: 8px; border-top: 1px solid var(--line-soft); }
  .seg { display: inline-flex; align-items: center; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 4px 12px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .seglabel { display: inline-flex; align-items: center; gap: 5px; padding: 0 4px 0 10px; color: var(--faint); font-size: 12px; }
  .rights { display: flex; align-items: center; gap: 6px; }
  .rights select { width: auto; height: 30px; padding: 2px 8px; font-size: 12.5px; }

  .tools { grid-column: 1; grid-row: 2; align-self: start; display: flex; flex-direction: column; gap: 4px; padding: 6px; }
  .tool { position: relative; display: grid; place-items: center; width: 40px; height: 40px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--muted); cursor: pointer; }
  .tool:hover { background: var(--panel-2); color: var(--text); }
  .tool.on { background: var(--accent-soft); border-color: var(--accent); color: var(--text); }
  .tool kbd { position: absolute; right: 3px; bottom: 1px; font: 600 9px var(--mono); color: var(--faint); }
  .tool:focus-visible, .seg button:focus-visible, .icon:focus-visible, .ghost:focus-visible, .row-btn:focus-visible, .tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }

  .side { grid-column: 3; grid-row: 1 / 4; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
  .dock { flex: 1 1 0; min-height: 220px; display: flex; flex-direction: column; gap: 8px; overflow: hidden; }
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line-soft); margin: -4px -4px 0; padding: 0 4px; }
  .tabs button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .n { padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .find { flex: none; display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .list { flex: 1 1 0; min-height: 60px; list-style: none; margin: 0; padding: 0; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .row-btn { display: flex; align-items: center; gap: 8px; width: 100%; padding: 5px 8px; border: 0; background: transparent; color: var(--text); font: inherit; cursor: pointer; text-align: left; }
  .row-btn:hover { background: var(--panel-2); }
  .row-btn.on { background: var(--accent-soft); }
  .row-btn > span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .row-btn .two { display: flex; flex-direction: column; line-height: 1.25; }
  .row-btn code { color: var(--muted); font-size: 11px; flex: none; }
  .pad { padding: 8px; }
  .more { margin: 0; flex: none; }
  .dock > :global(.btn) { flex: none; white-space: normal; height: auto; min-height: 30px; padding: 6px 12px; text-align: left; }
  .checks { flex: none; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13px; }

  .card { flex: none; display: flex; flex-direction: column; gap: 8px; }
  .card h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 14px; font-weight: 650; }
  .spacer { flex: 1; }
  .x { display: grid; place-items: center; width: 22px; height: 22px; padding: 0; border: 0; border-radius: 6px; background: none; color: var(--muted); cursor: pointer; }
  .x:hover { background: var(--panel-2); color: var(--text); }
  .card .btn { white-space: normal; height: auto; min-height: 30px; padding: 6px 12px; text-align: left; }
  .card .btn.small { min-height: 0; padding: 1px 8px; font-size: 12px; }
  .chip { padding: 0 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 12px; font-weight: 400; }
  .who { display: flex; gap: 8px; align-items: baseline; }
  .owner { display: flex; gap: 6px; align-items: center; }
  .history { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 200px; overflow: auto; }
  .history li { display: flex; gap: 8px; align-items: center; padding: 3px 6px; border-radius: var(--radius-s); }
  .history li.now { background: var(--accent-soft); }
  .history b { font-family: var(--mono); font-size: 12px; }

  .foot { grid-column: 1 / 3; grid-row: 3; display: flex; align-items: flex-end; justify-content: space-between; gap: 10px; pointer-events: none; }
  .foot > * { pointer-events: auto; }
  .tag { display: flex; gap: 10px; align-items: center; padding: 6px 10px; border-radius: var(--radius-s); background: rgba(14, 15, 18, 0.86); border: 1px solid var(--line); pointer-events: none; }
  .tag span { display: inline-flex; gap: 6px; align-items: center; }
  .zoom { display: flex; flex-direction: column; gap: 4px; padding: 4px; }
  .small { font-size: 12px; margin: 0; }
  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; flex: none; border: 1px solid rgba(255, 255, 255, 0.2); }
  .color { padding: 2px; height: 32px; }
  .err { color: var(--danger); font-size: 12px; }
  .bad { border-color: var(--danger); }
  code { font-family: var(--mono); font-size: 12px; }
  @media (max-width: 1000px) { .overlay { grid-template-columns: auto minmax(0, 1fr) 280px; } }
</style>
