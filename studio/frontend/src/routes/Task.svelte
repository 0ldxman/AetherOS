<script lang="ts">
  // Задача: название, описание (общий текст с курсорами), статус, приоритет 1–10, срок, исполнители, метки и сущности мира.
  // Правится на общем черновике, как остальные формы; обсуждение задачи в боковой панели «Обсуждение».
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import CodeEditor from "../lib/CodeEditor.svelte";
  import Dialog from "../lib/Dialog.svelte";
  import DraftState from "../lib/DraftState.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { go } from "../lib/router.svelte";
  import { SharedForm } from "../lib/shared.svelte";
  import { toast } from "../lib/toast.svelte";
  import { priorityColor } from "../lib/tasks";

  let { id }: { id: number } = $props();

  type Form = { title: string; body: string; status: string; priority: number; due: string | null; labels: string[]; links: string[]; assignees: number[] };
  let task = $state<Schemas["TkOut"] | null>(null);
  let meta = $state<Schemas["TkMeta"] | null>(null);
  let form = $state<Form>({ title: "", body: "", status: "open", priority: 5, due: null, labels: [], links: [], assignees: [] });
  let saved = $state("");
  let base = $state<Form | null>(null);
  let names = $state<Record<string, Schemas["TkLink"]>>({});        // подписи сущностей по пути API
  let newLabel = $state("");
  let dialog = $state(false);
  let query = $state("");
  let found = $state<Schemas["BdEntity"][]>([]);
  let busy = $state(false);

  const dirty = $derived(saved !== "" && JSON.stringify(form) !== saved);
  guardUnsaved(() => dirty && !share.ready);

  function valuesOf(data: Schemas["TkOut"]): Form {
    return { title: data.title, body: data.body, status: data.status, priority: data.priority, due: data.due ?? null, labels: [...data.labels],
             links: data.links.map((l) => l.target), assignees: [...data.assignees] };
  }

  function fill(data: Schemas["TkOut"], keepDraft = false) {
    task = data;
    if (!keepDraft) form = valuesOf(data);
    saved = JSON.stringify(valuesOf(data));
    base = valuesOf(data);
    names = { ...names, ...Object.fromEntries(data.links.map((l) => [l.target, l])) };
  }

  async function load(keepDraft = false) {
    const { data } = await api.GET("/studio/api/tasks/{task_id}", { params: { path: { task_id: id } } });
    if (data) fill(data, keepDraft);
    else toast("Задача не найдена.", "error");
  }
  onMount(async () => {
    meta = (await api.GET("/studio/api/tasks/meta")).data ?? null;
    await load();
  });

  const share = new SharedForm({ room: () => `tasks/${id}`, texts: ["title", "body"], draft: () => form, base: () => base, onRemoteSave: () => load(true) });

  async function save() {
    busy = true;
    const { data, error } = await api.PUT("/studio/api/tasks/{task_id}", { params: { path: { task_id: id } }, body: $state.snapshot(form) });
    busy = false;
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    fill(data);
    share.markSaved();
    toast("Задача сохранена.");
  }

  async function remove() {
    if (!(await ask(`Удалить задачу «${task?.title}»?`, "Её обсуждение тоже пропадёт.", "Удалить задачу"))) return;
    const { error } = await api.DELETE("/studio/api/tasks/{task_id}", { params: { path: { task_id: id } } });
    if (error) return toast(problem(error), "error");
    toast("Задача удалена.");
    go("/tasks");
  }

  function toggleAssignee(author: number) {
    form.assignees = form.assignees.includes(author) ? form.assignees.filter((a) => a !== author) : [...form.assignees, author];
  }
  function addLabel() {
    const name = newLabel.trim().toLowerCase();
    if (name && !form.labels.includes(name)) form.labels = [...form.labels, name];
    newLabel = "";
  }

  let timer: ReturnType<typeof setTimeout>;
  function search() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      found = (await api.GET("/studio/api/boards/entities", { params: { query: { q: query.trim() } } })).data ?? [];
    }, 200);
  }
  function addLink(entity: Schemas["BdEntity"]) {
    if (!form.links.includes(entity.target)) form.links = [...form.links, entity.target];
    names = { ...names, [entity.target]: { target: entity.target, kind: entity.kind, label: entity.label, link: entity.link } };
    dialog = false;
    query = "";
    found = [];
  }
  const linkOf = (target: string) => names[target] ?? { target, kind: "", label: target, link: `#/${target}` };
  const authorName = (author: number) => meta?.authors.find((a) => a.id === author)?.username ?? `#${author}`;
