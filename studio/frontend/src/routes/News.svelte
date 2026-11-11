<script lang="ts">
  // Новости команды игрокам: список слева, редактор справа. Новость пишется на общем черновике; публикация сразу или по времени.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import DraftState from "../lib/DraftState.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { canAct, canEdit } from "../lib/me.svelte";
  import { go } from "../lib/router.svelte";
  import { SharedForm } from "../lib/shared.svelte";
  import { when } from "../lib/time";
  import { toast } from "../lib/toast.svelte";

  let { id }: { id: number | null } = $props();

  type Form = { title: string; body: string; mode: string; at: string; pinned: boolean; important: boolean };
  let rows = $state<Schemas["NwRow"][]>([]);
  let post = $state<Schemas["NwOut"] | null>(null);
  let form = $state<Form>({ title: "", body: "", mode: "draft", at: "", pinned: false, important: false });
  let base = $state<Form | null>(null);
  let saved = $state("");
  let busy = $state(false);
  let loaded = $state(false);

  const editable = canEdit("news");
  const dirty = $derived(saved !== "" && JSON.stringify(form) !== saved);
  guardUnsaved(() => dirty && !share.ready);

  const STATUS: Record<string, string> = { draft: "черновик", scheduled: "запланирована", published: "опубликована" };
  const local = (stamp: string) => {
    const d = new Date(stamp);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  };
  const valuesOf = (p: Schemas["NwOut"]): Form => ({
    title: p.title, body: p.body, mode: p.status === "draft" ? "draft" : p.status === "scheduled" ? "later" : "now",
    at: p.publish_at && p.status === "scheduled" ? local(p.publish_at) : "", pinned: p.pinned, important: p.important,
  });

  async function loadList() {
    rows = (await api.GET("/studio/api/news")).data ?? [];
    loaded = true;
  }
  async function load(keepDraft = false) {
    if (!id) return;
    const { data } = await api.GET("/studio/api/news/{post_id}", { params: { path: { post_id: id } } });
    if (!data) return toast("Новость не найдена.", "error");
    post = data;
    base = valuesOf(data);
    if (!keepDraft) form = valuesOf(data);
    saved = JSON.stringify(valuesOf(data));
  }
  onMount(async () => {
    await loadList();
    if (id === null && rows.length) return go(`/news/${rows[0].id}`);
    await load();
  });

  const share = new SharedForm({ room: () => (id ? `news/${id}` : ""), texts: ["title", "body"], draft: () => form, base: () => base,
                                 onRemoteSave: () => { load(true); loadList(); } });

  function publishAt(): string | null {
    if (form.mode === "draft") return null;
    if (form.mode === "later") return form.at ? new Date(form.at).toISOString() : null;
    return post?.status === "published" && post.publish_at ? post.publish_at : new Date().toISOString();
  }

  async function save() {
    if (!id) return;
    if (form.mode === "later" && !form.at) return toast("Укажите, когда публиковать.", "error");
    if (form.mode === "now" && post?.status !== "published" && !(await ask("Опубликовать новость?", "Её сразу увидят все игроки с приложением news.", "Опубликовать"))) return;
    busy = true;
    const { data, error } = await api.PUT("/studio/api/news/{post_id}", { params: { path: { post_id: id } },
      body: { title: form.title, body: form.body, publish_at: publishAt(), pinned: form.pinned, important: form.important } });
    busy = false;
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    post = data;
    base = valuesOf(data);
    form = valuesOf(data);
    saved = JSON.stringify(valuesOf(data));
    share.markSaved();
    loadList();
    toast(data.status === "published" ? "Новость опубликована." : data.status === "scheduled" ? `Новость выйдет ${when(data.publish_at)}.` : "Черновик сохранён.");
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/news", { body: { title: "Новая новость", body: "", publish_at: null, pinned: false, important: false } });
    if (error || !data) return toast(problem(error, "Не создалось."), "error");
    go(`/news/${data.id}`);
  }

  async function remove() {
    if (!post || !(await ask(`Удалить новость «${post.title}»?`, post.status === "published" ? "Она пропадёт у игроков." : "", "Удалить новость"))) return;
    const { error } = await api.DELETE("/studio/api/news/{post_id}", { params: { path: { post_id: post.id } } });
    if (error) return toast(problem(error), "error");
    toast("Новость удалена.");
    go("/news");
  }
</script>

