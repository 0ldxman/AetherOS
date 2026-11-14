<script lang="ts">
  // Холст сценария (приложение graph): ноды и провода, Shift+A — добавить ноду, M — выключить, Ctrl+D — копия, Delete — убрать,
  // Ctrl+S — сохранить. Справа свойства выбранной ноды и проверка. Счётчики на нодах обновляются сами.
  import { onDestroy, onMount, untrack } from "svelte";
  import { Background, Controls, MiniMap, Panel, SvelteFlow, type Connection, type Edge, type Node } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";
  import { api, problem, type Schemas } from "../../lib/api";
  import { ask } from "../../lib/confirm.svelte";
  import { engine } from "../../lib/engine.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { canAct, canEdit } from "../../lib/me.svelte";
  import { go } from "../../lib/router.svelte";
  import { toast } from "../../lib/toast.svelte";
  import FitOnce from "../mail/FitOnce.svelte";
  import AddMenu from "./AddMenu.svelte";
  import FrameNode from "./FrameNode.svelte";
  import GraphNode from "./GraphNode.svelte";
  import NodePanel from "./NodePanel.svelte";
  import { REF, defaults, freeId, insOf, summaryOf, type Catalog, type Doc, type GNode, type GWire, type Kind } from "./kinds";

  let { id }: { id: number } = $props();
  type Detail = Schemas["GrDetail"];
  type Form = { slug: string; title: string; note: string; active: boolean };

  let graph = $state<Detail | null>(null);
  let catalog = $state<Catalog | null>(null);
  let form = $state<Form>({ slug: "", title: "", note: "", active: false });
  let doc = $state<Doc>({ nodes: [], wires: [] });
  let saved = $state("");
  let problems = $state<Schemas["GrProblem"][]>([]);
  let stats = $state<Schemas["GrStats"] | null>(null);
  let selected = $state("");
  let tab = $state<"node" | "check">("node");
  let busy = $state(false);
  let menu = $state<{ x: number; y: number; from: { node: string; out: string } | null } | null>(null);
  let pointer = { x: 300, y: 200 };

  const editable = canEdit("world");
  const store = engine();
  const current_json = $derived(JSON.stringify({ form, doc }));
  const dirty = $derived(saved !== "" && current_json !== saved);
  const errors = $derived(problems.filter((p) => p.level === "error").length);
  guardUnsaved(() => dirty);

  const kindOf = (type: string): Kind | undefined => catalog?.kinds.find((k) => k.name === type);
  const fedInto = $derived(new Set(doc.wires.filter((w) => !w.in.startsWith("f:")).map((w) => w.to)));
  const current = $derived(doc.nodes.find((n) => n.id === selected) ?? null);

  function fill(data: Detail) {
    graph = data;
    form = { slug: data.slug, title: data.title, note: data.note, active: data.active };
    const raw = data.doc as Partial<Doc>;
    doc = { nodes: (raw.nodes ?? []) as GNode[], wires: (raw.wires ?? []) as GWire[] };
    saved = JSON.stringify({ form, doc });
    problems = data.problems;
    stats = data.stats;
  }
  async function load() {
    const [found, cat] = await Promise.all([
      api.GET("/studio/api/world/graphs/{graph_id}", { params: { path: { graph_id: id } } }),
      catalog ? Promise.resolve({ data: catalog }) : api.GET("/studio/api/world/graphs/catalog"),
    ]);
    if (cat.data) catalog = cat.data;
    if (found.data) fill(found.data);
    else toast("Сценарий не найден.", "error");
  }
  let poll: ReturnType<typeof setInterval>;
  onMount(() => {
    load();
    poll = setInterval(async () => {
      if (!graph) return;
      const { data } = await api.GET("/studio/api/world/graphs/{graph_id}/stats", { params: { path: { graph_id: id } } });
      if (data) stats = data;
    }, 10000);
  });
  onDestroy(() => clearInterval(poll));

  // проверка черновика на лету
  let checkTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const body = JSON.stringify(doc);
    if (!graph) return;
    clearTimeout(checkTimer);
    checkTimer = setTimeout(async () => {
      const { data } = await api.POST("/studio/api/world/graphs/check", { body: { doc: JSON.parse(body) } });
      if (data && body === JSON.stringify(doc)) problems = data;
    }, 400);
  });

  async function save() {
    if (!graph || busy) return;
    busy = true;
    const { data, error } = await api.PUT("/studio/api/world/graphs/{graph_id}", { params: { path: { graph_id: id } }, body: { ...form, doc } });
    busy = false;
    if (error || !data) return toast(problem(error, "Не сохранилось."), "error");
    fill(data);
    toast(data.problems.some((p) => p.level === "error") ? "Сохранено, но есть ошибки: см. «Проверка»." : "Сценарий сохранён.");
  }
  async function remove() {
    if (!graph || !(await ask(`Удалить сценарий «${graph.title}»?`, "Вместе с прохождениями игроков и счётчиками нод.", "Удалить сценарий"))) return;
    const { error } = await api.DELETE("/studio/api/world/graphs/{graph_id}", { params: { path: { graph_id: id } } });
    if (error) return toast(problem(error), "error");
    toast("Сценарий удалён.");
    go("/graphs");
  }

  // ---- правка документа ----
  function patchNode(nodeId: string, patch: Partial<GNode>) {
    doc = { ...doc, nodes: doc.nodes.map((n) => (n.id === nodeId ? { ...n, ...patch } : n)) };
  }
  function addNode(kind: Kind, position: { x: number; y: number }, from: { node: string; out: string } | null = null) {
    const node: GNode = { id: freeId(doc), type: kind.name, x: Math.round(position.x), y: Math.round(position.y), data: defaults(kind) };
    if (kind.name === "frame") { node.w = 420; node.h = 260; }
    const wires = [...doc.wires];
    if (from) {
      const target = insOf(kind, node.data)[0];
      if (target) wires.push({ id: `${from.node}.${from.out}-${node.id}.${target.name}`, from: from.node, out: from.out, to: node.id, in: target.name });
    }
    doc = { nodes: [...doc.nodes, node], wires };
    selected = node.id;
    tab = "node";
    menu = null;
  }
  function removeNodes(ids: string[]) {
    const gone = new Set(ids);
    doc = { nodes: doc.nodes.filter((n) => !gone.has(n.id)), wires: doc.wires.filter((w) => !gone.has(w.from) && !gone.has(w.to)) };
    if (gone.has(selected)) selected = "";
  }
  function chosen(): string[] {
    const marked = nodes.filter((n) => n.selected).map((n) => n.id);
    return marked.length ? marked : selected ? [selected] : [];
  }
  function duplicate() {
    const ids = chosen();
    let next = doc;
    for (const nodeId of ids) {
      const source = next.nodes.find((n) => n.id === nodeId);
      if (!source) continue;
      const copy = { ...structuredClone($state.snapshot(source)) as GNode, id: freeId(next), x: source.x + 40, y: source.y + 40 };
      next = { ...next, nodes: [...next.nodes, copy] };
      selected = copy.id;
    }
    doc = next;
  }
  function toggleMute() {
    const ids = new Set(chosen());
    doc = { ...doc, nodes: doc.nodes.map((n) => (ids.has(n.id) ? { ...n, mute: n.mute ? undefined : true } : n)) };
  }

  // ---- холст ----
  const nodeTypes = { gnode: GraphNode, frame: FrameNode };
  let nodes = $state.raw<Node[]>([]);
  let edges = $state.raw<Edge[]>([]);

  $effect(() => {
    const list = doc.nodes;
    const wires = doc.wires;
    const found = problems;
    const chosenId = selected;
    const live = stats;
    const picks = store.catalog?.picks ?? {};
    if (!catalog) return;
    untrack(() => {
      const keep = new Set(nodes.filter((n) => n.selected).map((n) => n.id));
      nodes = list.flatMap((n): Node[] => {
        const kind = kindOf(n.type);
        if (!kind) return [];
        if (kind.name === "frame" || kind.name === "note") {
          return [{ id: n.id, type: "frame", position: { x: n.x, y: n.y }, zIndex: kind.name === "frame" ? -1 : 0, selected: n.id === chosenId || keep.has(n.id),
                    width: kind.name === "frame" ? n.w ?? 420 : undefined, height: kind.name === "frame" ? n.h ?? 260 : undefined,
                    data: { title: String(n.data.title ?? n.data.text ?? ""), note: kind.name === "note", onresize: (w: number, h: number) => patchNode(n.id, { w: Math.round(w), h: Math.round(h) }) } } satisfies Node];
        }
        const refFields = kind.group === "action" ? kind.fields.filter((f) => catalog!.ref_kinds[f.kind]).map((f) => ({ name: f.name, label: f.label })) : [];
        return [{
          id: n.id, type: "gnode", position: { x: n.x, y: n.y }, selected: n.id === chosenId || keep.has(n.id),
          data: { node: n, kind, waiting: fedInto.has(n.id), summary: summaryOf(kind, n.data, picks), refFields,
                  errors: found.filter((p) => p.node === n.id && p.level === "error").length, warnings: found.filter((p) => p.node === n.id && p.level === "warning").length,
                  stat: live?.nodes[n.id] ?? null, used: wires.filter((w) => w.from === n.id).map((w) => w.out) },
        } satisfies Node];
      });
      edges = wires.map((w) => ({ id: w.id || `${w.from}.${w.out}-${w.to}.${w.in}`, source: w.from, sourceHandle: w.out, target: w.to, targetHandle: w.in,
                                  class: w.out === REF ? "ref" : w.out === "fail" || w.out === "timeout" ? "bad" : "" }) satisfies Edge);
    });
  });

  function refKindOf(nodeId: string) {
    const n = doc.nodes.find((x) => x.id === nodeId);
    const kind = n && kindOf(n.type);
    return kind?.ref ?? "";
  }
  function valid(c: Connection | Edge): boolean {
    const out = c.sourceHandle ?? "", inp = c.targetHandle ?? "";
    if (out === REF) {
      if (!inp.startsWith("f:")) return false;
      const target = doc.nodes.find((x) => x.id === c.target);
      const field = target && kindOf(target.type)?.fields.find((f) => f.name === inp.slice(2));
      return !!field && catalog?.ref_kinds[field.kind] === refKindOf(c.source);
    }
    return !inp.startsWith("f:");
  }
  function onconnect(c: Connection) {
    if (!c.sourceHandle || !c.targetHandle || !valid(c)) return;
    const wire = { id: `${c.source}.${c.sourceHandle}-${c.target}.${c.targetHandle}`, from: c.source, out: c.sourceHandle, to: c.target, in: c.targetHandle };
    let wires = doc.wires.filter((w) => w.id !== wire.id);
    if (wire.in.startsWith("f:")) wires = wires.filter((w) => !(w.to === wire.to && w.in === wire.in));      // в поле — один провод
    doc = { ...doc, wires: [...wires, wire] };
  }
  // провод брошен в пустоту: меню нод, новая нода сразу подключится (как в Blender)
  function onconnectend(event: MouseEvent | TouchEvent, s: { isValid: boolean | null; fromNode: { id: string } | null; fromHandle: { id?: string | null; type?: string } | null }) {
    if (s.isValid || !s.fromNode || !s.fromHandle?.id || s.fromHandle.type === "target" || s.fromHandle.id === REF || !editable) return;
    const point = "changedTouches" in event ? event.changedTouches[0] : event;
    if (document.elementFromPoint(point.clientX, point.clientY)?.closest(".svelte-flow__node")) return;
    menu = { x: point.clientX, y: point.clientY, from: { node: s.fromNode.id, out: s.fromHandle.id } };
  }
  function ondelete({ nodes: goneNodes, edges: goneEdges }: { nodes: Node[]; edges: Edge[] }) {
    const ids = new Set(goneEdges.map((e) => e.id));
    doc = { ...doc, wires: doc.wires.filter((w) => !ids.has(w.id || `${w.from}.${w.out}-${w.to}.${w.in}`)) };
    if (goneNodes.length) removeNodes(goneNodes.map((n) => n.id));
  }
  function ondragstop({ nodes: moved }: { nodes: Node[] }) {
    const at = new Map(moved.map((n) => [n.id, n.position]));
    doc = { ...doc, nodes: doc.nodes.map((n) => { const p = at.get(n.id); return p && (p.x !== n.x || p.y !== n.y) ? { ...n, x: Math.round(p.x), y: Math.round(p.y) } : n; }) };
  }

  function onkeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, [contenteditable]")) return;
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "s") { event.preventDefault(); if (dirty && editable) save(); return; }
    if (!editable || !catalog) return;
    if (event.shiftKey && event.key.toLowerCase() === "a") { event.preventDefault(); menu = { x: pointer.x, y: pointer.y, from: null }; }
    else if (!mod && !event.shiftKey && event.key.toLowerCase() === "m") { event.preventDefault(); toggleMute(); }
    else if (mod && event.key.toLowerCase() === "d") { event.preventDefault(); duplicate(); }
  }
  const nodeProblems = $derived(current ? problems.filter((p) => p.node === current.id) : []);
  const fedFields = $derived.by(() => {
    if (!current) return {};
    const out: Record<string, string> = {};
    for (const w of doc.wires) if (w.to === current.id && w.in.startsWith("f:")) {
      const src = doc.nodes.find((n) => n.id === w.from);
      out[w.in.slice(2)] = src ? `${kindOf(src.type)?.label ?? src.type} ${summaryOf(kindOf(src.type)!, src.data, store.catalog?.picks ?? {})}`.trim() : w.from;
    }
    return out;
  });
  const labelOf = (nodeId: string) => { const n = doc.nodes.find((x) => x.id === nodeId); return n ? `${kindOf(n.type)?.label ?? n.type} · ${n.id}` : "сценарий"; };
