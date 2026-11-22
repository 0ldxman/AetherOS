<script lang="ts">
  // «Поток»: карта сценария слева направо. Узлы — точки с названием под ними («Этап», «Ветвление», старты), стрелки — переходы;
  // чего сценарий ждёт сейчас, подписано на стрелке, а узел перед ней обведён. «Ветвление» — узел, от которого вниз идёт дорожка:
  // карта потока внутри ветки. Прохождение общее для всего мира; потоки веток раскрываются списком по «⋯».
  import type { Schemas } from "../../lib/api";
  import Icon from "../../lib/Icon.svelte";
  import { ago, when } from "../../lib/time";
  import { COLW, PADX, PADY, R, BAND, ROWH, curve, middle, place, summary, type FlowEdge, type FlowFork, type FlowNode, type FlowTail, type WaitInfo } from "./flow";

  let { flow, active }: { flow: Schemas["PnFlow"]; active: boolean } = $props();

  const nodes = $derived(flow.nodes as FlowNode[]);
  const edges = $derived(flow.edges as FlowEdge[]);
  const tails = $derived(flow.tails as FlowTail[]);
  const forks = $derived(flow.forks as FlowFork[]);
  const spot = $derived(place(nodes));
  const byId = $derived(new Map(nodes.map((n) => [n.id, n])));
  const forkOf = $derived(new Map(forks.map((f) => [f.node, f])));

  const bands = $derived(
    [...new Set(nodes.filter((n) => n.branch).map((n) => n.branch))].flatMap((group) => {
      const own = nodes.filter((n) => n.branch === group);
      const xs = own.map((n) => spot.get(n.id)!.x), ys = own.map((n) => spot.get(n.id)!.y);
      const head = spot.get(group);
      const fork = forkOf.get(group);
      if (!own.length || !head || !fork) return [];
      const left = Math.min(...xs, head.x + COLW * 0.45) - COLW * 0.4;
      return [{ group, fork, x: left, y: Math.min(...ys) - 40, w: Math.max(...xs) + COLW * 0.45 - left, h: Math.max(...ys) - Math.min(...ys) + 40 + 92 }];
    }),
  );

  const width = $derived(PADX * 2 + Math.max(flow.cols - 1, 0) * COLW + 90);
  const height = $derived(PADY * 2 + Math.max(flow.rows, 1) * ROWH + BAND * bands.length + 10);

  let avail = $state(0);
  let zoom = $state<number | null>(null);                               // null — по ширине окна
  const fit = $derived(Math.max(0.7, Math.min(1, avail && width ? avail / width : 1)));
  const scale = $derived(zoom ?? fit);
  const step = (d: number) => (zoom = Math.min(1.6, Math.max(0.5, Math.round(((zoom ?? fit) + d) * 10) / 10)));

  type Sel = { kind: "node"; id: string } | { kind: "edge"; id: string } | { kind: "fork"; id: string } | null;
  let pick = $state<Sel>(null);
  const toggle = (next: Sel) => (pick = pick && next && pick.kind === next.kind && pick.id === next.id ? null : next);

  const key = (e: FlowEdge) => `${e.src}>${e.to}`;
  const clock = (iso: string) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const rowOf = (w: WaitInfo["waits"][number]) => `${w.free ? "свободная ветка" : w.owner || "любой игрок"} — ждёт ${w.kind === "time" ? (w.until ? `до ${when(w.until)}` : "время") : w.kind === "condition" ? "условие" : w.what ? `«${w.what}»` : "событие"}, с ${when(w.since)}`;
  const waitsOf = (id: string): WaitInfo["waits"] => [...edges.filter((e) => e.src === id && e.wait).flatMap((e) => e.wait!.waits), ...(tails.find((t) => t.node === id)?.waits ?? [])];

  const shown = $derived.by(() => {
    if (!pick) return null;
    if (pick.kind === "node") return { title: byId.get(pick.id)?.title ?? "", node: byId.get(pick.id) ?? null, waits: waitsOf(pick.id), fork: null as FlowFork | null };
    if (pick.kind === "edge") {
      const e = edges.find((x) => key(x) === pick!.id);
      return { title: `${byId.get(e?.src ?? "")?.title ?? ""} → ${byId.get(e?.to ?? "")?.title ?? ""}`, node: null, waits: e?.wait?.waits ?? [], fork: null as FlowFork | null };
    }
    return { title: forkOf.get(pick.id)?.title ?? "", node: null, waits: [], fork: forkOf.get(pick.id) ?? null };
  });
  const describe = (n: FlowNode) => `${n.role === "start" ? "Старт" : n.role === "fork" ? "Ветвление" : "Этап"} «${n.title}»: ${n.here ? "сценарий стоит после него" : n.state === "done" ? "пройден" : "ещё не проходили"}`;
  const BRANCH_STATE: Record<string, string> = { free: "свободная", taken: "идёт", done: "закончена" };
