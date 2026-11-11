<script lang="ts">
  // Главная Студии: лента изменений команды, игроки в мире прямо сейчас и что в мире требует внимания.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import Icon from "../lib/Icon.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { level, me } from "../lib/me.svelte";
  import { discussion } from "../lib/discussion.svelte";
  import { priorityColor } from "../lib/tasks";
  import { checkNotes, notes as noteState } from "../lib/notes.svelte";
  import { untrack } from "svelte";

  type Change = Schemas["TeamChange"];
  const PAGE = 15;

  let dash = $state<Schemas["DashOut"] | null>(null);
  let changes = $state<Change[]>([]);
  let mine = $state(false);
  let section = $state("");
  let more = $state(false);
  let loading = $state(false);
  let sections = $state<Schemas["TeamSection"][]>([]);
  let inbox = $state<Schemas["CmInbox"] | null>(null);
  let live = $state<Schemas["TeamLive"][] | null>(null);
  let notes = $state<Schemas["NtInbox"] | null>(null);
  let myTasks = $state<Schemas["TkOut"][] | null>(null);
  let support = $state<Schemas["SpRow"][] | null>(null);

  // правая колонка «Для меня»: вкладки; по умолчанию открыта та, где что-то ждёт
  let tab = $state<"notes" | "tasks" | "talks" | "">("");
  const unread = $derived(notes?.unread ?? 0);
  const waitingTalks = $derived(inbox?.rows.filter((r) => r.waiting || r.mentioned).length ?? 0);
  $effect(() => {
    if (tab || !notes || !myTasks) return;
    tab = unread ? "notes" : myTasks.length ? "tasks" : "notes";
  });
  const waitingSupport = $derived(support?.filter((t) => t.waiting_on_team) ?? []);
  const attention = $derived((dash?.problems.length ?? 0) + waitingSupport.length);

  async function loadFeed(append = false) {
    loading = true;
    const before = append && changes.length ? changes[changes.length - 1].id : undefined;
    const author = mine ? me.data?.id : undefined;
    const { data } = await api.GET("/studio/api/team/changes", { params: { query: { author, section, before, limit: PAGE } } });
    const rows = data ?? [];
    changes = append ? [...changes, ...rows] : rows;
    more = rows.length === PAGE;
    loading = false;
  }

  onMount(async () => {
    const [d, t, c, l] = await Promise.all([api.GET("/studio/api/dashboard"), api.GET("/studio/api/team"), api.GET("/studio/api/comments/inbox"), api.GET("/studio/api/team/live")]);
    live = l.data ?? [];
    if (level("support") !== "none") support = (await api.GET("/studio/api/support", { params: { query: { status: "active" } } })).data ?? [];
    await loadMine();
    dash = d.data ?? null;
    inbox = c.data ?? null;
    sections = t.data?.sections ?? [];
    await loadFeed();
  });

  function filter(next: { mine?: boolean; section?: string }) {
    if (next.mine !== undefined) mine = next.mine;
    if (next.section !== undefined) section = next.section;
    loadFeed();
  }

  // группировка ленты по дням: «Сегодня», «Вчера», дата
  function dayOf(value: string): string {
    const date = new Date(value);
    const today = new Date();
    const start = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
    const diff = Math.round((start(today) - start(date)) / 86400000);
    if (diff === 0) return "Сегодня";
    if (diff === 1) return "Вчера";
    return date.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: date.getFullYear() === today.getFullYear() ? undefined : "numeric" });
  }
  const time = (value: string) => new Date(value).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const ago = (value: string) => {
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    return seconds < 60 ? "только что" : `${Math.round(seconds / 60)} мин назад`;
  };

  const groups = $derived.by(() => {
    const out: { day: string; rows: Change[] }[] = [];
    for (const row of changes) {
      const day = dayOf(row.at);
      if (out.at(-1)?.day !== day) out.push({ day, rows: [] });
      out.at(-1)!.rows.push(row);
    }
    return out;
  });

  const ACTION_MARK: Record<string, string> = { create: "+", update: "✎", delete: "×", act: "•" };
  const NOTE_MARK: Record<string, string> = { assigned: "→", mention: "@", due: "…", overdue: "!" };

  async function readNotes(ids: number[]) {
    const { data } = await api.POST("/studio/api/notifications/read", { body: { ids } });
    if (data) notes = data;
    checkNotes();
  }

  // уведомления и свои задачи; перечитываются, когда меняется число непрочитанных (новое назначение, срок, упоминание)
  async function loadMine() {
    const [n, m] = await Promise.all([api.GET("/studio/api/notifications"), api.GET("/studio/api/tasks", { params: { query: { mine: true, status: "open,doing,review" } } })]);
    notes = n.data ?? null;
    myTasks = (m.data ?? []).sort((a, b) => Number(b.overdue) - Number(a.overdue) || b.priority - a.priority);
  }
  $effect(() => { noteState.stamp; untrack(() => { if (notes) loadMine(); }); });
