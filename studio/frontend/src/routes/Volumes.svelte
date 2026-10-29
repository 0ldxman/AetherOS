<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  let rows = $state<Schemas["VolumeRow"][]>([]);
  let loading = $state(true);
  let query = $state("");

  let creating = $state(false);
  let templates = $state<Schemas["Template"][]>([]);
  let machines = $state<Schemas["MachineRow"][]>([]);
  let form = $state({ name: "", slug: "", label: "", uuid: "", template: null as number | null, machine: null as number | null, mount_path: "/" });
  let slugTouched = false;
  let errors = $state<Record<string, string[]>>({});

  // слаг подсказывается из названия, пока его не правили руками
  function suggest() {
    if (!slugTouched) form.slug = form.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  async function openCreate() {
    form = { name: "", slug: "", label: "", uuid: "", template: null, machine: null, mount_path: "/" };
    slugTouched = false;
    errors = {};
    creating = true;
    const [t, m] = await Promise.all([api.GET("/studio/api/templates"), api.GET("/studio/api/machines")]);
    templates = t.data ?? [];
    machines = m.data ?? [];
  }

  async function create() {
    errors = {};
    const { data, error } = await api.POST("/studio/api/volumes", { body: { ...form, mount_path: form.machine ? form.mount_path : "" } });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Том не создался."), "error");
    }
    creating = false;
    go(`/volumes/${data.id}`);
  }

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
    <button class="btn primary" onclick={openCreate}>+ Новый том</button>
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

{#if creating}
  <Dialog title="Новый том" confirm="Создать" onsubmit={create} onclose={() => (creating = false)}>
    <label><span class="label">Название диска (как в игре)</span>
      <input class="field" bind:value={form.name} oninput={suggest} placeholder="Harbor" />
    </label>
    <label><span class="label">Слаг (латиницей, уникальный)</span>
      <input class="field mono" bind:value={form.slug} oninput={() => (slugTouched = true)} class:bad={errors.slug} placeholder="harbor" />
    </label>
    {#if errors.slug}<p class="err">{errors.slug.join(" ")}</p>{/if}
    <label><span class="label">Метка для студии (игрок не видит)</span><input class="field" bind:value={form.label} /></label>
    <label><span class="label">Структура</span>
      <select class="field" bind:value={form.template}>
        <option value={null}>пустой том</option>
        {#each templates as item}<option value={item.id}>{item.name} ({item.folders.length} папок)</option>{/each}
      </select>
    </label>
    <label><span class="label">Смонтировать на машину</span>
      <select class="field" bind:value={form.machine}>
        <option value={null}>не монтировать</option>
        {#each machines as item}<option value={item.id}>{item.hostname || item.name}</option>{/each}
      </select>
    </label>
    {#if form.machine}
      <label><span class="label">Точка монтирования</span>
        <input class="field mono" bind:value={form.mount_path} class:bad={errors.mount_path} placeholder="/" />
      </label>
      {#if errors.mount_path}<p class="err">{errors.mount_path.join(" ")}</p>{/if}
    {/if}
    <label><span class="label">UUID (пусто: сгенерируется)</span><input class="field mono" bind:value={form.uuid} class:bad={errors.uuid} /></label>
    {#if errors.uuid}<p class="err">{errors.uuid.join(" ")}</p>{/if}
  </Dialog>
{/if}

<style>
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .field.bad { border-color: var(--danger); }
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
