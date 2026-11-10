<script lang="ts">
  // Задачи команды: доска по статусам (карточку можно перетащить в другую колонку) или таблица; фильтры «мои»,
  // исполнитель, метка, просроченные, поиск. Перемещение карточки видят все, кто на этом экране.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { go } from "../lib/router.svelte";
  import { RoomPing } from "../lib/shared.svelte";
  import { toast } from "../lib/toast.svelte";
  import { priorityColor } from "../lib/tasks";

  type Task = Schemas["TkOut"];
  const VIEW_KEY = "studio.tasksView";

  let tasks = $state<Task[]>([]);
  let meta = $state<Schemas["TkMeta"] | null>(null);
  let view = $state<"board" | "table">((() => { try { return localStorage.getItem(VIEW_KEY) === "table" ? "table" : "board"; } catch { return "board"; } })());
  let mine = $state(false);
  let assignee = $state<number | null>(null);
  let label = $state("");
  let overdue = $state(false);
  let query = $state("");
  let dialog = $state(false);
  let title = $state("");
  let dragging = $state<number | null>(null);
  let over = $state("");
  let sort = $state<"priority" | "due" | "updated">("priority");

  async function load() {
    const { data } = await api.GET("/studio/api/tasks", { params: { query: { mine, assignee: assignee ?? undefined, label, overdue, q: query.trim() } } });
    tasks = data ?? [];
  }
  onMount(async () => {
    meta = (await api.GET("/studio/api/tasks/meta")).data ?? null;
  });
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => { mine; assignee; label; overdue; query; clearTimeout(timer); timer = setTimeout(load, 150); });
  new RoomPing({ room: () => "tasks", onPing: load });

  function setView(next: "board" | "table") {
    view = next;
    try { localStorage.setItem(VIEW_KEY, next); } catch { /* память браузера может быть закрыта */ }
  }

  const columns = $derived((meta?.statuses ?? []).map((s) => ({ value: s.value ?? "", label: s.label ?? "", tasks: tasks.filter((t) => t.status === s.value) })));
  const sorted = $derived([...tasks].sort((a, b) =>
    sort === "priority" ? b.priority - a.priority : sort === "due" ? (a.due ?? "9999").localeCompare(b.due ?? "9999") : b.updated_at.localeCompare(a.updated_at)));

  async function move(id: number, status: string) {
    const task = tasks.find((t) => t.id === id);
    if (!task || task.status === status) return;
    task.status = status;                                         // сразу на месте, сервер подтвердит
    const { error } = await api.POST("/studio/api/tasks/{task_id}/move", { params: { path: { task_id: id } }, body: { status } });
    if (error) {
      toast(problem(error), "error");
      await load();
    }
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/tasks", { body: { title, body: "", status: "open", priority: 5, due: null, labels: [], links: [], assignees: [] } });
    if (error || !data) return toast(problem(error, "Задача не создалась."), "error");
    dialog = false;
    title = "";
    go(`/tasks/${data.id}`);
  }

  const due = (value: string | null | undefined) => value ? new Date(value + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) : "";
</script>

