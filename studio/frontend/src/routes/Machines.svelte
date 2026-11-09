<script lang="ts">
  import PageHead from "../lib/PageHead.svelte";
  import { STATUS } from "../lib/labels";
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import { go } from "../lib/router.svelte";
  import { ago, full } from "../lib/time";
  import NewMachine from "./machine/NewMachine.svelte";

  let rows = $state<Schemas["MachineRow"][]>([]);
  let loading = $state(true);
  let query = $state("");
  let status = $state("");
  let creating = $state(false);
  let onlyWarned = $state(false);
  let sort = $state<{ key: string; down: boolean }>({ key: "host", down: false });

  const VALUE: Record<string, (row: Schemas["MachineRow"]) => string | number> = {
    host: (row) => (row.hostname || row.name).toLowerCase(),
    system: (row) => row.system,
    status: (row) => row.status,
    accounts: (row) => row.accounts,
    online: (row) => row.online,
    refusals: (row) => row.refusals,
    last_login: (row) => (row.last_login ? new Date(row.last_login).getTime() : 0),
    warnings: (row) => row.warnings,
  };
  function sortBy(key: string) {
    sort = { key, down: sort.key === key ? !sort.down : key !== "host" && key !== "system" && key !== "status" };
  }
  const arrow = (key: string) => (sort.key === key ? (sort.down ? " ↓" : " ↑") : "");
  const warned = $derived(rows.filter((row) => row.warnings > 0).length);

  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase();
    const found = rows.filter((row) => {
      if (status && row.status !== status) return false;
      if (onlyWarned && !row.warnings) return false;
      return !q || [row.hostname, row.name, row.system].some((text) => text.toLowerCase().includes(q));
    });
    const get = VALUE[sort.key];
    return [...found].sort((a, b) => (get(a) < get(b) ? -1 : get(a) > get(b) ? 1 : 0) * (sort.down ? -1 : 1));
  });

  onMount(async () => {
    const { data } = await api.GET("/studio/api/machines");
    rows = data ?? [];
    loading = false;
  });

</script>

<PageHead title="Машины">
  {#snippet sub()}Хосты мира: учётки, доступ, кто сейчас на них и что там происходило.{/snippet}
    <select class="field narrow" bind:value={status}>
      <option value="">все статусы</option>
      {#each Object.entries(STATUS) as [value, label]}<option {value}>{label}</option>{/each}
    </select>
    <button class="pill" class:on={onlyWarned} aria-pressed={onlyWarned} disabled={!warned && !onlyWarned} onclick={() => (onlyWarned = !onlyWarned)}
            title="Только машины, у которых на обзоре есть замечания">⚠ С замечаниями{warned ? ` · ${warned}` : ""}</button>
    <input class="field search" placeholder="Поиск по хосту, названию, ОС" bind:value={query} />
    <button class="btn primary" onclick={() => (creating = true)}>Новая машина</button>
</PageHead>

<section class="table">
  <div class="row head">
    <span><button class="sort" onclick={() => sortBy("host")}>Хост{arrow("host")}</button></span>
    <span><button class="sort" onclick={() => sortBy("system")}>ОС{arrow("system")}</button></span>
    <span><button class="sort" onclick={() => sortBy("status")}>Статус{arrow("status")}</button></span>
    <span class="num"><button class="sort" onclick={() => sortBy("accounts")}>Учёток{arrow("accounts")}</button></span>
    <span class="num"><button class="sort" onclick={() => sortBy("online")}>Сейчас{arrow("online")}</button></span>
    <span class="num"><button class="sort" onclick={() => sortBy("refusals")}>Отказов за сутки{arrow("refusals")}</button></span>
    <span><button class="sort" onclick={() => sortBy("last_login")}>Последний вход{arrow("last_login")}</button></span>
    <span class="num"><button class="sort" onclick={() => sortBy("warnings")}>Замечания{arrow("warnings")}</button></span>
  </div>
  {#if loading}
    <p class="muted pad">Загрузка…</p>
  {:else}
    {#each shown as row (row.id)}
      <a class="row" href="#/machines/{row.id}">
        <span class="host">
          <span class="dot {row.status.toLowerCase()}"></span>
          <span><b class="mono">{row.hostname || "—"}</b> <span class="muted">{row.name}</span></span>
          {#if row.is_system}<span class="chip">системная</span>{/if}
        </span>
        <span class="muted">{row.system}</span>
        <span class="muted">{STATUS[row.status] ?? row.status}</span>
        <span class="num">{row.accounts}</span>
        <span class="num" class:live={row.online > 0}>{row.online || "—"}</span>
        <span class="num" class:alarm={row.refusals > 0}>{row.refusals || "—"}</span>
        <span class="muted" title={full(row.last_login)}>{row.last_login ? ago(row.last_login) : "не входили"}</span>
        <span class="num" class:alarm={row.warnings > 0} title={row.warnings ? "Есть замечания: откройте машину" : ""}>{row.warnings ? `⚠ ${row.warnings}` : "—"}</span>
      </a>
    {:else}
      <p class="muted pad">{rows.length ? "Ничего не нашлось." : "Машин пока нет."}</p>
      {#if !rows.length}<button class="btn primary add-first" onclick={() => (creating = true)}>Новая машина</button>{/if}
    {/each}
  {/if}
</section>

{#if creating}<NewMachine machines={rows} onclose={() => (creating = false)} />{/if}

<style>
  .search { width: 280px; }
  .narrow { width: 150px; }
  .table { padding: 0 32px 32px; }
  .pad { padding: 12px 10px; }
  .row {
    display: grid; grid-template-columns: minmax(240px, 1fr) 100px 110px 70px 70px 140px 130px 90px; align-items: center; gap: 12px;
    width: 100%; height: 42px; padding: 0 12px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer;
  }
  a.row { color: inherit; text-decoration: none; }
  .row:not(.head):hover { background: var(--panel); }
  .row.head { height: 30px; color: var(--faint); font-size: 12px; border-bottom: 1px solid var(--line-soft); border-radius: 0; cursor: default; }
  .host { display: flex; align-items: center; gap: 10px; min-width: 0; white-space: nowrap; overflow: hidden; }
  .sort { padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
  .sort:hover { color: var(--text); }
  .pill { height: 30px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-2); cursor: pointer; }
  .pill.on { border-color: var(--warn); background: rgba(242, 198, 109, 0.12); }
  .pill:disabled { opacity: 0.45; cursor: default; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .live { color: var(--ok); font-weight: 600; }
  .alarm { color: var(--warn); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); flex: none; }
  .dot.online { background: var(--ok); box-shadow: 0 0 0 3px rgba(95, 208, 160, 0.15); }
  .dot.maintenance { background: var(--warn); }
  .add-first { margin: 0 12px 12px; }
</style>
