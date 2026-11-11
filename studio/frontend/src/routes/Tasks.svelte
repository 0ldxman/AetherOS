<script lang="ts">
  // Задачи команды: доска по статусам (карточку можно перетащить в другую колонку) или таблица; фильтры «мои»,
  // исполнитель, метка, просроченные, поиск. Перемещение карточки видят все, кто на этом экране.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Avatar from "../lib/Avatar.svelte";
  import Icon from "../lib/Icon.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { go } from "../lib/router.svelte";
  import { RoomPing } from "../lib/shared.svelte";
  import { toast } from "../lib/toast.svelte";
  import { priorityColor } from "../lib/tasks";

  type Task = Schemas["TkOut"];
  // значок и цвет статуса задачи
  const STATUS: Record<string, { icon: string; color: string }> = {
    open: { icon: "circle", color: "var(--muted)" },
    doing: { icon: "clock", color: "var(--accent)" },
    review: { icon: "eye", color: "var(--warn)" },
    done: { icon: "check", color: "var(--ok)" },
  };
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
    <button class:on={view === "board"} aria-pressed={view === "board"} onclick={() => setView("board")}><Icon name="board" size={14} />Доска</button>
    <button class:on={view === "table"} aria-pressed={view === "table"} onclick={() => setView("table")}><Icon name="table" size={14} />Таблица</button>
  </div>
  <button class="btn primary add" onclick={() => { title = ""; dialog = true; }}><Icon name="plus" size={15} />Задача</button>
</PageHead>

