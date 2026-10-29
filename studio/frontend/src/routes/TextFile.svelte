<script lang="ts">
  // Файл со своим текстом (без объекта): декорация и фон. Текст, защита этого места и то, что получит игрок.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  let { volume, id }: { volume: number; id: number } = $props();

  let file = $state<Schemas["TextFile"] | null>(null);
  let form = $state({ content: "", access: "", state: "" });
  let saved = $state("");
  let preview = $state<Schemas["TextPreview"] | null>(null);
  let formats = $state<Schemas["Format"][]>([]);
  let errors = $state<Record<string, string[]>>({});
  let converting = $state(false);

  const path = $derived({ volume_id: volume, placement_id: id });
  const dirty = $derived(JSON.stringify(form) !== saved);
  const markup = $derived(formats.find((found) => found.name === file?.format)?.markup ?? false);

  function fill(data: Schemas["TextFile"]) {
    file = data;
    form = { content: data.content, access: data.access, state: data.state };
    saved = JSON.stringify(form);
  }

  onMount(async () => {
    formats = (await api.GET("/studio/api/formats")).data ?? [];
    const { data } = await api.GET("/studio/api/volumes/{volume_id}/text-files/{placement_id}", { params: { path } });
    if (data) fill(data);
    else toast("Файл не найден.", "error");
  });

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const body = { ...form };
    clearTimeout(timer);
    timer = setTimeout(async () => {
      preview = (await api.POST("/studio/api/volumes/{volume_id}/text-files/{placement_id}/preview", { params: { path }, body })).data ?? null;
    }, 300);
  });

  async function save() {
    errors = {};
    const { data, error } = await api.PUT("/studio/api/volumes/{volume_id}/text-files/{placement_id}", { params: { path }, body: form });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    fill(data);
    toast("Сохранено.");
  }

  async function toItem() {
    if (dirty) await save();
    const { data, error } = await api.POST("/studio/api/volumes/{volume_id}/text-files/{placement_id}/to-item", { params: { path } });
    converting = false;
    if (error || !data) return toast(problem(error), "error");
    toast("Теперь это объект.");
    go(`/items/${data.item}`);
  }
</script>

<svelte:window onkeydown={(event) => { if ((event.ctrlKey || event.metaKey) && event.key === "s") { event.preventDefault(); save(); } }} />

{#if file}
  <div class="page">
    <header class="head">
      <button class="btn ghost" onclick={() => go(`/volumes/${volume}${file?.parent ? `/${file.parent}` : ""}`)}>←</button>
      <h1 class="mono">{file.name}</h1>
      <span class="chip">{file.format || "без формата"}</span>
      <span class="chip own">свой текст</span>
      <span class="muted mono path">{file.volume_name}:/{file.path}</span>
      <span class="spacer"></span>
      <span class="muted small">{dirty ? "Не сохранено" : "Сохранено"}</span>
      <button class="btn ghost" onclick={() => (converting = true)}>Сделать объектом</button>
      <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
    </header>

    <div class="cols">
      <section class="pane">
        <h2>Текст</h2>
        <div class="editor"><CodeEditor bind:value={form.content} {markup} onsave={save} /></div>
      </section>

      <div class="side">
        <section class="card">
          <h2>Защита этого файла</h2>
          <label><span class="label">Условие доступа (пусто: открыто)</span>
            <input class="field mono" bind:value={form.access} class:bad={preview?.access_error || errors.access} placeholder="открыто всем" /></label>
          {#if preview?.access_error}<p class="err">{preview.access_error}</p>{/if}
          {#if preview?.unknown_keys.length}<p class="err">Нет в реестре: {preview.unknown_keys.join(", ")}</p>{/if}
          <span class="label">Слои защиты</span>
          <div class="layers"><CodeEditor bind:value={form.state} onsave={save} /></div>
          {#if preview?.problems.length}
            <ul class="problems">{#each preview.problems as bad}<li><span class="mono">стр. {bad.line}</span> {bad.message}</li>{/each}</ul>
          {/if}
        </section>

        <section class="card">
          <h2>Что получит игрок</h2>
          {#snippet dump(title: string, data: Schemas["Dump"] | null | undefined)}
            <h3>{title}</h3>
            {#if data}
              <p class="muted small">{data.size} байт · формат {data.format ?? "—"} · читаемых {data.printable}%</p>
              <div class="hex">{#each data.rows.slice(0, 8) as row}<div class="hrow"><span class="off">{row.offset}</span><span>{row.hex}</span><span class="asc">{row.ascii}</span></div>{/each}</div>
            {/if}
          {/snippet}
          {@render dump("Без слоёв", preview?.plain)}
          {#if preview?.layered}{@render dump("Со слоями", preview.layered)}{/if}
        </section>
      </div>
    </div>
  </div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

{#if converting}
  <Dialog title="Сделать объектом?" confirm="Сделать" onsubmit={toItem} onclose={() => (converting = false)}>
    <p class="muted">Текст, условие и слои переедут в новый объект, а это место будет на него ссылаться. Тогда файл можно класть в
      другие тома и архивы, у него появятся история, вложенные ключи и подписи.</p>
  </Dialog>
{/if}

<style>
  .page { display: flex; flex-direction: column; height: 100%; }
  .pad { padding: 24px; }
  .head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--line-soft); }
  h1 { margin: 0; font-size: 17px; }
  .chip.own { background: var(--accent-soft); color: var(--accent); }
  .path { font-size: 12px; }
  .spacer { flex: 1; }
  .small { font-size: 12px; margin: 0; }
  .cols { flex: 1; min-height: 0; display: grid; grid-template-columns: 1.2fr 1fr; gap: 14px; padding: 14px 16px 16px; }
  .pane { display: flex; flex-direction: column; min-height: 0; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); overflow: hidden; }
  .pane h2 { padding: 10px 14px 0; }
  .editor { flex: 1; min-height: 0; }
  .side { display: flex; flex-direction: column; gap: 14px; min-height: 0; overflow: auto; }
  .card { display: flex; flex-direction: column; gap: 8px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  h2 { margin: 0; font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3 { margin: 4px 0 0; font-size: 13px; }
  .layers { height: 110px; border: 1px solid var(--line); border-radius: var(--radius-s); overflow: hidden; }
  .field.bad { border-color: var(--danger); }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .problems { margin: 0; padding: 8px 12px; list-style: none; border-radius: var(--radius-s); background: var(--danger-soft); color: var(--danger); font-size: 12.5px; }
  .hex { font: 12px/1.7 var(--mono); background: var(--bg); border-radius: var(--radius-s); padding: 8px 10px; overflow-x: auto; }
  .hrow { display: grid; grid-template-columns: 40px 1fr 140px; gap: 12px; white-space: pre; }
  .off { color: var(--faint); }
  .asc { color: var(--muted); }
</style>
