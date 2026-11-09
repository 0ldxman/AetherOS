<script lang="ts">
  // Владения: все записи «провинция → страна с даты». Фильтры, правка записи, добавление и удаление пачкой.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, showDate, today, type Country } from "./shared";

  const SIZE = 100;
  type Row = Schemas["MapOwnershipRow"];

  let q = $state("");
  let country = $state("");
  let after = $state("");
  let before = $state("");
  let flag = $state("");
  let page = $state(0);
  let data = $state<Schemas["MapOwnershipPage"]>({ total: 0, rows: [] });
  let countries = $state<Country[]>([]);
  let chosen = $state<number[]>([]);
  let editing = $state<null | { id: number | null; province: number; provinceName: string; country: number; date_from: string; de_jure: boolean; de_facto: boolean }>(null);
  let find = $state("");
  let found = $state<Schemas["MapProvinceRow"][]>([]);
  let errors = $state<Record<string, string[]>>({});

  const pages = $derived(Math.max(1, Math.ceil(data.total / SIZE)));
  const allChosen = $derived(data.rows.length > 0 && data.rows.every((r) => chosen.includes(r.id)));

  async function list() {
    const query: Record<string, string | number> = { q, flag, offset: page * SIZE, limit: SIZE };
    if (country) query.country = +country;
    if (after) query.after = after;
    if (before) query.before = before;
    data = (await api.GET("/studio/api/map/ownerships", { params: { query } })).data ?? { total: 0, rows: [] };
    chosen = chosen.filter((id) => data.rows.some((r) => r.id === id));
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { q; country; after; before; flag; page; clearTimeout(timer); timer = setTimeout(list, 200); });
  $effect(() => { q; country; after; before; flag; page = 0; });
  onMount(async () => { countries = (await api.GET("/studio/api/map/countries")).data ?? []; });

  let findTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const text = find.trim();
    clearTimeout(findTimer);
    if (!editing || editing.id !== null && !text) return;
    findTimer = setTimeout(async () => {
      found = text ? (await api.GET("/studio/api/map/provinces", { params: { query: { q: text, limit: 8 } } })).data?.rows ?? [] : [];
    }, 200);
  });

  function openNew() {
    editing = { id: null, province: 0, provinceName: "", country: +country || countries[0]?.id || 0, date_from: today(), de_jure: true, de_facto: true };
    find = "";
    found = [];
    errors = {};
  }
  function openEdit(row: Row) {
    editing = { id: row.id, province: row.province, provinceName: `${row.province_name} (${row.province_code})`, country: row.country, date_from: row.date_from, de_jure: row.de_jure, de_facto: row.de_facto };
    find = "";
    found = [];
    errors = {};
  }

  async function submit() {
    if (!editing) return;
    errors = {};
    const body = { province: editing.province, country: editing.country, date_from: editing.date_from, de_jure: editing.de_jure, de_facto: editing.de_facto };
    const { data: out, error } = editing.id === null
      ? await api.POST("/studio/api/map/ownerships", { body })
      : await api.PUT("/studio/api/map/ownerships/{ownership_id}", { params: { path: { ownership_id: editing.id } }, body });
    if (error || !out) { errors = fieldErrors(error); return toast(problem(error, "Не сохранилось."), "error"); }
    toast("Запись сохранена.");
    editing = null;
    list();
  }

  async function removeChosen() {
    if (!chosen.length) return;
    if (!(await ask(`Удалить записей: ${chosen.length}?`, "Провинции вернутся к прежним владельцам по более ранним записям."))) return;
    const { data: out, error } = await api.POST("/studio/api/map/ownerships/delete", { body: { ids: chosen } });
    if (error || !out) return toast(problem(error), "error");
    toast(`Удалено записей: ${out.deleted}.`);
    chosen = [];
    list();
  }

  function toggleAll() {
    chosen = allChosen ? [] : data.rows.map((r) => r.id);
  }
  const FLAGS: Record<string, string> = { "11": "юре+факто", "10": "юре", "01": "факто" };
</script>

