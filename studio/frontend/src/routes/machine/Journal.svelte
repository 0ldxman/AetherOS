<script lang="ts">
  import { api, type Schemas } from "../../lib/api";
  import { when } from "../../lib/time";

  let { machine, account }: { machine: Schemas["Overview"]; account: number | null } = $props();

  let filters = $state({ account: null as number | null, kind: "", player: "", days: 7 });
  let rows = $state<Schemas["Event"][]>([]);
  let loading = $state(true);

  $effect(() => { filters.account = account; });

  $effect(() => {
    const query = { account: filters.account ?? undefined, kind: filters.kind, player: filters.player.trim(), days: filters.days };
    loading = true;
    api.GET("/studio/api/machines/{machine_id}/events", { params: { path: { machine_id: machine.id }, query } }).then(({ data }) => {
      rows = data ?? [];
      loading = false;
    });
  });

  const KINDS = [
    ["", "все события"],
    ["ok", "входы"],
    ["bad_password,bad_key,bad_token", "неверные пароль, ключ, токен"],
    ["source,route,window", "отказы политики"],
    ["locked,unlocked", "блокировки"],
    ["kicked", "выкинут автором"],
  ];
  const TONE: Record<string, string> = { ok: "ok", unlocked: "info", kicked: "info" };
</script>

<div class="journal">
  <div class="filters">
    <select class="field" bind:value={filters.account}>
      <option value={null}>все учётки</option>
      {#each machine.accounts as item}<option value={item.id}>{item.login}</option>{/each}
    </select>
    <select class="field" bind:value={filters.kind}>{#each KINDS as [value, label]}<option {value}>{label}</option>{/each}</select>
    <input class="field" placeholder="игрок" bind:value={filters.player} />
    <select class="field" bind:value={filters.days}>
      <option value={1}>за сутки</option><option value={7}>за неделю</option><option value={30}>за месяц</option>
    </select>
    <span class="muted count">{loading ? "…" : `${rows.length} событий`}</span>
  </div>

  <div class="row head"><span>Когда</span><span>На часах машины</span><span>Событие</span><span>Учётка</span><span>Игрок</span><span>Откуда</span><span>Подробно</span></div>
  {#each rows as event (event.id)}
    <div class="row">
      <span class="mono">{when(event.at)}</span>
      <span class="mono muted">{when(event.shown_at)}</span>
      <span class="kind {TONE[event.kind] ?? 'bad'}">{event.label}</span>
      <a class="mono" href="#/machines/{machine.id}/accounts/{event.account}">{event.login}</a>
      <span>{event.player ?? "—"}</span>
      <span class="mono muted">{event.source || "—"}</span>
      <span class="muted">{event.detail}</span>
    </div>
  {:else}
    {#if !loading}<p class="muted empty">Событий за этот срок нет.</p>{/if}
  {/each}
</div>

<style>
  .journal { padding: 16px 20px 24px; }
  .filters { display: flex; gap: 8px; margin-bottom: 12px; align-items: center; }
  .filters .field { width: auto; min-width: 150px; }
  .count { margin-left: auto; }
  .row { display: grid; grid-template-columns: 110px 130px 190px 120px 110px 130px 1fr; gap: 12px; align-items: center; height: 32px; padding: 0 10px; border-radius: var(--radius-s); }
  .row:not(.head):hover { background: var(--panel); }
  .row.head { height: 28px; color: var(--faint); font-size: 12px; border-bottom: 1px solid var(--line-soft); border-radius: 0; }
  .kind.ok { color: var(--ok); }
  .kind.bad { color: var(--danger); }
  .kind.info { color: var(--accent); }
  .empty { padding: 16px 10px; }
</style>
