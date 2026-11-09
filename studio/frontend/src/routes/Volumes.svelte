<script lang="ts">
  import PageHead from "../lib/PageHead.svelte";
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Hint from "../lib/Hint.svelte";
  import { go } from "../lib/router.svelte";
  import { slugify } from "../lib/slug";
  import { toast } from "../lib/toast.svelte";

  type Row = Schemas["VolumeRow"];
  type Filter = "all" | "plain" | "system" | "unmounted";

  let rows = $state<Row[]>([]);
  let loading = $state(true);
  let failed = $state(false);
  let query = $state("");
  let filter = $state<Filter>("all");
  let sort = $state<"slug" | "name" | "files">("slug");

  let creating = $state(false);
  let templates = $state<Schemas["Template"][]>([]);
  let machines = $state<Schemas["MachineRow"][]>([]);
  let form = $state(blank());
  let slugTouched = false;
  let errors = $state<Record<string, string[]>>({});

  function blank() {
    return { name: "", slug: "", label: "", uuid: "", template: null as number | null, machine: null as number | null, mount_path: "/", capacity_gb: null as number | null, used_gb: null as number | null };
  }

  // слаг подсказывается из названия (русское читается транслитом), пока его не правили руками
  function suggest() {
    if (!slugTouched) form.slug = slugify(form.name);
  }

  async function openCreate() {
    form = blank();
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

  const lost = (row: Row) => !row.mounts.length;          // том, который нигде не смонтирован, игроку не виден: это ошибка
  const counts = $derived({
    all: rows.length,
    plain: rows.filter((r) => !r.system).length,
    system: rows.filter((r) => r.system).length,
    unmounted: rows.filter(lost).length,
  });
  const FILTERS: { key: Filter; label: string; hint: string }[] = [
    { key: "all", label: "Все", hint: "" },
    { key: "plain", label: "Тома", hint: "Обычные диски мира." },
    { key: "system", label: "Системные", hint: "Тома отличий машин: каждая машина хранит в своём все свои правки общих дисков." },
    { key: "unmounted", label: "Не смонтированные", hint: "Том, который нигде не смонтирован, игрок не увидит: скорее всего, это ошибка." },
  ];

  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase();
    const found = rows.filter((row) => {
      if (filter === "plain" && row.system) return false;
      if (filter === "system" && !row.system) return false;
      if (filter === "unmounted" && !lost(row)) return false;
      if (!q) return true;
      return [row.slug, row.name, row.label, ...row.mounts.map((m) => m.machine)].some((text) => text.toLowerCase().includes(q));
    });
    const by = {
      slug: (a: Row, b: Row) => a.slug.localeCompare(b.slug),
      name: (a: Row, b: Row) => (a.name || a.slug).localeCompare(b.name || b.slug, "ru"),
      files: (a: Row, b: Row) => b.files - a.files || a.slug.localeCompare(b.slug),
    }[sort];
    return [...found].sort(by);
  });

  async function load() {
    loading = true;
    failed = false;
    const { data, error } = await api.GET("/studio/api/volumes");
    if (error || !data) failed = true;
    else rows = data;
    loading = false;
  }
  onMount(load);
</script>

