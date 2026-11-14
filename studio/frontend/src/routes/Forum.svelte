<script lang="ts">
  // Форум в Студии: пространства слева, справа вкладки «Обзор» (машины и правила), «Разделы» (дерево) и «Темы» (модерация, голос персонажа).
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { canEdit } from "../lib/me.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import Overview from "./forum/Overview.svelte";
  import Sections from "./forum/Sections.svelte";
  import Topics from "./forum/Topics.svelte";

  let { slug, tab }: { slug: string | null; tab: string } = $props();

  const TABS = [{ key: "overview", label: "Обзор" }, { key: "sections", label: "Разделы" }, { key: "topics", label: "Темы" }];
  const current = $derived(TABS.some((t) => t.key === tab) ? tab : "overview");
  const editable = canEdit("forum");

  let rows = $state<Schemas["FoSpaceRow"][]>([]);
  let space = $state<Schemas["FoSpaceOut"] | null>(null);
  let loaded = $state(false);
  let dialog = $state<{ slug: string; title: string } | null>(null);
  let errors = $state<Record<string, string>>({});

  async function loadList() {
    rows = (await api.GET("/studio/api/forum/spaces")).data ?? [];
    loaded = true;
  }
  async function load() {
    space = null;
    if (!slug) return;
    const { data } = await api.GET("/studio/api/forum/spaces/{slug}", { params: { path: { slug } } });
    if (!data) return toast("Пространство не найдено.", "error");
    space = data;
  }
  onMount(async () => {
    await loadList();
    if (slug === null && rows.length) return go(`/forum/${rows[0].slug}`);
    await load();
  });

  async function create() {
    if (!dialog) return;
    const { data, error } = await api.POST("/studio/api/forum/spaces", { body: { slug: dialog.slug, title: dialog.title, about: "", order: 0, read_if: "", write: "players", write_if: "", create: "players", create_if: "", machines: [], rotation: {} } });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string> } | undefined)?.fields ?? {};
      return toast(Object.values(errors)[0] ?? problem(error), "error");
    }
    dialog = null;
    errors = {};
    await loadList();
    go(`/forum/${data.slug}`);
  }

  function saved(next: Schemas["FoSpaceOut"]) {
    space = next;
    loadList();
  }
  async function removed() {
    space = null;
    await loadList();
    go(rows.length ? `/forum/${rows[0].slug}` : "/forum");
  }
</script>

<ListDetail title="Форум">
  {#snippet list()}
    {#each rows as row (row.slug)}
      <a class="item" class:on={row.slug === slug} href={`#/forum/${row.slug}`}>
        <span class="name">{row.title}</span>
        <span class="muted small">{row.sections} разд. · {row.topics} тем · {row.machines} маш.{row.authors_only ? " · только авторы" : ""}</span>
      </a>
    {:else}
      {#if loaded}<p class="muted small pad-s">Пространств пока нет.</p>{/if}
    {/each}
  {/snippet}
  {#snippet add()}
    {#if editable}<button class="btn" onclick={() => (dialog = { slug: "", title: "" })}>+ Пространство</button>{/if}
  {/snippet}

  {#if !slug}
    <div class="pad">
      <h2>Форум</h2>
      <p class="muted">Пространство — место общения для набора машин. Игрок видит его в приложении «форум» на привязанной машине: дерево разделов, темы, ответы. Пространство создаёт автор, разделы создаёт автор (игроки смогут позже).</p>
    </div>
  {:else if !space}
    <p class="muted pad">Загрузка…</p>
  {:else}
    {@const here = space}
    <section class="screen">
      <PageHead title={here.title}>
        {#snippet sub()}адрес <code>{here.slug}</code>{/snippet}
      </PageHead>
      <nav class="tabs" aria-label="Разделы пространства">
        {#each TABS as t (t.key)}
          <a class="tab" class:on={current === t.key} href={`#/forum/${space.slug}/${t.key}`}>{t.label}</a>
        {/each}
      </nav>
      <div class="pane">
        {#if current === "overview"}
          {#key space.slug}<Overview {space} {editable} onsaved={saved} ondeleted={removed} />{/key}
        {:else if current === "sections"}
          {#key space.slug}<Sections {space} {editable} onchanged={load} />{/key}
        {:else}
          {#key space.slug}<Topics {space} {editable} />{/key}
        {/if}
      </div>
    </section>
  {/if}
</ListDetail>

{#if dialog}
  <Dialog title="Новое пространство" confirm="Создать" onsubmit={create} onclose={() => (dialog = null)}>
    <label class="row"><span class="label">Название</span><input class="field" bind:value={dialog.title} maxlength="120" /></label>
    {#if errors.title}<p class="error small">{errors.title}</p>{/if}
    <label class="row"><span class="label">Адрес (латиница, цифры, дефис)</span><input class="field mono" bind:value={dialog.slug} maxlength="48" /></label>
    {#if errors.slug}<p class="error small">{errors.slug}</p>{/if}
  </Dialog>
{/if}

<style>
  .pad { padding: 20px 32px; max-width: 560px; }
  .pad-s { padding: 4px 10px; }
  .small { font-size: 12px; margin: 0; }
  .name { font-weight: 600; }
  .screen { display: flex; flex-direction: column; min-height: 100%; }
  .tabs { display: flex; gap: 4px; padding: 0 32px; border-bottom: 1px solid var(--line-soft); }
  .tab { padding: 8px 14px; border-bottom: 2px solid transparent; color: var(--muted); text-decoration: none; }
  .tab.on { border-bottom-color: var(--accent); color: var(--text); }
  .pane { padding: 18px 32px 40px; }
  .row { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
  code { font-family: var(--mono); font-size: 12px; }
</style>
