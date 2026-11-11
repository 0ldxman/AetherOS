<script lang="ts">
  // Страны: список слева, карточка справа (цвет, годы жизни, предшественник) и подписи страны на карте.
  import { onMount } from "svelte";
  import DraftState from "../../lib/DraftState.svelte";
  import { SharedForm } from "../../lib/shared.svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import ListDetail from "../../lib/ListDetail.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import Icon from "../../lib/Icon.svelte";
  import LifeLine from "./LifeLine.svelte";
  import MaterialField from "./MaterialField.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, RANKS, showDate, today } from "./shared";

  type Form = Schemas["MapCountryIn"];
  let { id }: { id: number | null } = $props();

  let rows = $state<Schemas["MapCountryRow"][]>([]);
  let query = $state("");
  let country = $state<Schemas["MapCountryOut"] | null>(null);
  let form = $state<Form>(blank());
  let saved = $state("");
  let base = $state<Form | null>(null);                    // сохранённое: им наполняется общий черновик
  let errors = $state<Record<string, string[]>>({});
  let labels = $state<Schemas["MapLabelOut"][]>([]);
  let labelSaved = $state<Record<number, string>>({});
  let dialog = $state(false);
  let draft = $state<Form>(blank());

  function blank(): Form {
    return { code: "", name: "", color: "#9aa5b1", valid_from: today(), valid_to: null, predecessor: null, wiki_url: "", show_info: true, material: null };
  }
  // ---------- фильтр списка по датам жизни страны ----------
  let fmode = $state<"all" | "on" | "range">("all");
  let onDate = $state("");
  let rangeFrom = $state("");
  let rangeTo = $state("");
  let sort = $state<"name" | "start" | "end">("name");
  let nowDate = $state("");                                          // последняя дата, когда менялись границы
  const FAR = "9999-12-31";
  // что считается «существовала»: пересечение жизни страны и выбранной даты или периода
  const span = $derived<[string, string] | null>(
    fmode === "on" && onDate ? [onDate, onDate] : fmode === "range" && (rangeFrom || rangeTo) ? [rangeFrom || "0000-01-01", rangeTo || FAR] : null,
  );
  const visible = $derived.by(() => {
    const found = rows.filter((r) => !span || (r.valid_from <= span[1] && (r.valid_to ?? FAR) >= span[0]));
    if (sort === "start") return [...found].sort((a, b) => a.valid_from.localeCompare(b.valid_from) || a.name.localeCompare(b.name));
    if (sort === "end") return [...found].sort((a, b) => (a.valid_to ?? FAR).localeCompare(b.valid_to ?? FAR) || a.name.localeCompare(b.name));
    return found;
  });
  // общая ось времени для полосок: от самого раннего начала до самого позднего конца (или последней даты границ)
  const axis = $derived.by(() => {
    const stamps = rows.flatMap((r) => [Date.parse(r.valid_from), r.valid_to ? Date.parse(r.valid_to) : Date.parse(r.valid_from)]);
    if (nowDate) stamps.push(Date.parse(nowDate));
    const min = stamps.length ? Math.min(...stamps) : Date.parse("1900-01-01");
    const max = stamps.length ? Math.max(...stamps) : Date.now();
    return { min, max: max + Math.max(86400000 * 365, (max - min) * 0.02) };
  });
  const band = $derived<[number, number] | null>(span ? [Date.parse(span[0] === "0000-01-01" ? new Date(axis.min).toISOString().slice(0, 10) : span[0]), span[1] === FAR ? axis.max : Date.parse(span[1])] : null);
  const year = (value: string) => value.slice(0, 4);
  const others = $derived(rows.filter((r) => r.id !== country?.id));
  const plural = (n: number, one: string, few: string, many: string) => (n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many);
  const PALETTE = ["#c8372d", "#e8710a", "#f2c66d", "#6fcf97", "#2f9e8f", "#4aa3df", "#2f5fd0", "#8e5cd9", "#d95fa0", "#9aa5b1", "#5d6675", "#2b2f36"];

  // сколько прожила страна
  const lived = $derived.by(() => {
    const start = Date.parse(form.valid_from);
    const end = form.valid_to ? Date.parse(form.valid_to) : nowDate ? Date.parse(nowDate) : Date.now();
    if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return "";
    const months = Math.round((end - start) / (86400000 * 30.4375));
    const y = Math.floor(months / 12), m = months % 12;
    const text = [y && `${y} ${plural(y, "год", "года", "лет")}`, m && `${m} мес`].filter(Boolean).join(" ") || "меньше месяца";
    return form.valid_to ? `Просуществовала ${text}.` : `Существует ${text}${nowDate ? ` (на ${showDate(nowDate)})` : ""}.`;
  });

  // провинции страны сейчас: подгружаются при раскрытии
  let owned = $state<Schemas["MapProvincePage"] | null>(null);
  async function loadOwned() {
    if (!country) return;
    owned = (await api.GET("/studio/api/map/provinces", { params: { query: { owner: String(country.id), limit: 60 } } })).data ?? { total: 0, rows: [] };
  }
  $effect(() => { current; owned = null; });

  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);      // в совместном режиме черновик на сервере
  const current = $derived(id ?? rows[0]?.id ?? null);

  async function list() {
    rows = (await api.GET("/studio/api/map/countries", { params: { query: { q: query } } })).data ?? [];
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { query; clearTimeout(timer); timer = setTimeout(list, 200); });

  async function load(target: number | null) {
    country = null;
    base = null;
    errors = {};
    if (target === null) return;
    const { data } = await api.GET("/studio/api/map/countries/{country_id}", { params: { path: { country_id: target } } });
    if (!data) return;
    country = data;
    const { id: _id, provinces: _p, ownerships: _o, labels: _l, predecessor_name: _n, successors: _s, successor_ids: _si, material_info: _mi, label_list, ...fields } = data;
    form = fields;
    saved = JSON.stringify(form);
    base = JSON.parse(saved);
    labels = label_list;
    labelSaved = Object.fromEntries(label_list.map((l) => [l.id, JSON.stringify(pure(l))]));
  }
  $effect(() => { load(current); });
  // общий черновик страны; кто-то сохранил: перечитать сохранённое, черновик не трогается
  const share = new SharedForm({
    room: () => `map/countries/${current}`,
    texts: ["name", "wiki_url"],
    draft: () => form,
    base: () => base,
    onRemoteSave: async () => {
      if (current === null) return;
      const { data } = await api.GET("/studio/api/map/countries/{country_id}", { params: { path: { country_id: current } } });
      if (!data) return;
      country = data;
      const { id: _id, provinces: _p, ownerships: _o, labels: _l, predecessor_name: _n, successors: _s, successor_ids: _si, material_info: _mi, label_list: _ll, ...fields } = data;
      saved = JSON.stringify(fields);
      base = JSON.parse(saved);
      list();
    },
  });
  onMount(async () => {
    list();
    const dates = (await api.GET("/studio/api/map/territory/dates")).data ?? [];
    nowDate = dates.at(-1) ?? "";
    onDate = nowDate || today();
  });

  const pure = (l: Schemas["MapLabelOut"]) => ({ text: l.text, lng: l.lng, lat: l.lat, rank: l.rank });

  async function save() {
    if (!country) return;
    errors = {};
    const { data, error } = await api.PUT("/studio/api/map/countries/{country_id}", { params: { path: { country_id: country.id } }, body: form });
    if (error || !data) { errors = fieldErrors(error); return toast(problem(error, "Не сохранилось."), "error"); }
    share.markSaved();
    toast("Страна сохранена.");
    await load(data.id);
    list();
  }

  async function create() {
    errors = {};
    const { data, error } = await api.POST("/studio/api/map/countries", { body: draft });
    if (error || !data) { errors = fieldErrors(error); return toast(problem(error, "Не создалась."), "error"); }
    dialog = false;
    await list();
    go(`/map/countries/${data.id}`);
  }

  async function remove() {
    if (!country) return;
    if (!(await ask(`Удалить страну «${country.name}»?`, country.ownerships ? `У неё ${country.ownerships} записей владения: удалить не получится, пока они есть.` : "Подписи страны удалятся вместе с ней."))) return;
    const { error } = await api.DELETE("/studio/api/map/countries/{country_id}", { params: { path: { country_id: country.id } } });
    if (error) return toast(problem(error), "error");
    toast("Страна удалена.");
    await list();
    go("/map/countries");
  }

  const labelDirty = (l: Schemas["MapLabelOut"]) => labelSaved[l.id] !== JSON.stringify(pure(l));
  async function saveLabel(l: Schemas["MapLabelOut"]) {
    const { data, error } = await api.PUT("/studio/api/map/labels/{label_id}", { params: { path: { label_id: l.id } }, body: pure(l) });
    if (error || !data) return toast(problem(error, "Подпись не сохранилась."), "error");
    labelSaved[l.id] = JSON.stringify(pure(data));
    toast("Подпись сохранена.");
  }
  async function addLabel() {
    if (!country) return;
    const { data, error } = await api.POST("/studio/api/map/countries/{country_id}/labels", { params: { path: { country_id: country.id } }, body: { text: "", lng: 0, lat: 0, rank: 2 } });
    if (error || !data) return toast(problem(error, "Не добавилась."), "error");
    labels.push(data);
    labelSaved[data.id] = JSON.stringify(pure(data));
    list();
  }
  async function dropLabel(l: Schemas["MapLabelOut"]) {
    const { error } = await api.DELETE("/studio/api/map/labels/{label_id}", { params: { path: { label_id: l.id } } });
    if (error) return toast(problem(error), "error");
    labels = labels.filter((x) => x.id !== l.id);
    list();
  }