<div class="filters">
  <label class="find">
    <Icon name="search" size={15} />
    <input placeholder="Поиск по названию и описанию" bind:value={query} aria-label="Поиск задачи" />
  </label>
  <button class="toggle" class:on={mine} aria-pressed={mine} onclick={() => (mine = !mine)}><Icon name="team" size={14} />Мои</button>
  <button class="toggle" class:on={overdue} aria-pressed={overdue} onclick={() => (overdue = !overdue)}><Icon name="alert" size={14} />Просроченные</button>
  <label class="pick" class:off={mine}>
    <Icon name="players" size={14} />
    <select bind:value={assignee} aria-label="Исполнитель" disabled={mine}>
      <option value={null}>Все исполнители</option>
      {#each meta?.authors ?? [] as author (author.id)}<option value={author.id}>{author.username}</option>{/each}
    </select>
  </label>
  <label class="pick">
    <Icon name="tag" size={14} />
    <select bind:value={label} aria-label="Метка">
      <option value="">Все метки</option>
      {#each meta?.labels ?? [] as name}<option value={name}>{name}</option>{/each}
    </select>
  </label>
  <span class="total muted">{tasks.length} {tasks.length === 1 ? "задача" : tasks.length > 1 && tasks.length < 5 ? "задачи" : "задач"}</span>
</div>

{#if view === "board"}
  <div class="kanban">
    {#each columns as column (column.value)}
      {@const tone = STATUS[column.value] ?? STATUS.open}
      <section class="column" class:over={over === column.value} style="--tone: {tone.color}" aria-label={column.label}
               ondragover={(e) => { e.preventDefault(); over = column.value; }} ondragleave={() => (over = "")}
               ondrop={(e) => { e.preventDefault(); over = ""; if (dragging !== null) move(dragging, column.value); dragging = null; }}>
        <header><span class="state"><Icon name={tone.icon} size={16} /></span><b>{column.label}</b><span class="count">{column.tasks.length}</span></header>
        {#each column.tasks as task (task.id)}
          <a class="card" class:hot={task.overdue} href="#/tasks/{task.id}" draggable="true" ondragstart={() => (dragging = task.id)} ondragend={() => (dragging = null)}>
            <span class="top"><span class="prio" style="--prio: {priorityColor(task.priority)}" title="Приоритет {task.priority} из 10">{task.priority}</span><b class="title">{task.title}</b></span>
            {#if task.labels.length}<span class="labels">{#each task.labels as name}<span class="label-chip">{name}</span>{/each}</span>{/if}
            <span class="foot">
              <span class="who">
                {#if task.assignee_names.length}
                  <span class="faces">{#each task.assignee_names.slice(0, 3) as person}<Avatar name={person} size={20} />{/each}</span>
                  {#if task.assignee_names.length === 1}<span class="names">{task.assignee_names[0]}</span>{/if}
                {:else}<span class="muted">без исполнителя</span>{/if}
              </span>
              <span class="meta">
                {#if task.due}<span class="m" class:late={task.overdue} title={task.overdue ? "Срок прошёл" : "Срок"}><Icon name={task.overdue ? "alert" : "calendar"} size={13} />{due(task.due)}</span>{/if}
                {#if task.links.length}<span class="m" title="Сущностей мира: {task.links.length}"><Icon name="link" size={13} />{task.links.length}</span>{/if}
              </span>
            </span>
          </a>
        {:else}
          <p class="empty">{dragging !== null ? "Перетащите сюда" : "Пусто"}</p>
        {/each}
      </section>
    {/each}
  </div>
{:else}
  <div class="tablewrap">
    <table class="grid">
      <thead>
        <tr>
          <th class="narrow"><button class="sort" class:on={sort === "priority"} onclick={() => (sort = "priority")}>Приоритет</button></th>
          <th>Задача</th><th>Статус</th><th>Исполнители</th>
          <th><button class="sort" class:on={sort === "due"} onclick={() => (sort = "due")}>Срок</button></th>
          <th><button class="sort" class:on={sort === "updated"} onclick={() => (sort = "updated")}>Изменена</button></th>
        </tr>
      </thead>
      <tbody>
        {#each sorted as task (task.id)}
          {@const tone = STATUS[task.status] ?? STATUS.open}
          <tr>
            <td><span class="prio" style="--prio: {priorityColor(task.priority)}">{task.priority}</span></td>
            <td><a class="ttl" href="#/tasks/{task.id}">{task.title}</a>{#each task.labels as name}<span class="label-chip">{name}</span>{/each}</td>
            <td><span class="status" style="--tone: {tone.color}"><Icon name={tone.icon} size={14} />{task.status_label}</span></td>
            <td>
              {#if task.assignee_names.length}
                <span class="who"><span class="faces">{#each task.assignee_names.slice(0, 3) as person}<Avatar name={person} size={20} />{/each}</span>{#if task.assignee_names.length === 1}<span class="names">{task.assignee_names[0]}</span>{/if}</span>
              {:else}<span class="muted">—</span>{/if}
            </td>
            <td>{#if task.due}<span class="m" class:late={task.overdue}><Icon name={task.overdue ? "alert" : "calendar"} size={13} />{due(task.due)}</span>{:else}<span class="muted">—</span>{/if}</td>
            <td class="muted">{new Date(task.updated_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</td>
          </tr>
        {:else}
          <tr><td colspan="6" class="none muted">Задач по этим условиям нет.</td></tr>
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
  .seg button { display: inline-flex; align-items: center; gap: 6px; padding: 5px 14px; background: none; border: 0; color: var(--muted); cursor: pointer; font: inherit; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .add { display: inline-flex; align-items: center; gap: 6px; }
  .seg button:focus-visible, .toggle:focus-visible, .sort:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

  .filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 0 32px 16px; }
  .find { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 220px; max-width: 340px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; }
  .toggle, .pick { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: var(--panel); color: var(--muted); font: inherit; font-size: 13px; }
  .toggle { cursor: pointer; }
  .toggle:hover, .pick:hover { border-color: var(--line); color: var(--text); }
  .toggle.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .pick select { border: 0; outline: 0; background: none; color: inherit; font: inherit; cursor: pointer; padding-right: 2px; }
  .pick select option { background: var(--raise); color: var(--text); }
  .pick.off { opacity: 0.5; }
  .total { margin-left: auto; font-size: 12.5px; }

  .kanban { display: grid; grid-template-columns: repeat(4, minmax(240px, 1fr)); gap: 14px; padding: 0 32px 32px; align-items: start; overflow-x: auto; }
  .column { display: flex; flex-direction: column; gap: 8px; min-height: 140px; padding: 10px; border: 1px solid var(--line-soft); border-top: 3px solid var(--tone); border-radius: var(--radius); background: var(--panel); transition: border-color 0.1s, background 0.1s; }
  .column.over { border-color: var(--tone); background: color-mix(in srgb, var(--tone) 7%, var(--panel)); }
  .column header { display: flex; align-items: center; gap: 8px; padding: 2px 2px 6px; font-size: 13px; }
  .state { display: inline-flex; color: var(--tone); }
  .count { margin-left: auto; min-width: 22px; padding: 0 7px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 12px; text-align: center; font-variant-numeric: tabular-nums; }
  .card { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--bg); color: var(--text); cursor: grab; transition: border-color 0.1s, transform 0.1s; }
  .card:hover { border-color: var(--line); text-decoration: none; transform: translateY(-1px); }
  .card:active { cursor: grabbing; }
  .card:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  .card.hot { border-left: 3px solid var(--danger); }
  .top { display: flex; gap: 8px; align-items: flex-start; }
  .title { font-weight: 600; overflow-wrap: anywhere; line-height: 1.35; }
  .prio { flex: none; display: inline-grid; place-items: center; min-width: 22px; height: 22px; padding: 0 4px; border-radius: 6px; background: color-mix(in srgb, var(--prio) 22%, transparent); color: var(--prio); font-size: 12px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .labels { display: flex; flex-wrap: wrap; gap: 4px; }
  .label-chip { margin-left: 6px; padding: 1px 8px; border-radius: 999px; background: var(--panel-2); color: var(--muted); font-size: 11px; }
  .labels .label-chip { margin-left: 0; }
  .foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding-top: 8px; border-top: 1px solid var(--line-soft); font-size: 12px; }
  .who { display: inline-flex; align-items: center; gap: 6px; min-width: 0; }
  .faces { display: inline-flex; flex: none; }
  .faces :global(.avatar + .avatar) { margin-left: -6px; box-shadow: 0 0 0 2px var(--bg); }
  .names { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .meta { display: inline-flex; align-items: center; gap: 10px; flex: none; color: var(--muted); }
  .m { display: inline-flex; align-items: center; gap: 4px; white-space: nowrap; }
  .late { color: var(--danger); }
  .empty { margin: 2px 0; padding: 18px 8px; border: 1px dashed var(--line-soft); border-radius: var(--radius); text-align: center; color: var(--faint); font-size: 12.5px; }

  .tablewrap { margin: 0 32px 32px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); overflow-x: auto; }
  .grid { width: 100%; border-collapse: collapse; }
  .grid th { text-align: left; font-weight: 600; color: var(--faint); font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; padding: 9px 12px; border-bottom: 1px solid var(--line-soft); white-space: nowrap; }
  .grid td { padding: 9px 12px; border-bottom: 1px solid var(--line-soft); vertical-align: middle; }
  .grid tbody tr:last-child td { border-bottom: 0; }
  .grid tbody tr:hover { background: var(--panel-2); }
  .ttl { font-weight: 600; color: var(--text); }
  .none { padding: 24px 12px; text-align: center; }
  .status { display: inline-flex; align-items: center; gap: 6px; color: var(--tone); white-space: nowrap; }
  .sort { border: 0; background: none; color: inherit; font: inherit; letter-spacing: inherit; text-transform: inherit; cursor: pointer; padding: 0; }
  .sort:hover { color: var(--text); }
  .sort.on { color: var(--text); text-decoration: underline; text-underline-offset: 3px; }
</style>
