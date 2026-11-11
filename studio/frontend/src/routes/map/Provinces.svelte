<script lang="ts">
  // Провинции: таблица с поиском и фильтром по владельцу на дату; справа карточка выбранной с историей владений.
  import { onMount } from "svelte";
  import DraftState from "../../lib/DraftState.svelte";
  import { SharedForm } from "../../lib/shared.svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, NO_COLOR, showDate, type Country } from "./shared";
  import MaterialField from "./MaterialField.svelte";

  const SIZE = 100;
  type Form = Schemas["MapProvinceIn"];
  let { id }: { id: number | null } = $props();

  let q = $state("");
  let owner = $state("");              // "" все, "none" без владельца, иначе id страны
  let on = $state("");
  let page = $state(0);
  let sort = $state("name");                // name, code, records, last; со знаком «-» по убыванию
  let data = $state<Schemas["MapProvincePage"]>({ total: 0, rows: [] });
  let countries = $state<Country[]>([]);
  let province = $state<Schemas["MapProvinceOut"] | null>(null);
  let form = $state<Form>({ code: "", source_code: "", name: "", wiki_url: "", show_info: true, material: null });
  let saved = $state("");
  let base = $state<Form | null>(null);                    // сохранённое: им наполняется общий черновик
  let errors = $state<Record<string, string[]>>({});
  let dialog = $state(false);
  let draft = $state<Form>({ code: "", source_code: "", name: "", wiki_url: "", show_info: true, material: null });

  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);      // в совместном режиме черновик на сервере
  // щелчок по заголовку: сначала по возрастанию (у «изменений» и «последнего» по убыванию), второй щелчок меняет направление
  function sortBy(key: string) {
    const first = key === "records" || key === "last" ? `-${key}` : key;
    sort = sort === first ? (first.startsWith("-") ? key : `-${key}`) : first;
  }
  const arrow = (key: string) => (sort === key ? "↑" : sort === `-${key}` ? "↓" : "");
  const pages = $derived(Math.max(1, Math.ceil(data.total / SIZE)));

  async function list() {
    const query: { q: string; owner: string; on?: string; offset: number; limit: number; sort: string } = { q, owner, offset: page * SIZE, limit: SIZE, sort };
    if (on) query.on = on;
    data = (await api.GET("/studio/api/map/provinces", { params: { query } })).data ?? { total: 0, rows: [] };
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { q; owner; on; page; sort; clearTimeout(timer); timer = setTimeout(list, 200); });
  $effect(() => { q; owner; on; sort; page = 0; });

  async function load(target: number | null) {
    province = null;
    base = null;
    errors = {};
    if (target === null) return;
    const { data: found } = await api.GET("/studio/api/map/provinces/{province_id}", { params: { path: { province_id: target }, query: on ? { on } : {} } });
    if (!found) return;
    province = found;
    form = { code: found.code, source_code: found.source_code, name: found.name, wiki_url: found.wiki_url, show_info: found.show_info, material: found.material };
    saved = JSON.stringify(form);
    base = JSON.parse(saved);
  }
  // общий черновик провинции; кто-то сохранил: перечитать сохранённое, черновик не трогается
  const share = new SharedForm({
    room: () => `map/provinces/${id}`,
    texts: ["name", "wiki_url"],
    draft: () => form,
    base: () => base,
    onRemoteSave: async () => {
      if (id === null) return;
      const { data: found } = await api.GET("/studio/api/map/provinces/{province_id}", { params: { path: { province_id: id }, query: on ? { on } : {} } });
      if (!found) return;
      province = found;
      saved = JSON.stringify({ code: found.code, source_code: found.source_code, name: found.name, wiki_url: found.wiki_url, show_info: found.show_info, material: found.material });
      base = JSON.parse(saved);
      list();
    },
  });
  $effect(() => { load(id); });
  onMount(async () => { countries = (await api.GET("/studio/api/map/countries")).data ?? []; });

  async function save() {
    if (!province) return;
    errors = {};
    const { data: out, error } = await api.PUT("/studio/api/map/provinces/{province_id}", { params: { path: { province_id: province.id } }, body: form });
    if (error || !out) { errors = fieldErrors(error); return toast(problem(error, "Не сохранилось."), "error"); }
    share.markSaved();
    toast("Провинция сохранена.");
    await load(out.id);
    list();
  }

  async function create() {
    errors = {};
    const { data: out, error } = await api.POST("/studio/api/map/provinces", { body: draft });
    if (error || !out) { errors = fieldErrors(error); return toast(problem(error, "Не создалась."), "error"); }
    dialog = false;
    await list();
    go(`/map/provinces/${out.id}`);
  }

  async function remove() {
    if (!province) return;
    if (!(await ask(`Удалить провинцию «${province.name}»?`, province.records ? `Вместе с ней удалятся записи владения: ${province.records}.` : "", "Удалить"))) return;
    const { error } = await api.DELETE("/studio/api/map/provinces/{province_id}", { params: { path: { province_id: province.id } } });
    if (error) return toast(problem(error), "error");
    toast("Провинция удалена.");
    await list();
    go("/map/provinces");
  }
