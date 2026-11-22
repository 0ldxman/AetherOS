<script lang="ts">
  // «Поток»: карта сценария слева направо. Узлы — точки с названием под ними («Этап», «Ветвление», старты), стрелки — переходы;
  // чего сценарий ждёт сейчас, подписано на стрелке, а узел перед ней обведён. От «Ветвления» вниз идёт дорожка: карта потока внутри ветки.
  // Прохождение общее для всего мира; потоки веток раскрываются списком. Подробности и вмешательство автора — карточкой у выбранной точки.
  import { onMount, tick } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Icon from "../../lib/Icon.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { ago, when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";
  import { COLW, R, layoutMarks, place, route, summary, waitText, type FlowEdge, type FlowFork, type FlowNode, type FlowTail, type WaitRow } from "./flow";

  let { flow, active, id, editable, reload }: { flow: Schemas["PnFlow"]; active: boolean; id: number; editable: boolean; reload: () => Promise<void> } = $props();

  const nodes = $derived(flow.nodes as FlowNode[]);
  const edges = $derived(flow.edges as FlowEdge[]);
  const tails = $derived(flow.tails as FlowTail[]);
  const forks = $derived(flow.forks as FlowFork[]);
  const spot = $derived(place(nodes));
  const byId = $derived(new Map(nodes.map((n) => [n.id, n])));
  const forkOf = $derived(new Map(forks.map((f) => [f.node, f])));
  const clock = (iso: string) => new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  const marks = $derived(layoutMarks(nodes, edges, tails, spot, clock));

  const bands = $derived(
    [...new Set(nodes.filter((n) => n.branch).map((n) => n.branch))].flatMap((group) => {
      const own = nodes.filter((n) => n.branch === group);
      const head = spot.get(group);
      const fork = forkOf.get(group);
      if (!own.length || !head || !fork) return [];
      const xs = own.map((n) => spot.get(n.id)!.x), ys = own.map((n) => spot.get(n.id)!.y);
      const left = head.x + COLW / 2 - 26;
      const top = Math.min(...ys) - 54;
      const stub = own.some((n) => n.role === "lane");
      return [{ group, fork, x: left, y: top, w: Math.max(...xs) + (stub ? 190 : COLW * 0.5) - left, h: Math.max(...ys) + 66 - top }];
    }),
  );

  const width = $derived(Math.max(...[...spot.values()].map((p) => p.x), 0) + 130 + Math.max(0, ...marks.filter((m) => m.kind === "tail").map((m) => m.w)));
  const height = $derived(Math.max(150, Math.max(...[...spot.values()].map((p) => p.y), 0) + 96));

  let avail = $state(0);
  let zoom = $state<number | null>(null);                               // null — по ширине окна
  const fit = $derived(Math.max(0.7, Math.min(1, avail && width ? avail / width : 1)));
  const scale = $derived(zoom ?? fit);
  const step = (d: number) => (zoom = Math.min(1.6, Math.max(0.5, Math.round(((zoom ?? fit) + d) * 10) / 10)));

  type Sel = { kind: "node"; id: string } | { kind: "edge"; id: string } | { kind: "fork"; id: string } | null;
  let pick = $state<Sel>(null);
  const same = (a: Sel, b: Sel) => !!a && !!b && a.kind === b.kind && a.id === b.id;
  const toggle = (next: Sel) => (pick = same(pick, next) ? null : next);
  const edgeKey = (e: FlowEdge) => `${e.src}>${e.to}`;

  let mapEl = $state<HTMLElement>();
  let sizedEl = $state<HTMLElement>();
  let legend = $state(false);
  let pos = $state<{ x: number; y: number; above: boolean; side: boolean } | null>(null);
  let bump = $state(0);                                            // карта прокрутилась или окно изменилось: карточку ставим заново
  let busy = $state(false);

  const anchor = (p: NonNullable<Sel>) => (p.kind === "node" ? `n-${p.id}` : p.kind === "fork" ? `b-${p.id}` : `chip:${p.id}`);
  const nodeWaits = (nid: string): WaitRow[] => [...edges.filter((e) => e.src === nid && !e.lane && e.wait).flatMap((e) => e.wait!.waits), ...(tails.find((t) => t.node === nid)?.waits ?? [])];
  const here = $derived(nodes.filter((n) => n.here));

  const shown = $derived.by(() => {
    if (!pick) return null;
    if (pick.kind === "node") {
      const n = byId.get(pick.id);
      return n ? { title: n.title, hint: n.hint, node: n, waits: nodeWaits(n.id), fork: null as FlowFork | null } : null;
    }
    if (pick.kind === "edge") {
      const e = edges.find((x) => edgeKey(x) === pick!.id);
      const from = byId.get(e?.src ?? ""), to = byId.get(e?.to ?? "");
      return e ? { title: `${from?.title ?? ""} → ${to?.role === "lane" ? "ветка" : (to?.title ?? "")}`, hint: "", node: null, waits: e.wait?.waits ?? [], fork: null as FlowFork | null } : null;
    }
    const f = forkOf.get(pick.id);
    return f ? { title: f.title, hint: "", node: null, waits: [], fork: f } : null;
  });

  // карточка стоит у выбранной точки, в координатах прокручиваемой карты
  $effect(() => {
    pick; scale; flow; sizedEl; bump;
    tick().then(() => {
      const el = pick ? document.getElementById(anchor(pick)) : null;
      if (!el) return void (pos = null);
      const a = el.getBoundingClientRect();
      const side = innerWidth - a.right > 380 || a.left > 380;               // карточка сбоку от точки, чтобы не закрывать то, о чём она
      const right = innerWidth - a.right > 380;
      const above = !side && a.bottom > innerHeight * 0.6;
      pos = side ? { x: right ? a.right + 12 : a.left - 362, y: Math.max(8, Math.min(a.top - 20, innerHeight - 340)), above: false, side }
                 : { x: Math.max(8, Math.min(a.left + a.width / 2 - 175, innerWidth - 366)), y: above ? innerHeight - a.top + 10 : a.bottom + 10, above, side };
    });
  });
  const BRANCH_STATE: Record<string, string> = { free: "свободная", taken: "идёт", done: "закончена" };
  const gameShort = (stamp: string) => `${stamp.slice(8, 10)}.${stamp.slice(5, 7)} ${stamp.slice(11, 16)}`;
  const who = (w: WaitRow) => (w.free ? "свободная ветка" : w.owner || "любой игрок");
  const what = (w: WaitRow) => (w.kind === "time" ? (w.until_game ? `игрового времени ${gameShort(w.until_game)}` : "времени") : w.kind === "condition" ? "условия" : w.what ? `«${w.what}»` : "события");

  async function skip(w: WaitRow) {
    if (!(await ask("Пропустить ожидание?", `Поток пойдёт дальше, как будто ждать больше нечего: ${what(w)}.`, "Пропустить"))) return;
    busy = true;
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/waits/{wait_id}/skip", { params: { path: { graph_id: id, wait_id: w.id } } });
    busy = false;
    if (error) toast(problem(error), "error");
    else toast("Ожидание пропущено.");
    await reload();
  }

  async function stop(run: number, owner: string) {
    if (!(await ask("Остановить поток?", `Поток${owner ? ` «${owner}»` : ""} закончится. Занятое ветвлением место останется занятым.`, "Остановить"))) return;
    busy = true;
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/runs/{run_id}/stop", { params: { path: { graph_id: id, run_id: run } } });
    busy = false;
    if (error) toast(problem(error), "error");
    else toast("Поток остановлен.");
    await reload();
  }

  // ---------- движение по карте ----------
  const pan = (el: HTMLElement) => {
    let from: { x: number; y: number; sl: number; st: number; moved: boolean } | null = null;
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || (e.target as HTMLElement).closest("button, a, .pop")) return;
      from = { x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop, moved: false };
      el.setPointerCapture(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (!from) return;
      if (Math.abs(e.clientX - from.x) + Math.abs(e.clientY - from.y) > 4) { from.moved = true; el.classList.add("drag"); }
      el.scrollLeft = from.sl - (e.clientX - from.x);
      el.scrollTop = from.st - (e.clientY - from.y);
    };
    const up = () => {
      if (from && !from.moved) pick = null;                                   // щелчок по пустому месту закрывает карточку
      from = null;
      el.classList.remove("drag");
    };
    const wheel = (e: WheelEvent) => { if (e.ctrlKey) { e.preventDefault(); step(e.deltaY < 0 ? 0.1 : -0.1); } };
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
    el.addEventListener("wheel", wheel, { passive: false });
    return { destroy() { el.removeEventListener("pointerdown", down); el.removeEventListener("pointermove", move); el.removeEventListener("pointerup", up); el.removeEventListener("pointercancel", up); el.removeEventListener("wheel", wheel); } };
  };

  function toCurrent() {
    const target = here[0];
    const p = target && spot.get(target.id);
    if (!mapEl || !p) return;
    mapEl.scrollTo({ left: Math.max(0, p.x * scale - mapEl.clientWidth / 2), top: Math.max(0, p.y * scale - mapEl.clientHeight / 2), behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }
  let centered = false;
  $effect(() => { if (!centered && mapEl && avail && here.length) { centered = true; tick().then(toCurrent); } });

  function nav(e: KeyboardEvent, n: FlowNode) {
    if (e.key === "Escape") { pick = null; return; }
    let to: string | undefined;
    const column = nodes.filter((x) => x.col === n.col).sort((a, b) => a.row - b.row);
    const at = column.findIndex((x) => x.id === n.id);
    if (e.key === "ArrowRight") to = edges.find((x) => x.src === n.id && !x.back)?.to;
    else if (e.key === "ArrowLeft") to = edges.find((x) => x.to === n.id && !x.back)?.src;
    else if (e.key === "ArrowDown") to = column[at + 1]?.id;
    else if (e.key === "ArrowUp") to = column[at - 1]?.id;
    if (to) { e.preventDefault(); document.getElementById(`n-${to}`)?.focus(); }
  }

  // порядок в разметке — слева направо, как на карте: так идёт и Tab
  type Part = { x: number; y: number; kind: "node"; n: FlowNode } | { x: number; y: number; kind: "band"; b: (typeof bands)[number] } | { x: number; y: number; kind: "mark"; m: (typeof marks)[number] };
  const parts = $derived<Part[]>(
    [
      ...bands.map((b): Part => ({ x: b.x, y: b.y, kind: "band", b })),
      ...nodes.map((n): Part => ({ x: spot.get(n.id)!.x, y: spot.get(n.id)!.y, kind: "node", n })),
      ...marks.map((m): Part => ({ x: m.x, y: m.y, kind: "mark", m })),
    ].sort((a, b) => a.x - b.x || a.y - b.y),
  );

  const describe = (n: FlowNode) => `${n.role === "start" ? "Старт" : n.role === "fork" ? "Ветвление" : "Этап"} «${n.title}»: ${n.here ? "сценарий стоит после него" : n.state === "done" ? "пройден" : "ещё не проходили"}`;
  onMount(() => { const key = (e: KeyboardEvent) => { if (e.key === "Escape") { pick = null; legend = false; } }; const again = () => bump++; document.addEventListener("keydown", key); window.addEventListener("resize", again); window.addEventListener("scroll", again, true); return () => { document.removeEventListener("keydown", key); window.removeEventListener("resize", again); window.removeEventListener("scroll", again, true); }; });
</script>

{#if !nodes.length}
  <div class="pad"><p class="muted">Карта пока пуста. Добавьте в сценарий «Этап» (Shift+A) в ключевых местах, и он станет точкой на карте. Без этапов здесь были бы только старты и ожидания.</p></div>
{:else}
  <div class="bar">
    {#if !active}<span class="off"><Icon name="stop" size={13} /> Сценарий выключен: он не слышит события, ожидающие потоки стоят.</span>{/if}
    <span class="spacer"></span>
    {#if here.length}<button class="btn ghost" onclick={toCurrent}><Icon name="pin" size={14} />К текущему месту</button>{/if}
    <div class="legend">
      <button class="btn ghost" aria-expanded={legend} onclick={() => (legend = !legend)} aria-label="Что значат значки"><Icon name="help" size={14} /></button>
      {#if legend}
        <div class="lg" role="note">
          <p><i class="d done"></i> пройдено · <i class="d ahead"></i> ещё нет</p>
          <p><i class="d here"></i> сценарий стоит после этой точки</p>
          <p><i class="d sq"></i> старт · <i class="d dia"></i> ветвление</p>
          <p><i class="d pill">ждёт</i> чего ждёт сценарий (на стрелке)</p>
          <p class="muted">Время ожидания — игровое; реальное в карточке по клику.</p>
        </div>
      {/if}
    </div>
    <div class="zoom" role="group" aria-label="Масштаб карты">
      <button class="btn ghost" onclick={() => step(-0.1)} aria-label="Уменьшить"><Icon name="minus" size={14} /></button>
      <button class="btn ghost" onclick={() => (zoom = null)} aria-label="По ширине окна">По ширине</button>
      <button class="btn ghost" onclick={() => step(0.1)} aria-label="Увеличить"><Icon name="plus" size={14} /></button>
    </div>
  </div>

  <div class="map" bind:this={mapEl} bind:clientWidth={avail} use:pan role="group" aria-label="Карта сценария. Стрелки на клавиатуре переходят между точками, Escape закрывает карточку">
    <div class="sized" bind:this={sizedEl} style="width:{width * scale}px;height:{height * scale}px">
      <div class="world" style="width:{width}px;height:{height}px;transform:scale({scale})">
        <svg width={width} height={height} aria-hidden="true">
          <defs><marker id="head" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6.5" markerHeight="6.5" orient="auto"><path d="M0 0 8 4 0 8z" fill="currentColor" /></marker></defs>
          {#each bands as b (b.group)}<rect class="bandbox" x={b.x} y={b.y} width={b.w} height={b.h} rx="14" />{/each}
          {#each edges as e (edgeKey(e))}
            {@const a = spot.get(e.src)} {@const b = spot.get(e.to)}
            {#if a && b}
              <path d={route(a, b, e).d} class="edge" class:done={byId.get(e.src)?.state === "done" && byId.get(e.to)?.state === "done"} class:wait={!!e.wait} class:back={e.back} marker-end="url(#head)" />
            {/if}
          {/each}
          {#each tails as t (t.node)}
            {@const a = spot.get(t.node)}
            {#if a}<path d="M{a.x + R + 2} {a.y} L{a.x + 60} {a.y}" class="edge wait stub" marker-end="url(#head)" />{/if}
          {/each}
        </svg>

        {#each parts as part (part.kind === "node" ? "n" + part.n.id : part.kind === "band" ? "b" + part.b.group : part.m.key)}
          {#if part.kind === "band"}
            {@const b = part.b}
            <button id="b-{b.group}" class="bandhead" class:on={pick?.kind === "fork" && pick.id === b.group} style="left:{b.x + 40}px;top:{b.y + 10}px" aria-expanded={pick?.kind === "fork" && pick.id === b.group}
                    onclick={() => toggle({ kind: "fork", id: b.group })}>
              <span class="bn">{b.fork.title}</span>
              <span class="muted">{b.fork.repeat ? `занято ${b.fork.taken}${b.fork.total ? ` из ${b.fork.total}` : ""}` : b.fork.taken ? "занята" : "одна ветка"}{b.fork.done ? ` · закончили ${b.fork.done}` : ""}</span>
              <span class="count">потоки · {b.fork.branches.length}</span>
            </button>
          {:else if part.kind === "node"}
            {@const n = part.n}
            {#if n.role === "lane"}
              <span class="stubnode" style="left:{part.x}px;top:{part.y}px">{n.title}</span>
            {:else}
              <button id="n-{n.id}" class="node {n.role} {n.state}" class:here={n.here} class:on={pick?.kind === "node" && pick.id === n.id} style="left:{part.x}px;top:{part.y}px"
                      aria-label={describe(n)} aria-pressed={pick?.kind === "node" && pick.id === n.id} title={n.hint || n.title} onclick={() => toggle({ kind: "node", id: n.id })} onkeydown={(e) => nav(e, n)}>
                <span class="dot" aria-hidden="true"></span>
                <span class="name">{n.title}</span>
              </button>
            {/if}
          {:else}
            {@const m = part.m}
            {#if m.kind === "label"}
              <span class="elabel" style="left:{m.x}px;top:{m.y}px">{m.text}</span>
            {:else}
              {@const key = m.edge ? edgeKey(m.edge) : m.key.slice(5)}
              <button id="chip:{key}" class="chip" class:on={m.kind === "chip" && pick?.kind === "edge" && pick.id === key} style="left:{m.x}px;top:{m.y}px" aria-label="Сценарий ждёт: {m.text}"
                      onclick={() => (m.kind === "tail" ? toggle({ kind: "node", id: m.key.slice(5) }) : toggle({ kind: "edge", id: key }))}>{m.text}</button>
            {/if}
          {/if}
        {/each}
      </div>

      {#if shown && pos}
        <div class="pop" role="group" aria-label="Подробности: {shown.title}" style="left:{pos.x}px;{pos.above ? `bottom:${pos.y}px` : `top:${pos.y}px`}">
          <button class="x" onclick={() => (pick = null)} aria-label="Закрыть"><Icon name="close" size={14} /></button>
          <h3>{shown.title}</h3>
          {#if shown.node}
            {#if shown.hint}<p class="muted">{shown.hint}</p>{/if}
            <p class="muted">{shown.node.hits ? `Проходов: ${shown.node.hits}${shown.node.last_at ? `, последний ${ago(shown.node.last_at)}` : ""}` : "Ещё не проходили."}</p>
          {/if}
          {#if shown.waits.length}
            <ul class="waits">
              {#each shown.waits as w (w.id)}
                <li>
                  <span><b>{who(w)}</b> — ждёт {what(w)}</span>
                  <span class="muted">{w.until ? `реально ${when(w.until)}, ` : ""}с {when(w.since)}</span>
                  {#if editable && !w.free}
                    <span class="acts">
                      <button class="btn" disabled={busy} onclick={() => skip(w)}>Пропустить ожидание</button>
                      <button class="btn danger" disabled={busy} onclick={() => stop(w.run, w.owner)}>Остановить поток</button>
                    </span>
                  {/if}
                </li>
              {/each}
            </ul>
          {:else if pick?.kind === "edge"}<p class="muted">Здесь сейчас никто не ждёт.</p>{/if}
          {#if shown.fork}
            {#if shown.fork.branches.length}
              <ul class="branches">
                {#each shown.fork.branches as b (b.run)}
                  <li class={b.state}>
                    <span class="bd" aria-hidden="true"></span><b>{b.state === "free" ? "свободная ветка" : b.owner || "без владельца"}</b>
                    <span class="muted">{" · " + BRANCH_STATE[b.state] + (b.state === "done" ? (b.outcome ? `: ${b.outcome}` : "") : b.at ? `, ждёт «${b.at}»` : "")}</span>
                    {#if editable && b.state === "taken"}<button class="btn ghost danger mini" disabled={busy} onclick={() => stop(b.run, b.owner)}>Остановить</button>{/if}
                  </li>
                {/each}
              </ul>
            {:else}<p class="muted">Веток пока нет.</p>{/if}
          {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .pad { padding: 24px 32px; max-width: 640px; }
  .bar { display: flex; align-items: center; gap: 8px; padding: 12px 32px 0; min-height: 32px; position: relative; }
  .spacer { flex: 1; }
  .off { display: inline-flex; align-items: center; gap: 6px; color: var(--warn); font-size: 12.5px; }
  .bar .btn { height: 28px; padding: 0 8px; font-size: 12px; }
  .zoom { display: inline-flex; gap: 2px; }
  .legend { position: relative; }
  .lg { position: absolute; right: 0; top: 34px; z-index: 5; width: 300px; padding: 10px 14px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel-2); font-size: 12.5px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4); }
  .lg p { margin: 4px 0; display: flex; align-items: center; gap: 6px; }
  .d { display: inline-block; width: 12px; height: 12px; box-sizing: border-box; border-radius: 50%; border: 2px solid var(--line); }
  .d.done { background: var(--ok); border-color: var(--ok); }
  .d.ahead { border-style: dashed; border-color: var(--faint); }
  .d.here { border-color: var(--warn); box-shadow: 0 0 0 3px rgba(242, 198, 109, 0.35); }
  .d.sq { border-radius: 3px; border-color: var(--accent); background: var(--accent-soft); }
  .d.dia { border-radius: 2px; transform: rotate(45deg) scale(0.85); border-color: var(--ok); background: var(--ok); }
  .d.pill { width: auto; height: auto; padding: 0 7px; border-radius: 999px; border-color: rgba(242, 198, 109, 0.55); background: #2a2414; color: var(--warn); font-size: 11px; font-style: normal; }

  .map { position: relative; margin: 10px 32px 32px; overflow: auto; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); max-height: 72vh; cursor: grab; }
  :global(.map.drag) { cursor: grabbing; user-select: none; }
  .sized { position: relative; min-height: 120px; }
  .world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
  svg { position: absolute; inset: 0; color: #69707d; overflow: visible; pointer-events: none; }
  .edge { fill: none; stroke: currentColor; stroke-width: 1.6; }
  .edge.done { color: #3f9275; }
  .edge.wait { color: var(--warn); }
  .edge.back, .edge.stub { stroke-dasharray: 5 4; }
  .bandbox { fill: rgba(122, 162, 255, 0.04); stroke: #69707d; stroke-width: 1.5; stroke-dasharray: 6 5; }

  .bandhead { position: absolute; display: inline-flex; align-items: center; gap: 8px; max-width: 520px; padding: 3px 10px; border: 1px solid transparent; border-radius: 999px; background: transparent; color: var(--text); font-size: 12.5px; cursor: pointer; white-space: nowrap; }
  .bandhead:hover, .bandhead.on { background: var(--panel-2); border-color: var(--line); }
  .bn { font-weight: 600; overflow: hidden; text-overflow: ellipsis; }
  .count { padding: 0 8px; border-radius: 999px; background: var(--raise); color: var(--text); font-size: 11.5px; line-height: 18px; }
  .stubnode { position: absolute; transform: translate(-8px, -50%); font-size: 12.5px; color: var(--muted); white-space: nowrap; }

  .node { position: absolute; width: 0; height: 0; padding: 0; border: 0; background: transparent; color: var(--text); cursor: pointer; }
  .dot { position: absolute; left: -9px; top: -9px; width: 18px; height: 18px; box-sizing: border-box; border-radius: 50%; border: 2px solid var(--line); background: var(--panel); transition: transform 0.1s; }
  .dot::after { content: ""; position: absolute; inset: -6px; }                       /* зона нажатия 30 px */
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

  .chip { position: absolute; transform: translate(-50%, -50%); max-width: 200px; min-height: 24px; padding: 0 10px; border: 1px solid rgba(242, 198, 109, 0.55); border-radius: 999px; background: #2a2414; color: var(--warn); font-size: 11.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer; }
  .chip:hover, .chip.on { background: #3a3119; }
  .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .elabel { position: absolute; transform: translate(-50%, -50%); padding: 0 4px; background: var(--panel); font-size: 11px; font-weight: 600; letter-spacing: 0.3px; color: var(--accent); white-space: nowrap; }

  .pop { position: fixed; z-index: 30; width: 350px; max-width: calc(100vw - 48px); padding: 12px 16px 12px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel-2); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45); cursor: default; }
  .pop h3 { margin: 0 24px 4px 0; font-size: 14px; overflow-wrap: anywhere; }
  .pop p { margin: 2px 0; font-size: 12.5px; }
  .pop .x { position: absolute; right: 8px; top: 8px; display: inline-flex; padding: 4px; border: 0; border-radius: var(--radius-s); background: transparent; color: var(--muted); cursor: pointer; }
  .pop .x:hover { color: var(--text); background: var(--raise); }
  .pop ul { margin: 8px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; font-size: 12.5px; max-height: 280px; overflow: auto; }
  .waits li { display: flex; flex-direction: column; gap: 2px; padding-bottom: 8px; border-bottom: 1px solid var(--line-soft); }
  .waits li:last-child { border-bottom: 0; padding-bottom: 0; }
  .acts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .acts .btn { height: 28px; font-size: 12px; padding: 0 10px; }
  .branches li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
  .btn.mini { height: 24px; font-size: 11.5px; padding: 0 8px; margin-left: auto; }
  .bd { width: 8px; height: 8px; border-radius: 50%; background: var(--faint); align-self: center; }
  .branches .taken .bd { background: var(--warn); }
  .branches .free .bd { background: transparent; border: 1.5px solid var(--ok); }
  .branches .done .bd { background: var(--ok); }

  @media (max-width: 720px) { .bar { padding: 12px 16px 0; } .map { margin-left: 16px; margin-right: 16px; } }
  @media (prefers-reduced-motion: reduce) { .dot { transition: none; } }
</style>
