<script lang="ts">
  // Сведения о выбранном в файлах машины: откуда файл, чем защищён, где ещё лежит. Для нескольких: итоги выбора.
  import { api, type Schemas } from "../../lib/api";
  import FileIcon from "../../lib/FileIcon.svelte";
  import { ago } from "../../lib/time";

  type Row = Schemas["MachineFileRow"];
  let { rows, folder, shown, onopen, onrename, onprotect }: {
    rows: Row[];                 // выбранное
    folder: string;
    shown: number;               // сколько строк в таблице
    onopen: (row: Row) => void;
    onrename: (row: Row) => void;
    onprotect: (row: Row) => void;
  } = $props();

  const one = $derived(rows.length === 1 ? rows[0] : undefined);
  let where = $state<Schemas["Whereabouts"] | null>(null);
  let item = $state<Schemas["ItemOut"] | null>(null);

  $effect(() => {
    const id = one?.item?.id;
    where = null;
    item = null;
    if (!id) return;
    api.GET("/studio/api/items/{item_id}/where", { params: { path: { item_id: id } } }).then(({ data }) => { if (one?.item?.id === id) where = data ?? null; });
    api.GET("/studio/api/items/{item_id}", { params: { path: { item_id: id } } }).then(({ data }) => { if (one?.item?.id === id) item = data ?? null; });
  });

  const others = $derived(where?.placements ?? []);
  const size = (bytes: number | null | undefined) => (bytes == null ? "—" : bytes < 1024 ? `${bytes} Б` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1048576).toFixed(1)} МБ`);
  const WHY: Record<string, string> = {
    override: "Копия лежит в диске отличий этой машины, общий файл не тронут.",
    added: "Файла нет на общих дисках: он есть только на этой машине.",
    deleted: "Скрыт на этой машине. Общий диск не менялся.",
    base: "Файл общего диска. Правка создаст копию на этой машине.",
  };
  const label = (row: Row) => (row.kind === "dir" ? "Папка" : row.kind === "deleted" ? "Скрыт" : row.item ? `Объект · ${row.item.format || "без формата"}` : "Файл без объекта");
  const sum = $derived(rows.reduce((total, row) => total + (row.item?.size ?? 0), 0));
</script>

<aside class="details" aria-label="Сведения">
  {#if one}
    <header>
      <FileIcon kind={one.kind === "dir" ? "folder" : one.item ? "object" : "file"} own={one.kind === "file" && !one.item} size={22} />
      <div class="title"><b>{one.name}</b><span class="muted small">{label(one)}</span></div>
    </header>
    <dl>
      <dt>Путь</dt><dd class="mono">{one.path}</dd>
      <dt>Откуда</dt><dd><span class="mono">{one.volume || "—"}</span>{#if WHY[one.mark]}<br /><span class="muted small">{WHY[one.mark]}</span>{/if}</dd>
      {#if one.kind === "file"}<dt>Размер</dt><dd>{size(one.item?.size)}</dd>{/if}
      {#if item}<dt>Правка</dt><dd>{ago(item.updated_at)}{item.updated_by ? ` · ${item.updated_by}` : ""}</dd>{/if}
      <dt>Видимость</dt>
      <dd>{#if one.hidden}<span class="chip">скрыт</span>{/if}{#if one.system}<span class="chip">системный</span>{/if}{#if !one.hidden && !one.system}игрок видит{/if}</dd>
      {#if one.kind === "file"}
        <dt>Защита</dt>
        <dd>{#if one.layers}<span class="chip warn">слои</span>{/if}{#if one.condition}<span class="chip warn">условие</span>{/if}{#if !one.layers && !one.condition}нет{/if}</dd>
      {/if}
      {#if one.owner || one.mode}<dt>Права</dt><dd class="mono">{one.owner || "—"}{one.group ? `:${one.group}` : ""} {one.mode}</dd>{/if}
    </dl>
    {#if one.item}
      <h4>Объект лежит на дисках</h4>
      {#if where === null}<p class="muted small">Загрузка…</p>
      {:else if !others.length}<p class="muted small">Ни на одном диске.</p>
      {:else}
        <ul>
          {#each others.slice(0, 6) as place (place.placement)}
            <li><a class="mono" href="#/volumes/{place.volume}">{place.volume_name}:/{place.path}</a></li>
          {/each}
          {#if others.length > 6}<li class="muted small">и ещё {others.length - 6}</li>{/if}
        </ul>
      {/if}
    {/if}
    {#if one.kind !== "deleted"}
      <div class="acts">
        <button class="btn" onclick={() => onopen(one)}>{one.kind === "dir" ? "Открыть папку" : "Открыть и править"}</button>
        <button class="btn ghost" onclick={() => onrename(one)}>Переименовать…</button>
        {#if one.item}<button class="btn ghost" onclick={() => onprotect(one)} title="Своё условие и свои слои только для этой машины">Защита на машине…</button>{/if}
      </div>
    {/if}
  {:else if rows.length > 1}
    <header><div class="title"><b>Выбрано: {rows.length}</b></div></header>
    <dl>
      <dt>Папок</dt><dd>{rows.filter((row) => row.kind === "dir").length}</dd>
      <dt>Файлов</dt><dd>{rows.filter((row) => row.kind === "file").length}</dd>
      <dt>Скрытых</dt><dd>{rows.filter((row) => row.kind === "deleted").length}</dd>
      <dt>Объём</dt><dd>{size(sum)}</dd>
    </dl>
    <p class="muted small">Перетащите на папку, чтобы перенести. Правый клик: действия над всеми выбранными.</p>
  {:else}
    <header>
      <FileIcon kind="folder" size={22} />
      <div class="title"><b class="mono">{folder}</b><span class="muted small">Папка</span></div>
    </header>
    <dl><dt>Показано</dt><dd>{shown}</dd></dl>
    <p class="muted small">Выберите файл или папку, чтобы увидеть сведения. Ctrl и Shift выбирают несколько, двойной клик открывает.</p>
  {/if}
</aside>

<style>
  .details { width: 280px; flex: none; padding: 14px 16px; border-left: 1px solid var(--line-soft); background: var(--panel); overflow-y: auto; }
  header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .title { display: flex; flex-direction: column; min-width: 0; }
  .title b { overflow-wrap: anywhere; }
  .small { font-size: 12px; }
  dl { display: grid; grid-template-columns: 76px 1fr; gap: 6px 10px; margin: 0 0 14px; }
  dt { color: var(--muted); font-size: 12px; padding-top: 1px; }
  dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
  .chip.warn { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  h4 { margin: 0 0 6px; color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  ul { margin: 0 0 14px; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; }
  p { margin: 0 0 12px; }
  .acts { display: flex; flex-direction: column; align-items: stretch; gap: 6px; }
  .acts .btn { justify-content: center; }
</style>
