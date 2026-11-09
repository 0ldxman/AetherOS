<script lang="ts">
  // Сцены карты: список слева, редактор справа. Сцена это сохранённая карта: дата мира, камера и пометки поверх неё.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
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

<div class="screen">
  <aside class="list">
    <h2>Сцены</h2>
    <input class="field" placeholder="Найти…" bind:value={query} />
    <div class="items">
      {#each rows as row (row.id)}
        <a class="item" class:on={row.id === id} href="#/map/scenes/{row.id}">
          <b>{row.title}</b>
          <span class="muted small">{row.slug} · {row.features} пометок{row.base_date ? ` · ${showDate(row.base_date)}` : ""}{row.keys ? " · по ключам" : ""}</span>
        </a>
      {:else}
        <p class="muted small pad">Сцен нет.</p>
      {/each}
    </div>
    <div class="foot">
      <button class="btn" onclick={openNew}>+ Сцена</button>
      <div class="two">
        <button class="btn ghost" onclick={() => upload.click()}>Загрузить…</button>
        <button class="btn ghost" onclick={() => exportAll(id ? String(id) : "")} disabled={!rows.length}>{id ? "Выгрузить эту" : "Выгрузить все"}</button>
      </div>
      <input bind:this={upload} type="file" accept="application/json,.json" hidden onchange={importFile} />
    </div>
  </aside>

  <section class="work">
    {#if id}
      {#key id}<SceneEditor {id} onsaved={list} oncopy={copy} onremove={remove} />{/key}
    {:else}
      <div class="empty">
        <p><b>Сохранённые карты</b></p>
        <p class="muted">Сцена это карта на дату с пометками: метками, линиями, областями, текстом и выделенными странами. Их показывают игроку в окне карты и в статьях вики через ::map.</p>
        <p class="muted">Выберите сцену слева или создайте новую.</p>
      </div>
    {/if}
  </section>
</div>

{#if dialog}
  <Dialog title="Новая сцена" confirm="Создать" onsubmit={create} onclose={() => (dialog = false)} disabled={!draft.title.trim() || !draft.slug.trim()}>
    <label><span class="label">Название</span><input class="field" bind:value={draft.title} /></label>
    <label><span class="label">Слаг</span><input class="field mono" class:bad={errors.slug} bind:value={draft.slug} oninput={() => (slugTouched = true)} />
      {#if errors.slug}<span class="err">{errors.slug.join(" ")}</span>{/if}</label>
    {#if errors.title}<span class="err">{errors.title.join(" ")}</span>{/if}
  </Dialog>
{/if}

<style>
  .screen { display: grid; grid-template-columns: 260px 1fr; height: 100%; min-height: 0; }
  .list { display: flex; flex-direction: column; gap: 8px; padding: 14px 10px; border-right: 1px solid var(--line-soft); min-height: 0; }
  h2 { margin: 0 6px 4px; font-size: 16px; }
  .items { flex: 1; overflow: auto; display: flex; flex-direction: column; gap: 2px; }
  .item { display: flex; flex-direction: column; padding: 7px 10px; border-radius: var(--radius-s); color: var(--text); }
  .item:hover { background: var(--panel); text-decoration: none; }
  .item.on { background: var(--accent-soft); }
  .foot { display: flex; flex-direction: column; gap: 6px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .work { min-width: 0; min-height: 0; }
  .empty { max-width: 520px; padding: 40px; }
  .pad { padding: 8px; }
  .err { color: var(--danger); font-size: 12px; }
  .bad { border-color: var(--danger); }
  .mono { font-family: var(--mono); }
</style>
