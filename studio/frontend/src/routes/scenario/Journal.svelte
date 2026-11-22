<script lang="ts">
  // «Журнал»: что происходило в сценарии — кто нажал на пульте, какой этап пройден, чья ветка занята, кто вошёл в группу.
  // Записи от новых к старым; новые подтягиваются сами. Сброс сценария журнал не стирает.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import { full } from "../../lib/time";

  type Entry = Schemas["PnEntry"];
  let { id }: { id: number } = $props();

  const FILTERS = [
    { key: "", label: "Всё" },
    { key: "control", label: "Пульт" },
    { key: "stage", label: "Этапы" },
    { key: "start", label: "Старты" },
    { key: "branch", label: "Ветки" },
    { key: "crew", label: "Группы" },
  ];
  const KINDS: Record<string, string> = { note: "Запись", start: "Старт", stage: "Этап", control: "Пульт", branch: "Ветка", crew: "Группа", end: "Конец", reset: "Сброс", switch: "Включение" };

  let kind = $state("");
  let entries = $state<Entry[]>([]);
  let next = $state<number | null>(null);
  let loaded = $state(false);
  let failed = $state(false);
  let busy = $state(false);

  async function first() {
    const { data } = await api.GET("/studio/api/world/graphs/{graph_id}/journal", { params: { path: { graph_id: id }, query: { kind } } });
    failed = !data;
    loaded = true;
    if (!data) return;
    const known = new Set(entries.map((e) => e.id));
    const fresh = data.entries.filter((e) => !known.has(e.id));
    if (!entries.length) { entries = data.entries; next = data.next; }
    else if (fresh.length) entries = [...fresh, ...entries];
  }

  async function more() {
    if (next === null || busy) return;
    busy = true;
    const { data } = await api.GET("/studio/api/world/graphs/{graph_id}/journal", { params: { path: { graph_id: id }, query: { kind, before: next } } });
    busy = false;
    if (!data) return;
    entries = [...entries, ...data.entries];
    next = data.next;
  }

  function pick(key: string) {
    kind = key;
    entries = [];
    next = null;
    loaded = false;
    first();
  }

  onMount(() => {
    first();
    const tick = () => { if (!document.hidden) first(); };
    const timer = setInterval(tick, 5000);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
  });

  const day = (stamp: string) => {
    const d = new Date(stamp), now = new Date();
    const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
    const yesterday = new Date(now.getTime() - 86400000);
    return same(d, now) ? "Сегодня" : same(d, yesterday) ? "Вчера" : d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", ...(d.getFullYear() === now.getFullYear() ? {} : { year: "numeric" }) });
  };
  const clock = (stamp: string) => new Date(stamp).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const rows = $derived(entries.map((e, i) => ({ e, head: i === 0 || day(entries[i - 1].at) !== day(e.at) })));
</script>

<div class="bar" role="group" aria-label="Что показывать">
  {#each FILTERS as f (f.key)}
    <button class="pill" class:on={kind === f.key} aria-pressed={kind === f.key} onclick={() => pick(f.key)}>{f.label}</button>
  {/each}
</div>

{#if !loaded}
  <p class="muted pad">Загрузка…</p>
{:else if failed && !entries.length}
  <p class="pad">Не удалось загрузить журнал. <button class="btn" onclick={first}>Повторить</button></p>
{:else if !entries.length}
  <p class="muted pad">Записей пока нет. Здесь появятся нажатия пульта, пройденные этапы, занятые ветки, группы и сбросы.</p>
{:else}
  <ol class="log">
    {#each rows as { e, head } (e.id)}
      {#if head}<li class="day" aria-hidden="true">{day(e.at)}</li>{/if}
      <li class="row {e.kind}">
        <time datetime={e.at} title={full(e.at)}>{clock(e.at)}</time>
        <span class="who" class:none={!e.who}>{e.who || "мир"}</span>
        <span class="kind">{KINDS[e.kind] ?? e.kind}</span>
        <span class="text">{e.text}</span>
      </li>
    {/each}
  </ol>
  {#if next !== null}<div class="more"><button class="btn" disabled={busy} onclick={more}>{busy ? "Загрузка…" : "Показать ещё"}</button></div>{/if}
{/if}

<style>
  .bar { display: flex; flex-wrap: wrap; gap: 6px; padding: 14px 32px 0; }
  .pill { height: 28px; padding: 0 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel); color: var(--muted); cursor: pointer; font-size: 12.5px; }
  .pill:hover { color: var(--text); background: var(--panel-2); }
  .pill.on { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
  .pad { padding: 20px 32px; max-width: 640px; }

  .log { list-style: none; margin: 0; padding: 8px 32px 12px; display: flex; flex-direction: column; }
  .day { margin-top: 14px; padding-bottom: 4px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; border-bottom: 1px solid var(--line-soft); }
  .row { display: grid; grid-template-columns: 72px minmax(0, 150px) 86px minmax(0, 1fr); gap: 4px 12px; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--line-soft); font-size: 13px; }
  time { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12px; }
  .who { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .who.none { color: var(--muted); font-weight: 400; }
  .kind { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.3px; }
  .row.stage .kind { color: var(--ok); }
  .row.control .kind { color: var(--accent); }
  .row.branch .kind, .row.crew .kind { color: var(--warn); }
  .row.reset .kind { color: var(--danger); }
  .text { min-width: 0; overflow-wrap: anywhere; }
  .more { padding: 4px 32px 32px; }

  @media (max-width: 720px) {
    .bar, .log, .more { padding-left: 16px; padding-right: 16px; }
    .row { grid-template-columns: 64px minmax(0, 1fr); }
    .kind { grid-column: 2; }
    .text { grid-column: 1 / -1; }
  }
</style>
