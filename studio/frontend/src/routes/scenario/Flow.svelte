<script lang="ts">
  // «Поток»: карта опорных нод сценария (старты, этапы, ожидания, ветвления). Прохождение общее для всего мира:
  // пройденные ноды подсвечены, где сценарий стоит сейчас — отмечено, впереди — приглушено.
  import type { Schemas } from "../../lib/api";
  import Icon from "../../lib/Icon.svelte";
  import { ago, when } from "../../lib/time";

  type Flow = Schemas["PnFlow"];
  type Step = Schemas["PnStep"];
  let { flow, active }: { flow: Flow; active: boolean } = $props();

  const COLW = 244, ROWH = 104, NODEW = 208, NODEH = 80, PAD = 20;
  const ROLES: Record<string, string> = { start: "Старт", event: "Событие", stage: "Этап", wait: "Ожидание", branch: "Ветвление", end: "Конец", other: "Нода" };
  const WAITS: Record<string, string> = { event: "события", time: "времени", condition: "условия" };
  const STATE: Record<string, string> = { done: "пройдено", here: "стоим здесь", ahead: "впереди" };

  let picked = $state<string | null>(null);

  const spot = (s: Step) => ({ x: PAD + s.col * COLW, y: PAD + s.row * ROWH });
  const byId = $derived(Object.fromEntries(flow.nodes.map((n) => [n.id, n])));
  const width = $derived(PAD * 2 + Math.max(flow.cols - 1, 0) * COLW + NODEW);
  const height = $derived(PAD * 2 + Math.max(flow.rows - 1, 0) * ROWH + NODEH + 24);
  const here = $derived(flow.nodes.filter((n) => n.state === "here"));
  const chosen = $derived(picked ? byId[picked] ?? null : null);
  const forkOf = $derived(Object.fromEntries(flow.forks.map((f) => [f.node, f])));
  const lit = (n: Step) => n.state !== "ahead";

  function edge(from: Step, to: Step, back: boolean) {
    const a = spot(from), b = spot(to);
    const x1 = a.x + NODEW, y1 = a.y + NODEH / 2, x2 = b.x, y2 = b.y + NODEH / 2;
    if (back) {                                            // обратный провод цикла: обходит ноды снизу
      const low = Math.max(y1, y2) + NODEH / 2 + 18;
      return `M${x1} ${y1} C${x1 + 40} ${low} ${x2 - 40} ${low} ${x2} ${y2}`;
    }
    const dx = Math.max(32, (x2 - x1) / 2);
    return `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`;
  }

  const meta = (n: Step) => {
    if (n.state === "here") return `ждёт: ${n.here}`;
    if (n.state === "done") return `${n.role === "start" || n.role === "event" ? "сработал" : "прошли"} ${n.hits} · ${n.last_at ? ago(n.last_at) : ""}`;
    return ROLES[n.role] ?? "Нода";
  };
  const forkLabel = (n: Step) => (n.branch && forkOf[n.branch] ? `в ветке «${forkOf[n.branch].title}»` : "");
  const people = (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "поток" : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? "потока" : "потоков"}`;
</script>

{#if !flow.nodes.length}
  <div class="pad">
    <p class="muted">В сценарии пока нет опорных нод. Добавьте в редакторе «Этап» (Shift+A), стартовые события и ожидания: они появятся здесь картой.</p>
  </div>
{:else}
  <section class="now" aria-label="Где сценарий сейчас">
    {#if !active}
      <p class="muted"><Icon name="stop" size={14} /> Сценарий выключен: новые события он не слышит, ожидающие потоки стоят.</p>
    {/if}
    {#if here.length}
      <h2>Сейчас сценарий ждёт</h2>
      <ul>
        {#each here as n (n.id)}
          <li><button class="link" onclick={() => (picked = n.id)}>{n.title}</button><span class="muted">{" — " + people(n.here) + (n.waits[0]?.until ? `, до ${when(n.waits[0].until)}` : "")}</span></li>
        {/each}
      </ul>
    {:else if active}
      <p class="muted"><Icon name="clock" size={14} /> Сейчас никто ничего не ждёт: потоков нет, старты слушают события мира.</p>
    {/if}
  </section>

  <div class="legend" aria-hidden="true"><span class="k done"></span>пройдено<span class="k here"></span>стоим здесь<span class="k ahead"></span>впереди</div>

  <div class="work" class:with={chosen || flow.forks.length}>
    <div class="map" role="group" aria-label="Карта сценария">
      <div class="canvas" style="width:{width}px;height:{height}px">
        <svg width={width} height={height} aria-hidden="true">
          <defs>
            <marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 8 4 0 8z" fill="currentColor" /></marker>
          </defs>
          {#each flow.edges as e (e.src + ">" + e.to)}
            {#if byId[e.src] && byId[e.to]}
              <path d={edge(byId[e.src], byId[e.to], e.back)} class="edge" class:lit={lit(byId[e.src]) && lit(byId[e.to])} class:back={e.back} marker-end="url(#arr)" />
            {/if}
          {/each}
        </svg>
        {#each flow.nodes as n (n.id)}
          {@const p = spot(n)}
          <button class="node {n.state} role-{n.role}" class:pick={picked === n.id} style="left:{p.x}px;top:{p.y}px;width:{NODEW}px;height:{NODEH}px"
                  aria-pressed={picked === n.id} onclick={() => (picked = picked === n.id ? null : n.id)}
                  aria-label="{ROLES[n.role]} «{n.title}»: {STATE[n.state]}{n.state === 'here' ? `, ждёт ${people(n.here)}` : ''}">
            <span class="kind">{(ROLES[n.role] ?? "Нода") + (forkLabel(n) ? " · " + forkLabel(n) : "")}</span>
            <span class="title">{n.title}</span>
            <span class="meta">{meta(n)}</span>
          </button>
        {/each}
      </div>
    </div>

    <aside class="side" aria-live="polite">
      {#if chosen}
        <div class="card">
          <h3>{chosen.title}</h3>
          <p class="muted">{ROLES[chosen.role]} · {STATE[chosen.state]}</p>
          <dl>
            <dt>Проходов</dt><dd>{chosen.hits}</dd>
            <dt>Последний</dt><dd>{chosen.last_at ? `${when(chosen.last_at)} (${ago(chosen.last_at)})` : "ещё не было"}</dd>
          </dl>
          {#if chosen.waits.length}
            <h4>Чего ждёт</h4>
            <ul class="waits">
              {#each chosen.waits as w, i (i)}
                <li><b>{w.owner || "любой игрок"}</b>{" — ждёт " + (WAITS[w.kind] ?? w.kind)}<span class="muted">{" с " + when(w.since) + (w.until ? ", до " + when(w.until) : "")}</span></li>
              {/each}
              {#if chosen.here > chosen.waits.length}<li class="muted">…и ещё {chosen.here - chosen.waits.length}</li>{/if}
            </ul>
          {/if}
        </div>
      {/if}

      {#each flow.forks as f (f.node)}
        <div class="card fork">
          <h3><Icon name="layers" size={14} /> {f.title}</h3>
          <p class="muted">
            {#if f.repeat}Повтор: занято {f.taken}{f.total ? ` из ${f.total}` : ""}, набор {f.open ? "открыт" : "закрыт"}{:else}Одна ветка{/if}
          </p>
          {#if f.branches.length}
            <ul class="branches">
              {#each f.branches as b (b.run)}
                <li class={b.state}>
                  <span class="dot" aria-hidden="true"></span>
                  <span class="who">{b.state === "free" ? "свободная ветка" : b.owner || "без владельца"}</span>
                  <span class="muted at">{b.state === "done" ? (b.outcome || "закончена") : b.at ? `стоит: ${b.at}` : "идёт"}</span>
                </li>
              {/each}
            </ul>
          {:else}<p class="muted small">Веток пока нет.</p>{/if}
        </div>
      {/each}

      {#if !chosen && !flow.forks.length}<p class="muted small">Нажмите на ноду, чтобы увидеть, чего она ждёт.</p>{/if}
    </aside>
  </div>
{/if}

<style>
  .pad { padding: 24px 32px; max-width: 640px; }
  .now { padding: 14px 32px 0; }
  .now h2 { margin: 0 0 6px; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .now ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; font-size: 13.5px; }
  .now p { margin: 0 0 4px; display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .link { border: 0; background: transparent; padding: 0; color: var(--warn); font-weight: 600; cursor: pointer; text-align: left; }
  .link:hover { text-decoration: underline; }
  .legend { display: flex; align-items: center; gap: 6px; padding: 12px 32px 0; font-size: 12px; color: var(--muted); }
  .legend .k { width: 10px; height: 10px; border-radius: 3px; margin-left: 10px; border: 1px solid var(--line); }
  .legend .k:first-child { margin-left: 0; }
  .k.done { background: rgba(95, 208, 160, 0.35); border-color: var(--ok); }
  .k.here { background: rgba(242, 198, 109, 0.4); border-color: var(--warn); }
  .k.ahead { border-style: dashed; }

  .work { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; padding: 10px 32px 32px; align-items: start; }
  .work.with { grid-template-columns: minmax(0, 1fr) 300px; }
  .map { overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); max-height: 70vh; }
  .canvas { position: relative; }
  svg { position: absolute; inset: 0; color: var(--line); overflow: visible; }
  .edge { fill: none; stroke: currentColor; stroke-width: 1.5; }
  .edge.lit { color: #4a8f76; }
  .edge.back { stroke-dasharray: 5 4; }

  .node { position: absolute; display: flex; flex-direction: column; justify-content: center; gap: 1px; padding: 6px 10px 6px 12px; text-align: left; cursor: pointer;
          border: 1px solid var(--line); border-left-width: 4px; border-radius: var(--radius-s); background: var(--panel-2); color: var(--text); overflow: hidden; }
  .node:hover { background: var(--raise); }
  .node.pick { box-shadow: 0 0 0 2px var(--accent); }
  .node.done { border-color: rgba(95, 208, 160, 0.55); border-left-color: var(--ok); }
  .node.here { border-color: rgba(242, 198, 109, 0.7); border-left-color: var(--warn); background: rgba(242, 198, 109, 0.09); }
  .node.ahead { border-style: dashed; border-left-style: solid; color: var(--muted); background: transparent; }
  .node.role-branch { border-radius: 14px var(--radius-s) var(--radius-s) 14px; }
  .node.role-end { border-radius: var(--radius-s) 14px 14px var(--radius-s); }
  .kind { font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.4px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .node .title { font-size: 13px; font-weight: 600; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
  .meta { font-size: 11.5px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .node.here .meta { color: var(--warn); }

  .side { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .card { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .card h3 { display: flex; align-items: center; gap: 6px; margin: 0; font-size: 14px; overflow-wrap: anywhere; }
  .card h4 { margin: 4px 0 0; font-size: 11px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  .card p { margin: 0; font-size: 12.5px; }
  .small { font-size: 12px; }
  dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 4px 12px; margin: 0; font-size: 12.5px; }
  dt { color: var(--muted); }
  dd { margin: 0; }
  .waits, .branches { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; }
  .branches li { display: grid; grid-template-columns: 10px minmax(0, 1fr); gap: 2px 8px; align-items: center; }
  .branches .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); }
  .branches .taken .dot { background: var(--warn); }
  .branches .free .dot { background: transparent; border: 1.5px solid var(--ok); }
  .branches .done .dot { background: var(--ok); }
  .branches .at { grid-column: 2; }

  @media (max-width: 960px) { .work.with { grid-template-columns: minmax(0, 1fr); } }
  @media (max-width: 720px) { .now, .legend { padding-left: 16px; padding-right: 16px; } .work { padding-left: 16px; padding-right: 16px; } }
</style>
