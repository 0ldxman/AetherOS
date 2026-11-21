<script lang="ts">
  import PageHead from "../lib/PageHead.svelte";
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import { toast } from "../lib/toast.svelte";

  type Card = Schemas["PnCard"];
  type Control = Schemas["PnControl"];

  let cards = $state<Card[]>([]);
  let loaded = $state(false);
  let players = $state<{ id: number; username: string }[]>([]);
  let player = $state("");                                  // запускать от имени игрока (для проверки); пусто — мир
  let drafts = $state<Record<string, unknown>>({});         // правка, ещё не отправленная: опрос её не затирает
  let asking = $state<number | null>(null);                 // сценарий, у которого спросили «Сбросить?»

  const URL = "/studio/api/world/graphs";
  const key = (card: Card, control: Control) => `${card.id}:${control.node}`;
  const shown = (card: Card, control: Control) => (key(card, control) in drafts ? drafts[key(card, control)] : control.value);

  async function load() {
    const { data } = await api.GET("/studio/api/world/graphs/panel");
    if (data) cards = data;
    loaded = true;
  }

  onMount(() => {
    load();
    api.GET("/studio/api/players").then(({ data }) => { players = (data ?? []).filter((r) => !r.staff).map((r) => ({ id: r.id, username: r.username })); });
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  });

  async function send(card: Card, control: Control, value: unknown) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/control", { params: { path: { graph_id: card.id } }, body: { node: control.node, player: player ? +player : null, value } });
    delete drafts[key(card, control)];
    if (error) toast(problem(error), "error");
    else if (control.kind === "manual") toast(`«${control.name || "Запустить"}»: запущено.`);
    await load();
  }

  async function setActive(card: Card, active: boolean) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/active", { params: { path: { graph_id: card.id } }, body: { active } });
    if (error) toast(problem(error), "error");
    await load();
  }

  async function reset(card: Card) {
    asking = null;
    const { data, error } = await api.POST("/studio/api/world/graphs/{graph_id}/reset", { params: { path: { graph_id: card.id } } });
    if (error || !data) return toast(problem(error), "error");
    toast(`«${card.title}» начат заново.`);
    await load();
  }

  const top = (card: Card) => Math.max(1, ...card.stages.map((s) => s.hits));
  const text = (value: unknown) => (typeof value === "string" ? value : value === null || value === undefined ? "" : JSON.stringify(value));
</script>

