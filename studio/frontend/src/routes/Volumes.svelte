<script lang="ts">
  import { onMount } from "svelte";
  import { adminUrl, api, type Schemas } from "../lib/api";
  import { go } from "../lib/router.svelte";

  let rows = $state<Schemas["VolumeRow"][]>([]);
  let loading = $state(true);
  let query = $state("");

  const shown = $derived(
    rows.filter((row) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      return [row.slug, row.name, row.label, ...row.mounts.map((m) => m.machine)].some((text) => text.toLowerCase().includes(q));
    }),
  );

  onMount(async () => {
    const { data } = await api.GET("/studio/api/volumes");
    rows = data ?? [];
    loading = false;
  });
</script>

<header class="head">
  <div>
    <h1>Тома</h1>
    <p class="muted">Диски мира: что на них лежит и куда они смонтированы.</p>
  </div>
  <div class="tools">
    <input class="field search" placeholder="Поиск по названию, слагу, машине" bind:value={query} />
    <a class="btn" href={adminUrl("filesystem/volume/add/")}>Новый том</a>
  </div>
</header>

<section class="grid">
  {#if loading}
    <p class="muted pad">Загрузка…</p>
  {:else if !shown.length}
    <p class="muted pad">{rows.length ? "Ничего не нашлось." : "Томов пока нет."}</p>
  {:else}
    {#each shown as row (row.id)}
      <button class="card" onclick={() => go(`/volumes/${row.id}`)}>
        <div class="title">
          <span class="name">{row.name || row.slug}</span>
          {#if row.label}<span class="chip">{row.label}</span>{/if}
        </div>
        <div class="slug mono">{row.slug}</div>
        <div class="stats">
          <span><b>{row.files}</b> файлов</span>
          <span><b>{row.folders}</b> папок</span>
        </div>
        <div class="mounts">
          {#each row.mounts as mount}
            <span class="mount mono">{mount.machine}:{mount.path || "—"}</span>
          {:else}
            <span class="faint">не смонтирован</span>
          {/each}
        </div>
      </button>
    {/each}
  {/if}
</section>

<style>
  .head { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; padding: 28px 32px 18px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  .head p { margin: 4px 0 0; }
  .tools { display: flex; gap: 8px; }
  .search { width: 300px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; padding: 0 32px 32px; }
  .pad { padding: 8px 0; }
  .card {
    display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; text-align: left;
    border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); cursor: pointer;
    transition: border-color 0.12s, transform 0.12s, background 0.12s;
  }
  .card:hover { border-color: #39404d; background: var(--panel-2); transform: translateY(-1px); }
  .title { display: flex; align-items: center; gap: 8px; }
  .name { font-weight: 600; font-size: 15px; }
  .slug { color: var(--faint); }
  .stats { display: flex; gap: 14px; color: var(--muted); }
  .stats b { color: var(--text); font-weight: 600; }
  .mounts { display: flex; flex-wrap: wrap; gap: 6px; }
  .mount { padding: 1px 7px; border-radius: 4px; background: var(--bg); color: var(--muted); font-size: 11.5px; }
  .faint { color: var(--faint); font-size: 12px; }
</style>
