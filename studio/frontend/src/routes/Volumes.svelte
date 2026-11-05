<script lang="ts">
  import PageHead from "../lib/PageHead.svelte";
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
  let form = $state({ name: "", slug: "", label: "", uuid: "", template: null as number | null, machine: null as number | null, mount_path: "/", capacity_gb: null as number | null, used_gb: null as number | null });
  let slugTouched = false;
  let errors = $state<Record<string, string[]>>({});

  // слаг подсказывается из названия, пока его не правили руками
  function suggest() {
    if (!slugTouched) form.slug = form.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  async function openCreate() {
    form = { name: "", slug: "", label: "", uuid: "", template: null, machine: null, mount_path: "/", capacity_gb: null, used_gb: null };
    slugTouched = false;
    errors = {};
    creating = true;
    const [t, m] = await Promise.all([api.GET("/studio/api/templates"), api.GET("/studio/api/machines")]);
    templates = t.data ?? [];
    machines = m.data ?? [];
  }

  const gb = (value: string) => (value === "" ? null : Math.max(0, Math.round(+value)));

  // занято условно: от 20 до 70 % ёмкости
  function randomUsed() {
    if (form.capacity_gb) form.used_gb = Math.round((form.capacity_gb * (20 + Math.random() * 50)) / 100);
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

<PageHead title="Тома">
  {#snippet sub()}Диски мира: что на них лежит и куда они смонтированы.{/snippet}
    <input class="field search" placeholder="Поиск по названию, слагу, машине" bind:value={query} />
    <button class="btn primary" onclick={openCreate}>+ Новый том</button>
</PageHead>

<section class="grid">
  {#if loading}
    <p class="muted pad">Загрузка…</p>
  {:else if !shown.length}
    <p class="muted pad">{rows.length ? "Ничего не нашлось." : "Томов пока нет. Том — это диск мира: на нём лежат файлы."}</p>
    {#if !rows.length}<button class="btn primary add-first" onclick={openCreate}>+ Новый том</button>{/if}
  {:else}
    {#each shown as row (row.id)}
      <a class="card" href="#/volumes/{row.id}">
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
      </a>
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
    <div class="two">
      <label><span class="label">Ёмкость, ГБ (декор)</span><input class="field" type="number" min="0" value={form.capacity_gb ?? ""} oninput={(e) => (form.capacity_gb = gb(e.currentTarget.value))} /></label>
      <label><span class="label">Занято, ГБ</span>
        <span class="inline"><input class="field" type="number" min="0" value={form.used_gb ?? ""} oninput={(e) => (form.used_gb = gb(e.currentTarget.value))} />
          <button type="button" class="btn ghost" disabled={!form.capacity_gb} onclick={randomUsed}>Случайно</button></span>
      </label>
    </div>
    {#if errors.used_gb}<p class="err">{errors.used_gb.join(" ")}</p>{/if}
    <label><span class="label">UUID (пусто: сгенерируется)</span><input class="field mono" bind:value={form.uuid} class:bad={errors.uuid} /></label>
    {#if errors.uuid}<p class="err">{errors.uuid.join(" ")}</p>{/if}
  </Dialog>
{/if}

<style>
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .inline { display: flex; gap: 6px; }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .field.bad { border-color: var(--danger); }
  .search { width: 300px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; padding: 0 32px 32px; }
  .pad { padding: 8px 0; }
  .card {
    display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; text-align: left;
    border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); cursor: pointer;
    transition: border-color 0.12s, transform 0.12s, background 0.12s;
  }
  .card:hover { border-color: #39404d; background: var(--panel-2); transform: translateY(-1px); }
  a.card { color: inherit; text-decoration: none; }
  .title { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; min-width: 0; }
  .name { font-weight: 600; font-size: 15px; overflow-wrap: anywhere; }
  .slug { color: var(--faint); }
  .stats { display: flex; gap: 14px; color: var(--muted); }
  .stats b { color: var(--text); font-weight: 600; }
  .mounts { display: flex; flex-wrap: wrap; gap: 6px; }
  .mount { padding: 1px 7px; border-radius: 4px; background: var(--bg); color: var(--muted); font-size: 11.5px; }
  .faint { color: var(--faint); font-size: 12px; }
  .add-first { margin: 0 12px 12px; }
</style>
