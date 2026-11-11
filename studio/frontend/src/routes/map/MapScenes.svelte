<script lang="ts">
  // Сцены карты: список слева, редактор справа. Сцена это сохранённая карта: дата мира, камера и пометки поверх неё.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import Icon from "../../lib/Icon.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { go } from "../../lib/router.svelte";
  import { slugify } from "../../lib/sceneGeo";
  import { toast } from "../../lib/toast.svelte";
  import { fieldErrors, showDate } from "./shared";
  import SceneEditor from "./SceneEditor.svelte";

  let { id }: { id: number | null } = $props();

  let rows = $state<Schemas["MapSceneRow"][]>([]);
  let query = $state("");
  let dialog = $state(false);
  let draft = $state({ title: "", slug: "" });
  let slugTouched = false;
  let errors = $state<Record<string, string[]>>({});
  let upload: HTMLInputElement;
  let open = $state(false);

  async function list() {
    rows = (await api.GET("/studio/api/map/scenes", { params: { query: { q: query } } })).data ?? [];
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { query; clearTimeout(timer); timer = setTimeout(list, 200); });
  onMount(list);

  function openNew() {
    draft = { title: "", slug: "" };
    slugTouched = false;
    errors = {};
    dialog = true;
  }
  $effect(() => { if (!slugTouched) draft.slug = slugify(draft.title); });

  async function create() {
    errors = {};
    const { data, error } = await api.POST("/studio/api/map/scenes", { body: { ...draft, mode: "political", lat: 20, lon: 10, zoom: 3, flat: false, features: [], keys: "" } });
    if (error || !data) { errors = fieldErrors(error); return toast(problem(error, "Не создалась."), "error"); }
    dialog = false;
    await list();
    go(`/map/scenes/${data.id}`);
  }

  async function copy(sceneId: number) {
    const { data, error } = await api.POST("/studio/api/map/scenes/{scene_id}/copy", { params: { path: { scene_id: sceneId } } });
    if (error || !data) return toast(problem(error), "error");
    toast("Копия создана.");
    await list();
    go(`/map/scenes/${data.id}`);
  }

  async function remove() {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    if (!(await ask(`Удалить сцену «${row.title}»?`, `Пометок: ${row.features}. Ссылки на сцену (::map scene=${row.slug}) перестанут работать. Выгрузите её, если нужна копия.`))) return;
    const { error } = await api.DELETE("/studio/api/map/scenes/{scene_id}", { params: { path: { scene_id: row.id } } });
    if (error) return toast(problem(error), "error");
    toast("Сцена удалена.");
    await list();
    go("/map/scenes");
  }

  async function exportAll(ids = "") {
    const { data } = await api.GET("/studio/api/map/scenes/export", { params: { query: { ids } } });
    if (!data) return;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([JSON.stringify(data.items, null, 1)], { type: "application/json" }));
    link.download = ids ? `scene-${rows.find((r) => String(r.id) === ids)?.slug ?? ids}.json` : "map-scenes.json";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  async function importFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;
    let items: unknown;
    try { items = JSON.parse(await file.text()); } catch { return toast("Файл не читается как JSON.", "error"); }
    if (!Array.isArray(items)) return toast("В файле должен быть список сцен.", "error");
    const { data, error } = await api.POST("/studio/api/map/scenes/import", { body: { items: items as never } });
    if (error || !data) return toast(problem(error, "Загрузка не удалась."), "error");
    toast(`Загружено: создано ${data.created}, обновлено ${data.updated}.`);
    list();
  }
</script>

