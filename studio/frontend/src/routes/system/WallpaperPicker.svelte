<script lang="ts">
  // Выбор картинки рабочего стола в хранилище (Nextcloud, папка AETHER): папки и картинки.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import FileIcon from "../../lib/FileIcon.svelte";

  type Entry = Schemas["NextcloudEntry"];
  let { current, previewUrl, onpick, onclose }: { current: string; previewUrl: (fileId: string) => string; onpick: (fileId: string, name: string) => void; onclose: () => void } = $props();

  let folder = $state<Schemas["NextcloudFolder"] | null>(null);
  let loading = $state(true);
  let error = $state("");
  let filter = $state("");
  let picked = $state<Entry | null>(null);

  async function browse(path: string) {
    loading = true;
    error = "";
    picked = null;
    filter = "";
    const { data, error: failed } = await api.GET("/studio/api/items/nextcloud", { params: { query: { path } } });
    loading = false;
    if (failed || !data) {
      const fields = (failed as { fields?: Record<string, string[]> } | undefined)?.fields;
      error = fields ? Object.values(fields).flat().join(" ") : problem(failed, "Хранилище не отвечает.");
      return;
    }
    folder = data;
  }
  onMount(() => browse("AETHER"));

  const crumbs = $derived.by(() => {
    const parts = (folder?.path ?? "/AETHER").split("/").filter(Boolean);
    return parts.map((text, index) => ({ text, path: parts.slice(0, index + 1).join("/") }));
  });
  // папки и картинки: остальные файлы для фона не годятся
  const entries = $derived((folder?.items ?? []).filter((e) => e.is_parent || e.is_directory || e.kind === "image")
    .filter((e) => e.is_parent || !filter.trim() || e.name.toLowerCase().includes(filter.trim().toLowerCase())));

  function open(entry: Entry) {
    if (entry.is_directory) browse(entry.path.replace(/^\//, ""));
    else picked = entry;
  }
  function submit() { if (picked?.file_id) onpick(picked.file_id, picked.name); }
</script>

<Dialog title="Картинка из хранилища" confirm="Выбрать" wide disabled={!picked?.file_id} onsubmit={submit} {onclose}>
  <nav class="crumbs" aria-label="Путь в хранилище">
    {#each crumbs as crumb, index}
      {#if index}<span class="sep" aria-hidden="true">›</span>{/if}
      <button type="button" class="crumb" aria-current={index === crumbs.length - 1 ? "location" : undefined} onclick={() => browse(crumb.path)}>{crumb.text}</button>
    {/each}
    <input class="field find" placeholder="Найти в папке" bind:value={filter} aria-label="Найти в папке" />
  </nav>
  <div class="body">
    <div class="rows" class:dim={loading && folder}>
      {#if error}
        <p class="state">{error}</p>
      {:else}
        {#each entries as entry (entry.path + entry.name)}
          <button type="button" class="row" class:on={picked?.path === entry.path} class:cur={!entry.is_directory && entry.file_id === current} onclick={() => open(entry)} ondblclick={() => { if (!entry.is_directory && entry.file_id) onpick(entry.file_id, entry.name); }}>
            {#if entry.is_parent}<span class="up" aria-hidden="true">↑</span><span class="rname">На уровень выше</span>
            {:else}<FileIcon kind={entry.is_directory ? "folder" : "image"} size={18} /><span class="rname">{entry.name}</span>
              {#if !entry.is_directory && entry.file_id === current}<span class="chip">сейчас</span>{/if}{/if}
          </button>
        {:else}
          <p class="state muted">{loading ? "Загрузка…" : filter.trim() ? "В этой папке такого нет." : "Здесь нет картинок. Загрузите файл в Nextcloud, он появится в списке."}</p>
        {/each}
      {/if}
    </div>
    <div class="pv">
      {#if picked?.file_id}
        <img src={previewUrl(picked.file_id)} alt="" />
        <b class="pname">{picked.name}</b>
      {:else}
        <span class="muted small">Выберите картинку: здесь появится превью. Двойной щелчок выбирает сразу.</span>
      {/if}
    </div>
  </div>
</Dialog>

<style>
  .crumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; font-family: var(--mono); }
  .crumb { border: 0; background: none; padding: 2px 5px; border-radius: var(--radius-s); color: var(--accent); cursor: pointer; }
  .crumb:hover { background: var(--panel-2); }
  .crumb[aria-current="location"] { color: var(--text); cursor: default; }
  .sep { color: var(--faint); }
  .find { margin-left: auto; width: 180px; height: 28px; }
  .body { display: grid; grid-template-columns: minmax(0, 1fr) 240px; gap: 12px; min-height: 280px; }
  .rows { display: flex; flex-direction: column; max-height: 340px; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .rows.dim { opacity: 0.55; }
  .row { display: flex; align-items: center; gap: 10px; padding: 0 12px; height: 36px; border: 0; border-bottom: 1px solid var(--line-soft); background: none; color: var(--text); text-align: left; cursor: pointer; flex: none; }
  .row:hover { background: var(--panel-2); }
  .row.on { background: var(--accent-soft); }
  .row.cur .rname { color: var(--accent); }
  .row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .rname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .up { width: 18px; text-align: center; color: var(--muted); }
  .state { padding: 20px 12px; text-align: center; margin: 0; }
  .pv { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 10px; border: 1px dashed var(--line); border-radius: var(--radius-s); background: repeating-conic-gradient(var(--panel-2) 0 25%, var(--bg) 0 50%) 0 0 / 16px 16px; text-align: center; }
  .pv img { max-width: 100%; max-height: 200px; object-fit: contain; }
  .pname { overflow-wrap: anywhere; font-size: 12px; background: var(--panel); padding: 1px 6px; border-radius: var(--radius-s); }
  .small { font-size: 12px; }
</style>
