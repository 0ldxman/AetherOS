<script lang="ts">
  import { adminUrl, api, problem, type Schemas } from "../../lib/api";
  import { toast } from "../../lib/toast.svelte";
  import WeekGrid from "../../lib/WeekGrid.svelte";

  let { machine, account }: { machine: Schemas["Overview"]; account: number | null } = $props();

  let chosen = $state<number | null>(null);
  let policy = $state<Schemas["PolicyOut"] | null>(null);
  let form = $state({ source: "", chain: "", at: "", player: "", password: "", keys: "", token: "", usePassword: false });
  let verdict = $state<Schemas["Verdict"] | null>(null);
  let busy = $state(false);

  $effect(() => { chosen = account ?? machine.accounts[0]?.id ?? null; });
  const row = $derived(machine.accounts.find((item) => item.id === chosen));

  $effect(() => {
    const id = row?.policy?.id;
    policy = null;
    verdict = null;
    if (id) api.GET("/studio/api/machines/policies/{policy_id}", { params: { path: { policy_id: id } } }).then(({ data }) => (policy = data ?? null));
  });

  const mark = $derived.by(() => {
    if (!form.at) return null;
    const moment = new Date(form.at);
    return { day: (moment.getDay() + 6) % 7, slot: moment.getHours() * 2 + (moment.getMinutes() >= 30 ? 1 : 0) };
  });

  async function run() {
    if (chosen === null) return;
    busy = true;
    const split = (text: string) => text.split(/[\s,]+/).filter(Boolean);
    const { data, error } = await api.POST("/studio/api/machines/{machine_id}/check", {
      params: { path: { machine_id: machine.id } },
      body: {
        account: chosen, source: form.source, chain: split(form.chain), at: form.at || null, player: form.player,
        password: form.usePassword ? form.password : null, keys: split(form.keys), token: form.token,
      },
    });
    busy = false;
    if (error || !data) return toast(problem(error), "error");
    verdict = data;
  }

  const ORIGIN: Record<string, string> = { profile: "своя у учётки", machine: "от машины", system: "от типа системы" };
  const MODE: Record<string, string> = { all: "нужны и пароль, и ключ", any: "хватает пароля или ключа" };
</script>

<div class="grid">
  <section class="card">
    <label class="pickrow">
      <span class="label">Учётка</span>
      <select class="field mono" bind:value={chosen}>
        {#each machine.accounts as item}<option value={item.id}>{item.login}</option>{/each}
      </select>
    </label>

    {#if !row}
      <p class="muted">У машины нет учёток.</p>
    {:else if !row.policy}
      <p class="muted">Политики входа нет: войти можно откуда угодно и когда угодно, нужны только пароль и ключи учётки.</p>
    {:else if policy}
      <h2>«{policy.name}» <span class="muted">· {ORIGIN[row.policy.origin ?? ""]}</span></h2>
      {#if policy.description}<p class="muted">{policy.description}</p>{/if}
      <dl>
        <dt>Пароль и ключ</dt><dd>{MODE[policy.mode] ?? policy.mode}</dd>
        <dt>Откуда</dt><dd>{#if policy.sources.length}{#each policy.sources as host}<code>{host}</code> {/each}{:else}откуда угодно{/if}</dd>
        <dt>Только через</dt><dd>{#if policy.via.length}{#each policy.via as host}<code>{host}</code> {/each}{:else}—{/if}</dd>
        <dt>Ошибки</dt>
        <dd>{policy.max_attempts ? `${policy.max_attempts} за ${Math.round(policy.attempts_window / 60)} мин → блок на ${Math.round(policy.lock_seconds / 60)} мин` : "не блокируют"}</dd>
        <dt>Срок подключения</dt><dd>{policy.ttl ? `${policy.ttl} с` : "без ограничения"}</dd>
      </dl>
      {#if policy.grid}
        <h3>Когда можно войти</h3>
        <WeekGrid grid={policy.grid} {mark} />
        <p class="muted small mono">{policy.windows}</p>
      {:else}
        <p class="muted small">Окон нет: в любое время.</p>
      {/if}
      <p class="small"><a href={adminUrl(`machines/entrypolicy/${policy.id}/change/`)}>Править политику в старой админке</a></p>
    {:else}
      <p class="muted">Загрузка…</p>
    {/if}
  </section>

  <section class="card">
    <h2>Проверить вход</h2>
    <p class="muted small">Те же правила, что у игрока. Ничего не записывается: ни событий, ни расхода токена, ни блокировки.</p>
    <div class="pair">
      <label><span class="label">Откуда (хост)</span><input class="field mono" bind:value={form.source} placeholder="aether-main" /></label>
      <label><span class="label">Цепочка мостов</span><input class="field mono" bind:value={form.chain} placeholder="aether-main gw-02" /></label>
    </div>
    <div class="pair">
      <label><span class="label">Время на машине</span><input class="field" type="datetime-local" bind:value={form.at} /></label>
      <label><span class="label">Игрок (для блокировок)</span><input class="field" bind:value={form.player} placeholder="логин игрока" /></label>
    </div>
    <label class="check"><input type="checkbox" bind:checked={form.usePassword} /> проверить пароль</label>
    {#if form.usePassword}<input class="field" type="password" bind:value={form.password} placeholder="пароль" />{/if}
    <div class="pair">
      <label><span class="label">Ключи</span><input class="field mono" bind:value={form.keys} placeholder="cardkey door_key" /></label>
      <label><span class="label">Токен</span><input class="field mono" bind:value={form.token} placeholder="tk-…" /></label>
    </div>
    <button class="btn primary" disabled={busy || chosen === null} onclick={run}>Проверить</button>

    {#if verdict}
      <div class="verdict {verdict.admitted === true ? 'yes' : verdict.admitted === false ? 'no' : 'maybe'}">
        {verdict.admitted === true ? "Пустит" : verdict.admitted === false ? "Не пустит" : "Правила пропускают, остались пароль или ключи"}
      </div>
      <ol class="steps">
        {#each verdict.steps as step}
          <li class={step.ok === true ? "ok" : step.ok === false ? "bad" : "info"}>
            <span class="mark">{step.ok === true ? "✓" : step.ok === false ? "✗" : "•"}</span>{step.text}
          </li>
        {/each}
      </ol>
    {/if}
  </section>
</div>

<style>
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px 20px 24px; align-items: start; }
  .card { display: flex; flex-direction: column; gap: 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); padding: 14px 16px; }
  .pickrow { max-width: 260px; }
  h2 { margin: 0; font-size: 15px; font-weight: 600; }
  h3 { margin: 4px 0 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  dl { display: grid; grid-template-columns: 140px 1fr; gap: 6px 12px; margin: 0; }
  dt { color: var(--muted); }
  dd { margin: 0; }
  code { padding: 1px 6px; border-radius: 4px; background: var(--bg); font-family: var(--mono); font-size: 12px; }
  .small { font-size: 12px; margin: 0; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  .verdict { margin-top: 6px; padding: 10px 12px; border-radius: var(--radius-s); font-weight: 600; }
  .verdict.yes { background: rgba(95, 208, 160, 0.12); color: var(--ok); }
  .verdict.no { background: var(--danger-soft); color: var(--danger); }
  .verdict.maybe { background: var(--accent-soft); color: var(--accent); }
  .steps { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
  .steps li { display: flex; gap: 10px; }
  .steps .mark { width: 14px; text-align: center; font-weight: 700; }
  .steps .ok .mark { color: var(--ok); }
  .steps .bad { color: var(--danger); }
  .steps .info { color: var(--muted); }
</style>