</script>

<PageHead title="Главная">
  {#snippet sub()}Что требует внимания, что делает команда и кто сейчас в мире.{/snippet}
</PageHead>

<div class="stats">
  <a class="stat" href="#/players">
    <span class="chip"><Icon name="players" size={18} /></span>
    <span class="val"><b>{dash?.online.length ?? "…"}</b><span>игроков в мире</span></span>
  </a>
  <div class="stat">
    <span class="chip"><Icon name="pencil" size={18} /></span>
    <span class="val"><b>{dash?.changes_today ?? "…"}</b><span>изменений сегодня</span></span>
  </div>
  <button class="stat" onclick={() => (tab = "tasks")}>
    <span class="chip"><Icon name="tasks" size={18} /></span>
    <span class="val"><b>{myTasks?.length ?? "…"}</b><span>моих открытых задач</span></span>
  </button>
  <a class="stat" class:warn={attention > 0} class:ok={dash && attention === 0} href="#attention" onclick={(e) => { e.preventDefault(); document.getElementById("attention")?.scrollIntoView({ behavior: "smooth", block: "start" }); }}>
    <span class="chip"><Icon name={attention ? "alert" : "check"} size={18} /></span>
    <span class="val"><b>{dash ? attention : "…"}</b><span>{attention ? "требует внимания" : "всё спокойно"}</span></span>
  </a>
</div>

<div class="cols">
  <div class="stack">
    <section class="panel" id="attention">
      <header class="panel-head"><h2>Требует внимания</h2>{#if attention}<span class="badge warn">{attention}</span>{/if}</header>
      {#if !dash}
        <p class="muted empty">Загрузка…</p>
      {:else if !attention}
        <p class="okline"><Icon name="check" size={16} />Замечаний к миру нет, игроки ничего не ждут от команды.</p>
      {:else}
        <ul class="rows">
          {#each dash.problems as p, i (i)}
            <li class="item">
              <span class="ico warn"><Icon name="alert" size={15} /></span>
              <span class="body"><a href={p.link}>{p.title}</a><span class="muted">{p.text}</span></span>
            </li>
          {/each}
          {#each waitingSupport.slice(0, 6) as t (t.id)}
            <li class="item">
              <span class="ico"><Icon name="support" size={15} /></span>
              <span class="body">
                <span class="line"><a href={`#/support/${t.id}`}>#{t.id} {t.subject}</a>{#if t.status === "new"}<span class="badge new">новое</span>{/if}</span>
                <span class="muted">{t.player} · {ago(t.updated_at)}{t.assignee ? ` · исполнитель: ${t.assignee}` : " · никто не взял"}</span>
              </span>
            </li>
          {/each}
        </ul>
        {#if waitingSupport.length > 6}<a class="more-link" href="#/support">Ещё обращений: {waitingSupport.length - 6} →</a>{/if}
      {/if}
    </section>

    <section class="panel feed">
      <header class="panel-head">
        <h2>Лента изменений</h2>
        <span class="spacer"></span>
        <div class="seg" role="group" aria-label="Чьи изменения">
          <button class:on={!mine} aria-pressed={!mine} onclick={() => filter({ mine: false })}>Все</button>
          <button class:on={mine} aria-pressed={mine} disabled={!me.data} onclick={() => filter({ mine: true })}>Мои</button>
        </div>
        <select class="field small-field" value={section} onchange={(e) => filter({ section: e.currentTarget.value })} aria-label="Раздел">
          <option value="">все разделы</option>
          {#each sections as s (s.name)}<option value={s.name}>{s.label}</option>{/each}
          <option value="team">Команда</option>
        </select>
      </header>

      {#if !changes.length && !loading}
        <p class="muted empty">{mine || section ? "По этому фильтру изменений нет." : "Изменений пока нет: лента начинается с первого сохранения в Студии."}</p>
      {/if}
      <div class="scroll">
        {#each groups as group (group.day)}
          <h3 class="day">{group.day}</h3>
          <ul class="rows">
            {#each group.rows as row (row.id)}
              <li class="row">
                <span class="mark {row.action}" title={row.action_label}>{ACTION_MARK[row.action] ?? "•"}</span>
                <span class="what">
                  <span class="who">{row.username}</span>
                  <span class="muted">{row.action_label} · {row.kind}</span>
                  {#if row.link}<a href={row.link}>{row.label}</a>{:else}<span class="gone">{row.label}</span>{/if}
                  {#if row.summary}<span class="muted">· {row.summary}</span>{/if}
                </span>
                <span class="muted when">{time(row.at)}</span>
              </li>
            {/each}
          </ul>
        {/each}
        {#if more}<button class="btn ghost more" disabled={loading} onclick={() => loadFeed(true)}>{loading ? "Загрузка…" : "Показать ещё"}</button>{/if}
      </div>
    </section>
  </div>

  <div class="stack">
    <section class="panel">
      <header class="panel-head"><h2>Для меня</h2></header>
      <div class="tabs" role="tablist">
        <button role="tab" aria-selected={tab === "notes"} class:on={tab === "notes"} onclick={() => (tab = "notes")}>Уведомления{#if unread}<span class="badge new">{unread}</span>{/if}</button>
        <button role="tab" aria-selected={tab === "tasks"} class:on={tab === "tasks"} onclick={() => (tab = "tasks")}>Задачи{#if myTasks?.length}<span class="badge">{myTasks.length}</span>{/if}</button>
        <button role="tab" aria-selected={tab === "talks"} class:on={tab === "talks"} onclick={() => (tab = "talks")}>Обсуждения{#if waitingTalks}<span class="badge new">{waitingTalks}</span>{/if}</button>
      </div>

      {#if tab === "tasks"}
        {#if !myTasks}
          <p class="muted empty">Загрузка…</p>
        {:else if !myTasks.length}
          <p class="muted empty">Открытых задач на вас нет.</p>
        {:else}
          <ul class="rows">
            {#each myTasks.slice(0, 8) as task (task.id)}
              <li class="row">
                <span class="prio" style="--prio: {priorityColor(task.priority)}" title="Приоритет {task.priority}">{task.priority}</span>
                <span class="what"><a href="#/tasks/{task.id}">{task.title}</a> <span class="muted">· {task.status_label}</span></span>
                {#if task.due}<span class="when" class:late={task.overdue}>{task.overdue ? "просрочено" : new Date(task.due + "T00:00:00").toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span>{/if}
              </li>
            {/each}
          </ul>
        {/if}
        <a class="more-link" href="#/tasks">Все задачи →</a>
      {:else if tab === "talks"}
        {#if !inbox}
          <p class="muted empty">Загрузка…</p>
        {:else if !inbox.rows.length}
          <p class="muted empty">Обсуждений с вашим участием нет. Начать можно на любой странице кнопкой «Обсуждение» в меню слева.</p>
        {:else}
          <ul class="rows">
            {#each inbox.rows as r (r.thread)}
              <li class="item">
                <span class="body">
                  <span class="line">
                    {#if r.link}<a href={r.link} onclick={() => (discussion.open = true)}>{r.kind} {r.label}</a>{:else}<span>{r.kind} {r.label}</span>{/if}
                    {#if r.mentioned}<span class="badge">вас упомянули</span>{/if}
                    {#if r.waiting}<span class="badge new">ждёт ответа</span>{/if}
                  </span>
                  <span class="muted"><b>{r.last_by}:</b> {r.last_text}</span>
                </span>
              </li>
            {/each}
          </ul>
          <p class="foot-note muted">Открыто обсуждений всего: {inbox.open_total}</p>
        {/if}
      {:else}
        {#if !notes}
          <p class="muted empty">Загрузка…</p>
        {:else if !notes.rows.length}
          <p class="muted empty">Уведомлений нет: здесь появятся назначенные вам задачи, упоминания и сроки.</p>
        {:else}
          <ul class="rows">
            {#each notes.rows.slice(0, 8) as note (note.id)}
              <li class="note" class:unread={!note.read}>
                <span class="mark {note.kind}" aria-hidden="true">{NOTE_MARK[note.kind] ?? "•"}</span>
                {#if note.link}<a href={note.link} onclick={() => readNotes([note.id])}>{note.text}</a>{:else}<span>{note.text}</span>{/if}
              </li>
            {/each}
          </ul>
          {#if notes.unread}<button class="btn ghost tiny-btn" onclick={() => readNotes([])}>Прочитать все</button>{/if}
        {/if}
      {/if}
    </section>

    <section class="panel">
      <header class="panel-head"><h2>Сейчас</h2></header>
      <h3 class="sub">Игроки в мире{#if dash?.online.length}<span class="count">{dash.online.length}</span>{/if}</h3>
      {#if !dash}
        <p class="muted empty">Загрузка…</p>
      {:else if !dash.online.length}
        <p class="muted empty">Никого нет.</p>
      {:else}
        <ul class="rows">
          {#each dash.online as p (p.player + p.login + p.machine)}
            <li class="row">
              <span class="dot" aria-hidden="true"></span>
              <span class="what"><b>{p.player}</b> <span class="muted">как</span> <a href="#/machines/{p.machine}/accounts">{p.login}@{p.hostname}</a></span>
              <span class="muted when">{ago(p.seen_at)}</span>
            </li>
          {/each}
        </ul>
      {/if}

      <h3 class="sub">Авторы за правкой{#if live?.length}<span class="count">{live.length}</span>{/if}</h3>
      {#if !live}
        <p class="muted empty">Загрузка…</p>
      {:else if !live.length}
        <p class="muted empty">Никто ничего не правит, черновиков нет.</p>
      {:else}
        <ul class="rows">
          {#each live as r (r.room)}
            <li class="item">
              <span class="body">
                <span class="line">
                  {#if r.link}<a href={r.link}>{r.kind} {r.label}</a>{:else}<span>{r.kind} {r.label}</span>{/if}
                  {#if r.dirty}<span class="badge new">не сохранено</span>{/if}
                </span>
                <span class="muted">
                  {#if r.people.length}сейчас: {r.people.join(", ")}{/if}{#if r.people.length && r.dirty} · {/if}{#if r.dirty}правили: {r.editors.join(", ") || "—"}{/if}
                </span>
              </span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</div>

<style>
  .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 0 32px 16px; max-width: 1280px; }
  .stat {
    display: flex; align-items: center; gap: 12px; padding: 12px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel);
    color: var(--text); font: inherit; text-align: left; text-decoration: none; cursor: default;
  }
  a.stat, button.stat { cursor: pointer; }
  a.stat:hover, button.stat:hover { border-color: var(--line); background: var(--panel-2); text-decoration: none; }
  .stat:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .chip { flex: none; display: grid; place-items: center; width: 36px; height: 36px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); }
  .stat.warn .chip { background: rgba(242, 198, 109, 0.14); color: var(--warn); }
  .stat.ok .chip { background: rgba(95, 208, 160, 0.14); color: var(--ok); }
  .val { display: flex; flex-direction: column; min-width: 0; }
  .val b { font-size: 22px; line-height: 1.15; font-variant-numeric: tabular-nums; }
  .val span { color: var(--muted); font-size: 12.5px; }
  .cols { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 16px; padding: 0 32px 32px; align-items: start; max-width: 1280px; }
  .stack { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .panel { border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px 14px; min-width: 0; }
  .panel-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  h2 { margin: 0; font-size: 14px; font-weight: 650; }
  .spacer { flex: 1; }
  .seg { display: inline-flex; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 3px 12px; background: none; border: 0; color: var(--muted); cursor: pointer; font: inherit; font-size: 12.5px; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .seg button:disabled { cursor: default; opacity: 0.5; }
  .small-field { width: auto; padding: 3px 8px; font-size: 12.5px; }
  .scroll { max-height: 440px; overflow-y: auto; margin: 0 -8px; padding: 0 8px; }
  .day { margin: 12px 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--faint); font-weight: 600; }
  .day:first-child { margin-top: 2px; }
  .sub { display: flex; align-items: center; gap: 6px; margin: 12px 0 2px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--faint); font-weight: 600; }
  .sub:first-of-type { margin-top: 0; }
  .count { padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; letter-spacing: 0; }
  .rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .row { display: flex; align-items: baseline; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .row:last-child { border-bottom: 0; }
  .what { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .who { font-weight: 600; }
  .when { font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .mark { width: 18px; text-align: center; color: var(--muted); flex: none; }
  .mark.create { color: var(--ok); }
  .mark.delete { color: var(--danger); }
  .gone { text-decoration: line-through; color: var(--muted); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok); flex: none; align-self: center; }
  .item { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line-soft); }
  .item:last-child { border-bottom: 0; }
  .ico { flex: none; display: grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; background: var(--raise); color: var(--muted); }
  .ico.warn { background: rgba(242, 198, 109, 0.14); color: var(--warn); }
  .body { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; font-size: 13px; }
  .body .muted { font-size: 12.5px; overflow-wrap: anywhere; }
  .line { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .okline { display: flex; align-items: center; gap: 8px; margin: 4px 0; color: var(--ok); }
  .badge { padding: 1px 7px; border-radius: 999px; background: var(--accent-soft); font-size: 11px; font-weight: 600; }
  .badge.new { background: none; border: 1px solid var(--accent); color: var(--accent); }
  .badge.warn { background: rgba(242, 198, 109, 0.14); color: var(--warn); }
  .tabs { display: flex; gap: 2px; margin-bottom: 6px; border-bottom: 1px solid var(--line-soft); }
  .tabs button {
    display: inline-flex; align-items: center; gap: 6px; padding: 6px 8px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: none;
    color: var(--muted); font: inherit; font-size: 13px; cursor: pointer;
  }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: var(--radius-s); }
  .tiny-btn { margin-top: 8px; padding: 2px 10px; font-size: 12px; }
  .more-link { display: inline-block; margin-top: 8px; font-size: 12.5px; }
  .foot-note { margin: 8px 0 0; font-size: 12px; }
  .note { display: flex; gap: 8px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .note:last-child { border-bottom: 0; }
  .note:not(.unread) { opacity: 0.6; }
  .note .mark { width: 16px; color: var(--accent); font-weight: 700; }
  .note .mark.overdue { color: var(--danger); }
  .prio { flex: none; display: inline-grid; place-items: center; min-width: 20px; height: 20px; border-radius: 6px; background: color-mix(in srgb, var(--prio) 22%, transparent); color: var(--prio); font-size: 12px; font-weight: 700; align-self: center; }
  .late { color: var(--danger); }
  .empty { margin: 6px 0; font-size: 13px; }
  .more { margin: 8px 0 4px; }
  @media (max-width: 1000px) { .cols { grid-template-columns: 1fr; } .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