</script>

<ListDetail title="Страны">
  {#snippet list()}
    <div class="filter">
      <label class="find"><Icon name="search" size={14} /><input placeholder="Название или код" bind:value={query} aria-label="Поиск страны" /></label>
      <div class="seg" role="radiogroup" aria-label="Существовала">
        {#each [["all", "Все"], ["on", "На дату"], ["range", "Период"]] as [key, label] (key)}
          <button role="radio" aria-checked={fmode === key} class:on={fmode === key} onclick={() => (fmode = key as typeof fmode)}>{label}</button>
        {/each}
      </div>
      {#if fmode === "on"}
        <div class="dates">
          <input class="field" type="date" bind:value={onDate} aria-label="Дата" />
          <button class="mini" onclick={() => (onDate = nowDate)} disabled={!nowDate || onDate === nowDate} title="Последняя дата, когда менялись границы">Сейчас</button>
        </div>
      {:else if fmode === "range"}
        <div class="dates">
          <input class="field" type="date" bind:value={rangeFrom} aria-label="Период с" title="С" />
          <span class="muted">—</span>
          <input class="field" type="date" bind:value={rangeTo} aria-label="Период по" title="По" />
        </div>
      {/if}
      <div class="meta">
        <span class="muted small">{#if fmode !== "all" || query.trim()}Показано {visible.length} из {rows.length}{:else}Стран: {rows.length}{/if}</span>
        <select class="sort" bind:value={sort} aria-label="Порядок">
          <option value="name">по названию</option>
          <option value="start">по началу</option>
          <option value="end">по концу</option>
        </select>
      </div>
    </div>
    {#each visible as row (row.id)}
      <a class="item" class:on={row.id === current} href="#/map/countries/{row.id}">
        <span class="line"><i style="background:{row.color}"></i><b>{row.name}</b><code class="muted">{row.code}</code></span>
        <LifeLine from={row.valid_from} to={row.valid_to} min={axis.min} max={axis.max} color={row.color} {band} />
        <span class="muted small years">{year(row.valid_from)}–{row.valid_to ? year(row.valid_to) : "…"}{row.provinces ? ` · провинций ${row.provinces}` : ""}</span>
      </a>
    {:else}
      <p class="muted small pad">{rows.length ? "Под этот фильтр ничего не попало." : "Стран нет."}</p>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn" onclick={() => { draft = blank(); errors = {}; dialog = true; }}>+ Страна</button>
  {/snippet}

  {#if country}
    <section class="editor">
      <header class="top">
        <label class="swatch" style="background:{form.color}" title="Цвет на карте"><input type="color" bind:value={form.color} aria-label="Цвет на карте" /></label>
        <input class="title" class:bad={errors.name} bind:value={form.name} placeholder="Название страны" aria-label="Название страны" />
        <code class="codechip">{form.code}</code>
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={remove}>Удалить</button>
        <DraftState {share} {dirty} saved="" />
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
      </header>
      {#if errors.name}<p class="err">{errors.name.join(" ")}</p>{/if}

      <section class="life">
        <span class="status" class:gone={!!form.valid_to}>{form.valid_to ? `существовала ${showDate(form.valid_from)} — ${showDate(form.valid_to)}` : `существует с ${showDate(form.valid_from)}`}</span>
        <LifeLine from={form.valid_from} to={form.valid_to ?? null} min={axis.min} max={axis.max} color={form.color} tall />
        <div class="ticks"><span>{year(new Date(axis.min).toISOString())}</span><span>{lived}</span><span>{year(new Date(axis.max).toISOString())}</span></div>
        <div class="stats">
          <div class="stat"><b>{country.provinces}</b><span>провинций сейчас</span></div>
          <a class="stat" href="#/map/ownerships"><b>{country.ownerships}</b><span>записей владения</span></a>
          <div class="stat"><b>{labels.length}</b><span>{plural(labels.length, "подпись", "подписи", "подписей")} на карте</span></div>
        </div>
      </section>

      <div class="cols">
        <section class="card">
          <h3>Основное</h3>
          <label><span class="label">Код<Hint text="Короткий уникальный код страны, например POL или POL-2013. Его используют в виджетах ::map и выделениях сцен." /></span>
            <input class="field mono" class:bad={errors.code} bind:value={form.code} />{#if errors.code}<span class="err">{errors.code.join(" ")}</span>{/if}</label>
          <div class="field-row">
            <span class="label">Цвет на карте</span>
            <div class="palette" role="group" aria-label="Готовые цвета">
              {#each PALETTE as color (color)}
                <button class="dot" class:on={form.color.toLowerCase() === color} style="background:{color}" aria-label={color} aria-pressed={form.color.toLowerCase() === color} onclick={() => (form.color = color)}></button>
              {/each}
              <input class="hex mono" bind:value={form.color} aria-label="Цвет в формате #rrggbb" spellcheck="false" />
            </div>
            {#if errors.color}<span class="err">{errors.color.join(" ")}</span>{/if}
          </div>
        </section>

        <section class="card">
          <h3>Годы жизни</h3>
          <label><span class="label">Существует с<Hint text="Владения этой страны нельзя ставить на даты раньше." /></span>
            <input class="field" type="date" class:bad={errors.valid_from} bind:value={form.valid_from} />{#if errors.valid_from}<span class="err">{errors.valid_from.join(" ")}</span>{/if}</label>
          <div class="field-row">
            <span class="label">Существовала по<Hint text="Выключите «до сих пор», чтобы указать дату, когда страна перестала существовать." /></span>
            <div class="until">
              <input class="field" type="date" class:bad={errors.valid_to} bind:value={form.valid_to} disabled={form.valid_to === null} aria-label="Существовала по" />
              <label class="check"><input type="checkbox" checked={form.valid_to === null} onchange={(e) => (form.valid_to = e.currentTarget.checked ? null : (nowDate || today()))} /> до сих пор</label>
            </div>
            {#if errors.valid_to || errors.__all__}<span class="err">{(errors.valid_to ?? errors.__all__).join(" ")}</span>{/if}
          </div>
          <p class="muted small">{lived}</p>
        </section>

        <section class="card">
          <h3>Связи</h3>
          <label><span class="label">Предшественник<Hint text="Страна, из которой эта выросла: для истории и подсказок." /></span>
            <select class="field" bind:value={form.predecessor}>
              <option value={null}>— нет —</option>
              {#each others as r (r.id)}<option value={r.id}>{r.name} ({r.code})</option>{/each}
            </select></label>
          {#if form.predecessor}<a class="small" href="#/map/countries/{form.predecessor}">← {country.predecessor_name || "открыть предшественника"}</a>{/if}
          <div class="field-row">
            <span class="label">Наследники</span>
            {#if country.successors.length}
              <div class="succ">{#each country.successors as name, i (country.successor_ids[i])}<a class="chip" href="#/map/countries/{country.successor_ids[i]}">{name} →</a>{/each}</div>
            {:else}<span class="muted small">Пока никто не указал эту страну предшественником.</span>{/if}
          </div>
        </section>

        <section class="card">
          <h3>Материал</h3>
          <MaterialField scope="country" material={form.material} info={country.material_info} showInfo={form.show_info ?? true} url={form.wiki_url ?? ""} error={errors.material?.join(" ")}
                         onmaterial={(id) => (form.material = id)} onshow={(v) => (form.show_info = v)} onurl={(v) => (form.wiki_url = v)} />
        </section>
      </div>

      <section class="card">
        <h3>Подписи на карте<Hint text="У страны может быть несколько подписей: основная территория, острова, заморские владения. Ранг задаёт, при каком масштабе подпись видна." />
          <span class="spacer"></span><button class="btn" onclick={addLabel}>+ Подпись</button></h3>
        {#if !labels.length}<p class="muted small">Подписей нет: на карте у страны не будет названия.</p>{/if}
        <div class="labels">
          {#each labels as l (l.id)}
            <div class="label-card" class:changed={labelDirty(l)}>
              <div class="l-top">
                <input class="field" placeholder={form.name} bind:value={l.text} aria-label="Текст подписи" />
                <select class="field rank" bind:value={l.rank} aria-label="Ранг подписи">{#each RANKS as r (r.value)}<option value={r.value}>{r.label}</option>{/each}</select>
              </div>
              <div class="l-coords">
                <label><span class="muted small">Долгота</span><input class="field num" type="number" step="0.01" bind:value={l.lng} aria-label="Долгота" /></label>
                <label><span class="muted small">Широта</span><input class="field num" type="number" step="0.01" bind:value={l.lat} aria-label="Широта" /></label>
                <span class="spacer"></span>
                <a class="small" href="#/map/labels/{l.id}">на карте</a>
                <button class="btn" disabled={!labelDirty(l)} onclick={() => saveLabel(l)}>Сохранить</button>
                <button class="btn ghost danger" onclick={() => dropLabel(l)} aria-label="Удалить подпись">×</button>
              </div>
            </div>
          {/each}
        </div>
      </section>

      <details class="card owned" ontoggle={(e) => { if (e.currentTarget.open) loadOwned(); }}>
        <summary>Провинции сейчас <span class="chip">{country.provinces}</span></summary>
        {#if owned === null}<p class="muted small">Загрузка…</p>
        {:else if !owned.rows.length}<p class="muted small">Провинций нет.</p>
        {:else}
          <div class="plist">{#each owned.rows as p (p.id)}<a class="chip" href="#/map/provinces/{p.id}">{p.name}<code>{p.code}</code></a>{/each}</div>
          {#if owned.total > owned.rows.length}<p class="muted small">Показано {owned.rows.length} из {owned.total}. Остальные во вкладке «Провинции».</p>{/if}
        {/if}
      </details>
    </section>
  {:else}
    <p class="muted pad">Выберите страну слева или создайте новую.</p>
  {/if}
</ListDetail>

{#if dialog}
  <Dialog title="Новая страна" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)} disabled={!draft.code.trim() || !draft.name.trim()}>
    <label><span class="label">Код</span><input class="field mono" class:bad={errors.code} bind:value={draft.code} />{#if errors.code}<span class="err">{errors.code.join(" ")}</span>{/if}</label>
    <label><span class="label">Название</span><input class="field" bind:value={draft.name} /></label>
    <label><span class="label">Существует с</span><input class="field" type="date" bind:value={draft.valid_from} /></label>
    <label><span class="label">Цвет</span><input class="field color" type="color" bind:value={draft.color} /></label>
  </Dialog>
{/if}

<style>
  .filter { display: flex; flex-direction: column; gap: 8px; margin: 0 4px 8px; padding-bottom: 8px; border-bottom: 1px solid var(--line-soft); }
  .find { display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .seg { display: flex; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { flex: 1; padding: 4px 6px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .seg button:hover { color: var(--text); }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .seg button:focus-visible, .mini:focus-visible, .dot:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .dates { display: flex; align-items: center; gap: 6px; }
  .dates .field { min-width: 0; flex: 1; height: 30px; padding: 2px 6px; font-size: 12.5px; }
  .mini { height: 30px; padding: 0 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; white-space: nowrap; }
  .mini:hover:not(:disabled) { color: var(--text); border-color: var(--line); }
  .mini:disabled { opacity: 0.4; cursor: default; }
  .meta { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .sort { border: 0; background: none; color: var(--muted); font: inherit; font-size: 12px; cursor: pointer; }
  .sort option { background: var(--raise); color: var(--text); }
  :global(.item) .line { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  :global(.item) .line b { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-weight: 600; }
  :global(.item) .line code { font-size: 11px; }
  .years { margin-top: 3px; }

  .editor { display: flex; flex-direction: column; gap: 14px; padding: 20px 28px 40px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .top :global(.draft) { flex-wrap: nowrap; white-space: nowrap; }
  .swatch { position: relative; flex: none; width: 34px; height: 34px; border-radius: 9px; border: 1px solid rgba(255, 255, 255, 0.25); cursor: pointer; overflow: hidden; }
  .swatch input { position: absolute; inset: -6px; width: 60px; height: 60px; opacity: 0; cursor: pointer; }
  .swatch:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .title { height: 36px; min-width: 0; flex: 1 1 220px; max-width: 420px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font-size: 20px; font-weight: 650; outline: none; }
  .title:hover { border-color: var(--line); }
  .title:focus { border-color: var(--accent); background: var(--bg); }
  .title.bad { border-color: var(--danger); }
  .codechip { padding: 1px 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 12px; }
  .status { align-self: flex-start; padding: 2px 10px; border-radius: 999px; background: rgba(95, 208, 160, 0.14); color: var(--ok); font-size: 12.5px; white-space: nowrap; }
  .status.gone { background: var(--raise); color: var(--muted); }
  .spacer { flex: 1; }

  .life { display: flex; flex-direction: column; gap: 6px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .ticks { display: flex; justify-content: space-between; font-size: 11.5px; color: var(--faint); font-variant-numeric: tabular-nums; }
  .ticks span:nth-child(2) { color: var(--muted); }
  .stats { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 4px; }
  .stat { display: flex; flex-direction: column; min-width: 120px; padding: 8px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--text); }
  a.stat:hover { border-color: var(--line); text-decoration: none; }
  .stat b { font-size: 20px; line-height: 1.2; font-variant-numeric: tabular-nums; }
  .stat span { color: var(--muted); font-size: 12px; }

  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media (max-width: 1200px) { .cols { grid-template-columns: 1fr; } }
  .card { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); min-width: 0; }
  .card h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 14px; font-weight: 650; }
  .field-row { display: flex; flex-direction: column; gap: 4px; }
  .palette { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .dot { width: 22px; height: 22px; padding: 0; border: 2px solid transparent; border-radius: 50%; cursor: pointer; }
  .dot.on { border-color: var(--text); }
  .hex { width: 92px; height: 28px; padding: 2px 8px; margin-left: 4px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); color: var(--text); font-size: 12.5px; }
  .until { display: flex; align-items: center; gap: 12px; }
  .until .field { max-width: 180px; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13px; white-space: nowrap; }
  .succ, .plist { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px; background: var(--raise); color: var(--text); font-size: 12.5px; }
  .chip:hover { text-decoration: none; background: var(--accent-soft); }
  .chip code { color: var(--muted); font-size: 11px; }

  .labels { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 10px; }
  .label-card { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .label-card.changed { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--bg)); }
  .l-top { display: flex; gap: 8px; }
  .l-top .field { min-width: 0; }
  .l-top .rank { width: 120px; flex: none; }
  .l-coords { display: flex; align-items: flex-end; gap: 8px; flex-wrap: wrap; }
  .l-coords label { display: flex; flex-direction: column; gap: 2px; }
  .num { width: 92px; }
  .owned summary { cursor: pointer; font-size: 14px; font-weight: 650; display: flex; align-items: center; gap: 8px; list-style-position: inside; }
  .owned[open] summary { margin-bottom: 10px; }

  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; flex: none; border: 1px solid rgba(255, 255, 255, 0.2); }
  .color { padding: 2px; height: 32px; max-width: 120px; }
  .small { font-size: 12px; margin: 0; }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
  .bad { border-color: var(--danger); }
  .pad { padding: 20px; }
  .mono { font-family: var(--mono); }
</style>
