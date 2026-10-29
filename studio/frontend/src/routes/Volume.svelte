<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  type Node = Schemas["Node"];
  const OWN = "-";                  // вместо формата: файл со своим текстом, без объекта

  let { id, folder }: { id: number; folder: number | null } = $props();

  let volume = $state<Schemas["VolumeTree"] | null>(null);
  let formats = $state<Schemas["Format"][]>([]);
  let selected = $state<Set<number>>(new Set());
  let opened = $state<Set<number>>(new Set());
  let propsOpen = $state(false);
  let props_ = $state({ slug: "", name: "", label: "", uuid: "", capacity_gb: null as number | null, used_gb: null as number | null });
  let propErrors = $state<Record<string, string[]>>({});

  function openProps() {
    if (!volume) return;
    props_ = { slug: volume.slug, name: volume.name, label: volume.label, uuid: volume.uuid, capacity_gb: volume.capacity_gb ?? null, used_gb: volume.used_gb ?? null };
    propErrors = {};
    propsOpen = true;
  }

  async function saveProps() {
    const { data, error } = await api.PUT("/studio/api/volumes/{volume_id}", { params: { path: { volume_id: id } }, body: props_ });
    if (error || !data) {
      propErrors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    if (volume) volume = { ...volume, ...data, rows: volume.rows };
    propsOpen = false;
    toast("Свойства тома сохранены.");
  }

  const gbOf = (value: string) => (value === "" ? null : Math.max(0, Math.round(+value)));

  function randomUsed() {
    if (props_.capacity_gb) props_.used_gb = Math.round((props_.capacity_gb * (20 + Math.random() * 50)) / 100);
  }

  let dialog = $state<null | { kind: "folder" | "file" | "rename" | "delete"; name: string; format: string }>(null);
  let busy = $state(false);
  let dragging = $state<number[]>([]);
  let dropTarget = $state<number | null | undefined>(undefined);

  const byId = $derived(new Map((volume?.rows ?? []).map((row) => [row.id, row])));
  const children = $derived.by(() => {
    const found = new Map<number | null, Node[]>();
    for (const row of volume?.rows ?? []) {
      const list = found.get(row.parent) ?? [];
      list.push(row);
      found.set(row.parent, list);
    }
    for (const list of found.values()) {
      list.sort((a, b) => (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1) || a.name.localeCompare(b.name, "ru"));
    }
    return found;
  });
  const listing = $derived(children.get(folder) ?? []);
  const crumbs = $derived.by(() => {
    const chain: Node[] = [];
    let node = folder === null ? undefined : byId.get(folder);
    while (node) {
      chain.unshift(node);
      node = node.parent === null ? undefined : byId.get(node.parent);
    }
    return chain;
  });
  const single = $derived(selected.size === 1 ? byId.get([...selected][0]) : undefined);

  async function load() {
    const { data, error } = await api.GET("/studio/api/volumes/{volume_id}", { params: { path: { volume_id: id } } });
    if (error || !data) return toast("Том не найден.", "error");
    volume = data;
    selected = new Set([...selected].filter((key) => data.rows.some((row) => row.id === key)));
    for (const node of crumbs) opened.add(node.id);
  }

  onMount(async () => {
    const { data } = await api.GET("/studio/api/formats");
    formats = data ?? [];
    await load();
  });

  function openFolder(target: number | null) {
    selected = new Set();
    go(target === null ? `/volumes/${id}` : `/volumes/${id}/${target}`);
  }

  function activate(node: Node) {
    if (node.kind === "folder") openFolder(node.id);
    else if (node.item) go(`/items/${node.item.id}`);
    else if (node.kind === "file") go(`/volumes/${id}/text/${node.id}`);
  }

  function pick(node: Node, event: MouseEvent) {
    const next = new Set(event.ctrlKey || event.metaKey ? selected : []);
    if (event.shiftKey && selected.size) {
      const ids = listing.map((row) => row.id);
      const from = ids.indexOf([...selected].at(-1)!);
      const to = ids.indexOf(node.id);
      for (const key of ids.slice(Math.min(from, to), Math.max(from, to) + 1)) next.add(key);
    } else if (next.has(node.id)) next.delete(node.id);
    else next.add(node.id);
    selected = next;
  }

  function toggle(node: Node) {
    const next = new Set(opened);
    if (next.has(node.id)) next.delete(node.id);
    else next.add(node.id);
    opened = next;
  }

  async function run(action: () => Promise<{ error?: unknown }>, done: string) {
    busy = true;
    const { error } = await action();
    busy = false;
    if (error) return toast(problem(error), "error");
    dialog = null;
    toast(done);
    await load();
  }

  function submit() {
    if (!dialog) return;
    const path = { volume_id: id };
    if (dialog.kind === "folder") {
      run(() => api.POST("/studio/api/volumes/{volume_id}/folders", { params: { path }, body: { parent: folder, name: dialog!.name } }), "Папка создана.");
    } else if (dialog.kind === "file") {
      const { name, format } = dialog;
      busy = true;
      if (format === OWN) {
        api.POST("/studio/api/volumes/{volume_id}/text-files", { params: { path }, body: { parent: folder, name, content: "" } }).then(({ data, error }) => {
          busy = false;
          if (error) return toast(problem(error), "error");
          dialog = null;
          if (data) go(`/volumes/${id}/text/${data.id}`);
        });
        return;
      }
      api.POST("/studio/api/volumes/{volume_id}/files", { params: { path }, body: { parent: folder, name, format } }).then(({ data, error }) => {
        busy = false;
        if (error) return toast(problem(error), "error");
        dialog = null;
        if (data?.item) go(`/items/${data.item}`);
      });
    } else if (dialog.kind === "rename" && single) {
      run(() => api.PATCH("/studio/api/volumes/{volume_id}/placements/{placement_id}", {
        params: { path: { ...path, placement_id: single.id } }, body: { name: dialog!.name },
      }), "Переименовано.");
    } else if (dialog.kind === "delete") {
      run(() => api.POST("/studio/api/volumes/{volume_id}/delete", { params: { path }, body: { ids: [...selected] } }), "Удалено.");
    }
  }

  function setHidden(hidden: boolean) {
    const ids = [...selected];
    run(async () => {
      for (const placement_id of ids) {
        const answer = await api.PATCH("/studio/api/volumes/{volume_id}/placements/{placement_id}", {
          params: { path: { volume_id: id, placement_id } }, body: { hidden },
        });
        if (answer.error) return answer;
      }
      return {};
    }, hidden ? "Скрыто." : "Видно.");
  }

  function startDrag(node: Node, event: DragEvent) {
    dragging = selected.has(node.id) ? [...selected] : [node.id];
    event.dataTransfer?.setData("text/plain", dragging.join(","));
  }

  function canDrop(target: number | null) {
    return dragging.length > 0 && !dragging.includes(target as number);
  }

  function drop(target: number | null, event: DragEvent) {
    event.preventDefault();
    const ids = dragging;
    dragging = [];
    dropTarget = undefined;
    if (!ids.length || ids.includes(target as number)) return;
    const copy = event.altKey;
    run(
      () => api.POST(copy ? "/studio/api/volumes/{volume_id}/copy" : "/studio/api/volumes/{volume_id}/move", {
        params: { path: { volume_id: id } }, body: { ids, parent: target },
      }),
      copy ? "Скопировано." : "Перенесено.",
    );
  }

  function onKey(event: KeyboardEvent) {
    if (dialog || (event.target as HTMLElement).closest("input, textarea, select")) return;
    if (event.key === "Delete" && selected.size) dialog = { kind: "delete", name: "", format: "" };
    else if (event.key === "F2" && single) dialog = { kind: "rename", name: single.name, format: "" };
    else if (event.key === "Enter" && single) activate(single);
    else if ((event.ctrlKey || event.metaKey) && event.key === "a") {
      event.preventDefault();
      selected = new Set(listing.map((row) => row.id));
    }
  }

  function size(node: Node) {
    const bytes = node.item?.size;
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
    return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  }
</script>

<svelte:window onkeydown={onKey} />

{#snippet branch(parent: number | null, depth: number)}
  {#each (children.get(parent) ?? []).filter((row) => row.kind === "folder") as node (node.id)}
    {@const kids = (children.get(node.id) ?? []).some((row) => row.kind === "folder")}
    <div
      class="twig"
      class:on={folder === node.id}
      class:drop={dropTarget === node.id}
      style:padding-left="{10 + depth * 14}px"
      role="treeitem"
      aria-selected={folder === node.id}
      tabindex="-1"
      ondragover={(event) => { if (canDrop(node.id)) { event.preventDefault(); dropTarget = node.id; } }}
      ondragleave={() => (dropTarget = undefined)}
      ondrop={(event) => drop(node.id, event)}
    >
      <button class="arrow" class:open={opened.has(node.id)} class:none={!kids} onclick={() => toggle(node)} aria-label="Раскрыть">▸</button>
      <button class="twig-name" class:hidden={node.hidden} onclick={() => openFolder(node.id)}>{node.name}</button>
    </div>
    {#if opened.has(node.id)}{@render branch(node.id, depth + 1)}{/if}
  {/each}
{/snippet}

<div class="volume">
  <div class="tree" role="tree">
    <button class="back" onclick={() => go("/volumes")}>← Все тома</button>
    <div
      class="twig root"
      class:on={folder === null}
      class:drop={dropTarget === null}
      role="treeitem"
      aria-selected={folder === null}
      tabindex="-1"
      ondragover={(event) => { if (canDrop(null)) { event.preventDefault(); dropTarget = null; } }}
      ondragleave={() => (dropTarget = undefined)}
      ondrop={(event) => drop(null, event)}
    >
      <button class="twig-name" onclick={() => openFolder(null)}>{volume?.name || volume?.slug || "…"}</button>
    </div>
    {@render branch(null, 0)}
  </div>

  <section class="body">
    <header class="bar">
      <nav class="crumbs">
        <button onclick={() => openFolder(null)}>{volume?.name || volume?.slug || "…"}</button>
        {#each crumbs as node (node.id)}
          <span class="sep">/</span><button onclick={() => openFolder(node.id)}>{node.name}</button>
        {/each}
      </nav>
      <div class="actions">
        <button class="btn ghost" onclick={openProps}>Свойства</button>
        <button class="btn" onclick={() => (dialog = { kind: "folder", name: "", format: "" })}>Новая папка</button>
        <button class="btn primary" onclick={() => (dialog = { kind: "file", name: "", format: "" })}>Новый файл</button>
      </div>
    </header>

    <div class="selbar" class:show={selected.size > 0}>
      <span>Выбрано: {selected.size}</span>
      <button class="btn ghost" disabled={!single} onclick={() => single && (dialog = { kind: "rename", name: single.name, format: "" })}>Переименовать</button>
      <button class="btn ghost" onclick={() => setHidden(true)}>Скрыть</button>
      <button class="btn ghost" onclick={() => setHidden(false)}>Показать</button>
      <button class="btn ghost danger" onclick={() => (dialog = { kind: "delete", name: "", format: "" })}>Удалить</button>
      <span class="hint muted">Перетащите на папку, чтобы перенести (с Alt: скопировать)</span>
    </div>

    <div class="table" role="grid">
      <div class="row head" role="row">
        <span>Имя</span><span>Формат</span><span>Размер</span><span>Права</span><span></span>
      </div>
      {#each listing as node (node.id)}
        <div
          class="row"
          class:sel={selected.has(node.id)}
          class:drop={node.kind === "folder" && dropTarget === node.id}
          class:dim={node.hidden}
          role="row"
          tabindex="-1"
          draggable="true"
          onclick={(event) => pick(node, event)}
          ondblclick={() => activate(node)}
          onkeydown={() => {}}
          ondragstart={(event) => startDrag(node, event)}
          ondragend={() => { dragging = []; dropTarget = undefined; }}
          ondragover={(event) => { if (node.kind === "folder" && canDrop(node.id)) { event.preventDefault(); dropTarget = node.id; } }}
          ondragleave={() => (dropTarget = undefined)}
          ondrop={(event) => node.kind === "folder" && drop(node.id, event)}
        >
          <span class="name">
            <span class="ico" class:dir={node.kind === "folder"}>{node.kind === "folder" ? "▣" : "▤"}</span>
            {node.name}
          </span>
          <span class="muted">{node.item?.format || (node.kind === "folder" ? "папка" : node.kind === "file" ? "текст места" : "—")}</span>
          <span class="muted mono">{size(node)}</span>
          <span class="muted mono">{node.owner || "—"}{node.group ? `:${node.group}` : ""} {node.mode}</span>
          <span class="flags">
            {#if node.hidden}<span class="chip">скрыт</span>{/if}
            {#if node.system}<span class="chip">системный</span>{/if}
            {#if node.item && node.item.used > 1}<span class="chip" title="Тот же объект лежит в других местах">×{node.item.used}</span>{/if}
          </span>
        </div>
      {:else}
        <p class="empty muted">Папка пуста. Создайте файл или перетащите сюда что-нибудь из дерева.</p>
      {/each}
    </div>
  </section>
</div>

{#if propsOpen}
  <Dialog title="Свойства тома" confirm="Сохранить" onsubmit={saveProps} onclose={() => (propsOpen = false)}>
    <label><span class="label">Название диска (как в игре)</span><input class="field" bind:value={props_.name} /></label>
    <label><span class="label">Слаг</span><input class="field mono" bind:value={props_.slug} class:bad={propErrors.slug} /></label>
    {#if propErrors.slug}<p class="err">{propErrors.slug.join(" ")}</p>{/if}
    <label><span class="label">Метка для студии</span><input class="field" bind:value={props_.label} /></label>
    <div class="two">
      <label><span class="label">Ёмкость, ГБ (декор)</span><input class="field" type="number" min="0" value={props_.capacity_gb ?? ""} oninput={(e) => (props_.capacity_gb = gbOf(e.currentTarget.value))} /></label>
      <label><span class="label">Занято, ГБ</span>
        <span class="inline"><input class="field" type="number" min="0" value={props_.used_gb ?? ""} oninput={(e) => (props_.used_gb = gbOf(e.currentTarget.value))} />
          <button type="button" class="btn ghost" disabled={!props_.capacity_gb} onclick={randomUsed}>Случайно</button></span>
      </label>
    </div>
    {#if propErrors.used_gb}<p class="err">{propErrors.used_gb.join(" ")}</p>{/if}
    <label><span class="label">UUID</span><input class="field mono" bind:value={props_.uuid} class:bad={propErrors.uuid} /></label>
    {#if propErrors.uuid}<p class="err">{propErrors.uuid.join(" ")}</p>{/if}
  </Dialog>
{/if}

{#if dialog?.kind === "folder"}
  <Dialog title="Новая папка" confirm="Создать" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <input class="field" placeholder="Имя папки" bind:value={dialog.name} />
  </Dialog>
{:else if dialog?.kind === "file"}
  <Dialog title="Новый файл" confirm="Создать и открыть" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <label><span class="label">Имя (расширение подберёт формат)</span><input class="field" placeholder="report.rec" bind:value={dialog.name} /></label>
    <label>
      <span class="label">Формат</span>
      <select class="field" bind:value={dialog.format}>
        <option value="">по расширению</option>
        <option value={OWN}>Свой текст места (без объекта)</option>
        {#each formats as found}<option value={found.name}>{found.name} — {found.title}</option>{/each}
      </select>
    </label>
  </Dialog>
{:else if dialog?.kind === "rename"}
  <Dialog title="Переименовать" confirm="Сохранить" {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <input class="field" bind:value={dialog.name} />
  </Dialog>
{:else if dialog?.kind === "delete"}
  <Dialog title="Удалить {selected.size === 1 ? `«${single?.name}»` : `${selected.size} элементов`}?" confirm="Удалить" danger {busy} onsubmit={submit} onclose={() => (dialog = null)}>
    <p class="muted">Папки удаляются вместе с содержимым. Объекты, которые лежат и в других местах, там останутся.</p>
  </Dialog>
{/if}

<style>
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .inline { display: flex; gap: 6px; }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .field.bad { border-color: var(--danger); }
  .volume { display: grid; grid-template-columns: 250px 1fr; height: 100%; }
  .tree { padding: 12px 8px; border-right: 1px solid var(--line-soft); overflow: auto; background: var(--panel); }
  .back { margin: 0 0 10px 6px; background: none; border: 0; color: var(--muted); cursor: pointer; padding: 4px; }
  .back:hover { color: var(--text); }
  .twig { display: flex; align-items: center; gap: 2px; border-radius: var(--radius-s); }
  .twig.root { padding-left: 6px; font-weight: 600; }
  .twig.on { background: var(--accent-soft); }
  .twig.drop, .row.drop { outline: 1px dashed var(--accent); background: var(--accent-soft); }
  .arrow { width: 18px; border: 0; background: none; color: var(--faint); cursor: pointer; transition: transform 0.12s; padding: 0; }
  .arrow.open { transform: rotate(90deg); }
  .arrow.none { visibility: hidden; }
  .twig-name { flex: 1; min-width: 0; text-align: left; border: 0; background: none; padding: 5px 6px; cursor: pointer; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .twig-name.hidden { color: var(--muted); font-style: italic; }
  .body { display: flex; flex-direction: column; min-width: 0; }
  .bar { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 18px 24px 12px; }
  .crumbs { display: flex; align-items: center; gap: 4px; font-size: 15px; min-width: 0; flex-wrap: wrap; }
  .crumbs button { border: 0; background: none; cursor: pointer; padding: 2px 4px; border-radius: 4px; font-weight: 600; }
  .crumbs button:hover { background: var(--panel-2); }
  .sep { color: var(--faint); }
  .actions { display: flex; gap: 8px; }
  .selbar {
    display: flex; align-items: center; gap: 4px; margin: 0 24px; padding: 0 10px; height: 0; overflow: hidden;
    border-radius: var(--radius); background: var(--panel-2); transition: height 0.15s, margin 0.15s;
  }
  .selbar.show { height: 40px; margin-bottom: 10px; }
  .hint { margin-left: auto; font-size: 12px; }
  .table { padding: 0 24px 24px; overflow: auto; }
  .row {
    display: grid; grid-template-columns: minmax(220px, 1fr) 120px 90px 160px 170px; align-items: center; gap: 12px;
    padding: 0 10px; height: 34px; border-radius: var(--radius-s); cursor: default; user-select: none;
  }
  .row:not(.head):hover { background: var(--panel); }
  .row.sel { background: var(--accent-soft); }
  .row.dim .name { color: var(--muted); font-style: italic; }
  .row.head { color: var(--faint); font-size: 12px; height: 28px; border-bottom: 1px solid var(--line-soft); border-radius: 0; margin-bottom: 4px; }
  .name { display: flex; align-items: center; gap: 8px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
  .ico { color: var(--faint); font-size: 12px; }
  .ico.dir { color: var(--warn); }
  .flags { display: flex; gap: 4px; justify-content: flex-end; }
  .empty { padding: 24px 10px; }
</style>
