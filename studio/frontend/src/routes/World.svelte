<script lang="ts">
  import PageHead from "../lib/PageHead.svelte";
  import Hint from "../lib/Hint.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import { toast } from "../lib/toast.svelte";
  import DraftState from "../lib/DraftState.svelte";
  import { SharedForm } from "../lib/shared.svelte";

  type World = Schemas["WorldOut"];

  let world = $state<World | null>(null);
  let clock = $state({ day: "", time: "" });
  let saved = $state("");
  let base = $state<World | null>(null);                   // сохранённое: им наполняются общие черновики
  let clockBase = $state<{ day: string; time: string } | null>(null);
  let errors = $state<Record<string, string[]>>({});

  const body = $derived(world ? { ...world, game_now: `${clock.day}T${clock.time || "00:00"}:00Z` } : null);
  const dirty = $derived(JSON.stringify(body) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);   // пока ничего не загружено, правок нет; черновик на сервере

  function fill(data: World, keepDraft = false) {
    const next = { day: data.game_now.slice(0, 10), time: data.game_now.slice(11, 16) };
    if (!keepDraft) {
      world = { ...data };
      clock = { ...next };
    }
    saved = JSON.stringify({ ...data, game_now: `${next.day}T${next.time}:00Z` });
    base = { ...data };
    clockBase = next;
    errors = {};
  }

  // общий черновик мира (поля и отдельно «сейчас»); кто-то сохранил: перечитать сохранённое, черновик не трогается
  async function refresh() {
    const { data } = await api.GET("/studio/api/world");
    if (data) fill(data, true);
  }
  const share = new SharedForm({ room: () => "world", draft: () => world ?? {}, base: () => base, onRemoteSave: refresh });
  const clockShare = new SharedForm({ room: () => "world", scope: () => "clock", draft: () => clock, base: () => clockBase, onRemoteSave: refresh });

  onMount(async () => {
    const { data } = await api.GET("/studio/api/world");
    if (data) fill(data);
  });

  async function save() {
    if (!body) return;
    const { data, error } = await api.PUT("/studio/api/world", { body });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    fill(data);
    share.markSaved();
    clockShare.markSaved();
    toast("Мир сохранён.");
  }

  const num = (value: string) => Math.max(0, Math.round(+value) || 0);
</script>

<PageHead title="Мир">
  {#snippet sub()}Настройки мира: от них считаются даты и числа на экранах входа, загрузки и в приветствии ОС (<code>{"{date}"}</code>, <code>{"{core_days}"}</code>, <code>{"{stations}"}</code> и другие).{/snippet}
</PageHead>

{#if world}
  <section class="card">
    <h2>Время</h2>
    <div class="row">
      <label><span class="label">«Сейчас» в мире: дата</span><input class="field" type="date" bind:value={clock.day} /></label>
      <label><span class="label">время (UTC)<Hint text="Мировое время по Гринвичу для даты слева. От этого момента считаются «N дней назад» и время писем." /></span><input class="field" type="time" bind:value={clock.time} /></label>
    </div>
    <p class="muted small">От этой даты считаются «N дней назад» и время писем.</p>
  </section>

  <section class="card">
    <h2>Центр и станции</h2>
    <div class="row">
      <label><span class="label">Последний контакт с центром</span><input class="field" type="date" bind:value={world.core_last_contact} /></label>
      <label><span class="label">Последнее обновление списков станций и мостов</span><input class="field" type="date" bind:value={world.beacon_last_sync} /></label>
      <label><span class="label">Сертификат узла действует до</span><input class="field" type="date" bind:value={world.cert_not_after} /></label>
    </div>
    <div class="row">
      <label><span class="label">Станций в каталоге</span><input class="field" type="number" min="0" value={world.stations_known} oninput={(e) => (world!.stations_known = num(e.currentTarget.value))} /></label>
      <label><span class="label">Станций отвечает</span><input class="field" type="number" min="0" value={world.stations_reachable} oninput={(e) => (world!.stations_reachable = num(e.currentTarget.value))} /></label>
      <label><span class="label">Записей аудита за сутки</span><input class="field" type="number" min="0" value={world.audit_per_day} oninput={(e) => (world!.audit_per_day = num(e.currentTarget.value))} /></label>
    </div>
    {#each Object.values(errors).flat() as text}<p class="err">{text}</p>{/each}
  </section>

  <div class="actions"><DraftState {share} {dirty} saved="" /><button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button></div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

<style>
  .card { margin: 12px 32px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 10px; }
  h2 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
  .small { font-size: 12px; margin: 0; }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .actions { padding: 0 32px 32px; display: flex; align-items: center; justify-content: flex-end; gap: 12px; }
  .pad { padding: 24px 32px; }
</style>