{#snippet switcher()}
  <div class="switch">
    <button class="pick" onclick={(e) => { e.stopPropagation(); open = !open; }} aria-haspopup="listbox" aria-expanded={open} title="Другая сцена">
      <Icon name="scenes" size={16} /><span>Сцены</span><Icon name="chevron" size={14} />
    </button>
    {#if open}
      <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
      <div class="pop panel" onclick={(e) => e.stopPropagation()}>
        <label class="find"><Icon name="search" size={14} /><input placeholder="Найти сцену" bind:value={query} aria-label="Поиск сцены" /></label>
        <ul class="plist" role="listbox">
          {#each rows as row (row.id)}
            <li><a class="prow" class:on={row.id === id} href="#/map/scenes/{row.id}" onclick={() => (open = false)}>
              <b>{row.title}</b><span class="muted small">{row.slug} · {row.features} пометок{row.keys ? " · по ключам" : ""}</span></a></li>
          {:else}
            <li class="muted small pad">Сцен нет.</li>
          {/each}
        </ul>
        <div class="pfoot">
          <button class="btn" onclick={() => { open = false; openNew(); }}><Icon name="plus" size={14} />Сцена</button>
          <button class="btn ghost" onclick={() => { open = false; go("/map/scenes"); }}>Все сцены</button>
        </div>
      </div>
    {/if}
  </div>
{/snippet}

<svelte:window onclick={() => (open = false)} />

{#if id}
  {#key id}<SceneEditor {id} {switcher} onsaved={list} oncopy={copy} onremove={remove} />{/key}
{:else}
  <div class="cards-page">
    <header class="chead">
      <h2>Сцены</h2>
      <label class="find"><Icon name="search" size={14} /><input placeholder="Найти сцену" bind:value={query} aria-label="Поиск сцены" /></label>
      <span class="grow"></span>
      <button class="btn ghost" onclick={() => upload.click()}><Icon name="upload" size={14} />Загрузить…</button>
      <button class="btn ghost" onclick={() => exportAll()} disabled={!rows.length}><Icon name="download" size={14} />Выгрузить все</button>
      <button class="btn primary" onclick={openNew}><Icon name="plus" size={14} />Сцена</button>
    </header>
    <p class="muted intro">Сцена это карта на дату с пометками: метками, линиями, областями, текстом и выделенными странами. Игрок видит её в окне карты и в статьях вики через <code>::map</code>.</p>
    <div class="grid">
      {#each rows as row (row.id)}
        <a class="card" href="#/map/scenes/{row.id}">
          <b class="ct">{row.title}</b>
          <code class="muted">{row.slug}</code>
          <span class="tags">
            <span class="tag"><Icon name="calendar" size={12} />{row.base_date ? showDate(row.base_date) : "последние границы"}</span>
            <span class="tag"><Icon name="pin" size={12} />{row.features}</span>
            <span class="tag">{row.mode === "physical" ? "Физическая" : "Политическая"}</span>
            {#if row.keys}<span class="tag key"><Icon name="lock" size={12} />по ключам</span>{/if}
          </span>
        </a>
      {:else}
        <p class="muted pad">{query.trim() ? "Ничего не нашлось." : "Сцен пока нет. Создайте первую кнопкой «Сцена»."}</p>
      {/each}
    </div>
  </div>
{/if}
<input bind:this={upload} type="file" accept="application/json,.json" hidden onchange={importFile} />

{#if dialog}
  <Dialog title="Новая сцена" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)} disabled={!draft.title.trim() || !draft.slug.trim()}>
    <label><span class="label">Название</span><input class="field" bind:value={draft.title} /></label>
    <label><span class="label">Слаг</span><input class="field mono" class:bad={errors.slug} bind:value={draft.slug} oninput={() => (slugTouched = true)} />
      {#if errors.slug}<span class="err">{errors.slug.join(" ")}</span>{/if}</label>
    {#if errors.title}<span class="err">{errors.title.join(" ")}</span>{/if}
  </Dialog>
{/if}

<style>
  .cards-page { padding: 18px 24px; display: flex; flex-direction: column; gap: 12px; overflow: auto; height: 100%; }
  .chead { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  h2 { margin: 0 8px 0 0; font-size: 18px; }
  .grow { flex: 1; }
  .intro { margin: 0; max-width: 720px; }
  .find { display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .chead .find { width: 260px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
  .card { display: flex; flex-direction: column; gap: 6px; padding: 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); color: var(--text); }
  .card:hover { border-color: var(--accent); text-decoration: none; background: var(--panel-2); }
  .ct { font-size: 15px; }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .tag { display: inline-flex; align-items: center; gap: 5px; padding: 1px 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 12px; }
  .tag.key { color: var(--warn); }
  .pad { padding: 8px; }
  .small { font-size: 12px; }
  .err { color: var(--danger); font-size: 12px; }
  .bad { border-color: var(--danger); }
  .mono { font-family: var(--mono); }
  code { font-family: var(--mono); font-size: 12px; }

  .switch { position: relative; flex: none; }
  .pick { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); color: var(--text); font: inherit; font-size: 13px; cursor: pointer; }
  .pick:hover { border-color: var(--line); background: var(--raise); }
  .pop { position: absolute; z-index: 20; left: 0; top: 36px; width: 300px; display: flex; flex-direction: column; gap: 8px; padding: 10px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45); }
  .plist { list-style: none; margin: 0; padding: 0; max-height: 280px; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .prow { display: flex; flex-direction: column; padding: 6px 10px; color: var(--text); }
  .prow:hover { background: var(--panel-2); text-decoration: none; }
  .prow.on { background: var(--accent-soft); }
  .pfoot { display: flex; gap: 6px; justify-content: space-between; }
</style>
