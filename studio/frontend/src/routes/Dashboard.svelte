<script lang="ts">
  // Главная Студии: лента изменений команды, игроки в мире прямо сейчас и что в мире требует внимания.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import PageHead from "../lib/PageHead.svelte";
  import { level, me } from "../lib/me.svelte";
  import { discussion } from "../lib/discussion.svelte";
  import { priorityColor } from "../lib/tasks";
  import { checkNotes, notes as noteState } from "../lib/notes.svelte";
  import { untrack } from "svelte";

  type Change = Schemas["TeamChange"];
  const PAGE = 40;

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
  {#snippet sub()}Что меняла команда, кто из игроков в мире и что требует внимания.{/snippet}
</PageHead>

<div class="stats">
  <div class="stat"><b>{dash?.online.length ?? "…"}</b><span>игроков в мире</span></div>
  <div class="stat"><b>{dash?.changes_today ?? "…"}</b><span>изменений сегодня</span></div>
  <div class="stat"><b>{myTasks?.length ?? "…"}</b><span>моих открытых задач</span></div>
  <div class="stat" class:warn={!!dash?.problems.length}><b>{dash?.problems.length ?? "…"}</b><span>замечаний к миру</span></div>
</div>

<div class="cols">
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
    {#each groups as group (group.day)}
      <h3 class="day">{group.day}</h3>
      <ul class="rows">
        {#each group.rows as row (row.id)}
          <li class="row">
            <span class="mark {row.action}" title={row.action_label}>{ACTION_MARK[row.action] ?? "•"}</span>
            <span class="what">
              <span class="who">{row.username}</span>
              <span class="muted">{row.action_label} ·</span>
              <span class="muted">{row.kind}</span>
              {#if row.link}<a href={row.link}>{row.label}</a>{:else}<span class="gone">{row.label}</span>{/if}
              {#if row.summary}<span class="muted">· {row.summary}</span>{/if}
            </span>
            <span class="muted when">{time(row.at)}</span>
          </li>
        {/each}
      </ul>
    {/each}
    {#if more}<button class="btn ghost more" disabled={loading} onclick={() => loadFeed(true)}>{loading ? "Загрузка…" : "Показать ещё"}</button>{/if}
  </section>

  <div class="side">
    <section class="panel">
      <header class="panel-head"><h2>Уведомления{#if notes?.unread}<span class="badge new">{notes.unread}</span>{/if}</h2><span class="spacer"></span>
        {#if notes?.unread}<button class="btn ghost tiny-btn" onclick={() => readNotes([])}>Прочитать все</button>{/if}</header>
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
      {/if}
    </section>

    <section class="panel">
      <header class="panel-head"><h2>Мои задачи</h2><span class="spacer"></span><a class="small-note" href="#/tasks">все задачи →</a></header>
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
    </section>

    <section class="panel">
      <header class="panel-head"><h2>В работе</h2></header>
      {#if !live}
        <p class="muted empty">Загрузка…</p>
      {:else if !live.length}
        <p class="muted empty">Сейчас никто ничего не правит, несохранённых черновиков нет.</p>
      {:else}
        <ul class="rows">
          {#each live as r (r.room)}
            <li class="problem">
              <span class="talk-head">
                {#if r.link}<a href={r.link}>{r.kind} {r.label}</a>{:else}<span>{r.kind} {r.label}</span>{/if}
                {#if r.dirty}<span class="badge new">не сохранено</span>{/if}
              </span>
              <span class="muted">
                {#if r.people.length}сейчас: {r.people.join(", ")}{/if}{#if r.people.length && r.dirty} · {/if}{#if r.dirty}правили: {r.editors.join(", ") || "—"}{/if}
              </span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    {#if support}
      {@const waiting = support.filter((t) => t.waiting_on_team)}
      <section class="panel">
        <header class="panel-head"><h2>Поддержка{#if waiting.length}<span class="badge new">{waiting.length}</span>{/if}</h2><span class="spacer"></span>
          <a class="small-note" href="#/support">все обращения →</a></header>
        {#if !waiting.length}
          <p class="muted empty">Игроки ничего не ждут от команды.{#if support.length} Открытых обращений: {support.length}.{/if}</p>
        {:else}
          <ul class="rows">
            {#each waiting.slice(0, 6) as t (t.id)}
              <li class="problem">
                <span class="talk-head"><a href={`#/support/${t.id}`}>#{t.id} {t.subject}</a>{#if t.status === "new"}<span class="badge new">новое</span>{/if}</span>
                <span class="muted">{t.player} · {ago(t.updated_at)}{t.assignee ? ` · исполнитель: ${t.assignee}` : " · никто не взял"}</span>
              </li>
            {/each}
          </ul>
        {/if}
      </section>
    {/if}

    <section class="panel">
      <header class="panel-head"><h2>Обсуждения</h2><span class="spacer"></span>{#if inbox}<span class="muted small-note">открыто всего: {inbox.open_total}</span>{/if}</header>
      {#if !inbox}
        <p class="muted empty">Загрузка…</p>
      {:else if !inbox.rows.length}
        <p class="muted empty">Обсуждений с вашим участием нет. Начать можно на любой странице: кнопка «Обсуждение» слева внизу.</p>
      {:else}
        <ul class="rows">
          {#each inbox.rows as r (r.thread)}
            <li class="problem">
              <span class="talk-head">
                {#if r.link}<a href={r.link} onclick={() => (discussion.open = true)}>{r.kind} {r.label}</a>{:else}<span>{r.kind} {r.label}</span>{/if}
                {#if r.mentioned}<span class="badge">вас упомянули</span>{/if}
                {#if r.waiting}<span class="badge new">ждёт ответа</span>{/if}
              </span>
              <span class="muted"><b>{r.last_by}:</b> {r.last_text}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>

    <section class="panel">
      <header class="panel-head"><h2>Игроки в мире</h2></header>
      {#if !dash}
        <p class="muted empty">Загрузка…</p>
      {:else if !dash.online.length}
        <p class="muted empty">Сейчас в мире никого.</p>
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
    </section>

    <section class="panel">
      <header class="panel-head"><h2>Требует внимания</h2></header>
      {#if !dash}
        <p class="muted empty">Загрузка…</p>
      {:else if !dash.problems.length}
        <p class="muted empty">Замечаний нет.</p>
      {:else}
        <ul class="rows">
          {#each dash.problems as p, i (i)}
            <li class="problem">
              <a href={p.link}>{p.title}</a>
              <span class="muted">{p.text}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
</div>

<style>
  .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 0 32px 16px; }
  .stat { display: flex; flex-direction: column; gap: 2px; padding: 12px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .stat b { font-size: 22px; font-variant-numeric: tabular-nums; }
  .stat span { color: var(--muted); font-size: 12.5px; }
  .stat.warn b { color: var(--warn, #e0b34a); }
  .cols { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); gap: 16px; padding: 0 32px 32px; align-items: start; }
  .side { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .panel { border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 12px 16px 14px; min-width: 0; }
  .panel-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
  h2 { margin: 0; font-size: 14px; font-weight: 650; }
  .spacer { flex: 1; }
  .seg { display: inline-flex; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 3px 12px; background: none; border: 0; color: var(--muted); cursor: pointer; font: inherit; font-size: 12.5px; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .seg button:disabled { cursor: default; opacity: 0.5; }
  .small-field { width: auto; padding: 3px 8px; font-size: 12.5px; }
  .day { margin: 12px 0 4px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--faint); font-weight: 600; }
  .rows { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .row { display: flex; align-items: baseline; gap: 10px; padding: 5px 0; border-bottom: 1px solid var(--line-soft); }
  .row:last-child { border-bottom: 0; }
  .what { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .who { font-weight: 600; }
  .when { font-size: 12px; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .mark { width: 18px; text-align: center; color: var(--muted); flex: none; }
  .mark.create { color: var(--ok, #6fcf97); }
  .mark.delete { color: var(--danger); }
  .gone { text-decoration: line-through; color: var(--muted); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--ok, #6fcf97); flex: none; align-self: center; }
  .problem { display: flex; flex-direction: column; gap: 2px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .problem:last-child { border-bottom: 0; }
  .talk-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .badge { padding: 1px 7px; border-radius: 999px; background: var(--accent-soft); font-size: 11px; }
  .badge.new { background: none; border: 1px solid var(--accent); color: var(--accent); }
  .small-note { font-size: 12px; }
  .tiny-btn { padding: 1px 8px; font-size: 12px; }
  .panel-head .badge { margin-left: 6px; }
  .note { display: flex; gap: 8px; align-items: baseline; padding: 5px 0; border-bottom: 1px solid var(--line-soft); }
  .note:last-child { border-bottom: 0; }
  .note:not(.unread) { opacity: 0.6; }
  .note .mark { width: 16px; text-align: center; color: var(--accent); flex: none; font-weight: 700; }
  .note .mark.overdue { color: var(--danger); }
  .prio { flex: none; display: inline-grid; place-items: center; min-width: 20px; height: 20px; border-radius: 6px; background: color-mix(in srgb, var(--prio) 22%, transparent); color: var(--prio); font-size: 12px; font-weight: 700; align-self: center; }
  .late { color: var(--danger); }
  .problem span { font-size: 12.5px; }
  .empty { margin: 6px 0; }
  .more { margin-top: 8px; }
  @media (max-width: 1000px) { .cols { grid-template-columns: 1fr; } .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
