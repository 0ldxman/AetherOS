<script lang="ts">
  // Выбор файла из хранилища (Nextcloud): что сейчас прикреплено, и обзор папки AETHER, где файл можно выбрать.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import FileIcon from "../../lib/FileIcon.svelte";

  type Entry = Schemas["NextcloudEntry"];
  let { item, asset, canClear, hasText = false, busy = false, onpick, onclear }: {
    item: Schemas["ItemOut"];
    asset: Schemas["FilePick"] | null;
    canClear: boolean;
    hasText?: boolean;               // у объекта есть текст: файл выбрать нельзя, пока текст не очищен
    busy?: boolean;
    onpick: (fileId: string, view: string) => void;
    onclear: () => void;
  } = $props();

  const VIEWS: [string, string][] = [["", "Авто"], ["image", "Картинка"], ["audio", "Аудио"], ["video", "Видео"], ["pdf", "PDF"], ["text", "Текст"], ["raw", "Сырой файл"]];
  const KIND_TEXT: Record<string, string> = { image: "Картинка", audio: "Аудио", video: "Видео", pdf: "PDF", text: "Текст", raw: "Файл" };

  let folder = $state<Schemas["NextcloudFolder"] | null>(null);
  let loading = $state(true);
  let error = $state("");
  let filter = $state("");
  let picked = $state<Entry | null>(null);
  let thumbBroken = $state(false);

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
  const entries = $derived((folder?.items ?? []).filter((entry) => entry.is_parent || !filter.trim() || entry.name.toLowerCase().includes(filter.trim().toLowerCase())));
  const files = $derived((folder?.items ?? []).filter((entry) => !entry.is_directory).length);

  function size(bytes: number | null | undefined) {
    if (bytes == null) return "";
    if (bytes < 1024) return `${bytes} Б`;
    return bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} КБ` : bytes < 1073741824 ? `${(bytes / 1048576).toFixed(1)} МБ` : `${(bytes / 1073741824).toFixed(1)} ГБ`;
  }
  const iconKind = (entry: Entry) => (entry.is_directory ? "folder" : entry.kind === "image" ? "image" : entry.kind === "text" || entry.kind === "pdf" ? "doc" : "file");

  function open(entry: Entry) {
    if (entry.is_directory) browse(entry.path.replace(/^\//, ""));
    else picked = entry;
  }
  function choose(entry: Entry) {
    onpick(entry.file_id ?? "", asset?.file_id === entry.file_id ? asset?.view ?? "" : "");
    picked = null;
  }
  $effect(() => { asset?.file_id; thumbBroken = false; });
</script>

<div class="picker">
  <section class="now" aria-label="Файл объекта">
    {#if asset}
      <div class="thumb">
        {#if asset.shown === "image" && item.file_url && !thumbBroken}
          <img src="{item.file_url}content/?v={encodeURIComponent(asset.file_id)}" alt="" onerror={() => (thumbBroken = true)} />
        {:else}
          <FileIcon kind={asset.shown === "image" ? "image" : asset.shown === "text" || asset.shown === "pdf" ? "doc" : "file"} size={30} />
        {/if}
      </div>
      <div class="meta">
        <b class="name">{asset.label}</b>
        <span class="muted small">{KIND_TEXT[asset.shown] ?? "Файл"}{asset.size != null ? ` · ${size(asset.size)}` : ""}</span>
        <div class="how">
          <label class="muted small" for="file-view">Показывать как</label>
          <select id="file-view" class="field" value={asset.view} disabled={busy} onchange={(e) => onpick(asset.file_id, (e.currentTarget as HTMLSelectElement).value)}>
            {#each VIEWS as [code, text]}<option value={code}>{code === "" ? `Авто (${(KIND_TEXT[asset.kind === "file" ? "raw" : asset.kind] ?? "файл").toLowerCase()})` : text}</option>{/each}
          </select>
        </div>
      </div>
      <div class="acts">
        {#if item.file_url}<a class="btn" href={item.file_url} target="_blank" rel="noreferrer">Открыть</a>{/if}
        {#if canClear}<button class="btn ghost danger" disabled={busy} onclick={onclear}>Убрать файл</button>{/if}
      </div>
    {:else}
      <div class="thumb empty" aria-hidden="true"><FileIcon kind="file" size={30} /></div>
      <div class="meta"><b>Файл не выбран</b><span class="muted small">Выберите его в списке ниже. Хранилище показывает папку AETHER из Nextcloud.</span></div>
    {/if}
  </section>

  <section class="browser" aria-label="Хранилище">
    <header>
      <nav class="crumbs" aria-label="Путь в хранилище">
        {#each crumbs as crumb, index}
          {#if index}<span class="sep" aria-hidden="true">›</span>{/if}
          <button class="crumb" aria-current={index === crumbs.length - 1 ? "location" : undefined} onclick={() => browse(crumb.path)}>{crumb.text}</button>
        {/each}
      </nav>
      <input class="field find" placeholder="Найти в папке" bind:value={filter} aria-label="Найти в папке" />
    </header>

    <div class="rows" class:dim={loading && folder}>
      {#if error}
        <div class="state"><p>{error}</p><button class="btn" onclick={() => browse(folder?.path.replace(/^\//, "") || "AETHER")}>Повторить</button></div>
      {:else if loading && !folder}
        {#each [1, 2, 3, 4] as n (n)}<div class="skeleton" aria-hidden="true"></div>{/each}
      {:else}
        {#each entries as entry (entry.path + entry.name)}
          <button class="row" class:on={picked?.path === entry.path} class:current={!entry.is_directory && asset?.file_id === entry.file_id}
                  aria-pressed={picked?.path === entry.path} onclick={() => open(entry)} ondblclick={() => !entry.is_directory && choose(entry)}>
            {#if entry.is_parent}
              <span class="up" aria-hidden="true">↑</span><span class="rname">На уровень выше</span>
            {:else}
              <FileIcon kind={iconKind(entry)} size={18} />
              <span class="rname">{entry.name}</span>
              {#if !entry.is_directory && asset?.file_id === entry.file_id}<span class="chip">сейчас</span>{/if}
              {#if !entry.is_directory}<span class="muted small kindtext">{KIND_TEXT[entry.kind] ?? "Файл"}</span><span class="muted small num">{size(entry.size)}</span>
              {:else}<span class="muted small">папка</span>{/if}
            {/if}
          </button>
        {:else}
          <div class="state">
            <p class="muted">{filter.trim() ? "В этой папке такого нет." : "Папка пуста."}</p>
            {#if !filter.trim()}<p class="muted small">Загрузите файл в Nextcloud в эту папку, он появится здесь.</p>{/if}
          </div>
        {/each}
      {/if}
    </div>

    <footer>
      {#if hasText}
        <span class="warn small">У объекта есть текст. Очистите его на вкладке «Текст», тогда файл можно будет выбрать.</span>
      {:else if picked}
        <span class="pickname"><b>{picked.name}</b> <span class="muted small">{KIND_TEXT[picked.kind] ?? "Файл"} · {size(picked.size)}</span></span>
        <button class="btn primary" disabled={busy} onclick={() => choose(picked!)}>{asset ? "Заменить на этот файл" : "Выбрать этот файл"}</button>
      {:else}
        <span class="muted small">{files ? `Файлов в папке: ${files}. Щёлкните по файлу, чтобы выбрать, двойной щелчок выбирает сразу.` : "Щёлкните по файлу, чтобы выбрать."}</span>
      {/if}
    </footer>
  </section>
</div>

<style>
  .picker { display: flex; flex-direction: column; gap: 14px; padding: 14px 16px; overflow: auto; height: 100%; box-sizing: border-box; }
  .small { font-size: 12px; }
  .now { display: grid; grid-template-columns: auto 1fr auto; gap: 14px; align-items: center; padding: 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .thumb { width: 72px; height: 72px; display: grid; place-items: center; overflow: hidden; border-radius: var(--radius-s); background: var(--bg); border: 1px solid var(--line-soft); }
  .thumb img { width: 100%; height: 100%; object-fit: cover; }
  .thumb.empty { border-style: dashed; }
  .meta { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .name { overflow-wrap: anywhere; }
  .how { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
  .how select { width: auto; height: 26px; }
  .acts { display: flex; flex-direction: column; gap: 6px; align-items: stretch; }
  .acts .btn { justify-content: center; text-decoration: none; }
  .browser { display: flex; flex-direction: column; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); min-height: 0; overflow: hidden; }
  header { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--line-soft); }
  .crumbs { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; flex: 1; min-width: 0; font-family: var(--mono); }
  .crumb { border: 0; background: none; padding: 2px 5px; border-radius: var(--radius-s); color: var(--accent); cursor: pointer; }
  .crumb:hover { background: var(--panel-2); }
  .crumb[aria-current="location"] { color: var(--text); cursor: default; }
  .sep { color: var(--faint); }
  .find { width: 180px; height: 28px; }
  .rows { display: flex; flex-direction: column; max-height: 340px; overflow: auto; }
  .rows.dim { opacity: 0.55; }
  .row { display: flex; align-items: center; gap: 10px; padding: 0 12px; height: 38px; border: 0; border-bottom: 1px solid var(--line-soft); background: none; color: var(--text); text-align: left; cursor: pointer; }
  .row:hover { background: var(--panel-2); }
  .row.on { background: var(--accent-soft); }
  .row.current .rname { color: var(--accent); }
  .row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .rname { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .up { width: 18px; text-align: center; color: var(--muted); }
  .kindtext { width: 64px; }
  .num { width: 70px; text-align: right; font-variant-numeric: tabular-nums; }
  .skeleton { height: 38px; margin: 0 12px; border-bottom: 1px solid var(--line-soft); background: linear-gradient(90deg, transparent, var(--panel-2), transparent); }
  .state { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 24px 16px; text-align: center; }
  .state p { margin: 0; }
  footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border-top: 1px solid var(--line-soft); min-height: 46px; box-sizing: border-box; }
  .warn { color: var(--warn); }
  .pickname { min-width: 0; overflow-wrap: anywhere; }
  @media (prefers-reduced-motion: no-preference) { .skeleton { animation: pulse 1.2s ease-in-out infinite; } @keyframes pulse { 50% { opacity: 0.4; } } }
</style>
