<script lang="ts">
  // Панель сведений о выбранном: что это, где лежит, чем защищено, кто правил. Для папки и пустого выбора: итоги по папке.
  import { api, type Schemas } from "../../lib/api";
  import FileIcon from "../../lib/FileIcon.svelte";
  import { type Described } from "../../lib/fileKind";
  import { ago } from "../../lib/time";

  type Node = Schemas["Node"];

  let { nodes, folderNodes, folderPath, kind, pathOf, onopen, onrename, onprotect }: {
    nodes: Node[];                      // выбранное
    folderNodes: Node[];                // то, что показано в таблице сейчас
    folderPath: string;
    kind: (node: Node) => Described;
    pathOf: (node: Node) => string;
    onopen: (node: Node) => void;
    onrename: (node: Node) => void;
    onprotect: (node: Node) => void;
  } = $props();

  const one = $derived(nodes.length === 1 ? nodes[0] : undefined);
  let where = $state<Schemas["Whereabouts"] | null>(null);
  let item = $state<Schemas["ItemOut"] | null>(null);

  // у объекта подгружаем, где он ещё лежит и кто его правил
  $effect(() => {
    const id = one?.item?.id;
    where = null;
    item = null;
    if (!id) return;
    api.GET("/studio/api/items/{item_id}/where", { params: { path: { item_id: id } } }).then(({ data }) => { if (one?.item?.id === id) where = data ?? null; });
    api.GET("/studio/api/items/{item_id}", { params: { path: { item_id: id } } }).then(({ data }) => { if (one?.item?.id === id) item = data ?? null; });
  });

  const others = $derived((where?.placements ?? []).filter((place) => place.placement !== one?.id));

  function size(bytes: number | null | undefined) {
    if (bytes == null) return "—";
    if (bytes < 1024) return `${bytes} Б`;
    return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1048576).toFixed(1)} МБ`;
  }

  const sum = $derived(nodes.reduce((total, node) => total + (node.size ?? 0), 0));
  const files = $derived(folderNodes.filter((node) => node.kind !== "folder"));
</script>

<aside class="details" aria-label="Сведения">
  {#if one}
    {@const info = kind(one)}
    <header>
      <FileIcon kind={info.kind} own={info.own} size={22} />
      <div class="title"><b>{one.name}</b><span class="muted small" class:obj={!info.own && one.kind !== "folder"}>{info.label}</span></div>
    </header>
    <dl>
      <dt>Где лежит</dt><dd class="mono">{pathOf(one)}</dd>
      {#if one.kind !== "folder"}<dt>Размер</dt><dd>{size(one.size)}</dd>{/if}
      {#if one.item}<dt>Формат</dt><dd>{one.item.format || "не задан"}</dd>{/if}
      {#if item}<dt>Правка</dt><dd>{ago(item.updated_at)}{item.updated_by ? ` · ${item.updated_by}` : ""}</dd>{/if}
      <dt>Видимость</dt>
      <dd>
        {#if one.hidden}<span class="chip">скрыт</span>{/if}
        {#if one.system}<span class="chip">системный</span>{/if}
        {#if !one.hidden && !one.system}игрок видит{/if}
      </dd>
      {#if one.kind !== "folder"}
        <dt>Защита</dt>
        <dd>
          {#if one.layers}<span class="chip warn">слои</span>{/if}
          {#if one.condition}<span class="chip warn">условие</span>{/if}
          {#if !one.layers && !one.condition}нет{/if}
        </dd>
      {/if}
      {#if one.owner || one.mode}<dt>Права</dt><dd class="mono">{one.owner || "—"}{one.group ? `:${one.group}` : ""} {one.mode}</dd>{/if}
    </dl>
    {#if one.item}
      <h4>Где ещё лежит</h4>
      {#if where === null}<p class="muted small">Загрузка…</p>
      {:else if !others.length}<p class="muted small">Только здесь.</p>
      {:else}
        <ul>
          {#each others.slice(0, 6) as place (place.placement)}
            <li><a class="mono" href="#/volumes/{place.volume}{place.parent ? `/${place.parent}` : ''}">{place.volume_name}:/{place.path}</a></li>
          {/each}
          {#if others.length > 6}<li class="muted small">и ещё {others.length - 6}</li>{/if}
        </ul>
      {/if}
    {/if}
    <div class="acts">
      <button class="btn" onclick={() => onopen(one)}>Открыть</button>
      <button class="btn ghost" onclick={() => onrename(one)}>Переименовать</button>
      {#if one.item}<button class="btn ghost" onclick={() => onprotect(one)} title="Своё условие и свои слои только для этого места">Защита места…</button>{/if}
    </div>
  {:else if nodes.length > 1}
    <header><div class="title"><b>Выбрано: {nodes.length}</b></div></header>
    <dl>
      <dt>Папок</dt><dd>{nodes.filter((node) => node.kind === "folder").length}</dd>
      <dt>Файлов</dt><dd>{nodes.filter((node) => node.kind !== "folder").length}</dd>
      <dt>Объём</dt><dd>{size(sum)}</dd>
      <dt>Скрыто</dt><dd>{nodes.filter((node) => node.hidden).length}</dd>
    </dl>
    <p class="muted small">Перетащите на папку, чтобы перенести. Правый клик: действия над всеми выбранными.</p>
  {:else}
    <header>
      <FileIcon kind="folder" size={22} />
      <div class="title"><b class="mono">{folderPath}</b><span class="muted small">Папка</span></div>
    </header>
    <dl>
      <dt>Показано</dt><dd>{folderNodes.length}</dd>
      <dt>Файлов без объекта</dt><dd>{files.filter((node) => node.own).length}</dd>
      <dt>Объектов</dt><dd>{files.filter((node) => node.item).length}</dd>
      <dt>С защитой</dt><dd>{files.filter((node) => node.layers || node.condition).length}</dd>
    </dl>
    <p class="muted small">Выберите файл или папку, чтобы увидеть сведения. Двойной клик открывает.</p>
  {/if}
</aside>

<style>
  .details { width: 280px; flex: none; padding: 14px 16px; border-left: 1px solid var(--line-soft); background: var(--panel); overflow-y: auto; }
  header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .title { display: flex; flex-direction: column; min-width: 0; }
  .title b { overflow-wrap: anywhere; }
  .small { font-size: 12px; }
  .obj { color: var(--accent); }
  dl { display: grid; grid-template-columns: 90px 1fr; gap: 6px 10px; margin: 0 0 14px; }
  dt { color: var(--muted); font-size: 12px; padding-top: 1px; }
  dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .chip.warn { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  h4 { margin: 0 0 6px; color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  ul { margin: 0 0 14px; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
  p { margin: 0 0 12px; }
  .acts { display: flex; flex-direction: column; align-items: stretch; gap: 6px; }
  .acts .btn { justify-content: center; }
</style>