<ListDetail title="Новости">
  {#snippet list()}
    {#each rows as r (r.id)}
      <a class="item" class:on={r.id === id} href={`#/news/${r.id}`}>
        <span class="title-row">{#if r.pinned}<span class="pin" title="Закреплена">●</span>{/if}{r.title}</span>
        <span class="muted small"><span class="st {r.status}">{STATUS[r.status]}</span>{#if r.publish_at && r.status !== "draft"}&nbsp;· {when(r.publish_at)}{/if}{#if r.status === "published"}&nbsp;· прочли {r.reads}{/if}</span>
      </a>
    {:else}
      {#if loaded}<p class="muted small pad-s">Новостей пока нет.</p>{/if}
    {/each}
  {/snippet}
  {#snippet add()}
    {#if editable}<button class="btn" onclick={create}>+ Новость</button>{/if}
  {/snippet}

  {#if !id}
    <div class="pad"><h2>Новости</h2><p class="muted">Объявления команды игрокам: обновления, техработы, события. Видны всем, у кого на столе приложение news.</p></div>
  {:else if !post}
    <p class="muted pad">Загрузка…</p>
  {:else}
    <section class="editor">
      <header class="head">
        <input class="title" bind:value={form.title} aria-label="Заголовок" disabled={!editable} />
        <span class="spacer"></span>
        <DraftState {share} {dirty} saved={STATUS[post.status]} />
        {#if canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
        <button class="btn primary" disabled={!dirty || busy || !editable || !form.title.trim()} onclick={save}>
          {form.mode === "now" && post.status !== "published" ? "Опубликовать" : "Сохранить"}</button>
      </header>

      <div class="opts">
        <div class="seg" role="radiogroup" aria-label="Публикация">
          <label class:on={form.mode === "draft"}><input type="radio" bind:group={form.mode} value="draft" disabled={!editable} />Черновик</label>
          <label class:on={form.mode === "now"}><input type="radio" bind:group={form.mode} value="now" disabled={!editable} />{post.status === "published" ? "Опубликована" : "Опубликовать сейчас"}</label>
          <label class:on={form.mode === "later"}><input type="radio" bind:group={form.mode} value="later" disabled={!editable} />По расписанию</label>
        </div>
        {#if form.mode === "later"}<input class="field when" type="datetime-local" bind:value={form.at} aria-label="Когда публиковать" disabled={!editable} />{/if}
        <label class="check"><input type="checkbox" bind:checked={form.pinned} disabled={!editable} />Закрепить сверху</label>
        <label class="check" title="Всплывает уведомлением на столе, пока игрок не прочтёт"><input type="checkbox" bind:checked={form.important} disabled={!editable} />Важная</label>
        {#if post.status === "published"}<span class="muted small">Прочитали: {post.reads}</span>{/if}
      </div>

      <div class="body">
        {#key share.texts.body}<CodeEditor bind:value={form.body} shared={share.texts.body ?? null} field="Текст новости" onsave={save} />{/key}
      </div>
      <p class="muted small hint">Разметка: <code># заголовок</code>, <code>- список</code>, <code>&gt; цитата</code>, <code>**жирный**</code>, <code>*курсив*</code>, <code>`код`</code>, ссылки http(s). Игроки читают на английском.</p>
    </section>
  {/if}
</ListDetail>

<style>
  .pad { padding: 20px 32px; max-width: 560px; }
  .pad-s { padding: 4px 10px; }
  .small { font-size: 12px; margin: 0; }
  .title-row { display: flex; gap: 6px; align-items: baseline; }
  .pin { color: var(--accent); font-size: 9px; }
  .st.draft { color: var(--faint); }
  .st.scheduled { color: var(--warn); }
  .st.published { color: var(--ok); }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 28px; height: 100vh; box-sizing: border-box; }
  .head { display: flex; align-items: center; gap: 10px; }
  .title { flex: 1; min-width: 0; max-width: 640px; padding: 6px 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; font-size: 18px; font-weight: 600; }
  .title:hover, .title:focus { border-color: var(--line-soft); background: var(--bg); outline: none; }
  .spacer { flex: 1; }
  .opts { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
  .seg { display: flex; gap: 4px; }
  .seg label { display: inline-flex; align-items: center; padding: 4px 12px; border: 1px solid var(--line-soft); border-radius: 999px; color: var(--muted); cursor: pointer; font-size: 13px; }
  .seg label.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .seg input { position: absolute; opacity: 0; pointer-events: none; }
  .seg label:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .when { width: 210px; }
  .check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .body { flex: 1; min-height: 240px; border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; }
  .hint { margin-bottom: 12px; }
  code { font-family: var(--mono); font-size: 11.5px; }
</style>