<PageHead title="Задачи">
  {#snippet sub()}Кто что делает: статус, исполнители, приоритет от 1 до 10, срок и сущности мира, к которым задача относится.{/snippet}
  <div class="seg" role="group" aria-label="Вид">
    <button class:on={view === "board"} aria-pressed={view === "board"} onclick={() => setView("board")}>Доска</button>
    <button class:on={view === "table"} aria-pressed={view === "table"} onclick={() => setView("table")}>Таблица</button>
  </div>
  <button class="btn primary" onclick={() => { title = ""; dialog = true; }}>+ Задача</button>
</PageHead>

<div class="filters">
  <label class="check"><input type="checkbox" bind:checked={mine} /> мои</label>
  <select class="field small" bind:value={assignee} aria-label="Исполнитель" disabled={mine}>
    <option value={null}>все исполнители</option>
    {#each meta?.authors ?? [] as author (author.id)}<option value={author.id}>{author.username}</option>{/each}
  </select>
  <select class="field small" bind:value={label} aria-label="Метка">
    <option value="">все метки</option>
    {#each meta?.labels ?? [] as name}<option value={name}>{name}</option>{/each}
  </select>
  <label class="check"><input type="checkbox" bind:checked={overdue} /> просроченные</label>
  <input class="field small find" placeholder="Поиск по названию и описанию" bind:value={query} aria-label="Поиск задачи" />
</div>

{#if view === "board"}
  <div class="kanban">
    {#each columns as column (column.value)}
      <section class="column" class:over={over === column.value} aria-label={column.label}
               ondragover={(e) => { e.preventDefault(); over = column.value; }} ondragleave={() => (over = "")}
               ondrop={(e) => { e.preventDefault(); over = ""; if (dragging !== null) move(dragging, column.value); dragging = null; }}>
        <header><b>{column.label}</b><span class="muted">{column.tasks.length}</span></header>
        {#each column.tasks as task (task.id)}
          <a class="card" href="#/tasks/{task.id}" draggable="true" ondragstart={() => (dragging = task.id)} ondragend={() => (dragging = null)}>
            <span class="top"><span class="prio" style="--prio: {priorityColor(task.priority)}" title="Приоритет {task.priority} из 10">{task.priority}</span><b class="title">{task.title}</b></span>
            {#if task.labels.length}<span class="labels">{#each task.labels as name}<span class="label-chip">{name}</span>{/each}</span>{/if}
            <span class="foot muted">
              {task.assignee_names.join(", ") || "без исполнителя"}
              {#if task.due}<span class:late={task.overdue}>· {task.overdue ? "просрочено " : "до "}{due(task.due)}</span>{/if}
              {#if task.links.length}<span>· сущностей: {task.links.length}</span>{/if}
            </span>
          </a>
        {:else}
          <p class="muted empty">Пусто{dragging !== null ? ": перетащите сюда" : ""}</p>
        {/each}
      </section>
    {/each}
  </div>
{:else}
  <div class="tablewrap">
    <table class="grid">
      <thead>
        <tr>
          <th><button class="sort" class:on={sort === "priority"} onclick={() => (sort = "priority")}>Приоритет</button></th>
          <th>Задача</th><th>Статус</th><th>Исполнители</th>
          <th><button class="sort" class:on={sort === "due"} onclick={() => (sort = "due")}>Срок</button></th>
          <th><button class="sort" class:on={sort === "updated"} onclick={() => (sort = "updated")}>Изменена</button></th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as task (task.id)}
          <tr>
            <td><span class="prio" style="--prio: {priorityColor(task.priority)}">{task.priority}</span></td>
            <td><a href="#/tasks/{task.id}">{task.title}</a>{#each task.labels as name}<span class="label-chip">{name}</span>{/each}</td>
            <td>{task.status_label}</td>
            <td class="muted">{task.assignee_names.join(", ") || "—"}</td>
            <td class:late={task.overdue}>{due(task.due) || "—"}</td>
            <td class="muted">{new Date(task.updated_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</td>
          </tr>
        {:else}
          <tr><td colspan="6" class="muted">Задач нет.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

{#if dialog}
  <Dialog title="Новая задача" confirm="Создать" disabled={!title.trim()} onsubmit={create} onclose={() => (dialog = false)}>
    <label><span class="label">Что сделать</span><input class="field" bind:value={title} placeholder="Придумать загадку для порта" /></label>
    <p class="muted small">Исполнителей, срок, приоритет и сущности зададите на странице задачи.</p>
  </Dialog>
{/if}

<style>
  .seg { display: inline-flex; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 5px 14px; background: none; border: 0; color: var(--muted); cursor: pointer; font: inherit; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 0 32px 14px; }
  .check { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  .small { width: auto; padding: 4px 8px; font-size: 13px; }
  .find { min-width: 240px; flex: 1; max-width: 360px; }
  .kanban { display: grid; grid-template-columns: repeat(4, minmax(220px, 1fr)); gap: 12px; padding: 0 32px 32px; align-items: start; overflow-x: auto; }
  .column { display: flex; flex-direction: column; gap: 8px; min-height: 120px; padding: 10px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); transition: border-color 0.1s; }
  .column.over { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--panel)); }
  .column header { display: flex; justify-content: space-between; align-items: baseline; padding: 0 2px 4px; font-size: 13px; }
  .card { display: flex; flex-direction: column; gap: 6px; padding: 9px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--text); cursor: grab; }
  .card:hover { border-color: var(--line); text-decoration: none; }
  .card:active { cursor: grabbing; }
  .top { display: flex; gap: 8px; align-items: flex-start; }
  .title { font-weight: 600; overflow-wrap: anywhere; }
  .prio { flex: none; display: inline-grid; place-items: center; min-width: 20px; height: 20px; padding: 0 4px; border-radius: 6px; background: color-mix(in srgb, var(--prio) 22%, transparent); color: var(--prio); font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .labels { display: flex; flex-wrap: wrap; gap: 4px; }
  .label-chip { margin-left: 4px; padding: 0 7px; border-radius: 999px; background: var(--panel-2); color: var(--muted); font-size: 11px; }
  .labels .label-chip { margin-left: 0; }
  .foot { display: flex; flex-wrap: wrap; gap: 4px; font-size: 12px; }
  .late { color: var(--danger); }
  .empty { margin: 4px 2px; font-size: 12.5px; }
  .tablewrap { padding: 0 32px 32px; overflow-x: auto; }
  .grid { width: 100%; border-collapse: collapse; }
  .grid th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; padding: 6px 8px; border-bottom: 1px solid var(--line-soft); }
  .grid td { padding: 7px 8px; border-bottom: 1px solid var(--line-soft); }
  .sort { border: 0; background: none; color: inherit; font: inherit; cursor: pointer; padding: 0; }
  .sort.on { color: var(--text); text-decoration: underline; text-underline-offset: 3px; }
</style>
