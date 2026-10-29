<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import { go } from "../lib/router.svelte";
  import NewMachine from "./machine/NewMachine.svelte";

  let rows = $state<Schemas["MachineRow"][]>([]);
  let loading = $state(true);
  let query = $state("");
  let status = $state("");
  let creating = $state(false);

  const shown = $derived(
    rows.filter((row) => {
      const q = query.trim().toLowerCase();
      if (status && row.status !== status) return false;
      return !q || [row.hostname, row.name, row.system].some((text) => text.toLowerCase().includes(q));
    }),
  );

  onMount(async () => {
    const { data } = await api.GET("/studio/api/machines");
    rows = data ?? [];
    loading = false;
  });

  const STATUS: Record<string, string> = { ONLINE: "online", OFFLINE: "offline", MAINTENANCE: "обслуживание" };
</script>

<header class="head">
  <div>
    <h1>Машины</h1>
    <p class="muted">Хосты мира: учётки, доступ, кто сейчас на них и что там происходило.</p>
  </div>
  <div class="tools">
    <select class="field narrow" bind:value={status}>
      <option value="">все статусы</option>
      {#each Object.entries(STATUS) as [value, label]}<option {value}>{label}</option>{/each}
    </select>
    <input class="field search" placeholder="Поиск по хосту, названию, типу" bind:value={query} />
    <button class="btn primary" onclick={() => (creating = true)}>Новая машина</button>
  </div>
</header>

<section class="table">
  <div class="row head">
    <span>Хост</span><span>Тип</span><span>Статус</span><span class="num">Учёток</span><span class="num">Сейчас</span><span class="num">Отказов за сутки</span>
  </div>
  {#if loading}
    <p class="muted pad">Загрузка…</p>
  {:else}
    {#each shown as row (row.id)}
      <button class="row" onclick={() => go(`/machines/${row.id}`)}>
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
      </button>
    {:else}
      <p class="muted pad">{rows.length ? "Ничего не нашлось." : "Машин пока нет."}</p>
    {/each}
  {/if}
</section>

{#if creating}<NewMachine machines={rows} onclose={() => (creating = false)} />{/if}

<style>
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; padding: 28px 32px 18px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  .head p { margin: 4px 0 0; }
  .tools { display: flex; gap: 8px; }
  .search { width: 280px; }
  .narrow { width: 150px; }
  .table { padding: 0 32px 32px; }
  .pad { padding: 12px 10px; }
  .row {
    display: grid; grid-template-columns: minmax(260px, 1fr) 110px 120px 80px 80px 140px; align-items: center; gap: 12px;
    width: 100%; height: 42px; padding: 0 12px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer;
  }
  .row:not(.head):hover { background: var(--panel); }
  .row.head { height: 30px; color: var(--faint); font-size: 12px; border-bottom: 1px solid var(--line-soft); border-radius: 0; cursor: default; }
  .host { display: flex; align-items: center; gap: 10px; min-width: 0; white-space: nowrap; overflow: hidden; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .live { color: var(--ok); font-weight: 600; }
  .alarm { color: var(--warn); font-weight: 600; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); flex: none; }
  .dot.online { background: var(--ok); box-shadow: 0 0 0 3px rgba(95, 208, 160, 0.15); }
  .dot.maintenance { background: var(--warn); }
</style>