</script>

{#if !task}
  <p class="muted pad">Загрузка…</p>
{:else}
  <div class="task">
    <header class="head">
      <a class="btn ghost" href="#/tasks" aria-label="К задачам" title="К задачам">←</a>
      <input class="title" bind:value={form.title} aria-label="Название задачи" />
      <span class="spacer"></span>
      <DraftState {share} {dirty} saved={`изменена ${new Date(task.updated_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}`} />
      {#if task.deletable}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
      <button class="btn primary" disabled={!dirty || busy || !form.title.trim()} onclick={save}>Сохранить</button>
    </header>

    <div class="cols">
      <section class="main">
        <div class="statuses" role="radiogroup" aria-label="Статус">
          {#each meta?.statuses ?? [] as s (s.value)}
            <label class="status" class:on={form.status === s.value}><input type="radio" name="status" value={s.value} bind:group={form.status} />{s.label}</label>
          {/each}
        </div>
        <div class="body">
          <span class="label">Описание</span>
          <div class="editor">{#key share.texts.body}<CodeEditor bind:value={form.body} shared={share.texts.body ?? null} field="Описание" onsave={save} />{/key}</div>
        </div>
      </section>

      <aside class="side">
        <label class="block"><span class="label">Приоритет <b style="color: {priorityColor(form.priority)}">{form.priority}</b> из 10</span>
          <input type="range" min="1" max="10" step="1" bind:value={form.priority} aria-label="Приоритет" style="accent-color: {priorityColor(form.priority)}" />
          <span class="scale muted"><span>1 · спокойно</span><span>10 · горит</span></span></label>

        <label class="block"><span class="label">Срок</span>
          <span class="row"><input class="field" type="date" value={form.due ?? ""} onchange={(e) => (form.due = e.currentTarget.value || null)} aria-label="Срок" />
            {#if form.due}<button class="btn ghost tiny" onclick={() => (form.due = null)}>без срока</button>{/if}</span>
          {#if task.overdue}<span class="late">Срок прошёл.</span>{/if}</label>

        <div class="block">
          <span class="label">Исполнители</span>
          <div class="chips">
            {#each meta?.authors ?? [] as author (author.id)}
              <button type="button" class="chip" class:on={form.assignees.includes(author.id as number)} aria-pressed={form.assignees.includes(author.id as number)}
                      onclick={() => toggleAssignee(author.id as number)}>{author.username}</button>
            {/each}
          </div>
          {#if !form.assignees.length}<span class="muted small">Никто не назначен.</span>{:else}<span class="muted small">Назначены: {form.assignees.map(authorName).join(", ")}</span>{/if}
        </div>

        <div class="block">
          <span class="label">Метки</span>
          <div class="chips">
            {#each form.labels as name (name)}<span class="chip on">{name}<button class="x" onclick={() => (form.labels = form.labels.filter((l) => l !== name))} aria-label="Убрать метку {name}">✕</button></span>{/each}
          </div>
          <input class="field" list="task-labels" placeholder="загадка, сюжет, баг… Enter добавляет" bind:value={newLabel} onkeydown={(e) => { if (e.key === "Enter") { e.preventDefault(); addLabel(); } }} aria-label="Новая метка" />
          <datalist id="task-labels">{#each meta?.labels ?? [] as name}<option value={name}></option>{/each}</datalist>
        </div>

        <div class="block">
          <span class="label">Сущности мира</span>
          {#each form.links as target (target)}
            {@const l = linkOf(target)}
            <span class="link-row"><a href={l.link}><span class="muted">{l.kind}</span> {l.label}</a><button class="x" onclick={() => (form.links = form.links.filter((t) => t !== target))} aria-label="Убрать связь">✕</button></span>
          {:else}
            <span class="muted small">Задача ни к чему не привязана.</span>
          {/each}
          <button class="btn ghost tiny" onclick={() => { dialog = true; query = ""; found = []; }}>+ Сущность</button>
        </div>

        <p class="muted small">Создатель: {task.created_by || "—"} · {new Date(task.created_at).toLocaleDateString("ru-RU")}. Обсуждение задачи: кнопка «Обсуждение» слева внизу.</p>
      </aside>
    </div>
  </div>
{/if}

{#if dialog}
  <Dialog title="Привязать сущность" confirm="Готово" onsubmit={() => (dialog = false)} onclose={() => (dialog = false)}>
    <label><span class="label">Что</span><input class="field" bind:value={query} oninput={search} placeholder="Машина, объект, учётка, игрок, ОС, сцена, диск" /></label>
    <div class="found">
      {#each found as entity (entity.link)}
        <button type="button" class="pick" onclick={() => addLink(entity)}><span class="muted">{entity.kind}</span> <b>{entity.label}</b></button>
      {:else}
        <p class="muted small">{query.trim() ? "Ничего не нашлось." : "Начните вводить название."}</p>
      {/each}
    </div>
  </Dialog>
{/if}

<style>
  .pad { padding: 20px 32px; }
  .task { display: flex; flex-direction: column; height: 100vh; }
  .head { display: flex; align-items: center; gap: 10px; padding: 14px 20px; border-bottom: 1px solid var(--line-soft); }
  .title { flex: 1; min-width: 0; max-width: 640px; padding: 6px 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; font-size: 18px; font-weight: 600; }
  .title:hover, .title:focus { border-color: var(--line-soft); background: var(--bg); outline: none; }
  .spacer { flex: 1; }
  .cols { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 320px; }
  .main { display: flex; flex-direction: column; gap: 12px; padding: 14px 20px; min-height: 0; }
  .statuses { display: flex; flex-wrap: wrap; gap: 6px; }
  .status { display: inline-flex; align-items: center; padding: 5px 12px; border: 1px solid var(--line-soft); border-radius: 999px; cursor: pointer; color: var(--muted); }
  .status input { position: absolute; opacity: 0; pointer-events: none; }
  .status.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .status:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
  .body { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 6px; }
  .editor { flex: 1; min-height: 200px; border: 1px solid var(--line-soft); border-radius: var(--radius); overflow: hidden; }
  .side { display: flex; flex-direction: column; gap: 14px; padding: 14px 16px; border-left: 1px solid var(--line-soft); overflow-y: auto; }
  .block { display: flex; flex-direction: column; gap: 6px; }
  .scale { display: flex; justify-content: space-between; font-size: 11px; }
  .row { display: flex; gap: 6px; align-items: center; }
  .tiny { padding: 2px 8px; font-size: 12px; align-self: flex-start; }
  .late { color: var(--danger); font-size: 12px; }
  .chips { display: flex; flex-wrap: wrap; gap: 5px; }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); cursor: pointer; font: inherit; font-size: 12.5px; }
  .chip.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 0 2px; font-size: 11px; }
  .x:hover { color: var(--danger); }
  .link-row { display: flex; justify-content: space-between; align-items: center; gap: 6px; }
  .small { font-size: 12px; margin: 0; }
  .found { display: flex; flex-direction: column; gap: 4px; max-height: 300px; overflow-y: auto; }
  .pick { display: flex; gap: 8px; align-items: baseline; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--text); cursor: pointer; text-align: left; font: inherit; }
  .pick:hover { background: var(--panel-2); }
</style>