</script>

{#if !nodes.length}
  <div class="pad"><p class="muted">Карта пока пуста. Добавьте в сценарий «Этап» (Shift+A) в ключевых местах, и он станет точкой на карте. Без этапов здесь были бы только старты и ожидания.</p></div>
{:else}
  <div class="bar">
    {#if !active}<span class="off"><Icon name="stop" size={13} /> Сценарий выключен: он не слышит события, ожидающие потоки стоят.</span>{/if}
    <span class="spacer"></span>
    <div class="zoom" role="group" aria-label="Масштаб карты">
      <button class="btn ghost" onclick={() => step(-0.1)} aria-label="Уменьшить"><Icon name="minus" size={14} /></button>
      <button class="btn ghost" onclick={() => (zoom = null)} aria-label="По ширине окна">По ширине</button>
      <button class="btn ghost" onclick={() => step(0.1)} aria-label="Увеличить"><Icon name="plus" size={14} /></button>
    </div>
  </div>

  <div class="map" bind:clientWidth={avail} role="group" aria-label="Карта сценария">
    <div class="sized" style="width:{width * scale}px;height:{height * scale}px">
      <div class="world" style="width:{width}px;height:{height}px;transform:scale({scale})">
        {#each bands as b (b.group)}
          <div class="band" style="left:{b.x}px;top:{b.y}px;width:{b.w}px;height:{b.h}px">
            <button class="bandhead" class:on={pick?.kind === "fork" && pick.id === b.group} onclick={() => toggle({ kind: "fork", id: b.group })} aria-expanded={pick?.kind === "fork" && pick.id === b.group}
                    aria-label="Ветки «{b.fork.title}»: показать список потоков">
              <span class="bn">{b.fork.title}</span>
              <span class="muted">{b.fork.repeat ? `занято ${b.fork.taken}${b.fork.total ? ` из ${b.fork.total}` : ""}` : b.fork.taken ? "занята" : "одна ветка"}{b.fork.done ? ` · ✓ ${b.fork.done}` : ""}</span>
              <span class="dots" aria-hidden="true">⋯</span>
            </button>
          </div>
        {/each}

        <svg width={width} height={height} aria-hidden="true">
          <defs><marker id="head" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6.5" markerHeight="6.5" orient="auto"><path d="M0 0 8 4 0 8z" fill="currentColor" /></marker></defs>
          {#each edges as e (key(e))}
            {@const a = spot.get(e.src)} {@const b = spot.get(e.to)}
            {#if a && b}
              <path d={curve(a, b, e.back)} class="edge" class:done={byId.get(e.src)?.state === "done" && byId.get(e.to)?.state === "done"} class:wait={!!e.wait} class:back={e.back} marker-end="url(#head)" />
            {/if}
          {/each}
          {#each tails as t (t.node)}
            {@const a = spot.get(t.node)}
            {#if a}<path d="M{a.x + R + 2} {a.y} L{a.x + 62} {a.y}" class="edge wait stub" marker-end="url(#head)" />{/if}
          {/each}
        </svg>

        {#each edges as e (key(e) + ":l")}
          {@const a = spot.get(e.src)} {@const b = spot.get(e.to)}
          {#if a && b}
            {#if e.label}<span class="elabel" style="left:{b.x - 60}px;top:{b.y - 30}px">{e.label}</span>{/if}
            {#if e.wait}
              {@const m = middle(a, b, e.back)}
              <button class="chip" class:on={pick?.kind === "edge" && pick.id === key(e)} style="left:{m.x}px;top:{m.y}px" onclick={() => toggle({ kind: "edge", id: key(e) })}
                      aria-label="Сценарий ждёт: {summary(e.wait, clock)}">{summary(e.wait, clock)}</button>
            {/if}
          {/if}
        {/each}
        {#each tails as t (t.node + ":t")}
          {@const a = spot.get(t.node)}
          {#if a}<button class="chip tail" class:on={pick?.kind === "node" && pick.id === t.node} style="left:{a.x + 62}px;top:{a.y}px" onclick={() => toggle({ kind: "node", id: t.node })}
                         aria-label="Сценарий ждёт: {summary(t, clock)}">{summary(t, clock)}</button>{/if}
        {/each}

        {#each nodes as n (n.id)}
          {@const p = spot.get(n.id)!}
          <button class="node {n.role} {n.state}" class:here={n.here} class:on={pick?.kind === "node" && pick.id === n.id} style="left:{p.x}px;top:{p.y}px" aria-label={describe(n)} aria-pressed={pick?.kind === "node" && pick.id === n.id}
                  onclick={() => toggle({ kind: "node", id: n.id })}>
            <span class="dot" aria-hidden="true"></span>
            <span class="name">{n.title}</span>
          </button>
        {/each}
      </div>
    </div>
  </div>

  <div class="detail" aria-live="polite">
    {#if shown}
      <h3>{shown.title}</h3>
      {#if shown.node}
        <p class="muted">{shown.node.hits ? `Проходов: ${shown.node.hits}${shown.node.last_at ? `, последний ${ago(shown.node.last_at)}` : ""}` : "Ещё не проходили."}</p>
      {/if}
      {#if shown.waits.length}
        <ul>{#each shown.waits as w, i (i)}<li>{rowOf(w)}</li>{/each}</ul>
      {:else if !shown.fork && pick?.kind !== "node"}<p class="muted">Здесь сейчас никто не ждёт.</p>{/if}
      {#if shown.fork}
        {#if shown.fork.branches.length}
          <ul class="branches">
            {#each shown.fork.branches as b (b.run)}
              <li class={b.state}><span class="bd" aria-hidden="true"></span><b>{b.state === "free" ? "свободная ветка" : b.owner || "без владельца"}</b>
                <span class="muted">{" · " + BRANCH_STATE[b.state] + (b.state === "done" ? (b.outcome ? `: ${b.outcome}` : "") : b.at ? `, ждёт «${b.at}»` : "")}</span></li>
            {/each}
          </ul>
        {:else}<p class="muted">Веток пока нет.</p>{/if}
      {/if}
    {:else}
      <p class="muted">Нажмите на точку, подпись на стрелке или шапку дорожки, чтобы увидеть подробности.</p>
    {/if}
  </div>
{/if}

<style>
  .pad { padding: 24px 32px; max-width: 640px; }
  .bar { display: flex; align-items: center; gap: 12px; padding: 12px 32px 0; min-height: 32px; }
  .spacer { flex: 1; }
  .off { display: inline-flex; align-items: center; gap: 6px; color: var(--warn); font-size: 12.5px; }
  .zoom { display: inline-flex; gap: 2px; }
  .zoom .btn { height: 28px; padding: 0 8px; font-size: 12px; }

  .map { margin: 10px 32px 0; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); max-height: 72vh; }
  .sized { position: relative; }
  .world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
  svg { position: absolute; inset: 0; color: var(--line); overflow: visible; pointer-events: none; }
  .edge { fill: none; stroke: currentColor; stroke-width: 1.6; }
  .edge.done { color: #3f9275; }
  .edge.wait { color: var(--warn); }
  .edge.back, .edge.stub { stroke-dasharray: 5 4; }

  .band { position: absolute; border: 1.5px dashed var(--line); border-radius: 14px; background: rgba(122, 162, 255, 0.04); }
  .bandhead { position: absolute; left: 10px; bottom: 8px; display: inline-flex; align-items: center; gap: 8px; max-width: calc(100% - 20px); padding: 3px 10px; border: 1px solid transparent; border-radius: 999px; background: transparent; color: var(--text); font-size: 12.5px; cursor: pointer; }
  .bandhead:hover, .bandhead.on { background: var(--panel-2); border-color: var(--line); }
  .bn { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dots { color: var(--muted); font-size: 16px; line-height: 1; }

  .node { position: absolute; width: 0; height: 0; padding: 0; border: 0; background: transparent; color: var(--text); cursor: pointer; }
  .dot { position: absolute; left: -9px; top: -9px; width: 18px; height: 18px; box-sizing: border-box; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); transition: transform 0.1s; }
  .node:hover .dot { transform: scale(1.15); }
  .node.done .dot { background: var(--ok); border-color: var(--ok); }
  .node.ahead .dot { border-style: dashed; border-color: var(--faint); }
  .node.start .dot { border-radius: 4px; border-color: var(--accent); background: var(--accent-soft); }
  .node.start.done .dot { background: var(--accent); }
  .node.fork .dot { border-radius: 4px; transform: rotate(45deg); }
  .node.fork:hover .dot { transform: rotate(45deg) scale(1.15); }
  .node.here .dot { box-shadow: 0 0 0 4px rgba(242, 198, 109, 0.35); border-color: var(--warn); }
  .node.on .dot { outline: 2px solid var(--accent); outline-offset: 3px; }
  .node:focus-visible { outline: none; }
  .node:focus-visible .dot { outline: 2px solid var(--accent); outline-offset: 3px; }
  .name { position: absolute; left: -76px; top: 16px; width: 152px; text-align: center; font-size: 12.5px; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; color: var(--text); }
  .node.ahead .name { color: var(--muted); }

  .chip { position: absolute; transform: translate(-50%, -50%); max-width: 150px; padding: 1px 9px; border: 1px solid rgba(242, 198, 109, 0.55); border-radius: 999px; background: #2a2414; color: var(--warn); font-size: 11.5px; line-height: 18px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
  .chip.tail { transform: translate(0, -50%); }
  .chip:hover, .chip.on { background: #3a3119; }
  .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .elabel { position: absolute; font-size: 11px; font-weight: 600; letter-spacing: 0.3px; color: var(--accent); white-space: nowrap; }

  .detail { margin: 12px 32px 32px; padding: 12px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); min-height: 24px; }
  .detail h3 { margin: 0 0 4px; font-size: 14px; overflow-wrap: anywhere; }
  .detail p { margin: 2px 0; font-size: 12.5px; }
  .detail ul { margin: 6px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; max-height: 240px; overflow: auto; }
  .branches li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
  .bd { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); align-self: center; }
  .branches .taken .bd { background: var(--warn); }
  .branches .free .bd { background: transparent; border: 1.5px solid var(--ok); }
  .branches .done .bd { background: var(--ok); }

  @media (max-width: 720px) { .bar, .map, .detail { margin-left: 16px; margin-right: 16px; padding-left: 0; padding-right: 0; } .bar { margin: 0 16px; } .detail { padding: 12px; } }
  @media (prefers-reduced-motion: reduce) { .dot { transition: none; } }
</style>
