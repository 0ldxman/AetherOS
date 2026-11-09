<script lang="ts">
  // Территории: карта на выбранную дату. Режимы: просмотр, покраска страной, выбор кликами, рамка, страна целиком, ластик.
  // Выделение можно передать стране, убрать (записи этой даты) или выделить в новую страну; страну можно передать целиком.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import MapView from "../../lib/MapView.svelte";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, NO_COLOR, showDate, today, type Country } from "./shared";

  type Mode = "inspect" | "paint" | "select" | "box" | "country" | "erase";
  const MODES: { key: Mode; label: string; hint: string }[] = [
    { key: "inspect", label: "Просмотр", hint: "Клик по провинции показывает её владельца и историю. Ничего не меняет." },
    { key: "paint", label: "Покраска", hint: "Выберите страну слева и кликайте по провинциям: каждая сразу переходит стране с выбранной даты." },
    { key: "select", label: "Выбор", hint: "Клик добавляет провинцию в выделение или убирает её. Потом выделение передают стране справа." },
    { key: "box", label: "Рамка", hint: "Тяните рамку по карте: всё под ней попадает в выделение. С Alt рамка убирает из выделения." },
    { key: "country", label: "Страна", hint: "Клик выделяет все провинции страны, которой принадлежит эта. С Shift добавляет к выделению." },
    { key: "erase", label: "Ластик", hint: "Клик убирает запись владения, начатую ровно в выбранную дату: провинция возвращается к прежнему владельцу." },
  ];

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

  const colors = $derived(Object.fromEntries(Object.entries(owners).map(([code, own]) => [code, own.color])));
  const byId = $derived(new Map(countries.map((c) => [c.id, c])));
  const shown = $derived(countries.filter((c) => !filter.trim() || `${c.name} ${c.code}`.toLowerCase().includes(filter.trim().toLowerCase())));
  const activeCountry = $derived(active === null ? null : byId.get(active) ?? null);
  const hoverOwner = $derived(hover && owners[hover] ? byId.get(owners[hover].country) : null);
  const mayPaint = $derived(mode === "paint" && activeCountry !== null);

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
</script>

