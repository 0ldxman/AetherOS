<script lang="ts">
  // Справка автора: оглавление и поиск слева, страница справа. Тексты лежат в docs/guide, картинки и видео снимает docs_media.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import ListDetail from "../lib/ListDetail.svelte";
  import { go } from "../lib/router.svelte";

  let { slug }: { slug: string | null } = $props();

  let sections = $state<Schemas["GdSection"][]>([]);
  let loaded = $state(false);
  let page = $state<Schemas["GdOut"] | null>(null);
  let failed = $state(false);
  let query = $state("");
  let hits = $state<Schemas["GdHit"][]>([]);
  let article = $state<HTMLElement>();
  let timer: ReturnType<typeof setTimeout> | undefined;

  onMount(async () => {
    sections = (await api.GET("/studio/api/guide")).data ?? [];
    loaded = true;
    if (slug === null && sections.length) go(`/guide/${sections[0].pages[0].slug}`);
  });

  $effect(() => {
    const current = slug;
    page = null;
    failed = false;
    if (!current) return;
    api.GET("/studio/api/guide/{slug}", { params: { path: { slug: current } } }).then(({ data }) => {
      if (slug !== current) return;
      if (data) { page = data; article?.scrollTo?.({ top: 0 }); } else failed = true;
    });
  });

  function find() {
    clearTimeout(timer);
    const q = query.trim();
    if (!q) { hits = []; return; }
    timer = setTimeout(async () => { hits = (await api.GET("/studio/api/guide/search", { params: { query: { q } } })).data ?? []; }, 200);
  }

  function jump(id: string) {
    article?.querySelector(`[id="${id}"]`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
</script>

<ListDetail title="Справка">
  {#snippet list()}
    <input class="field search" type="search" placeholder="Поиск по справке" bind:value={query} oninput={find} aria-label="Поиск по справке" />
    {#if query.trim()}
      {#each hits as hit (hit.slug)}
        <a class="item" class:on={hit.slug === slug} href={`#/guide/${hit.slug}`}>
          <span>{hit.title}</span>
          <span class="muted small">{hit.section} · {hit.snippet}</span>
        </a>
      {:else}
        <p class="muted small pad-s">Ничего не нашлось.</p>
      {/each}
    {:else}
      {#each sections as section (section.title)}
        <h2 class="section">{section.title}</h2>
        {#each section.pages as p (p.slug)}
          <a class="item" class:on={p.slug === slug} href={`#/guide/${p.slug}`}><span>{p.title}</span></a>
        {/each}
      {:else}
        {#if loaded}<p class="muted small pad-s">Страниц справки пока нет.</p>{/if}
      {/each}
    {/if}
  {/snippet}
  {#snippet add()}{/snippet}

  <div class="body" bind:this={article}>
    {#if failed}
      <p class="muted pad">Такой страницы нет в справке.</p>
    {:else if !page}
      <p class="muted pad">{loaded && !slug ? "Выберите страницу слева." : "Загрузка…"}</p>
    {:else}
      <article class="doc">
        <p class="muted crumb">{page.section}</p>
        <div class="text">{@html page.html}</div>
        {#if page.missing}<p class="note">Не снято картинок и видео: {page.missing}. Запустите <code>manage.py docs_media</code>.</p>{/if}
        <nav class="pager" aria-label="Соседние страницы">
          {#if page.prev}<a href={`#/guide/${page.prev.slug}`}>← {page.prev.title}</a>{:else}<span></span>{/if}
          {#if page.next}<a href={`#/guide/${page.next.slug}`}>{page.next.title} →</a>{/if}
        </nav>
      </article>
      {#if page.heads.length > 1}
        <aside class="toc" aria-label="На странице">
          <span class="label">На странице</span>
          {#each page.heads as head (head.id)}
            <button class="toc-item" style:padding-left={`${(head.level - 2) * 10}px`} onclick={() => jump(head.id)}>{head.title}</button>
          {/each}
        </aside>
      {/if}
    {/if}
  </div>
</ListDetail>

<style>
  .search { margin: 0 4px 10px; width: calc(100% - 8px); }
  .section { margin: 14px 10px 4px; font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--faint); }
  .small { font-size: 12px; margin: 0; overflow-wrap: anywhere; }
  .pad { padding: 20px 32px; }
  .pad-s { padding: 4px 10px; }
  .body { display: flex; gap: 32px; align-items: flex-start; padding: 24px 32px 48px; min-width: 0; }
  .doc { flex: 1; min-width: 0; max-width: 780px; }
  .crumb { margin: 0 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; }
  .toc { position: sticky; top: 24px; display: flex; flex-direction: column; gap: 2px; width: 190px; flex: none; }
  .toc-item { text-align: left; padding: 3px 0; background: none; border: 0; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .toc-item:hover { color: var(--text); }
  .note { margin: 24px 0 0; padding: 8px 12px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); font-size: 12.5px; }
  .pager { display: flex; justify-content: space-between; gap: 16px; margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line-soft); }

  .text :global(h1) { margin: 0 0 16px; font-size: 26px; font-weight: 650; line-height: 1.2; }
  .text :global(h2) { margin: 32px 0 10px; font-size: 18px; font-weight: 650; }
  .text :global(h3) { margin: 22px 0 8px; font-size: 15px; font-weight: 650; }
  .text :global(p), .text :global(li) { line-height: 1.65; font-size: 14px; }
  .text :global(p) { margin: 0 0 12px; }
  .text :global(ul), .text :global(ol) { margin: 0 0 12px; padding-left: 22px; }
  .text :global(code) { font-family: var(--mono); font-size: 12.5px; padding: 1px 5px; border-radius: 4px; background: var(--panel-2); }
  .text :global(pre) { margin: 0 0 14px; padding: 12px 14px; border-radius: var(--radius-s); background: var(--panel); border: 1px solid var(--line-soft); overflow-x: auto; }
  .text :global(pre code) { padding: 0; background: none; }
  .text :global(table) { border-collapse: collapse; margin: 0 0 14px; font-size: 13px; }
  .text :global(th), .text :global(td) { padding: 6px 12px; border: 1px solid var(--line); text-align: left; }
  .text :global(th) { background: var(--panel); }
  .text :global(figure) { margin: 18px 0; }
  .text :global(figure img), .text :global(figure video) { display: block; max-width: 100%; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); }
  .text :global(figcaption) { margin-top: 6px; color: var(--muted); font-size: 12.5px; }
  .text :global(figure.missing div) { padding: 28px 16px; border: 1px dashed var(--line); border-radius: var(--radius); color: var(--faint); text-align: center; font-size: 12.5px; }
</style>
