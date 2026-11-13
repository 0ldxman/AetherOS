<script lang="ts">
  // Темы пространства: список с фильтрами, выбранная тема с сообщениями, модерация (скрыть, вернуть, закрепить, закрыть) и голос персонажа.
  import { api, problem, type Schemas } from "../../lib/api";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  type Row = Schemas["FoTopicRow"];
  let { space, editable }: { space: Schemas["FoSpaceOut"]; editable: boolean } = $props();

  let rows = $state<Row[]>([]);
  let section = $state<number | "">("");
  let hidden = $state(false);
  let q = $state("");
  let topic = $state<Schemas["FoTopicOut"] | null>(null);
  let say = $state({ name: "SYSOP", kind: "character", text: "", parent: null as number | null });
  let fresh = $state<{ section: number | ""; name: string; title: string; text: string; kind: string } | null>(null);
  let busy = $state(false);

  async function load() {
    const { data } = await api.GET("/studio/api/forum/spaces/{slug}/topics", { params: { path: { slug: space.slug }, query: { section: section || undefined, hidden, q } } });
    rows = data ?? [];
  }
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { section; hidden; q; clearTimeout(timer); timer = setTimeout(load, 200); });

  async function open(id: number) {
    topic = (await api.GET("/studio/api/forum/topics/{topic_id}", { params: { path: { topic_id: id } } })).data ?? null;
    say.parent = null;
  }
  function show(next: Schemas["FoTopicOut"] | undefined) { if (next) { topic = next; load(); } }

  async function flags(patch: { pinned?: boolean; locked?: boolean }) {
    if (!topic) return;
    show((await api.PUT("/studio/api/forum/topics/{topic_id}", { params: { path: { topic_id: topic.id } }, body: patch })).data);
  }
  async function hide(post: Schemas["FoPost"]) {
    const reason = post.root ? prompt("Причина (необязательно)") ?? "" : "";
    show((await api.POST("/studio/api/forum/posts/{post_id}/hide", { params: { path: { post_id: post.id } }, body: { reason } })).data);
  }
  async function restore(post: Schemas["FoPost"]) {
    show((await api.POST("/studio/api/forum/posts/{post_id}/restore", { params: { path: { post_id: post.id } } })).data);
  }
  async function reply() {
    if (!topic) return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/forum/topics/{topic_id}/posts", { params: { path: { topic_id: topic.id } }, body: { name: say.name, text: say.text, kind: say.kind, parent: say.parent } });
    busy = false;
    if (error || !data) return toast(Object.values((error as { fields?: Record<string, string> } | undefined)?.fields ?? {})[0] ?? problem(error), "error");
    say.text = "";
    say.parent = null;
    show(data);
  }
  async function start() {
    if (!fresh || fresh.section === "") return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/forum/topics", { body: { section: fresh.section, name: fresh.name, title: fresh.title, text: fresh.text, kind: fresh.kind } });
    busy = false;
    if (error || !data) return toast(Object.values((error as { fields?: Record<string, string> } | undefined)?.fields ?? {})[0] ?? problem(error), "error");
    fresh = null;
    show(data);
  }
  const flatSections = $derived.by(() => {
    const out: { id: number; title: string; depth: number }[] = [];
    const walk = (parent: number | null, depth: number) => { for (const s of space.sections.filter((x) => x.parent === parent)) { out.push({ id: s.id, title: s.title, depth }); walk(s.id, depth + 1); } };
    walk(null, 0);
    return out;
  });
</script>

