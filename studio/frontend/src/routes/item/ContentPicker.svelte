<script lang="ts">
  // Откуда берётся содержимое объекта, когда это не текст: ассет, сцена карты, письмо или ссылка.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import { toast } from "../../lib/toast.svelte";

  let { item, format, onchange }: { item: Schemas["ItemOut"]; format: Schemas["Format"] | undefined; onchange: () => void } = $props();

  let content = $state<Schemas["ContentOut"] | null>(null);
  let kind = $state("asset");
  let query = $state("");
  let found = $state<Schemas["PickRef"][]>([]);
  let url = $state("");

  const path = $derived({ item_id: item.id });
  const ALLOWED: Record<string, string[]> = {
    text: [], text_asset: ["asset"], asset: ["asset"], link_asset: ["link", "asset"], scene: ["scene"], message: ["message"], none: [],
  };
  const allowed = $derived(ALLOWED[format?.content ?? "text_asset"] ?? []);
  const LABEL: Record<string, string> = { asset: "Ассет", link: "Ссылка", scene: "Сцена карты", message: "Письмо" };

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
    if (which === "link") return;
    timer = setTimeout(async () => {
      const route = which === "scene" ? "/studio/api/items/pick/scenes" : which === "message" ? "/studio/api/items/pick/messages" : "/studio/api/items/pick/assets";
      found = (await api.GET(route, { params: { query: { q: text } } })).data ?? [];
    }, 200);
  });

  async function choose(id: number | null) {
    const body = { kind, asset: kind === "asset" ? id : null, scene: kind === "scene" ? id : null, message: kind === "message" ? id : null, url: kind === "link" ? url : "" };
    const { data, error } = await api.PUT("/studio/api/items/{item_id}/content", { params: { path }, body });
    if (error || !data) {
      const fields = (error as { fields?: Record<string, string[]> } | undefined)?.fields;
      return toast(fields ? Object.values(fields).flat().join(" ") : problem(error), "error");
    }
    content = data;
    toast("Содержимое выбрано.");
    onchange();
  }

  const current = $derived(content && content.kind !== "text" ? (content[content.kind as "asset" | "scene" | "message"] ?? null) : null);
</script>

<div class="picker">
  <div class="kinds">
    {#each allowed as option}<button class="pick" class:on={kind === option} onclick={() => (kind = option)}>{LABEL[option]}</button>{/each}
  </div>

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
      <button class="btn primary" disabled={!url.trim()} onclick={() => choose(null)}>Сохранить ссылку</button>
    </div>
    <p class="muted small">Картинку по внешней ссылке игрок увидит, но байты по ней не скачиваются: они выдуманы по зерну объекта.</p>
  {:else}
    <input class="field" placeholder="Поиск" bind:value={query} />
    <div class="found">
      {#each found as ref (ref.id)}
        <button class="ref" class:on={current && ref.id === (content?.[content.kind as "asset" | "scene" | "message"]?.id)} onclick={() => choose(ref.id)}>
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
  .found { display: flex; flex-direction: column; gap: 2px; }
  .ref { display: flex; align-items: baseline; gap: 10px; padding: 7px 10px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; }
  .ref:hover { background: var(--panel-2); }
  .ref.on { background: var(--accent-soft); }
</style>
