<script lang="ts">
  // Страны: список слева, карточка справа (цвет, годы жизни, предшественник) и подписи страны на карте.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import ListDetail from "../../lib/ListDetail.svelte";
  import { ask } from "../../lib/confirm.svelte";
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
  let errors = $state<Record<string, string[]>>({});
  let labels = $state<Schemas["MapLabelOut"][]>([]);
  let labelSaved = $state<Record<number, string>>({});
  let dialog = $state(false);
  let draft = $state<Form>(blank());

  function blank(): Form {
    return { code: "", name: "", color: "#9aa5b1", valid_from: today(), valid_to: null, predecessor: null, wiki_url: "" };
  }
  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty);
  const current = $derived(id ?? rows[0]?.id ?? null);

  async function list() {
    rows = (await api.GET("/studio/api/map/countries", { params: { query: { q: query } } })).data ?? [];
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { query; clearTimeout(timer); timer = setTimeout(list, 200); });

  async function load(target: number | null) {
    country = null;
    errors = {};
    if (target === null) return;
    const { data } = await api.GET("/studio/api/map/countries/{country_id}", { params: { path: { country_id: target } } });
    if (!data) return;
    country = data;
    const { id: _id, provinces: _p, ownerships: _o, labels: _l, predecessor_name: _n, successors: _s, label_list, ...fields } = data;
    form = fields;
    saved = JSON.stringify(form);
    labels = label_list;
    labelSaved = Object.fromEntries(label_list.map((l) => [l.id, JSON.stringify(pure(l))]));
  }
  $effect(() => { load(current); });
  onMount(list);

  const pure = (l: Schemas["MapLabelOut"]) => ({ text: l.text, lng: l.lng, lat: l.lat, rank: l.rank });

  async function save() {
    if (!country) return;
    errors = {};
    const { data, error } = await api.PUT("/studio/api/map/countries/{country_id}", { params: { path: { country_id: country.id } }, body: form });
    if (error || !data) { errors = fieldErrors(error); return toast(problem(error, "Не сохранилось."), "error"); }
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

  const others = $derived(rows.filter((r) => r.id !== country?.id));
</script>

<ListDetail title="Страны">
  {#snippet list()}
    <input class="field" placeholder="Найти…" bind:value={query} />
    {#each rows as row (row.id)}
      <a class="item" class:on={row.id === current} href="#/map/countries/{row.id}">
        <span class="line"><i style="background:{row.color}"></i><b>{row.name}</b></span>
        <span class="muted small">{row.code} · {row.provinces ? `провинций ${row.provinces}` : "провинций нет"}</span>
      </a>
    {:else}
      <p class="muted small pad">Стран нет.</p>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn" onclick={() => { draft = blank(); errors = {}; dialog = true; }}>+ Страна</button>
  {/snippet}

  {#if country}
    <section class="editor">
      <header class="top">
        <i class="big" style="background:{form.color}"></i>
        <h2>{form.name || "Без названия"}</h2>
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={remove}>Удалить</button>
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
      </header>

      <div class="stats">
        <span class="chip">провинций сейчас: {country.provinces}</span>
        <span class="chip">записей владения: {country.ownerships}</span>
        {#if country.successors.length}<span class="chip">наследники: {country.successors.join(", ")}</span>{/if}
        <a class="small" href="#/map/ownerships">записи владения</a>
      </div>

      <div class="cols">
        <div class="block">
          <h3>Страна</h3>
          <label><span class="label">Код<Hint text="Короткий уникальный код страны, например POL или POL-2013. Его используют в виджетах ::map и пометках сцен." /></span>
            <input class="field mono" class:bad={errors.code} bind:value={form.code} />{#if errors.code}<span class="err">{errors.code.join(" ")}</span>{/if}</label>
          <label><span class="label">Название</span>
            <input class="field" class:bad={errors.name} bind:value={form.name} />{#if errors.name}<span class="err">{errors.name.join(" ")}</span>{/if}</label>
          <label><span class="label">Цвет на карте</span>
            <input class="field color" type="color" bind:value={form.color} />{#if errors.color}<span class="err">{errors.color.join(" ")}</span>{/if}</label>
          <label><span class="label">Страница в вики<Hint text="Куда ведёт клик по провинциям страны, у которых нет своей страницы." /></span>
            <input class="field" bind:value={form.wiki_url} placeholder="/wiki/…" />{#if errors.wiki_url}<span class="err">{errors.wiki_url.join(" ")}</span>{/if}</label>
        </div>
        <div class="block">
          <h3>Годы жизни</h3>
          <label><span class="label">Существует с<Hint text="Владения этой страны нельзя ставить на даты раньше." /></span>
            <input class="field" type="date" class:bad={errors.valid_from} bind:value={form.valid_from} />{#if errors.valid_from}<span class="err">{errors.valid_from.join(" ")}</span>{/if}</label>
          <label><span class="label">Существовала по<Hint text="Пусто: страна существует до сих пор." /></span>
            <input class="field" type="date" class:bad={errors.valid_to} bind:value={form.valid_to} />
            {#if errors.valid_to || errors.__all__}<span class="err">{(errors.valid_to ?? errors.__all__).join(" ")}</span>{/if}</label>
          <label><span class="label">Предшественник<Hint text="Страна, из которой эта выросла: для истории и подсказок." /></span>
            <select class="field" bind:value={form.predecessor}>
              <option value={null}>— нет —</option>
              {#each others as r (r.id)}<option value={r.id}>{r.name} ({r.code})</option>{/each}
            </select></label>
        </div>
      </div>

      <div class="block">
        <h3>Подписи на карте<Hint text="У страны может быть несколько подписей: основная территория, острова, заморские владения. Ранг задаёт размер и то, с какого зума подпись видна. Пустой текст: берётся название страны." />
          <button class="btn" onclick={addLabel}>+ Подпись</button></h3>
        {#if !labels.length}<p class="muted small">Подписей нет: на карте у страны не будет названия.</p>{/if}
        {#each labels as l (l.id)}
          <div class="label-row" class:changed={labelDirty(l)}>
            <input class="field" placeholder={form.name} bind:value={l.text} aria-label="Текст подписи" />
            <input class="field num" type="number" step="0.01" bind:value={l.lng} aria-label="Долгота" title="Долгота" />
            <input class="field num" type="number" step="0.01" bind:value={l.lat} aria-label="Широта" title="Широта" />
            <select class="field rank" bind:value={l.rank} aria-label="Ранг">{#each RANKS as r (r.value)}<option value={r.value}>{r.label}</option>{/each}</select>
            <a class="small" href="#/map/labels/{l.id}">на карте</a>
            <button class="btn" disabled={!labelDirty(l)} onclick={() => saveLabel(l)}>Сохранить</button>
            <button class="btn ghost danger" onclick={() => dropLabel(l)} aria-label="Удалить подпись">×</button>
          </div>
        {/each}
      </div>
      <p class="muted small">Страна в системе с {showDate(country.valid_from)}{country.valid_to ? ` по ${showDate(country.valid_to)}` : ""}.</p>
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
  .editor { display: flex; flex-direction: column; gap: 14px; padding: 20px 28px 40px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 12px; }
  h2 { margin: 0; font-size: 20px; }
  .spacer { flex: 1; }
  .stats { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media (max-width: 1200px) { .cols { grid-template-columns: 1fr; } }
  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; flex: none; border: 1px solid rgba(255, 255, 255, 0.2); }
  i.big { width: 22px; height: 22px; border-radius: 6px; }
  .line { display: flex; align-items: center; gap: 8px; }
  .color { padding: 2px; height: 32px; max-width: 120px; }
  .label-row { display: grid; grid-template-columns: 1fr 96px 96px 120px auto auto auto; gap: 8px; align-items: center; padding: 4px; border-radius: var(--radius-s); }
  .label-row.changed { background: var(--accent-soft); }
  .err { color: var(--danger); font-size: 12px; }
  .bad { border-color: var(--danger); }
  .pad { padding: 20px; }
  .mono { font-family: var(--mono); }
</style>
