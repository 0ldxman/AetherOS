<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import FormatOptions from "../lib/FormatOptions.svelte";
  import Hint from "../lib/Hint.svelte";
  import { toast } from "../lib/toast.svelte";
  import { go } from "../lib/router.svelte";
  import { ago } from "../lib/time";

  let rows = $state<Schemas["LibraryRow"][]>([]);
  let formats = $state<Schemas["Format"][]>([]);
  let filters = $state({ q: "", format: "", kind: "", only: "", volume: "", path: "", sort: "-updated_at" });
  let loading = $state(true);

  let volumes = $state<Schemas["VolumeRow"][]>([]);
  let dialog = $state<{ name: string; format: string; slug: string; volume: string } | null>(null);
  let busy = $state(false);

  onMount(async () => {
    formats = (await api.GET("/studio/api/formats")).data ?? [];
    volumes = (await api.GET("/studio/api/volumes")).data ?? [];
  });

  async function create() {
    if (!dialog) return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/items", {
      body: { name: dialog.name, format: dialog.format, slug: dialog.slug, volume: dialog.volume ? Number(dialog.volume) : null },
    });
    busy = false;
    if (error) return toast(problem(error), "error");
    dialog = null;
    if (data) go(`/items/${data.id}`);
  }

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const query = { ...filters, volume: filters.volume ? Number(filters.volume) : undefined };
    clearTimeout(timer);
    timer = setTimeout(async () => {
      loading = true;
      rows = (await api.GET("/studio/api/items", { params: { query } })).data ?? [];
      loading = false;
    }, 200);
  });

  const ONLY = [
    ["", "все"], ["markup", "С разметкой"], ["recent", "правили за неделю"], ["mine", "правил я"], ["shared", "в нескольких местах"],
    ["orphans", "нигде не лежат"], ["layers", "со слоями"], ["access", "с условием"], ["keys", "ключи"],
  ];
  const KIND: Record<string, string> = { text: "текст", asset: "ассет", link: "ссылка", scene: "сцена", message: "письмо", empty: "пусто" };

  const MARKUP_TIP = "Форматы с разметкой: подходят для статей и документов";

  function sortBy(field: string) {
    filters.sort = filters.sort === field ? `-${field}` : field;
  }
  const arrow = (field: string) => (filters.sort === field ? " ↑" : filters.sort === `-${field}` ? " ↓" : "");

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
      <FormatOptions {formats} codeOnly />
    </select>
    <select class="field" bind:value={filters.volume}>
      <option value="">любой том</option>
      {#each volumes as found}<option value={found.id}>{found.name || found.slug}</option>{/each}
    </select>
    <input class="field path mono" placeholder="папка: ports/reports" title="Путь к папке внутри тома: покажет объекты из неё и из вложенных" bind:value={filters.path} />
    <input class="field search" placeholder="Название, слаг или текст" bind:value={filters.q} />
    <button class="btn primary" onclick={() => (dialog = { name: "", format: "", slug: "", volume: "" })}>Новый объект</button>
  </div>
</header>

<nav class="chips">
  {#each ONLY as [value, label]}
    <button class="pick" class:on={filters.only === value} title={value === "markup" ? MARKUP_TIP : undefined} onclick={() => (filters.only = value)}>{value === "markup" ? "✎ " : ""}{label}</button>
  {/each}
  <span class="muted count">{loading ? "…" : rows.length >= 200 ? "первые 200" : `${rows.length}`}</span>
</nav>

<section class="table">
  <div class="row head">
    <span><button class="sort" onclick={() => sortBy("name")}>Объект{arrow("name")}</button></span>
    <span>Содержимое</span>
    <span><button class="sort" onclick={() => sortBy("places")}>Где лежит{arrow("places")}</button><Hint text="Том и путь, где лежит объект. Один объект может лежать в нескольких местах сразу: правка видна во всех. «арх.» — входит в архив (zip и подобные)." /></span>
    <span>Защита<Hint text="«слои» — шифрование и иные слои защиты содержимого. «условие» — правило, при котором игрок вообще получит доступ." /></span>
    <span class="num"><button class="sort" onclick={() => sortBy("size")}>Размер{arrow("size")}</button></span>
    <span><button class="sort" onclick={() => sortBy("updated_at")}>Правка{arrow("updated_at")}</button></span>
  </div>
  {#each rows as row (row.id)}
    <button class="row" onclick={() => go(`/items/${row.id}`)}>
      <span class="name"><b>{row.name}</b>{#if row.format}<span class="chip">{row.format}</span>{/if}<span class="mono slug">{row.slug}</span></span>
      <span class="muted">{KIND[row.kind]}</span>
      <span class="where" class:warn={row.places + row.archives === 0} title={row.where.join("\n")}>
        {#if row.where.length}
          <span class="mono">{row.where[0]}</span>{#if row.places > 1}<span class="muted">&nbsp;+{row.places - 1}</span>{/if}
        {:else if !row.archives}нигде{/if}
        {#if row.archives}<span class="muted"> · арх. {row.archives}</span>{/if}
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

{#if dialog}
  <Dialog title="Новый объект" confirm="Создать и открыть" {busy} onsubmit={create} onclose={() => (dialog = null)}>
    <label><span class="label">Название (расширение подберёт формат)</span><input class="field" placeholder="report.rec" bind:value={dialog.name} /></label>
    <label>
      <span class="label">Формат</span>
      <select class="field" bind:value={dialog.format}>
        <option value="">по расширению</option>
        <FormatOptions {formats} />
      </select>
    </label>
    <label><span class="label">Слаг (пусто: по названию)<Hint text="Короткое имя объекта латиницей, уникальное во всём мире: по нему на объект ссылаются из других мест. Обычно хватает названия: слаг подставится сам." /></span><input class="field mono" bind:value={dialog.slug} /></label>
    <label>
      <span class="label">Сразу положить</span>
      <select class="field" bind:value={dialog.volume}>
        <option value="">никуда (положить позже в «Где лежит»)</option>
        {#each volumes as found}<option value={found.id}>в корень тома «{found.name || found.slug}»</option>{/each}
      </select>
    </label>
  </Dialog>
{/if}

<style>
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 12px 24px; padding: 28px 32px 12px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  .head p { margin: 4px 0 0; max-width: 640px; }
  .tools { display: flex; flex-wrap: wrap; gap: 8px; }
  .tools .field { width: auto; }
  .search { width: 220px !important; }
  .path { width: 170px !important; }
  .sort { padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
  .sort:hover { color: var(--text); }
  .where { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 0 32px 12px; }
  .pick { padding: 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--muted); cursor: pointer; }
  .pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .count { margin-left: auto; }
  .table { padding: 0 32px 32px; }
  .pad { padding: 12px 10px; }
  .row {
    display: grid; grid-template-columns: minmax(260px, 1fr) 90px minmax(220px, 1fr) 150px 80px 190px; align-items: center; gap: 12px;
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