</script>

<div class="screen" class:open={province}>
  <section class="main">
    <header class="bar">
      <input class="field q" placeholder="Название, код или код тайлов…" bind:value={q} />
      <label class="inline"><span class="muted">Владелец</span>
        <select class="field" bind:value={owner}>
          <option value="">любой</option>
          <option value="none">без владельца</option>
          {#each countries as c (c.id)}<option value={String(c.id)}>{c.name} ({c.code})</option>{/each}
        </select></label>
      <label class="inline"><span class="muted">На дату<Hint text="Владелец считается на эту дату. Пусто: по самым свежим записям." /></span>
        <input class="field" type="date" bind:value={on} /></label>
      <span class="spacer"></span>
      <span class="muted">{data.total} шт.</span>
      <button class="btn" onclick={() => { draft = { code: "", source_code: "", name: "", wiki_url: "", show_info: true, material: null }; errors = {}; dialog = true; }}>+ Провинция</button>
    </header>

    <table>
      <thead>
        <tr>
          <th><button class="sort" class:on={sort.replace("-", "") === "name"} onclick={() => sortBy("name")}>Название {arrow("name")}</button></th>
          <th><button class="sort" class:on={sort.replace("-", "") === "code"} onclick={() => sortBy("code")}>Код {arrow("code")}</button></th>
          <th class="r"><button class="sort" class:on={sort.replace("-", "") === "records"} onclick={() => sortBy("records")}>Всего изменений владения {arrow("records")}</button></th>
          <th><button class="sort" class:on={sort.replace("-", "") === "last"} onclick={() => sortBy("last")}>Последнее изменение {arrow("last")}</button></th>
        </tr>
      </thead>
      <tbody>
        {#each data.rows as row (row.id)}
          <tr class:on={row.id === id} onclick={() => go(`/map/provinces/${row.id}`)}>
            <td><b>{row.name}</b></td>
            <td>
              <button type="button" class="codecell" aria-label="Код {row.code}, код тайла {row.source_code}">
                <code>{row.code}</code>
                <span class="pop" role="tooltip">
                  <span class="muted">Код провинции</span><code>{row.code}</code>
                  <span class="muted">Код тайла</span><code>{row.source_code}</code>
                </span>
              </button>
            </td>
            <td class="r num">{row.records}</td>
            <td>
              {#if row.last_change}
                {@const c = row.last_change}
                <span class="change">
                  {#if c.old}<i style="background:{c.old_color || NO_COLOR}"></i>{c.old}{:else}<span class="muted">нет владельца</span>{/if}
                  <span class="muted arrow">→</span>
                  <i style="background:{c.new_color || NO_COLOR}"></i><b>{c.new}</b>
                  <span class="muted when">{showDate(c.date)}</span>
                  {#if c.de_jure}<span class="tag">де-юре</span>{/if}{#if c.de_facto}<span class="tag">де-факто</span>{/if}
                </span>
              {:else}<span class="muted">изменений нет</span>{/if}
            </td>
          </tr>
        {:else}
          <tr><td colspan="4" class="muted empty">Ничего не найдено.</td></tr>
        {/each}
      </tbody>
    </table>

    <footer class="pager">
      <button class="btn ghost" disabled={page === 0} onclick={() => page--}>← назад</button>
      <span class="muted">страница {page + 1} из {pages}</span>
      <button class="btn ghost" disabled={page + 1 >= pages} onclick={() => page++}>дальше →</button>
    </footer>
  </section>

  {#if province}
    <aside class="side">
      <header class="top">
        <h2>{province.name}</h2>
        <span class="spacer"></span>
        <button class="btn ghost" onclick={() => go("/map/provinces")} aria-label="Закрыть">×</button>
      </header>
      <div class="block">
        <label><span class="label">Название</span><input class="field" class:bad={errors.name} bind:value={form.name} />{#if errors.name}<span class="err">{errors.name.join(" ")}</span>{/if}</label>
        <label><span class="label">Код<Hint text="Читаемый код вида RUS-32: его пишут в виджетах и пометках сцен." /></span><input class="field mono" class:bad={errors.code} bind:value={form.code} />{#if errors.code}<span class="err">{errors.code.join(" ")}</span>{/if}</label>
        <label><span class="label">Код тайлов</span><input class="field mono" class:bad={errors.source_code} bind:value={form.source_code} />{#if errors.source_code}<span class="err">{errors.source_code.join(" ")}</span>{/if}</label>
        <MaterialField scope="province" material={form.material} info={province.material_info} showInfo={form.show_info ?? true} url={form.wiki_url ?? ""} error={errors.material?.join(" ")}
                       onmaterial={(id) => (form.material = id)} onshow={(v) => (form.show_info = v)} onurl={(v) => (form.wiki_url = v)} />
        <div class="row">
          <button class="btn ghost danger" onclick={remove}>Удалить</button>
          <span class="spacer"></span>
          <DraftState {share} {dirty} saved="" />
          <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
        </div>
      </div>
      <div class="block">
        <h3>История владений</h3>
        {#if !province.history.length}<p class="muted small">Записей нет: провинция ничья.</p>{/if}
        <ul class="history">
          {#each province.history as row (row.id)}
            <li class:now={row.current}><i style="background:{row.color}"></i><span>{showDate(row.date_from)}</span><b>{row.country_code}</b>
              <small class="muted">{row.de_jure && row.de_facto ? "юре+факто" : row.de_jure ? "юре" : "факто"}</small></li>
          {/each}
        </ul>
        <a class="small" href="#/map/ownerships">Править записи во «Владениях»</a>
      </div>
    </aside>
  {/if}
</div>

{#if dialog}
  <Dialog title="Новая провинция" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)} disabled={!draft.name.trim() || !draft.code.trim() || !draft.source_code.trim()}>
    <p class="muted small">Границы провинции берутся из файла тайлов, поэтому код тайлов должен совпадать с тем, что в нём есть. Новую границу из Студии нарисовать нельзя.</p>
    <label><span class="label">Название</span><input class="field" bind:value={draft.name} /></label>
    <label><span class="label">Код</span><input class="field mono" class:bad={errors.code} bind:value={draft.code} />{#if errors.code}<span class="err">{errors.code.join(" ")}</span>{/if}</label>
    <label><span class="label">Код тайлов</span><input class="field mono" class:bad={errors.source_code} bind:value={draft.source_code} />{#if errors.source_code}<span class="err">{errors.source_code.join(" ")}</span>{/if}</label>
  </Dialog>
{/if}

<style>
  .screen { display: grid; grid-template-columns: 1fr; height: 100%; min-height: 0; }
  .screen.open { grid-template-columns: 1fr 340px; }
  .main { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: auto; }
  .bar { display: flex; flex-wrap: wrap; gap: 10px 14px; align-items: center; padding: 14px 20px; position: sticky; top: 0; background: var(--bg); z-index: 1; border-bottom: 1px solid var(--line-soft); }
  .q { max-width: 280px; }
  .inline { display: flex; align-items: center; gap: 8px; }
  .inline .field { width: auto; min-width: 150px; }
  .spacer { flex: 1; }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; padding: 8px 14px; font-weight: 500; color: var(--muted); font-size: 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
  td { padding: 6px 14px; border-bottom: 1px solid var(--line-soft); }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--panel); }
  tbody tr.on { background: var(--accent-soft); }
  .r { text-align: right; }
  .num { font-variant-numeric: tabular-nums; }
  .sort { padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
  .sort:hover, .sort.on { color: var(--text); }
  .sort:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .codecell { position: relative; display: inline-block; padding: 1px 4px; margin: -1px -4px; border: 0; border-radius: 4px; background: none; color: inherit; font: inherit; text-align: left; cursor: help; }
  .codecell code { font-family: var(--mono); font-size: 12.5px; }
  .codecell .pop { display: none; position: absolute; z-index: 5; left: 0; top: calc(100% + 4px); grid-template-columns: auto auto; gap: 2px 12px; padding: 8px 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--raise); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); white-space: nowrap; font-size: 12px; }
  .codecell:hover .pop, .codecell:focus-visible .pop { display: grid; }
  .codecell:focus-visible { outline: 2px solid var(--accent); }
  .change { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .change i { margin-right: 4px; }
  .change .arrow { margin: 0 2px; }
  .change .when { margin-left: 8px; font-variant-numeric: tabular-nums; }
  .tag { padding: 0 7px; margin-left: 4px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11.5px; }
  .empty { padding: 24px; text-align: center; }
  .pager { display: flex; gap: 14px; align-items: center; justify-content: center; padding: 14px; }
  .side { border-left: 1px solid var(--line-soft); padding: 16px; display: flex; flex-direction: column; gap: 12px; overflow: auto; }
  .top { display: flex; align-items: center; gap: 8px; }
  h2 { margin: 0; font-size: 17px; }
  .row { display: flex; align-items: center; }
  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 8px; border: 1px solid rgba(255, 255, 255, 0.2); }
  .history { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; max-height: 300px; overflow: auto; }
  .history li { display: flex; gap: 8px; align-items: center; padding: 3px 6px; border-radius: var(--radius-s); }
  .history li i { margin: 0; }
  .history li.now { background: var(--accent-soft); }
  .history b { font-family: var(--mono); font-size: 12px; }
  .err { color: var(--danger); font-size: 12px; }
  .bad { border-color: var(--danger); }
  .mono { font-family: var(--mono); font-size: 12.5px; }
</style>
