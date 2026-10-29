<script lang="ts">
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import { go } from "../lib/router.svelte";
  import { ago } from "../lib/time";

  let rows = $state<Schemas["LibraryRow"][]>([]);
  let formats = $state<Schemas["Format"][]>([]);
  let filters = $state({ q: "", format: "", kind: "", only: "" });
  let loading = $state(true);

  onMount(async () => { formats = (await api.GET("/studio/api/formats")).data ?? []; });

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const query = { ...filters };
    clearTimeout(timer);
    timer = setTimeout(async () => {
      loading = true;
      rows = (await api.GET("/studio/api/items", { params: { query } })).data ?? [];
      loading = false;
    }, 200);
  });

  const ONLY = [
    ["", "все"], ["recent", "правили за неделю"], ["mine", "правил я"], ["shared", "в нескольких местах"],
    ["orphans", "нигде не лежат"], ["layers", "со слоями"], ["access", "с условием"], ["keys", "ключи"],
  ];
  const KIND: Record<string, string> = { text: "текст", asset: "ассет", link: "ссылка", scene: "сцена", message: "письмо", empty: "пусто" };

  function size(bytes: number | null | undefined) {
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} Б`;
    return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1048576).toFixed(1)} МБ`;
  }
</script>

<header class="head">
  <div>
    <h1>Объекты</h1>
    <p class="muted">Всё, что лежит в мире. Один объект может лежать в нескольких томах и архивах: правка видна везде.</p>
  </div>
  <div class="tools">
    <select class="field" bind:value={filters.kind}>
      <option value="">любое содержимое</option>
      {#each Object.entries(KIND) as [value, label]}<option {value}>{label}</option>{/each}
    </select>
    <select class="field" bind:value={filters.format}>
      <option value="">любой формат</option>
      {#each formats as found}<option value={found.name}>{found.name}</option>{/each}
    </select>
    <input class="field search" placeholder="Название, слаг или текст" bind:value={filters.q} />
  </div>
</header>

<nav class="chips">
  {#each ONLY as [value, label]}
    <button class="pick" class:on={filters.only === value} onclick={() => (filters.only = value)}>{label}</button>
  {/each}
  <span class="muted count">{loading ? "…" : rows.length >= 200 ? "первые 200" : `${rows.length}`}</span>
</nav>

<section class="table">
  <div class="row head"><span>Объект</span><span>Содержимое</span><span class="num">Мест</span><span>Защита</span><span class="num">Размер</span><span>Правка</span></div>
  {#each rows as row (row.id)}
    <button class="row" onclick={() => go(`/items/${row.id}`)}>
      <span class="name"><b>{row.name}</b>{#if row.format}<span class="chip">{row.format}</span>{/if}<span class="mono slug">{row.slug}</span></span>
      <span class="muted">{KIND[row.kind]}</span>
      <span class="num" class:warn={row.places + row.archives === 0}>
        {row.places}{#if row.archives}<span class="muted"> +{row.archives} арх.</span>{/if}
      </span>
      <span class="flags">
        {#if row.layers}<span class="chip warnchip">слои</span>{/if}
        {#if row.access}<span class="chip warnchip">условие</span>{/if}
      </span>
      <span class="num mono muted">{size(row.size)}</span>
      <span class="muted">{ago(row.updated_at)}{row.updated_by ? ` · ${row.updated_by}` : ""}</span>
    </button>
  {:else}
    {#if !loading}<p class="muted pad">Ничего не нашлось.</p>{/if}
  {/each}
</section>

<style>
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; padding: 28px 32px 12px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  .head p { margin: 4px 0 0; max-width: 560px; }
  .tools { display: flex; gap: 8px; }
  .tools .field { width: auto; }
  .search { width: 260px !important; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 0 32px 12px; }
  .pick { padding: 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--muted); cursor: pointer; }
  .pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .count { margin-left: auto; }
  .table { padding: 0 32px 32px; }
  .pad { padding: 12px 10px; }
  .row {
    display: grid; grid-template-columns: minmax(280px, 1fr) 90px 90px 150px 80px 190px; align-items: center; gap: 12px;
    width: 100%; height: 40px; padding: 0 12px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer;
  }
  .row:not(.head):hover { background: var(--panel); }
  .row.head { height: 30px; color: var(--faint); font-size: 12px; border-bottom: 1px solid var(--line-soft); border-radius: 0; cursor: default; }
  .name { display: flex; align-items: center; gap: 8px; min-width: 0; white-space: nowrap; overflow: hidden; }
  .slug { color: var(--faint); font-size: 11.5px; overflow: hidden; text-overflow: ellipsis; }
  .num { text-align: right; font-variant-numeric: tabular-nums; }
  .warn { color: var(--warn); }
  .flags { display: flex; gap: 4px; }
  .chip.warnchip { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
</style>
