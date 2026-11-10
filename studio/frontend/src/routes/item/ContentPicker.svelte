<script lang="ts">
  // Откуда берётся содержимое объекта, когда это не текст: файл из хранилища, сцена карты, письмо или ссылка.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { toast } from "../../lib/toast.svelte";

  let { item, format, onchange }: { item: Schemas["ItemOut"]; format: Schemas["Format"] | undefined; onchange: () => void } = $props();

  let content = $state<Schemas["ContentOut"] | null>(null);
  let kind = $state("asset");
  let query = $state("");
  let found = $state<Schemas["PickRef"][]>([]);
  let url = $state("");
  let folder = $state<Schemas["NextcloudFolder"] | null>(null);
  let folderError = $state("");
  let loadingFolder = $state(false);

  const path = $derived({ item_id: item.id });
  const ALLOWED: Record<string, string[]> = {
    text: [], text_asset: ["asset"], asset: ["asset"], link_asset: ["link", "asset"], scene: ["scene"], message: ["message"], none: [],
  };
  const allowed = $derived(ALLOWED[format?.content ?? "text_asset"] ?? []);
  const LABEL: Record<string, string> = { asset: "Файл", link: "Ссылка", scene: "Сцена карты", message: "Письмо" };

  async function load() {
    const { data } = await api.GET("/studio/api/items/{item_id}/content", { params: { path } });
    if (!data) return;
    content = data;
    url = data.url;
    kind = data.kind !== "text" ? data.kind : allowed[0] ?? "asset";
  }
  onMount(load);

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const which = kind, text = query;
    clearTimeout(timer);
    if (which === "link" || which === "asset") return;
    timer = setTimeout(async () => {
      const route = which === "scene" ? "/studio/api/items/pick/scenes" : "/studio/api/items/pick/messages";
      found = (await api.GET(route, { params: { query: { q: text } } })).data ?? [];
    }, 200);
  });

  async function browse(path: string) {
    loadingFolder = true;
    folderError = "";
    const { data, error } = await api.GET("/studio/api/items/nextcloud", { params: { query: { path } } });
    loadingFolder = false;
    if (error || !data) {
      const fields = (error as { fields?: Record<string, string[]> } | undefined)?.fields;
      folderError = fields ? Object.values(fields).flat().join(" ") : problem(error, "Хранилище не отвечает.");
      return;
    }
    folder = data;
  }
  $effect(() => { if (kind === "asset" && !folder && !loadingFolder && !folderError) browse("AETHER"); });

  async function choose(id: number | null, fileId = "") {
    const body = { kind, file_id: kind === "asset" ? fileId : "", scene: kind === "scene" ? id : null, message: kind === "message" ? id : null, url: kind === "link" ? url : "" };
    const { data, error } = await api.PUT("/studio/api/items/{item_id}/content", { params: { path }, body });
    if (error || !data) {
      const fields = (error as { fields?: Record<string, string[]> } | undefined)?.fields;
      return toast(fields ? Object.values(fields).flat().join(" ") : problem(error), "error");
    }
    content = data;
    toast("Содержимое выбрано.");
    onchange();
  }

  const current = $derived(content && content.kind !== "text" && content.kind !== "asset" && content.kind !== "link" ? (content[content.kind as "scene" | "message"] ?? null) : null);
</script>

<div class="picker">
  <div class="kinds">
    {#each allowed as option}<button class="pick" class:on={kind === option} onclick={() => (kind = option)}>{LABEL[option]}</button>{/each}
  </div>

  {#if content && content.kind !== "text"}
    <div class="now">
      <span class="muted small">Сейчас: {LABEL[content.kind]}</span>
      {#if content.kind === "link"}<b class="mono">{content.url}</b>
      {:else if content.kind === "asset" && content.asset}<b>{content.asset.label}</b> <span class="chip">{content.asset.kind}</span>
      {:else if current}<b>{current.label}</b> <span class="muted mono">{current.sub}</span>{/if}
    </div>
  {:else}
    <p class="muted small">Содержимое не выбрано.</p>
  {/if}

  {#if kind === "link"}
    <div class="row">
      <input class="field mono" placeholder="https://…" bind:value={url} />
      <button class="btn primary" disabled={!url.trim()} onclick={() => choose(null)}>Сохранить ссылку</button>
    </div>
    <p class="muted small">Картинку по внешней ссылке игрок увидит, но байты по ней не скачиваются: они выдуманы по зерну объекта.</p>
  {:else if kind === "asset"}
    {#if folderError}
      <p class="err">{folderError} <button class="btn ghost" onclick={() => { folderError = ""; folder = null; }}>Повторить</button></p>
    {:else if !folder}
      <p class="muted small">Загрузка хранилища…</p>
    {:else}
      <p class="muted small mono">{folder.path}</p>
      <div class="found" class:busy={loadingFolder}>
        {#each folder.items as entry (entry.path + entry.name)}
          {#if entry.is_directory}
            <button class="ref" onclick={() => browse(entry.path.replace(/^\//, ""))}><b>{entry.is_parent ? "↑ выше" : entry.name}</b>{#if !entry.is_parent}<span class="muted small">папка</span>{/if}</button>
          {:else}
            <button class="ref" class:on={entry.file_id === content?.asset?.file_id} onclick={() => choose(null, entry.file_id ?? "")}><b>{entry.name}</b></button>
          {/if}
        {:else}
          <p class="muted small">Папка пуста.</p>
        {/each}
      </div>
    {/if}
    <p class="muted small">Файлы лежат в Nextcloud, в папке AETHER. Сам файл здесь не загружается: положите его туда и выберите.</p>
  {:else}
    <input class="field" placeholder="Поиск" bind:value={query} />
    <div class="found">
      {#each found as ref (ref.id)}
        <button class="ref" class:on={current && ref.id === current.id} onclick={() => choose(ref.id)}>
          <b>{ref.label}</b><span class="muted mono small">{ref.sub}</span>{#if ref.kind}<span class="chip">{ref.kind}</span>{/if}
        </button>
      {:else}
        <p class="muted small">Ничего не нашлось.</p>
      {/each}
    </div>
  {/if}
</div>

<style>
  .picker { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; overflow: auto; height: 100%; }
  .kinds { display: flex; gap: 6px; }
  .pick { padding: 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--muted); cursor: pointer; }
  .pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .now { display: flex; align-items: baseline; gap: 10px; padding: 8px 10px; border-radius: var(--radius-s); background: var(--panel-2); }
  .row { display: flex; gap: 8px; }
  .small { font-size: 12px; margin: 0; }
  .err { margin: 0; color: var(--danger); }
  .busy { opacity: 0.5; }
  .found { display: flex; flex-direction: column; gap: 2px; }
  .ref { display: flex; align-items: baseline; gap: 10px; padding: 7px 10px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; }
  .ref:hover { background: var(--panel-2); }
  .ref.on { background: var(--accent-soft); }
</style>
