<script lang="ts">
  import AccessBuilder from "../lib/AccessBuilder.svelte";
  import LayerBuilder from "../lib/LayerBuilder.svelte";
  // Файл со своим текстом (без объекта): декорация и фон. Текст, защита этого места и то, что получит игрок.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import DocPreview from "../lib/DocPreview.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import Dialog from "../lib/Dialog.svelte";
  import { go, takeOrigin } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  let { volume, id }: { volume: number; id: number } = $props();

  let file = $state<Schemas["TextFile"] | null>(null);
  let form = $state({ content: "", access: "", state: "" });
  let saved = $state("");
  let preview = $state<Schemas["TextPreview"] | null>(null);
  let formats = $state<Schemas["Format"][]>([]);
  let errors = $state<Record<string, string[]>>({});
  let converting = $state(false);
  let conflict = $state<Schemas["TextConflict"] | null>(null);

  const path = $derived({ volume_id: volume, placement_id: id });
  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty);

  const known = $derived(formats.find((found) => found.name === file?.format));
  const markup = $derived(known?.markup ?? false);

  // предпросмотр по формату: с разметкой это документ, остальное (и несуществующие форматы) как есть
  let side = $state<"preview" | "guard" | "dump">("preview");
  let issues = $state<Schemas["Issue"][]>([]);
  const previewNote = $derived(
    known?.markup ? `Рисуется как документ: формат «${known.title || known.name}».`
      : known ? `У формата «${known.title || known.name}» нет разметки: текст показан как есть.`
      : "Такого формата нет в каталоге: текст показан как есть.",
  );

  // путь к файлу: диск и папки, каждая ведёт обратно к файлам
  let tree = $state<Schemas["VolumeTree"] | null>(null);
  const crumbs = $derived.by(() => {
    const list = [{ name: file?.volume_name ?? "", href: `#/volumes/${volume}` }];
    const chain: Schemas["Node"][] = [];
    let node = file?.parent == null ? undefined : tree?.rows.find((row) => row.id === file!.parent);
    while (node) {
      chain.unshift(node);
      const up: number | null = node.parent;
      node = up == null ? undefined : tree?.rows.find((row) => row.id === up);
    }
    return [...list, ...chain.map((folder) => ({ name: folder.name, href: `#/volumes/${volume}/${folder.id}` }))];
  });
  const origin = takeOrigin();
  const folderHref = $derived(origin.path ? `#${origin.path}` : `#/volumes/${volume}${file?.parent ? `/${file.parent}` : ""}`);

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
    tree = (await api.GET("/studio/api/volumes/{volume_id}", { params: { path: { volume_id: volume } } })).data ?? null;
  });

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const body = { ...form, version: "", force: false };
    clearTimeout(timer);
    timer = setTimeout(async () => {
      preview = (await api.POST("/studio/api/volumes/{volume_id}/text-files/{placement_id}/preview", { params: { path }, body })).data ?? null;
    }, 300);
  });

  async function save(force = false) {
    errors = {};
    const { data, error, response } = await api.PUT("/studio/api/volumes/{volume_id}/text-files/{placement_id}", {
      params: { path }, body: { ...form, version: file?.version ?? "", force },
    });
    if (response.status === 409) {
      conflict = error as unknown as Schemas["TextConflict"];
      return;
    }
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    conflict = null;
    fill(data);
    toast("Сохранено.");
  }

  async function reload() {
    conflict = null;
    const { data } = await api.GET("/studio/api/volumes/{volume_id}/text-files/{placement_id}", { params: { path } });
    if (data) fill(data);
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
      <a class="btn back" href={folderHref} title={origin.label || "Вернуться к файлам этой папки"}>← К файлам</a>
      <nav class="crumbs" aria-label="Путь к файлу">
        {#each crumbs as crumb}<a href={crumb.href}>{crumb.name}</a><span class="sep">/</span>{/each}
        <h1 class="mono">{file.name}</h1>
      </nav>
      <span class="chip" title={file.format ? "Формат по расширению имени" : "Такого формата нет в каталоге: файл остаётся текстом"}>{file.format || (file.name.includes(".") && !file.name.startsWith(".") ? file.name.slice(file.name.lastIndexOf(".")) : "без формата")}</span>
      <span class="chip own">свой текст</span>
      <span class="spacer"></span>
      <span class="muted small">{dirty ? "Не сохранено" : "Сохранено"}</span>
      <button class="btn ghost" onclick={() => (converting = true)}>Сделать объектом</button>
      <button class="btn primary" disabled={!dirty} onclick={() => save()}>Сохранить</button>
    </header>

    {#if conflict}
      <div class="banner" role="alert">
        <span>{conflict.detail}</span>
        <button class="btn" onclick={reload}>Открыть их версию</button>
        <button class="btn danger" onclick={() => save(true)}>Сохранить моё поверх</button>
      </div>
    {/if}

    <div class="cols">
      <section class="pane">
        <h2>Текст</h2>
        <div class="editor"><CodeEditor bind:value={form.content} {markup} onsave={() => save()} /></div>
      </section>

      <div class="side">
        <div class="tabs" role="tablist">
          <button class:on={side === "preview"} onclick={() => (side = "preview")}>Предпросмотр</button>
          <button class:on={side === "guard"} onclick={() => (side = "guard")}>Защита{#if form.state.trim() || form.access.trim()} <span class="dot">●</span>{/if}</button>
          <button class:on={side === "dump"} onclick={() => (side = "dump")}>Что получит игрок</button>
        </div>

        {#if side === "preview"}
        <section class="card previewcard">
          <p class="muted small note">{previewNote}</p>
          <DocPreview format={file.format} title={file.name} body={form.content} bind:issues />
          {#if issues.length}
            <ul class="issues">
              {#each issues as issue}<li class={issue.level}><span class="mono">стр. {issue.line}</span> {issue.message}</li>{/each}
            </ul>
          {/if}
        </section>
        {:else if side === "guard"}
        <section class="card">
          <h2>Защита этого файла</h2>
          <label><span class="label">Условие доступа (пусто: открыто)</span>
            <AccessBuilder bind:value={form.access} bad={!!(preview?.access_error || errors.access)} /></label>
          {#if preview?.access_error}<p class="err">{preview.access_error}</p>{/if}
          {#if preview?.unknown_keys.length}<p class="err">Нет в реестре: {preview.unknown_keys.join(", ")}</p>{/if}
          <span class="label">Слои защиты</span>
          <LayerBuilder bind:value={form.state} onsave={() => save()} />
          {#if preview?.problems.length}
            <ul class="problems">{#each preview.problems as bad}<li><span class="mono">стр. {bad.line}</span> {bad.message}</li>{/each}</ul>
          {/if}
        </section>
        {:else}
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
        {/if}
      </div>
    </div>
  </div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

{#if converting}
  <Dialog title="Сделать объектом?" confirm="Сделать" onsubmit={toItem} onclose={() => (converting = false)}>
    <p class="muted">Текст, условие и слои переедут в новый объект, а это место будет на него ссылаться. Тогда файл можно класть в
      другие диски и архивы, у него появятся история, вложенные ключи и подписи.</p>
  </Dialog>
{/if}

<style>
  .page { display: flex; flex-direction: column; height: 100%; }
  .pad { padding: 24px; }
  .banner { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 12px 16px 0; padding: 10px 14px; border: 1px solid rgba(255, 122, 122, 0.3); border-radius: var(--radius); background: var(--danger-soft); }
  .banner span { flex: 1; }
  .head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--line-soft); }
  h1 { margin: 0; font-size: 17px; }
  .back { text-decoration: none; color: var(--text); }
  .back:hover { text-decoration: none; }
  .crumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; min-width: 0; font-size: 13px; }
  .crumbs .sep { color: var(--faint); }
  .tabs { display: flex; gap: 2px; padding: 4px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .tabs button { flex: 1; padding: 6px 10px; border: 0; border-radius: var(--radius-s); background: none; color: var(--muted); cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { background: var(--panel-2); color: var(--text); }
  .dot { color: var(--warn); font-size: 9px; }
  .previewcard { flex: 1; min-height: 320px; padding: 0; gap: 0; overflow: hidden; }
  .note { padding: 8px 14px; border-bottom: 1px solid var(--line-soft); }
  .issues { margin: 0; padding: 8px 12px; list-style: none; max-height: 120px; overflow: auto; border-top: 1px solid var(--line-soft); font-size: 12.5px; }
  .issues .error { color: var(--danger); }
  .issues .warning { color: var(--warn); }
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
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .problems { margin: 0; padding: 8px 12px; list-style: none; border-radius: var(--radius-s); background: var(--danger-soft); color: var(--danger); font-size: 12.5px; }
  .hex { font: 12px/1.7 var(--mono); background: var(--bg); border-radius: var(--radius-s); padding: 8px 10px; overflow-x: auto; }
  .hrow { display: grid; grid-template-columns: 40px 1fr 140px; gap: 12px; white-space: pre; }
  .off { color: var(--faint); }
  .asc { color: var(--muted); }
</style>
