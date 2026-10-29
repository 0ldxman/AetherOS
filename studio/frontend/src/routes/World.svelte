<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import { toast } from "../lib/toast.svelte";

  type World = Schemas["WorldOut"];

  let world = $state<World | null>(null);
  let day = $state("");
  let time = $state("");
  let saved = $state("");
  let errors = $state<Record<string, string[]>>({});

  const body = $derived(world ? { ...world, game_now: `${day}T${time || "00:00"}:00Z` } : null);
  const dirty = $derived(JSON.stringify(body) !== saved);

  function fill(data: World) {
    world = data;
    day = data.game_now.slice(0, 10);
    time = data.game_now.slice(11, 16);
    saved = JSON.stringify({ ...data, game_now: `${day}T${time}:00Z` });
    errors = {};
  }

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
    toast("Мир сохранён.");
  }

  const num = (value: string) => Math.max(0, Math.round(+value) || 0);
</script>

<header class="head">
  <h1>Мир</h1>
  <p class="muted">Настройки мира: от них считаются даты и числа на экранах входа, загрузки и в приветствии ОС (<code>{"{date}"}</code>, <code>{"{core_days}"}</code>, <code>{"{stations}"}</code> и другие).</p>
</header>

{#if world}
  <section class="card">
    <h2>Время</h2>
    <div class="row">
      <label><span class="label">«Сейчас» в мире: дата</span><input class="field" type="date" bind:value={day} /></label>
      <label><span class="label">время (UTC)</span><input class="field" type="time" bind:value={time} /></label>
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

  <div class="actions"><button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button></div>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

<style>
  .head { padding: 28px 32px 8px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  .head p { margin: 4px 0 0; }
  .card { margin: 12px 32px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 10px; }
  h2 { margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; }
  .small { font-size: 12px; margin: 0; }
  .err { margin: 0; color: var(--danger); font-size: 12px; }
  .actions { padding: 0 32px 32px; }
  .pad { padding: 24px 32px; }
</style>