<PageHead title="Мир">
  {#snippet sub()}Сценарии: включить, сбросить, посмотреть этапы и управлять пультом. Игровое время — в разделе <a href="#/time">Время</a>.{/snippet}
  {#if players.length}
    <label class="as"><span class="muted small">Запускать от имени</span>
      <select class="field" bind:value={player}>
        <option value="">мира (без игрока)</option>
        {#each players as p (p.id)}<option value={String(p.id)}>{p.username}</option>{/each}
      </select>
    </label>
  {/if}
</PageHead>

{#if !loaded}
  <p class="muted pad">Загрузка…</p>
{:else if !cards.length}
  <p class="muted pad">Сценариев пока нет: их создают в разделе <a href="#/graphs">Сценарии</a>.</p>
{:else}
  <div class="cards">
    {#each cards as card (card.id)}
      <section class="card" class:off={!card.active}>
        <header>
          <a class="title" href="#/graphs/{card.id}">{card.title}</a>
          <span class="muted small">{card.slug}{card.running ? ` · идёт потоков: ${card.running}` : ""}</span>
          <span class="spacer"></span>
          <label class="on"><input type="checkbox" checked={card.active} onchange={(e) => setActive(card, e.currentTarget.checked)} /> Включён</label>
          {#if asking === card.id}
            <span class="ask">Всё сбросится. <button class="btn tiny danger" onclick={() => reset(card)}>Да, начать заново</button> <button class="btn tiny ghost" onclick={() => (asking = null)}>Отмена</button></span>
          {:else}
            <button class="btn tiny ghost" onclick={() => (asking = card.id)}>Сбросить</button>
          {/if}
        </header>

        {#if card.stages.length}
          <div class="block">
            <h2>Этапы</h2>
            {#each card.stages as stage (stage.node)}
              <div class="stage">
                <span class="name">{stage.title}</span>
                <span class="bar"><i style="width: {Math.round((stage.hits / top(card)) * 100)}%"></i></span>
                <span class="muted small">прошли {stage.hits} · игроков {stage.players}{stage.waiting ? ` · ждут ${stage.waiting}` : ""}</span>
              </div>
            {/each}
          </div>
        {/if}

        {#if card.controls.length}
          <div class="block">
            <h2>Пульт</h2>
            <div class="controls">
              {#each card.controls as c (c.node)}
                <div class="control">
                  <span class="name">{c.kind === "manual" ? "Кнопка" : c.name || "без названия"}</span>
                  {#if c.kind === "manual"}
                    <button class="btn" disabled={!card.active} onclick={() => send(card, c, null)}>{c.name || "Запустить"}</button>
                  {:else if c.kind === "ctl_switch"}
                    <label class="on"><input type="checkbox" checked={!!shown(card, c)} disabled={!card.active || !c.name} onchange={(e) => send(card, c, e.currentTarget.checked)} /> {shown(card, c) ? "включено" : "выключено"}</label>
                  {:else if c.kind === "ctl_choice"}
                    <select class="field" disabled={!card.active} value={text(shown(card, c))} onchange={(e) => send(card, c, e.currentTarget.value)}>
                      <option value="" disabled>— не выбрано —</option>
                      {#each c.options as o (o)}<option value={o}>{o}</option>{/each}
                    </select>
                  {:else if c.kind === "ctl_number"}
                    <input class="range" type="range" min={c.min ?? 0} max={c.max ?? 100} step={c.step ?? 1} disabled={!card.active}
                           value={Number(shown(card, c) ?? c.min ?? 0)}
                           oninput={(e) => (drafts[key(card, c)] = +e.currentTarget.value)} onchange={(e) => send(card, c, +e.currentTarget.value)} />
                    <span class="num">{Number(shown(card, c) ?? c.min ?? 0)}</span>
                  {:else}
                    <input class="field" type="text" disabled={!card.active} value={text(shown(card, c))} oninput={(e) => (drafts[key(card, c)] = e.currentTarget.value)}
                           onkeydown={(e) => e.key === "Enter" && send(card, c, e.currentTarget.value)} />
                    <button class="btn" disabled={!card.active || !(key(card, c) in drafts)} onclick={() => send(card, c, drafts[key(card, c)])}>Задать</button>
                  {/if}
                </div>
              {/each}
            </div>
            {#if !card.active}<p class="muted small">Сценарий выключен: пульт не работает.</p>{/if}
          </div>
        {/if}

        {#if Object.keys(card.variables).length}
          <details class="block">
            <summary>Переменные ({Object.keys(card.variables).length})</summary>
            <div class="vars">
              {#each Object.entries(card.variables) as [name, value] (name)}
                <span class="mono">{name}</span><span class="mono muted">{text(value)}</span>
              {/each}
            </div>
          </details>
        {/if}

        {#if !card.stages.length && !card.controls.length && !Object.keys(card.variables).length}
          <p class="muted small">В сценарии нет этапов и управления. Добавьте ноды «Этап» и «Управление».</p>
        {/if}
      </section>
    {/each}
  </div>
{/if}

<style>
  .cards { display: flex; flex-direction: column; gap: 12px; padding: 12px 32px 32px; }
  .card { padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); display: flex; flex-direction: column; gap: 14px; }
  .card.off { opacity: 0.7; }
  header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .title { font-size: 15px; font-weight: 600; color: var(--text); }
  .spacer { flex: 1; }
  .on { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; }
  .ask { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--danger); }
  h2 { margin: 0 0 6px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .block { display: flex; flex-direction: column; gap: 6px; }
  .stage { display: grid; grid-template-columns: minmax(120px, 220px) minmax(80px, 1fr) auto; align-items: center; gap: 12px; }
  .stage .name, .control .name { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .bar { height: 6px; border-radius: 3px; background: var(--panel-2); overflow: hidden; }
  .bar i { display: block; height: 100%; background: var(--accent); }
  .controls { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 8px; }
  .control { display: grid; grid-template-columns: minmax(90px, 140px) 1fr auto; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); }
  .control .field { min-width: 0; }
  .range { width: 100%; }
  .num { font-variant-numeric: tabular-nums; min-width: 32px; text-align: right; }
  summary { cursor: pointer; font-size: 12px; color: var(--muted); }
  .vars { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; padding-top: 8px; font-size: 12px; }
  .as { display: inline-flex; align-items: center; gap: 8px; }
  .mono { font-family: var(--mono); }
  .pad { padding: 24px 32px; }
</style>