<div class="split">
  <aside class="list">
    <div class="filters">
      <select class="field" bind:value={section} aria-label="Раздел"><option value="">Все разделы</option>
        {#each flatSections as s (s.id)}<option value={s.id}>{" ".repeat(s.depth)}{s.title}</option>{/each}</select>
      <input class="field" bind:value={q} placeholder="поиск по тексту" aria-label="Поиск" />
      <label class="check"><input type="checkbox" bind:checked={hidden} />Скрытые</label>
    </div>
    {#each rows as row (row.id)}
      <button class="item" class:on={topic?.id === row.id} onclick={() => open(row.id)}>
        <span class="name">{row.pinned ? "▲ " : ""}{row.title}{row.locked ? " [закрыта]" : ""}</span>
        <span class="muted small">{row.section_title} · {row.name} · {row.replies} отв. · {when(row.bumped_at)}</span>
      </button>
    {:else}
      <p class="muted small">Тем нет.</p>
    {/each}
    {#if editable}<button class="btn" onclick={() => (fresh = { section: typeof section === "number" ? section : "", name: "SYSOP", title: "", text: "", kind: "character" })}>+ Тема от персонажа</button>{/if}
  </aside>

  <div class="view">
    {#if fresh}
      <h3>Новая тема</h3>
      <label class="row"><span class="label">Раздел</span><select class="field" bind:value={fresh.section}><option value="">—</option>{#each flatSections as s (s.id)}<option value={s.id}>{" ".repeat(s.depth)}{s.title}</option>{/each}</select></label>
      <div class="inline">
        <label class="row"><span class="label">Подпись</span><input class="field" bind:value={fresh.name} maxlength="16" /></label>
        <label class="row"><span class="label">От кого</span><select class="field" bind:value={fresh.kind}><option value="character">Персонаж</option><option value="system">Система (показание)</option></select></label>
      </div>
      <label class="row"><span class="label">Заголовок</span><input class="field" bind:value={fresh.title} maxlength="160" /></label>
      <label class="row"><span class="label">Текст</span><textarea class="field" rows="5" bind:value={fresh.text}></textarea></label>
      <div class="tools"><button class="btn primary" disabled={busy || fresh.section === "" || !fresh.title.trim() || !fresh.text.trim()} onclick={start}>Опубликовать</button><button class="btn ghost" onclick={() => (fresh = null)}>Отмена</button></div>
    {:else if topic}
      <header class="head">
        <h3>{topic.title}</h3>
        {#if editable}
          <button class="btn ghost" onclick={() => flags({ pinned: !topic!.pinned })}>{topic.pinned ? "Открепить" : "Закрепить"}</button>
          <button class="btn ghost" onclick={() => flags({ locked: !topic!.locked })}>{topic.locked ? "Открыть" : "Закрыть"}</button>
        {/if}
      </header>
      {#each topic.posts as post (post.id)}
        <article class="post" class:gone={post.hidden} class:system={post.kind === "system"}>
          <div class="bar">
            <strong>{post.name}</strong>
            {#if post.player}<span class="muted small">игрок {post.player}</span>{:else}<span class="muted small">{post.kind === "system" ? "система" : "автор"}</span>{/if}
            <span class="muted small">{when(post.created_at)}</span>
            {#if post.parent}<span class="muted small">→ #{post.parent}</span>{/if}
            <span class="muted small">#{post.id}</span>
          </div>
          <p>{post.text}</p>
          {#if post.hidden}<p class="muted small">Скрыто{post.hidden_reason ? `: ${post.hidden_reason}` : ""}</p>{/if}
          {#if editable}
            <div class="tools">
              {#if post.hidden}<button class="link" onclick={() => restore(post)}>вернуть</button>{:else}<button class="link" onclick={() => hide(post)}>{post.root ? "скрыть тему" : "скрыть"}</button>{/if}
              <button class="link" onclick={() => (say.parent = post.id)}>ответить от персонажа</button>
            </div>
          {/if}
        </article>
      {/each}
      {#if editable}
        <div class="reply">
          <span class="muted small">{say.parent ? `Ответ на #${say.parent}` : "Ответ в тему"}{#if say.parent} <button class="link" onclick={() => (say.parent = null)}>сбросить</button>{/if}</span>
          <div class="inline">
            <input class="field" bind:value={say.name} maxlength="16" aria-label="Подпись" />
            <select class="field" bind:value={say.kind} aria-label="От кого"><option value="character">Персонаж</option><option value="system">Система</option></select>
          </div>
          <textarea class="field" rows="3" bind:value={say.text} placeholder="текст"></textarea>
          <div class="tools"><button class="btn primary" disabled={busy || !say.text.trim() || !say.name.trim()} onclick={reply}>Отправить</button></div>
        </div>
      {/if}
    {:else}
      <p class="muted">Выберите тему слева.</p>
    {/if}
  </div>
</div>

<style>
  .split { display: grid; grid-template-columns: 300px minmax(0, 1fr); gap: 24px; align-items: start; }
  .list { display: flex; flex-direction: column; gap: 2px; }
  .filters { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
  .item { display: flex; flex-direction: column; gap: 1px; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .item:hover { background: var(--panel); }
  .item.on { background: var(--accent-soft); }
  .name { font-weight: 600; overflow-wrap: anywhere; }
  .view { display: flex; flex-direction: column; gap: 10px; max-width: 700px; min-width: 0; }
  .head { display: flex; align-items: center; gap: 8px; }
  .head h3 { flex: 1; margin: 0; }
  .post { padding: 8px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .post.system { border-style: dashed; color: var(--muted); }
  .post.gone { opacity: 0.55; }
  .post p { margin: 4px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  .bar { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; }
  .tools { display: flex; gap: 12px; }
  .link { padding: 0; border: 0; background: none; color: var(--accent); font: inherit; font-size: 12px; cursor: pointer; }
  .reply { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; border-top: 1px solid var(--line-soft); }
  .inline { display: flex; gap: 12px; }
  .row { display: flex; flex-direction: column; gap: 4px; }
  .check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .small { font-size: 12px; }
</style>
