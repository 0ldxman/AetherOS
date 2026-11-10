<script lang="ts">
  // Главная Студии: лента изменений команды, игроки в мире прямо сейчас и что в мире требует внимания.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../lib/api";
  import PageHead from "../lib/PageHead.svelte";
  import { me } from "../lib/me.svelte";

  type Change = Schemas["TeamChange"];
  const PAGE = 40;

  let dash = $state<Schemas["DashOut"] | null>(null);
  let changes = $state<Change[]>([]);
  let mine = $state(false);
  let section = $state("");
  let more = $state(false);
  let loading = $state(false);
  let sections = $state<Schemas["TeamSection"][]>([]);

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
    const [d, t] = await Promise.all([api.GET("/studio/api/dashboard"), api.GET("/studio/api/team")]);
    dash = d.data ?? null;
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
</script>

<PageHead title="Главная">
  {#snippet sub()}Что меняла команда, кто из игроков в мире и что требует внимания.{/snippet}
</PageHead>

<div class="stats">
  <div class="stat"><b>{dash?.online.length ?? "…"}</b><span>игроков в мире</span></div>
  <div class="stat"><b>{dash?.changes_today ?? "…"}</b><span>изменений сегодня</span></div>
  <div class="stat"><b>{dash?.authors_today ?? "…"}</b><span>авторов работали сегодня</span></div>
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
  .problem span { font-size: 12.5px; }
  .empty { margin: 6px 0; }
  .more { margin-top: 8px; }
  @media (max-width: 1000px) { .cols { grid-template-columns: 1fr; } .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