</script>

<svelte:window {onkeydown} />

{#if !graph || !catalog}
  <p class="muted pad">Загрузка…</p>
{:else}
  <div class="editor">
    <header class="head">
      <a class="btn ghost" href="#/graphs" aria-label="К списку сценариев" title="К списку сценариев">←</a>
      <input class="title" bind:value={form.title} aria-label="Название сценария" disabled={!editable} />
      <label class="switch" title="Выключенный сценарий не запускается и не двигает прохождения">
        <input type="checkbox" bind:checked={form.active} disabled={!editable} />{form.active ? "Включён" : "Выключен"}</label>
      {#if stats}<span class="muted small">идёт прохождений: {stats.running}</span>{/if}
      <span class="spacer"></span>
      {#if dirty}<span class="muted small">не сохранено</span>{/if}
      {#if canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
      <button class="btn primary" disabled={!dirty || busy || !editable || !form.title.trim()} onclick={save}>Сохранить</button>
    </header>

    <div class="cols">
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div class="map" onmousemove={(e) => (pointer = { x: e.clientX, y: e.clientY })}>
        <SvelteFlow bind:nodes bind:edges {nodeTypes} colorMode="dark" minZoom={0.15} maxZoom={1.6} nodesDraggable={editable} nodesConnectable={editable}
                    deleteKey={editable ? ["Delete", "Backspace"] : null} isValidConnection={valid} {onconnect} {onconnectend} {ondelete} onnodedragstop={ondragstop}
                    onnodeclick={({ node }) => { selected = node.id; tab = "node"; }} onpaneclick={() => (selected = "")}
                    defaultEdgeOptions={{ type: "default" }} proOptions={{ hideAttribution: true }}>
          <FitOnce />
          <Background gap={24} />
          <Controls showLock={false} />
          <MiniMap pannable zoomable bgColor="#15171c" nodeColor="#2a2e37" maskColor="rgba(0, 0, 0, 0.5)" />
          <Panel position="top-left">
            {#if editable}<button class="btn" onclick={(e) => (menu = { x: e.clientX, y: e.clientY + 30, from: null })}>+ Нода</button>{/if}
            <span class="tip muted">Shift+A — добавить · M — выключить · Ctrl+D — копия · Delete — убрать · провод в пустоту — новая нода</span>
          </Panel>
          {#if menu}
            <AddMenu at={menu} {catalog} filter={menu.from ? (k) => insOf(k, {}).length > 0 && !k.start_only : null}
                     onpick={(kind, position) => addNode(kind, position, menu?.from ?? null)} onclose={() => (menu = null)} />
          {/if}
        </SvelteFlow>
      </div>

      <aside class="side">
        <div class="tabs" role="tablist">
          <button role="tab" class:on={tab === "node"} aria-selected={tab === "node"} onclick={() => (tab = "node")}>{current ? labelOf(current.id) : "Сценарий"}</button>
          <button role="tab" class:on={tab === "check"} aria-selected={tab === "check"} onclick={() => (tab = "check")}>Проверка{#if problems.length}<span class="count" class:bad={errors > 0}>{problems.length}</span>{/if}</button>
        </div>
        <div class="pane">
          {#if tab === "node" && current && kindOf(current.type)}
            {#key current.id}
              <NodePanel node={current} kind={kindOf(current.type)!} {catalog} waiting={fedInto.has(current.id)} fed={fedFields} problems={nodeProblems}
                         stat={stats?.nodes[current.id] ?? null} graphId={id} {editable} onchange={(patch) => patchNode(current.id, patch)}
                         onremove={() => removeNodes([current.id])} onstarted={load} />
            {/key}
          {:else if tab === "node"}
            <div class="settings">
              <label><span class="label">Имя</span><input class="field mono" bind:value={form.slug} disabled={!editable} /></label>
              <label><span class="label">Заметка автора</span><textarea class="field" rows="5" bind:value={form.note} disabled={!editable} placeholder="Что задумано, как игрок проходит, что проверить"></textarea></label>
              <p class="muted small">Нод {doc.nodes.length}, проводов {doc.wires.length}. Существительное без входящего провода — старт: его событие запускает прохождение игрока. С входящим — ожидание. Выберите ноду, чтобы править её поля.</p>
              {#if stats && Object.keys(stats.outcomes).length}
                <p class="muted small">Закончено: {Object.entries(stats.outcomes).map(([k, v]) => `${({ passed: "прошли", failed: "провалили", aborted: "прервано", done: "без исхода" } as Record<string, string>)[k] ?? k} ${v}`).join(", ")}</p>
              {/if}
            </div>
          {:else}
            <div class="checks">
              {#each problems as p, i (i)}
                <button class="problem" class:error={p.level === "error"} onclick={() => { if (p.node) { selected = p.node; tab = "node"; } }}>
                  {#if p.node}<span class="mono">{labelOf(p.node)}</span>{/if}<span>{p.text}</span>
                </button>
              {:else}
                <p class="muted small">Ошибок нет.</p>
              {/each}
            </div>
          {/if}
        </div>
      </aside>
    </div>
  </div>
{/if}

<style>
  .pad { padding: 20px 32px; }
  .editor { display: flex; flex-direction: column; height: 100vh; }
  .head { display: flex; align-items: center; gap: 10px; padding: 12px 20px; border-bottom: 1px solid var(--line-soft); }
  .title { min-width: 0; width: 340px; padding: 6px 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; font-size: 18px; font-weight: 600; }
  .title:hover, .title:focus { border-color: var(--line-soft); background: var(--bg); outline: none; }
  .switch { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
  .spacer { flex: 1; }
  .small { font-size: 12px; margin: 0; }
  .cols { flex: 1; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) 380px; }
  .map { position: relative; min-width: 0; min-height: 0; }
  .side { display: flex; flex-direction: column; min-height: 0; border-left: 1px solid var(--line-soft); }
  .tabs { display: flex; gap: 2px; padding: 8px 10px 0; border-bottom: 1px solid var(--line-soft); }
  .tabs button { padding: 7px 12px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); cursor: pointer; font: inherit; font-size: 13px; }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .count { margin-left: 6px; padding: 0 6px; border-radius: 999px; background: var(--warn); color: #111; font-size: 11px; font-weight: 700; }
  .count.bad { background: var(--danger); }
  .pane { flex: 1; min-height: 0; overflow-y: auto; padding: 14px 16px 40px; }
  .settings { display: flex; flex-direction: column; gap: 12px; }
  label { display: flex; flex-direction: column; gap: 4px; }
  .switch { flex-direction: row; }
  textarea { resize: vertical; font: inherit; }
  .tip { font-size: 12px; margin-left: 10px; }
  .checks { display: flex; flex-direction: column; gap: 6px; }
  .problem { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border: 0; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); text-align: left; font: inherit; font-size: 12.5px; cursor: pointer; }
  .problem.error { background: var(--danger-soft); color: var(--danger); }
  .problem .mono { font-size: 11.5px; opacity: 0.85; }
  .map :global(.svelte-flow) { --xy-background-color: var(--bg); --xy-edge-stroke: #c9ced6; --xy-edge-stroke-width: 1.6; --xy-controls-button-background-color: var(--panel-2);
                               --xy-controls-button-border-color: var(--line); --xy-controls-button-color: var(--text); }
  .map :global(.svelte-flow__edge.ref path) { stroke: #c792ea; stroke-dasharray: 5 4; }
  .map :global(.svelte-flow__edge.bad path) { stroke: var(--warn); }
  .map :global(.svelte-flow__edge.selected path) { stroke: var(--accent); stroke-width: 3; }
  .map :global(.svelte-flow__node) { border: 0; padding: 0; background: none; width: auto; }
</style>