<PageHead title="Тома">
  {#snippet sub()}Диски мира: что на них лежит и куда они смонтированы.{/snippet}
  <input class="field search" placeholder="Поиск по названию, слагу, машине" bind:value={query} aria-label="Поиск" />
  <button class="btn primary" onclick={openCreate}>+ Новый том</button>
</PageHead>

{#if rows.length}
  <div class="bar">
    <div class="filters" role="group" aria-label="Фильтр">
      {#each FILTERS as item (item.key)}
        <button class="pill" class:on={filter === item.key} class:warn={item.key === "unmounted" && counts.unmounted > 0} aria-pressed={filter === item.key}
                title={item.hint} onclick={() => (filter = item.key)}>{item.label} <span class="n">{counts[item.key]}</span></button>
      {/each}
    </div>
    <label class="sort"><span class="muted">Порядок</span>
      <select class="field" bind:value={sort}>
        <option value="slug">по слагу</option>
        <option value="name">по названию</option>
        <option value="files">больше файлов</option>
      </select></label>
  </div>
{/if}

<section class="grid">
  {#if loading}
    <p class="muted pad">Загрузка…</p>
  {:else if failed}
    <p class="muted pad">Тома не загрузились. <button class="btn" onclick={load}>Повторить</button></p>
  {:else if !shown.length}
    <p class="muted pad">{rows.length ? "Ничего не нашлось." : "Томов пока нет. Том — это диск мира: на нём лежат файлы и папки, а машины монтируют его в свою файловую систему."}</p>
    {#if !rows.length}<button class="btn primary add-first" onclick={openCreate}>+ Новый том</button>{/if}
  {:else}
    {#each shown as row (row.id)}
      <a class="card" class:lost={lost(row)} href="#/volumes/{row.id}">
        <div class="title">
          <span class="name">{row.name || row.slug}</span>
          {#if row.system}<span class="chip sys" title="Том отличий машины {row.overlay_of}: все её правки общих дисков лежат здесь.">Системный · {row.overlay_of}</span>{/if}
          {#if row.label}<span class="chip lab" title={row.label}>{row.label}</span>{/if}
        </div>
        {#if row.name && row.name !== row.slug}<div class="slug mono">{row.slug}</div>{/if}
        <div class="stats">
          <span><b>{row.files}</b> файлов</span>
          <span><b>{row.folders}</b> папок</span>
        </div>
        <div class="mounts">
          {#each row.mounts as mount}
            <span class="mount mono">{mount.machine}:{mount.path || "—"}</span>
          {:else}
            <span class="alert" title="Том нигде не смонтирован, игрок его не увидит. Смонтируйте его на машину.">⚠ не смонтирован</span>
          {/each}
        </div>
      </a>
    {/each}
  {/if}
</section>

{#if creating}
  <Dialog title="Новый том" confirm="Создать" onsubmit={create} onclose={() => (creating = false)} disabled={!form.slug.trim()}>
    <label><span class="label">Название диска (как в игре)</span>
      <input class="field" bind:value={form.name} oninput={suggest} placeholder="Harbor" />
    </label>
    <label><span class="label">Слаг (латиницей, уникальный)<Hint text="Идентификатор для Студии и импорта, в игре не виден. Подставляется из названия." /></span>
      <input class="field mono" bind:value={form.slug} oninput={() => (slugTouched = true)} class:bad={errors.slug} placeholder="harbor" />
    </label>
    {#if errors.slug}<p class="err">{errors.slug.join(" ")}</p>{/if}
    <label><span class="label">Структура</span>
      <select class="field" bind:value={form.template}>
        <option value={null}>пустой том</option>
        {#each templates as item}<option value={item.id}>{item.name} ({item.folders.length} папок)</option>{/each}
      </select>
    </label>
    <label><span class="label">Смонтировать на машину<Hint text="Том, который нигде не смонтирован, игрок не увидит. Монтировать можно и позже." /></span>
      <select class="field" bind:value={form.machine}>
        <option value={null}>не монтировать (потом)</option>
        {#each machines as item}<option value={item.id}>{item.hostname || item.name}</option>{/each}
      </select>
    </label>
    {#if form.machine}
      <label><span class="label">Точка монтирования</span>
        <input class="field mono" bind:value={form.mount_path} class:bad={errors.mount_path} placeholder="/" />
      </label>
      {#if errors.mount_path}<p class="err">{errors.mount_path.join(" ")}</p>{/if}
    {/if}

    <details class="more">
      <summary>Дополнительно</summary>
      <label><span class="label">Метка для Студии (игрок не видит)</span><input class="field" bind:value={form.label} /></label>
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
    </details>
  </Dialog>
{/if}

<style>
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .inline { display: flex; gap: 6px; }
  .more { display: flex; flex-direction: column; gap: 10px; }
  .more summary { cursor: pointer; color: var(--muted); margin-bottom: 8px; }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .field.bad { border-color: var(--danger); }
  .search { width: 300px; max-width: 100%; }
  .bar { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 16px; padding: 0 32px 12px; }
  .filters { display: flex; flex-wrap: wrap; gap: 6px; }
  .pill { height: 28px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-2); cursor: pointer; }
  .pill:hover { background: var(--raise); }
  .pill.on { background: var(--accent-soft); border-color: var(--accent); }
  .pill.warn:not(.on) { border-color: rgba(242, 198, 109, 0.5); color: var(--warn); }
  .n { color: var(--muted); margin-left: 4px; }
  .sort { display: flex; align-items: center; gap: 8px; }
  .sort .field { width: auto; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; padding: 0 32px 32px; }
  .pad { padding: 8px 0; }
  .card {
    display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; text-align: left; min-width: 0;
    border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); cursor: pointer;
    transition: border-color 0.12s, transform 0.12s, background 0.12s;
  }
  .card:hover { border-color: #39404d; background: var(--panel-2); transform: translateY(-1px); }
  .card:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .card.lost { border-color: rgba(242, 198, 109, 0.4); }
  a.card { color: inherit; text-decoration: none; }
  .title { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; min-width: 0; }
  .name { font-weight: 600; font-size: 15px; overflow-wrap: anywhere; }
  .chip.sys { background: var(--accent-soft); color: var(--accent); }
  .chip.lab { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
  .slug { color: var(--faint); }
  .stats { display: flex; gap: 14px; color: var(--muted); }
  .stats b { color: var(--text); font-weight: 600; }
  .mounts { display: flex; flex-wrap: wrap; gap: 6px; }
  .mount { padding: 1px 7px; border-radius: 4px; background: var(--bg); color: var(--muted); font-size: 11.5px; overflow-wrap: anywhere; }
  .alert { color: var(--warn); font-size: 12px; }
  .add-first { margin: 0 12px 12px; }
</style>
