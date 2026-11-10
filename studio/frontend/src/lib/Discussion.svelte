<script lang="ts">
  // Боковая панель обсуждения сущности: ветки с ответами, упоминания @имя, «решено», правка и удаление своих сообщений.
  import { tick } from "svelte";
  import { api, problem, type Schemas } from "./api";
  import { ask } from "./confirm.svelte";
  import { discussion } from "./discussion.svelte";
  import { toast } from "./toast.svelte";
  import { go } from "./router.svelte";
  import { priorityColor } from "./tasks";

  let { target, onchange }: { target: string; onchange?: (open: number) => void } = $props();

  type Thread = Schemas["CmThread"];
  let threads = $state<Thread[]>([]);
  let loaded = $state(false);
  let authors = $state<string[]>([]);
  let draft = $state("");
  let replies = $state<Record<number, string>>({});
  let replying = $state<number | null>(null);
  let editing = $state<{ id: number; text: string } | null>(null);
  let showResolved = $state(false);
  let busy = $state(false);
  let suggest = $state<{ key: string; list: string[] } | null>(null);
  let typing: HTMLTextAreaElement | null = null;          // поле, в котором набирают упоминание

  const open = $derived(threads.filter((t) => !t.resolved_at));
  const taskable = $derived(!target.startsWith("tasks") && target !== "tasks");

  // задачи про эту сущность и новая задача про неё; задача из ветки обсуждения
  let related = $state<Schemas["TkOut"][]>([]);
  $effect(() => {
    const now = target;
    related = [];
    if (now.startsWith("tasks")) return;
    api.GET("/studio/api/tasks", { params: { query: { target: now } } }).then(({ data }) => { if (now === target) related = data ?? []; });
  });
  async function newTask() {
    const { data, error } = await api.POST("/studio/api/tasks", { body: { title: "Новая задача", body: "", status: "open", priority: 5, due: null, labels: [], links: [target], assignees: [] } });
    if (error || !data) return toast(problem(error, "Задача не создалась."), "error");
    go(`/tasks/${data.id}`);
  }
  async function toTask(thread: Thread) {
    const { data, error } = await api.POST("/studio/api/tasks/from-thread", { body: { thread: thread.id } });
    if (error || !data) return toast(problem(error, "Задача не создалась."), "error");
    toast("Задача создана, ссылка на неё оставлена в ветке.");
    go(`/tasks/${data.id}`);
  }
  const resolved = $derived(threads.filter((t) => t.resolved_at));

  async function load() {
    const { data } = await api.GET("/studio/api/comments", { params: { query: { target } } });
    threads = data ?? [];
    loaded = true;
    onchange?.(threads.filter((t) => !t.resolved_at).length);
  }
  $effect(() => { target; loaded = false; load(); });
  $effect(() => {
    if (discussion.open && !authors.length) api.GET("/studio/api/comments/authors").then(({ data }) => (authors = (data ?? []).map((a) => a.username)));
  });

  function replace(thread: Thread) {
    threads = threads.map((t) => (t.id === thread.id ? thread : t));
    if (!threads.some((t) => t.id === thread.id)) threads = [...threads, thread];
    onchange?.(threads.filter((t) => !t.resolved_at).length);
  }

  async function start() {
    if (!draft.trim()) return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/comments", { body: { target, text: draft, parent: null } });
    busy = false;
    if (error || !data) return toast(problem(error, "Сообщение не отправилось."), "error");
    draft = "";
    replace(data);
  }

  async function reply(thread: Thread) {
    const text = replies[thread.id] ?? "";
    if (!text.trim()) return;
    busy = true;
    const { data, error } = await api.POST("/studio/api/comments", { body: { target, text, parent: thread.id } });
    busy = false;
    if (error || !data) return toast(problem(error, "Ответ не отправился."), "error");
    replies[thread.id] = "";
    replying = null;
    replace(data);
  }

  async function setResolved(thread: Thread, value: boolean) {
    const { data, error } = await api.POST("/studio/api/comments/{comment_id}/resolve", { params: { path: { comment_id: thread.id } }, body: { resolved: value } });
    if (error || !data) return toast(problem(error), "error");
    replace(data);
    toast(value ? "Обсуждение решено." : "Обсуждение снова открыто.");
  }

  async function saveEdit() {
    if (!editing) return;
    const { error } = await api.PUT("/studio/api/comments/{comment_id}", { params: { path: { comment_id: editing.id } }, body: { text: editing.text } });
    if (error) return toast(problem(error), "error");
    editing = null;
    await load();
  }

  async function remove(message: Schemas["CmMessage"], first: boolean) {
    const text = first ? "Это первое сообщение: вместе с ним удалится вся ветка с ответами." : "";
    if (!(await ask("Удалить сообщение?", text, "Удалить"))) return;
    const { error } = await api.DELETE("/studio/api/comments/{comment_id}", { params: { path: { comment_id: message.id } } });
    if (error) return toast(problem(error), "error");
    await load();
  }

  // подсказка упоминаний: слово перед курсором начинается с @
  function mention(event: Event, key: string) {
    const area = event.currentTarget as HTMLTextAreaElement;
    typing = area;
    const before = area.value.slice(0, area.selectionStart);
    const found = before.match(/(?:^|\s)@([\w.+-]*)$/);
    if (!found) { suggest = null; return; }
    const part = found[1].toLowerCase();
    const list = authors.filter((name) => name.toLowerCase().startsWith(part)).slice(0, 6);
    suggest = list.length ? { key, list } : null;
  }
  // имя встаёт на место набранного «@на» у курсора, курсор сразу после имени
  async function insert(key: string, name: string) {
    const area = typing;
    const text = key === "new" ? draft : replies[+key] ?? "";
    const caret = area?.selectionStart ?? text.length;
    const before = text.slice(0, caret).replace(/@([\w.+-]*)$/, `@${name} `);
    const next = before + text.slice(caret);
    if (key === "new") draft = next;
    else replies[+key] = next;
    suggest = null;
    await tick();
    area?.focus();
    area?.setSelectionRange(before.length, before.length);
  }

  function parts(text: string): { text: string; mention: boolean }[] {
    return text.split(/(@[\w.+-]+)/).filter(Boolean).map((piece) => ({ text: piece, mention: piece.startsWith("@") && authors.includes(piece.slice(1)) }));
  }
  const when = (value: string) => new Date(value).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  function keydown(event: KeyboardEvent, send: () => void) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); send(); }
    if (event.key === "Escape") suggest = null;
  }