<div class="terr">
  <aside class="left">
    <div class="block when">
      <span class="label">Дата<Hint text="Карта показывает владения на эту дату. Правки действуют с неё: более поздние записи не трогаются." /></span>
      <input class="field" type="date" bind:value={date} />
      <div class="stepper">
        <button class="btn ghost" onclick={() => step(-1)} disabled={!dates.some((d) => d < date)}>◀ раньше</button>
        <button class="btn ghost" onclick={() => step(1)} disabled={!dates.some((d) => d > date)}>позже ▶</button>
      </div>
      <p class="muted small">Дат, когда менялись границы: {dates.length}{dates.length ? ", последняя " + showDate(dates.at(-1)) : ""}.</p>
    </div>

    <div class="modes" role="radiogroup" aria-label="Режим">
      {#each MODES as item (item.key)}
        <button class="mode" class:on={mode === item.key} role="radio" aria-checked={mode === item.key} title={item.hint} onclick={() => (mode = item.key)}>{item.label}</button>
      {/each}
    </div>
    <p class="muted small modehint">{MODES.find((m) => m.key === mode)?.hint}</p>

    <input class="field" placeholder="Страна…" bind:value={filter} />
    <ul class="countries">
      {#each shown as c (c.id)}
        <li>
          <button class="country" class:on={c.id === active} onclick={() => (active = c.id === active ? null : c.id)}>
            <i style="background:{c.color}"></i><span>{c.name}</span><code>{c.code}</code>
          </button>
        </li>
      {:else}
        <li class="muted small pad">Стран нет. Создайте их на вкладке «Страны».</li>
      {/each}
    </ul>
    <button class="btn" onclick={openTransfer} disabled={countries.length < 2}>Передать страну целиком…</button>
  </aside>

  <div class="mapbox">
    <MapView {colors} selected={selection} boxMode={mode === "box"} onpick={pick} onhover={(c) => (hover = c)} {onbox} />
    <div class="tag">
      {#if hover}
        <b>{hover}</b>
        {#if hoverOwner}<span><i style="background:{hoverOwner.color}"></i>{hoverOwner.name}</span>{:else}<span class="muted">без владельца на {showDate(date)}</span>{/if}
      {:else}
        <span class="muted">{mayPaint ? `Красим: ${activeCountry?.name}` : "Наведите на провинцию"}</span>
      {/if}
    </div>
  </div>

  <aside class="right">
    <section class="block">
      <h3>Выделение <span class="chip">{selection.length}</span>
        {#if selection.length}<button class="btn ghost" onclick={() => (selection = [])}>Очистить</button>{/if}</h3>
      {#if !selection.length}
        <p class="muted small">Пусто. Режимы «Выбор», «Рамка» и «Страна» собирают провинции сюда.</p>
      {:else}
        <label class="check"><input type="checkbox" bind:checked={jure} /> де-юре</label>
        <label class="check"><input type="checkbox" bind:checked={facto} /> де-факто</label>
        <button class="btn primary" onclick={give} disabled={!activeCountry || !flagsOk || busy}>
          {activeCountry ? `Передать «${activeCountry.name}» с ${showDate(date)}` : "Выберите страну слева"}
        </button>
        <button class="btn" onclick={openSplit} disabled={busy}>В новую страну…</button>
        <button class="btn danger" onclick={() => erase(selection)} disabled={busy}>Убрать записи этой даты</button>
      {/if}
    </section>

    {#if mode === "paint" || mode === "country"}
      <section class="block">
        <h3>Права владения</h3>
        <label class="check"><input type="checkbox" bind:checked={jure} /> де-юре<Hint text="Страна владеет провинцией по праву (признанные границы)." /></label>
        <label class="check"><input type="checkbox" bind:checked={facto} /> де-факто<Hint text="Страна реально контролирует провинцию. Нужно отметить хотя бы одно." /></label>
      </section>
    {/if}

    <section class="block">
      <h3>Провинция</h3>
      {#if !province}
        <p class="muted small">Режим «Просмотр»: кликните по провинции.</p>
      {:else}
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
      {/if}
    </section>
  </aside>
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
  .terr { display: grid; grid-template-columns: 250px 1fr 300px; height: 100%; min-height: 0; }
  .left, .right { display: flex; flex-direction: column; gap: 10px; padding: 12px; overflow: auto; min-height: 0; }
  .left { border-right: 1px solid var(--line-soft); }
  .right { border-left: 1px solid var(--line-soft); }
  .when { gap: 6px; padding: 10px 12px; }
  .stepper { display: flex; justify-content: space-between; }
  .stepper .btn { padding: 0 6px; height: 26px; }
  .modes { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
  .mode { height: 30px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); cursor: pointer; }
  .mode:hover { background: var(--raise); }
  .mode.on { background: var(--accent-soft); border-color: var(--accent); color: var(--text); }
  .modehint { margin: -4px 0 0; min-height: 3.6em; }
  .countries { list-style: none; margin: 0; padding: 0; flex: 1; min-height: 80px; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .country { display: flex; align-items: center; gap: 8px; width: 100%; padding: 5px 8px; border: 0; background: transparent; cursor: pointer; text-align: left; }
  .country:hover { background: var(--panel-2); }
  .country.on { background: var(--accent-soft); }
  .country span { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .country code { color: var(--muted); font-size: 11px; }
  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; flex: none; border: 1px solid rgba(255, 255, 255, 0.2); }
  .pad { padding: 8px; }
  .mapbox { position: relative; min-height: 0; }
  .tag { position: absolute; left: 12px; bottom: 12px; display: flex; gap: 10px; align-items: center; padding: 6px 10px; border-radius: var(--radius-s);
         background: rgba(14, 15, 18, 0.86); border: 1px solid var(--line); pointer-events: none; }
  .tag span { display: inline-flex; gap: 6px; align-items: center; }
  .right .btn { white-space: normal; height: auto; min-height: 30px; padding: 6px 12px; text-align: left; }
  .right .btn { white-space: normal; height: auto; min-height: 30px; padding: 6px 12px; text-align: left; }
  .check { display: flex; align-items: center; gap: 6px; }
  .who { display: flex; gap: 8px; align-items: baseline; }
  .owner { display: flex; gap: 6px; align-items: center; }
  .history { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 240px; overflow: auto; }
  .history li { display: flex; gap: 8px; align-items: center; padding: 3px 6px; border-radius: var(--radius-s); }
  .history li.now { background: var(--accent-soft); }
  .history b { font-family: var(--mono); font-size: 12px; }
  .color { padding: 2px; height: 32px; }
  .err { color: var(--danger); font-size: 12px; }
  .bad { border-color: var(--danger); }
  code { font-family: var(--mono); font-size: 12px; }
</style>