<div class="screen">
  <header class="bar">
    <input class="field q" placeholder="Провинция…" bind:value={q} />
    <select class="field" bind:value={country} aria-label="Страна">
      <option value="">любая страна</option>
      {#each countries as c (c.id)}<option value={String(c.id)}>{c.name} ({c.code})</option>{/each}
    </select>
    <label class="inline"><span class="muted">с</span><input class="field" type="date" bind:value={after} /></label>
    <label class="inline"><span class="muted">по</span><input class="field" type="date" bind:value={before} /></label>
    <select class="field" bind:value={flag} aria-label="Права">
      <option value="">любые права</option>
      <option value="both">юре и факто</option>
      <option value="jure">только юре</option>
      <option value="facto">только факто</option>
    </select>
    <span class="spacer"></span>
    <span class="muted">{data.total} записей</span>
    {#if chosen.length}<button class="btn danger" onclick={removeChosen}>Удалить ({chosen.length})</button>{/if}
    <button class="btn" onclick={openNew} disabled={!countries.length}>+ Запись</button>
  </header>

  <table>
    <thead><tr>
      <th class="c"><input type="checkbox" checked={allChosen} onchange={toggleAll} aria-label="Выбрать все" /></th>
      <th>С даты</th><th>Провинция</th><th>Страна</th><th>Права<Hint text="Де-юре: по праву, признанные границы. Де-факто: реальный контроль." /></th>
    </tr></thead>
    <tbody>
      {#each data.rows as row (row.id)}
        <tr onclick={() => openEdit(row)}>
          <td class="c" onclick={(e) => e.stopPropagation()}><input type="checkbox" bind:group={chosen} value={row.id} aria-label="Выбрать" /></td>
          <td>{showDate(row.date_from)}</td>
          <td><b>{row.province_name}</b> <span class="muted mono">{row.province_code}</span></td>
          <td><i style="background:{row.color}"></i>{row.country_name} <span class="muted mono">{row.country_code}</span></td>
          <td class="muted">{FLAGS[`${+row.de_jure}${+row.de_facto}`]}</td>
        </tr>
      {:else}
        <tr><td colspan="5" class="muted empty">Записей нет.</td></tr>
      {/each}
    </tbody>
  </table>

  <footer class="pager">
    <button class="btn ghost" disabled={page === 0} onclick={() => page--}>← назад</button>
    <span class="muted">страница {page + 1} из {pages}</span>
    <button class="btn ghost" disabled={page + 1 >= pages} onclick={() => page++}>дальше →</button>
  </footer>
</div>

{#if editing}
  {@const draft = editing}
  <Dialog title={draft.id === null ? "Новая запись владения" : "Запись владения"} confirm="Сохранить" onsubmit={submit} onclose={() => (editing = null)} disabled={!draft.province || !draft.country || !draft.date_from || !(draft.de_jure || draft.de_facto)}>
    <div class="who">
      <span class="label">Провинция</span>
      {#if draft.province}<div class="picked"><b>{draft.provinceName}</b><button class="btn ghost" onclick={() => { draft.province = 0; draft.provinceName = ""; find = ""; }}>сменить</button></div>
      {:else}
        <input class="field" placeholder="Название или код провинции…" bind:value={find} />
        {#each found as p (p.id)}
          <button class="pick" onclick={() => { draft.province = p.id; draft.provinceName = `${p.name} (${p.code})`; found = []; }}>{p.name} <span class="muted mono">{p.code}</span></button>
        {/each}
      {/if}
    </div>
    <label><span class="label">Страна</span>
      <select class="field" bind:value={draft.country}>{#each countries as c (c.id)}<option value={c.id}>{c.name} ({c.code})</option>{/each}</select></label>
    <label><span class="label">С даты</span><input class="field" type="date" bind:value={draft.date_from} /></label>
    <label class="check"><input type="checkbox" bind:checked={draft.de_jure} /> де-юре</label>
    <label class="check"><input type="checkbox" bind:checked={draft.de_facto} /> де-факто</label>
    {#each Object.values(errors).flat() as text}<p class="err">{text}</p>{/each}
  </Dialog>
{/if}

<style>
  .screen { display: flex; flex-direction: column; min-height: 100%; }
  .bar { display: flex; flex-wrap: wrap; gap: 10px 12px; align-items: center; padding: 14px 20px; position: sticky; top: 0; background: var(--bg); z-index: 1; border-bottom: 1px solid var(--line-soft); }
  .bar .field { width: auto; min-width: 140px; }
  .q { max-width: 240px; }
  .inline { display: flex; align-items: center; gap: 6px; }
  .spacer { flex: 1; }
  table { border-collapse: collapse; width: 100%; }
  th { text-align: left; padding: 8px 14px; font-weight: 500; color: var(--muted); font-size: 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
  td { padding: 6px 14px; border-bottom: 1px solid var(--line-soft); }
  .c { width: 34px; }
  tbody tr { cursor: pointer; }
  tbody tr:hover { background: var(--panel); }
  .empty { padding: 24px; text-align: center; }
  .pager { display: flex; gap: 14px; align-items: center; justify-content: center; padding: 14px; }
  i { display: inline-block; width: 11px; height: 11px; border-radius: 3px; margin-right: 8px; border: 1px solid rgba(255, 255, 255, 0.2); }
  .mono { font-family: var(--mono); font-size: 12px; }
  .who { display: flex; flex-direction: column; gap: 4px; }
  .picked { display: flex; align-items: center; justify-content: space-between; }
  .pick { text-align: left; padding: 6px 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); cursor: pointer; }
  .pick:hover { background: var(--raise); }
  .check { display: flex; align-items: center; gap: 6px; }
  .err { color: var(--danger); font-size: 12px; margin: 0; }
</style>
