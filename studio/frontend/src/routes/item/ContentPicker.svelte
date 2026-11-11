<script lang="ts">
  // Откуда берётся содержимое объекта, когда это не текст: файл из хранилища, сцена карты, письмо или ссылка.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { toast } from "../../lib/toast.svelte";
  import FilePicker from "./FilePicker.svelte";

  let { item, format, onchange }: { item: Schemas["ItemOut"]; format: Schemas["Format"] | undefined; onchange: () => void } = $props();

  let content = $state<Schemas["ContentOut"] | null>(null);
  let kind = $state("asset");
  let query = $state("");
  let found = $state<Schemas["PickRef"][]>([]);
  let url = $state("");
  let busy = $state(false);

  const path = $derived({ item_id: item.id });
  const ALLOWED: Record<string, string[]> = {
    text: [], text_asset: ["asset"], asset: ["asset"], link_asset: ["link", "asset"], scene: ["scene"], none: [],
  };
  const allowed = $derived(ALLOWED[format?.content ?? "text_asset"] ?? []);
  const LABEL: Record<string, string> = { asset: "Файл", link: "Ссылка", scene: "Сцена карты" };

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
      found = (await api.GET("/studio/api/items/pick/scenes", { params: { query: { q: text } } })).data ?? [];
    }, 200);
  });

  async function put(body: Schemas["ContentIn"], done: string) {
    busy = true;
    const { data, error } = await api.PUT("/studio/api/items/{item_id}/content", { params: { path }, body });
    busy = false;
    if (error || !data) {
      const fields = (error as { fields?: Record<string, string[]> } | undefined)?.fields;
      return toast(fields ? Object.values(fields).flat().join(" ") : problem(error), "error");
    }
    content = data;
    toast(done);
    onchange();
  }

  const choose = (id: number | null) =>
    put({ kind, file_id: "", view: "", scene: kind === "scene" ? id : null, url: kind === "link" ? url : "" }, "Содержимое выбрано.");
  const pickFile = (fileId: string, view: string) => put({ kind: "asset", file_id: fileId, view, scene: null, url: "" }, view && content?.asset?.file_id === fileId ? "Вид показа сохранён." : "Файл выбран.");
  const clearFile = () => put({ kind: "text", file_id: "", view: "", scene: null, url: "" }, "Файл убран.");

  const current = $derived(content && content.kind === "scene" ? (content.scene ?? null) : null);
</script>

<div class="picker" class:flush={kind === "asset"}>
  {#if allowed.length > 1}
    <div class="kinds">
      {#each allowed as option}<button class="pick" class:on={kind === option} onclick={() => (kind = option)}>{LABEL[option]}</button>{/each}
    </div>
  {/if}

  {#if kind === "asset"}
    <FilePicker {item} asset={content?.asset ?? null} canClear={format?.content === "text_asset"} hasText={item.body.trim() !== ""} {busy} onpick={pickFile} onclear={clearFile} />
  {:else}
    {#if content && content.kind !== "text"}
      <div class="now">
        <span class="muted small">Сейчас: {LABEL[content.kind]}</span>
        {#if content.kind === "link"}<b class="mono">{content.url}</b>{:else if current}<b>{current.label}</b> <span class="muted mono">{current.sub}</span>{/if}
      </div>
    {:else}
      <p class="muted small">Содержимое не выбрано.</p>
    {/if}

    {#if kind === "link"}
      <div class="row">
        <input class="field mono" placeholder="https://…" bind:value={url} />
        <button class="btn primary" disabled={!url.trim() || busy} onclick={() => choose(null)}>Сохранить ссылку</button>
      </div>
      <p class="muted small">Картинку по внешней ссылке игрок увидит, но байты по ней не скачиваются: они выдуманы по зерну объекта.</p>
    {:else}
      <input class="field" placeholder="Поиск" bind:value={query} />
      <div class="found">
        {#each found as ref (ref.id)}
          <button class="ref" class:on={current && ref.id === current.id} onclick={() => choose(ref.id)}>
            <b>{ref.label}</b><span class="muted mono small">{ref.sub}</span>
          </button>
        {:else}
          <p class="muted small">Ничего не нашлось.</p>
        {/each}
      </div>
    {/if}
  {/if}
</div>

<style>
  .picker { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; overflow: auto; height: 100%; box-sizing: border-box; }
  .picker.flush { padding: 0; gap: 0; }
  .kinds { display: flex; gap: 6px; }
  .flush .kinds { padding: 14px 16px 0; }
  .pick { padding: 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); color: var(--muted); cursor: pointer; }
  .pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .now { display: flex; align-items: baseline; gap: 10px; padding: 8px 10px; border-radius: var(--radius-s); background: var(--panel-2); }
  .row { display: flex; gap: 8px; }
  .small { font-size: 12px; margin: 0; }
  .found { display: flex; flex-direction: column; gap: 2px; }
  .ref { display: flex; align-items: baseline; gap: 10px; padding: 7px 10px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; }
  .ref:hover { background: var(--panel-2); }
  .ref.on { background: var(--accent-soft); }
</style>