</script>

{#snippet messages(thread: Thread)}
  {#each thread.messages as m, i (m.id)}
    <div class="msg">
      <div class="meta">
        <b>{m.username}</b>
        <span class="muted">{when(m.created_at)}{m.edited_at ? " · изменено" : ""}</span>
        <span class="spacer"></span>
        {#if m.own}
          <button class="link" onclick={() => (editing = { id: m.id, text: m.text })}>Править</button>
          <button class="link danger" onclick={() => remove(m, i === 0)}>Удалить</button>
        {/if}
      </div>
      {#if editing?.id === m.id}
        <textarea class="field" rows="3" bind:value={editing.text} onkeydown={(e) => keydown(e, saveEdit)}></textarea>
        <div class="row"><button class="btn ghost tiny" onclick={() => (editing = null)}>Отмена</button><button class="btn primary tiny" onclick={saveEdit}>Сохранить</button></div>
      {:else}
        <p class="text">{#each parts(m.text) as piece}{#if piece.mention}<span class="at">{piece.text}</span>{:else}{piece.text}{/if}{/each}</p>
      {/if}
    </div>
  {/each}
{/snippet}

{#snippet composer(key: string, value: string, set: (v: string) => void, send: () => void, label: string, placeholder: string)}
  <div class="composer">
    <textarea class="field" rows="3" {placeholder} value={value} aria-label={label}
              oninput={(e) => { set(e.currentTarget.value); mention(e, key); }} onkeydown={(e) => keydown(e, send)}></textarea>
    {#if suggest?.key === key}
      <div class="suggest" role="listbox" aria-label="Кого упомянуть">
        {#each suggest.list as name}<button type="button" role="option" aria-selected="false" onclick={() => insert(key, name)}>@{name}</button>{/each}
      </div>
    {/if}
    <div class="row"><span class="muted hint">@имя упоминает автора · Ctrl+Enter отправляет</span><button class="btn primary tiny" disabled={busy || !value.trim()} onclick={send}>{label}</button></div>
  </div>
{/snippet}

<aside class="drawer" aria-label="Обсуждение">
  <header class="head">
    <b>Обсуждение</b>
    <span class="muted small">этой страницы</span>
    <span class="spacer"></span>
    <button class="btn ghost tiny" onclick={() => (discussion.open = false)} aria-label="Закрыть обсуждение">✕</button>
  </header>

  {#if taskable}
    <section class="tasks">
      <div class="row"><b class="small">Задачи про это{related.length ? ` · ${related.length}` : ""}</b><span class="spacer"></span><button class="btn ghost tiny" onclick={newTask}>+ Задача про это</button></div>
      {#each related as task (task.id)}
        <a class="task" href="#/tasks/{task.id}"><span class="prio" style="--prio: {priorityColor(task.priority)}">{task.priority}</span>{task.title}<span class="muted small">{task.status_label}</span></a>
      {/each}
    </section>
  {/if}

  {@render composer("new", draft, (v) => (draft = v), start, "Начать обсуждение", "Что нужно обсудить?")}

  {#if !loaded}
    <p class="muted small">Загрузка…</p>
  {:else if !threads.length}
    <p class="muted small">Здесь ещё не обсуждали. Начните ветку: например, попросите проверить загадку или оставьте заметку для команды.</p>
  {/if}

  {#each open as thread (thread.id)}
    <section class="thread">
      {@render messages(thread)}
      <div class="row foot">
        {#if replying === thread.id}
          <div class="grow">{@render composer(String(thread.id), replies[thread.id] ?? "", (v) => (replies[thread.id] = v), () => reply(thread), "Ответить", "Ваш ответ")}</div>
        {:else}
          <button class="btn ghost tiny" onclick={() => (replying = thread.id)}>Ответить</button>
          <span class="spacer"></span>
          {#if taskable}<button class="btn ghost tiny" onclick={() => toTask(thread)} title="Создать задачу из этой ветки">Сделать задачей</button>{/if}
          <button class="btn ghost tiny" onclick={() => setResolved(thread, true)}>✓ Решено</button>
        {/if}
      </div>
    </section>
  {/each}

  {#if resolved.length}
    <button class="link toggle" onclick={() => (showResolved = !showResolved)} aria-expanded={showResolved}>{showResolved ? "▾" : "▸"} Решённые ({resolved.length})</button>
    {#if showResolved}
      {#each resolved as thread (thread.id)}
        <section class="thread done">
          {@render messages(thread)}
          <div class="row foot"><span class="muted small">решено: {thread.resolved_by}</span><span class="spacer"></span><button class="btn ghost tiny" onclick={() => setResolved(thread, false)}>Открыть снова</button></div>
        </section>
      {/each}
    {/if}
  {/if}
</aside>

<style>
  .drawer { position: fixed; top: 0; right: 0; bottom: 0; width: min(420px, 100vw); z-index: 40; display: flex; flex-direction: column; gap: 12px;
            padding: 14px 16px 24px; background: var(--panel); border-left: 1px solid var(--line); box-shadow: -12px 0 32px rgba(0, 0, 0, 0.35); overflow-y: auto; box-sizing: border-box; }
  .head { display: flex; align-items: center; gap: 8px; }
  .spacer { flex: 1; }
  .small { font-size: 12px; margin: 0; }
  .hint { font-size: 11.5px; }
  .tiny { padding: 2px 10px; font-size: 12.5px; }
  .row { display: flex; align-items: center; gap: 8px; }
  .grow { flex: 1; }
  .composer { position: relative; display: flex; flex-direction: column; gap: 6px; }
  .composer .row { justify-content: space-between; }
  .suggest { position: absolute; top: 72px; left: 8px; z-index: 2; display: flex; flex-direction: column; background: var(--raise); border: 1px solid var(--line); border-radius: var(--radius-s); padding: 4px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
  .suggest button { background: none; border: 0; color: var(--text); text-align: left; padding: 4px 10px; cursor: pointer; border-radius: var(--radius-s); font: inherit; }
  .suggest button:hover, .suggest button:focus-visible { background: var(--accent-soft); }
  .thread { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg, transparent); }
  .thread.done { opacity: 0.75; }
  .msg { display: flex; flex-direction: column; gap: 2px; }
  .msg + .msg { padding-top: 8px; border-top: 1px solid var(--line-soft); }
  .meta { display: flex; align-items: baseline; gap: 8px; font-size: 12.5px; }
  .text { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
  .at { color: var(--accent); font-weight: 600; }
  .link { background: none; border: 0; padding: 0; color: var(--muted); cursor: pointer; font: inherit; font-size: 12px; }
  .link:hover { color: var(--text); }
  .link.danger:hover { color: var(--danger); }
  .toggle { font-size: 12.5px; align-self: flex-start; }
  .foot { padding-top: 4px; }
  .tasks { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius); }
  .task { display: flex; align-items: center; gap: 8px; padding: 3px 0; color: var(--text); }
  .task .small { margin-left: auto; }
  .prio { display: inline-grid; place-items: center; min-width: 18px; height: 18px; border-radius: 5px; background: color-mix(in srgb, var(--prio) 22%, transparent); color: var(--prio); font-size: 11px; font-weight: 700; }
</style>
