<script lang="ts">
  // Холст сценария (приложение graph): ноды и провода, Shift+A — добавить ноду, M — выключить, Ctrl+D — копия, Delete — убрать,
  // Ctrl+G — собрать выбранное в группу, Tab — войти в группу или выйти, Ctrl+H — спрятать неподключённые сокеты, Ctrl+S — сохранить.
  // Справа свойства выбранной ноды и проверка. Счётчики на нодах обновляются сами. Холст показывает один уровень: граф или группу.
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
  import { BOXES, REF, defaults, freeId, ifaceOfLevel, insOf, summaryOf, type Catalog, type Doc, type GNode, type GWire, type Group, type Iface, type Kind, type Level } from "./kinds";

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
  let path = $state<{ node: string; group: string }[]>([]);            // где мы: цепочка групп от графа вглубь
  let graphs = $state<Schemas["GrRow"][]>([]);

  const gid = $derived(path.length ? path[path.length - 1].group : "");
  const level = $derived<Level>(gid ? doc.groups?.[gid] ?? { nodes: [], wires: [] } : doc);
  const statPrefix = $derived(path.map((p) => p.node).join("/") + (path.length ? "/" : ""));
  const keyOf = (nodeId: string) => (gid ? `${gid}::${nodeId}` : nodeId);
  function setLevel(next: Level) {
    if (gid) doc = { ...doc, groups: { ...doc.groups, [gid]: { ...(doc.groups?.[gid] as Group), nodes: next.nodes, wires: next.wires } } };
    else doc = { ...doc, nodes: next.nodes, wires: next.wires };
  }
  function ifaceOf(n: GNode): Iface | null {
    if (n.type === "group") return ifaceOfLevel(doc.groups?.[String(n.data.group ?? "")]);
    if (n.type === "scenario") return graphs.find((g) => g.slug === n.data.graph)?.iface ?? null;
    return null;
  }

  const editable = canEdit("world");
  const store = engine();
  const current_json = $derived(JSON.stringify({ form, doc }));
  const dirty = $derived(saved !== "" && current_json !== saved);
  const errors = $derived(problems.filter((p) => p.level === "error").length);
  guardUnsaved(() => dirty);

  const kindOf = (type: string): Kind | undefined => catalog?.kinds.find((k) => k.name === type);
  const fedInto = $derived(new Set(level.wires.filter((w) => !w.in.startsWith("f:")).map((w) => w.to)));
  const current = $derived(level.nodes.find((n) => n.id === selected) ?? null);

  function fill(data: Detail) {
    graph = data;
    form = { slug: data.slug, title: data.title, note: data.note, active: data.active };
    const raw = data.doc as Partial<Doc>;
    const ids = (wires: GWire[] | undefined) => (wires ?? []).map((w) => ({ ...w, id: wireId(w) }));
    const groups = raw.groups ? Object.fromEntries(Object.entries(raw.groups as Record<string, Group>).map(([k, g]) => [k, { ...g, wires: ids(g.wires) }])) : null;
    doc = { nodes: (raw.nodes ?? []) as GNode[], wires: ids(raw.wires as GWire[]), ...(groups ? { groups } : {}) };
    if (gid && !doc.groups?.[gid]) path = [];
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
    graphs = (await api.GET("/studio/api/world/graphs")).data ?? [];
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
      const { data } = await api.POST("/studio/api/world/graphs/check", { body: { doc: JSON.parse(body), slug: form.slug } });
      if (data && body === JSON.stringify(doc)) problems = data;
    }, 400);
  });

  async function save() {
    if (!graph || busy) return;
    busy = true;
    const { data, error } = await api.PUT("/studio/api/world/graphs/{graph_id}", { params: { path: { graph_id: id } }, body: { ...form, doc: pruned() } });
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

  // группы, на которые больше нет нод, при сохранении убираются
  function pruned(): Doc {
    const groups = doc.groups ?? {};
    const used = new Set<string>();
    const walk = (lvl: Level) => {
      for (const n of lvl.nodes) {
        const g = String(n.data.group ?? "");
        if (n.type === "group" && groups[g] && !used.has(g)) { used.add(g); walk(groups[g]); }
      }
    };
    walk(doc);
    const kept = Object.fromEntries(Object.entries(groups).filter(([key]) => used.has(key)));
    return { nodes: doc.nodes, wires: doc.wires, ...(Object.keys(kept).length ? { groups: kept } : {}) };
  }
  function wireId(w: Omit<GWire, "id">) { return `${w.from}.${w.out}-${w.to}.${w.in}`; }
  function freeGroup(): string {
    let n = Object.keys(doc.groups ?? {}).length + 1;
    while (doc.groups?.[`g${n}`]) n += 1;
    return `g${n}`;
  }

  // ---- правка документа ----
  function patchNode(nodeId: string, patch: Partial<GNode>) {
    setLevel({ ...level, nodes: level.nodes.map((n) => (n.id === nodeId ? { ...n, ...patch } : n)) });
  }
  function setGroupTitle(group: string, title: string) {
    const found = doc.groups?.[group];
    if (found) doc = { ...doc, groups: { ...doc.groups, [group]: { ...found, title } } };
  }
  function addNode(kind: Kind, position: { x: number; y: number }, from: { node: string; out: string } | null = null) {
    const node: GNode = { id: freeId(level), type: kind.name, x: Math.round(position.x), y: Math.round(position.y), data: defaults(kind) };
    if (kind.name === "frame") { node.w = 420; node.h = 260; }
    if (kind.name === "group_in" || kind.name === "group_out") node.data = { sockets: [{ name: "s1", label: kind.name === "group_in" ? "Вход" : "Выход" }] };
    if (kind.name === "group") {
      const group = freeGroup();
      node.data = { group };
      doc = { ...doc, groups: { ...doc.groups, [group]: { title: "Группа", wires: [], nodes: [
        { id: "in", type: "group_in", x: 0, y: 0, data: { sockets: [{ name: "s1", label: "Вход" }] } },
        { id: "out", type: "group_out", x: 520, y: 0, data: { sockets: [{ name: "s1", label: "Выход" }] } }] } } };
    }
    const wires = [...level.wires];
    if (from) {
      const target = insOf(kind, node.data, ifaceOf(node))[0];
      if (target) wires.push({ id: wireId({ from: from.node, out: from.out, to: node.id, in: target.name }), from: from.node, out: from.out, to: node.id, in: target.name });
    }
    setLevel({ nodes: [...level.nodes, node], wires });
    selected = node.id;
    tab = "node";
    menu = null;
  }
  function removeNodes(ids: string[]) {
    const gone = new Set(ids);
    setLevel({ nodes: level.nodes.filter((n) => !gone.has(n.id)), wires: level.wires.filter((w) => !gone.has(w.from) && !gone.has(w.to)) });
    if (gone.has(selected)) selected = "";
  }
  // Ctrl+G: выбранные ноды уезжают в новую группу; провода через границу становятся её входами и выходами
  function groupSelected() {
    const ids = new Set(chosen().filter((nodeId) => { const n = level.nodes.find((x) => x.id === nodeId); return n && n.type !== "group_in" && n.type !== "group_out"; }));
    if (!ids.size) return;
    const picked = level.nodes.filter((n) => ids.has(n.id));
    const inside = level.wires.filter((w) => ids.has(w.from) && ids.has(w.to));
    const incoming = level.wires.filter((w) => !ids.has(w.from) && ids.has(w.to) && !w.in.startsWith("f:"));
    const outgoing = level.wires.filter((w) => ids.has(w.from) && !ids.has(w.to) && w.out !== REF);
    const inKeys = [...new Set(incoming.map((w) => `${w.to}|${w.in}`))];
    const outKeys = [...new Set(outgoing.map((w) => `${w.from}|${w.out}`))];
    const xs = picked.map((n) => n.x), ys = picked.map((n) => n.y);
    const midY = Math.round(ys.reduce((a, b) => a + b, 0) / ys.length);
    const taken = new Set(picked.map((n) => n.id));
    const pickId = (base: string) => { let name = base, n = 1; while (taken.has(name)) name = `${base}${++n}`; taken.add(name); return name; };
    const inId = pickId("in"), outId = pickId("out");
    const inSocks = inKeys.map((_, i) => ({ name: `s${i + 1}`, label: `Вход ${i + 1}` }));
    const outSocks = outKeys.map((_, i) => ({ name: `s${i + 1}`, label: `Выход ${i + 1}` }));
    const group = freeGroup();
    const box: GNode = { id: freeId(level), type: "group", x: Math.round(xs.reduce((a, b) => a + b, 0) / xs.length), y: midY, data: { group } };
    const innerWires: GWire[] = [
      ...inside,
      ...inKeys.map((key, i) => { const [to, inp] = key.split("|"); const w = { from: inId, out: inSocks[i].name, to, in: inp }; return { ...w, id: wireId(w) }; }),
      ...outKeys.map((key, i) => { const [from, out] = key.split("|"); const w = { from, out, to: outId, in: outSocks[i].name }; return { ...w, id: wireId(w) }; }),
    ];
    const outerWires: GWire[] = [
      ...level.wires.filter((w) => !ids.has(w.from) && !ids.has(w.to)),
      ...incoming.map((w) => { const next = { from: w.from, out: w.out, to: box.id, in: inSocks[inKeys.indexOf(`${w.to}|${w.in}`)].name }; return { ...next, id: wireId(next) }; }),
      ...outgoing.map((w) => { const next = { from: box.id, out: outSocks[outKeys.indexOf(`${w.from}|${w.out}`)].name, to: w.to, in: w.in }; return { ...next, id: wireId(next) }; }),
    ];
    const groupDef: Group = { title: "Группа", wires: [...new Map(innerWires.map((w) => [w.id, w])).values()], nodes: [
      ...picked,
      { id: inId, type: "group_in", x: Math.min(...xs) - 280, y: midY, data: { sockets: inSocks } },
      { id: outId, type: "group_out", x: Math.max(...xs) + 280, y: midY, data: { sockets: outSocks } }] };
    doc = { ...doc, groups: { ...doc.groups, [group]: groupDef } };
    setLevel({ nodes: [...level.nodes.filter((n) => !ids.has(n.id)), box], wires: [...new Map(outerWires.map((w) => [w.id, w])).values()] });
    selected = box.id;
    toast("Собрано в группу. Tab — войти внутрь.");
  }
  function enter(nodeId: string) {
    const n = level.nodes.find((x) => x.id === nodeId);
    if (!n || n.type !== "group" || !doc.groups?.[String(n.data.group)]) return;
    path = [...path, { node: n.id, group: String(n.data.group) }];
    selected = "";
  }
  function leave(depth = path.length - 1) {
    const back = path[depth];
    path = path.slice(0, Math.max(0, depth));
    selected = back?.node ?? "";
  }
  function chosen(): string[] {
    const marked = nodes.filter((n) => n.selected).map((n) => n.id);
    return marked.length ? marked : selected ? [selected] : [];
  }
  function duplicate() {
    const ids = chosen();
    let next: Level = level;
    for (const nodeId of ids) {
      const source = next.nodes.find((n) => n.id === nodeId);
      if (!source) continue;
      const copy = { ...structuredClone($state.snapshot(source)) as GNode, id: freeId(next), x: source.x + 40, y: source.y + 40 };
      next = { ...next, nodes: [...next.nodes, copy] };
      selected = copy.id;
    }
    setLevel(next);
  }
  function toggle(flag: "mute" | "collapsed") {
    const ids = new Set(chosen());
    setLevel({ ...level, nodes: level.nodes.map((n) => (ids.has(n.id) ? { ...n, [flag]: n[flag] ? undefined : true } : n)) });
  }

  // ---- холст ----
  const nodeTypes = { gnode: GraphNode, frame: FrameNode };
  let nodes = $state.raw<Node[]>([]);
  let edges = $state.raw<Edge[]>([]);

  $effect(() => {
    const list = level.nodes;
    const wires = level.wires;
    const prefix = statPrefix;
    const groupKey = gid;
    const allGraphs = graphs;
    const found = problems;
    const chosenId = selected;
    const live = stats;
    const picks = store.catalog?.picks ?? {};
    if (!catalog) return;
    untrack(() => {
      allGraphs;
      const key = (nodeId: string) => (groupKey ? `${groupKey}::${nodeId}` : nodeId);
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
        const inner = n.type === "group" ? String(n.data.group ?? "") : "";
        const boxStat = BOXES.includes(n.type) && live ? Object.entries(live.nodes).filter(([k]) => k.startsWith(`${prefix}${n.id}/`))
          .reduce((acc, [, v]) => ({ hits: Math.max(acc.hits, v.hits), players: Math.max(acc.players, v.players), waiting: acc.waiting + v.waiting,
                                    oldest_days: Math.max(acc.oldest_days, v.oldest_days) }), { hits: 0, players: 0, waiting: 0, oldest_days: 0 }) : null;
        return [{
          id: n.id, type: "gnode", position: { x: n.x, y: n.y }, selected: n.id === chosenId || keep.has(n.id),
          data: { node: n, kind, waiting: fedInto.has(n.id), refFields, iface: ifaceOf(n),
                  summary: n.type === "group" ? doc.groups?.[inner]?.title ?? "" : summaryOf(kind, n.data, picks),
                  errors: found.filter((p) => p.node === key(n.id) && p.level === "error").length, warnings: found.filter((p) => p.node === key(n.id) && p.level === "warning").length,
                  box: inner ? found.filter((p) => p.node.startsWith(`${inner}::`) && p.level === "error").length : 0,
                  stat: boxStat ?? live?.nodes[prefix + n.id] ?? null, used: wires.filter((w) => w.from === n.id).map((w) => w.out),
                  usedIn: wires.filter((w) => w.to === n.id).map((w) => w.in) },
        } satisfies Node];
      });
      edges = wires.map((w) => ({ id: w.id || `${w.from}.${w.out}-${w.to}.${w.in}`, source: w.from, sourceHandle: w.out, target: w.to, targetHandle: w.in,
                                  class: w.out === REF ? "ref" : w.out === "fail" || w.out === "timeout" ? "bad" : "" }) satisfies Edge);
    });
  });

  function refKindOf(nodeId: string) {
    const n = level.nodes.find((x) => x.id === nodeId);
    const kind = n && kindOf(n.type);
    return kind?.ref ?? "";
  }
  function valid(c: Connection | Edge): boolean {
    const out = c.sourceHandle ?? "", inp = c.targetHandle ?? "";
    if (out === REF) {
      if (!inp.startsWith("f:")) return false;
      const target = level.nodes.find((x) => x.id === c.target);
      const field = target && kindOf(target.type)?.fields.find((f) => f.name === inp.slice(2));
      return !!field && catalog?.ref_kinds[field.kind] === refKindOf(c.source);
    }
    return !inp.startsWith("f:");
  }
  function onconnect(c: Connection) {
    if (!c.sourceHandle || !c.targetHandle || !valid(c)) return;
    const wire = { id: `${c.source}.${c.sourceHandle}-${c.target}.${c.targetHandle}`, from: c.source, out: c.sourceHandle, to: c.target, in: c.targetHandle };
    let wires = level.wires.filter((w) => w.id !== wire.id);
    if (wire.in.startsWith("f:")) wires = wires.filter((w) => !(w.to === wire.to && w.in === wire.in));      // в поле — один провод
    setLevel({ ...level, wires: [...wires, wire] });
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
    setLevel({ ...level, wires: level.wires.filter((w) => !ids.has(w.id || wireId(w))) });
    if (goneNodes.length) removeNodes(goneNodes.map((n) => n.id));
  }
  function ondragstop({ nodes: moved }: { nodes: Node[] }) {
    const at = new Map(moved.map((n) => [n.id, n.position]));
    setLevel({ ...level, nodes: level.nodes.map((n) => { const p = at.get(n.id); return p && (p.x !== n.x || p.y !== n.y) ? { ...n, x: Math.round(p.x), y: Math.round(p.y) } : n; }) });
  }

  function onkeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    if (target?.closest("input, textarea, select, [contenteditable]")) return;
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === "s") { event.preventDefault(); if (dirty && editable) save(); return; }
    if (event.key === "Tab" && !mod) {
      event.preventDefault();
      const n = level.nodes.find((x) => x.id === selected);
      if (n?.type === "group") enter(n.id);
      else if (path.length) leave();
      return;
    }
    if (!editable || !catalog) return;
    if (event.shiftKey && event.key.toLowerCase() === "a") { event.preventDefault(); menu = { x: pointer.x, y: pointer.y, from: null }; }
    else if (!mod && !event.shiftKey && event.key.toLowerCase() === "m") { event.preventDefault(); toggle("mute"); }
    else if (mod && event.key.toLowerCase() === "h") { event.preventDefault(); toggle("collapsed"); }
    else if (mod && event.key.toLowerCase() === "g") { event.preventDefault(); groupSelected(); }
    else if (mod && event.key.toLowerCase() === "d") { event.preventDefault(); duplicate(); }
  }
  const nodeProblems = $derived(current ? problems.filter((p) => p.node === keyOf(current.id)) : []);
  const fedFields = $derived.by(() => {
    if (!current) return {};
    const out: Record<string, string> = {};
    for (const w of level.wires) if (w.to === current.id && w.in.startsWith("f:")) {
      const src = level.nodes.find((n) => n.id === w.from);
      out[w.in.slice(2)] = src ? `${kindOf(src.type)?.label ?? src.type} ${summaryOf(kindOf(src.type)!, src.data, store.catalog?.picks ?? {})}`.trim() : w.from;
    }
    return out;
  });
  const labelOf = (nodeId: string) => { const n = level.nodes.find((x) => x.id === nodeId); return n ? `${kindOf(n.type)?.label ?? n.type} · ${n.id}` : "сценарий"; };
  // проблема во вкладке «Проверка»: где она (граф или группа) и переход к ноде
  function problemPlace(key: string) {
    const [group, nodeId] = key.includes("::") ? key.split("::") : ["", key];
    const title = group ? `группа «${doc.groups?.[group]?.title ?? group}» · ` : "";
    const lvl: Level | undefined = group ? doc.groups?.[group] : doc;
    const n = lvl?.nodes.find((x) => x.id === nodeId);
    return { group, nodeId, text: `${title}${n ? `${kindOf(n.type)?.label ?? n.type} · ${n.id}` : nodeId}` };
  }
  // найти путь до группы (через ноды-группы на уровнях выше)
  function pathTo(group: string): { node: string; group: string }[] | null {
    const walk = (lvl: Level, trail: { node: string; group: string }[], seen: Set<string>): { node: string; group: string }[] | null => {
      for (const n of lvl.nodes) {
        const g = String(n.data.group ?? "");
        if (n.type !== "group" || seen.has(g) || !doc.groups?.[g]) continue;
        const next = [...trail, { node: n.id, group: g }];
        if (g === group) return next;
        const deeper = walk(doc.groups[g], next, new Set([...seen, g]));
        if (deeper) return deeper;
      }
      return null;
    };
    return group ? walk(doc, [], new Set()) : [];
  }
  function showProblem(key: string) {
    if (!key) return;
    const place = problemPlace(key);
    const found = pathTo(place.group);
    if (found === null) return;
    path = found;
    selected = place.nodeId;
    tab = "node";
  }
</script>

<svelte:window {onkeydown} />

{#if !graph || !catalog}
  <p class="muted pad">Загрузка…</p>
{:else}
  <div class="editor">
    <header class="head">
      <a class="btn ghost" href="#/graphs" aria-label="К списку сценариев" title="К списку сценариев">←</a>
      <input class="title" bind:value={form.title} aria-label="Название сценария" disabled={!editable} />
      {#if path.length}
        <nav class="crumbs" aria-label="Уровень">
          <button class="crumb" onclick={() => leave(0)}>граф</button>
          {#each path as step, i (i)}<span class="muted">›</span>
            {#if i < path.length - 1}<button class="crumb" onclick={() => leave(i + 1)}>{doc.groups?.[step.group]?.title || step.group}</button>
            {:else}<b>{doc.groups?.[step.group]?.title || step.group}</b>{/if}
          {/each}
        </nav>
      {/if}
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
        {#key gid}
        <SvelteFlow bind:nodes bind:edges {nodeTypes} colorMode="dark" minZoom={0.15} maxZoom={1.6} nodesDraggable={editable} nodesConnectable={editable}
                    deleteKey={editable ? ["Delete", "Backspace"] : null} isValidConnection={valid} {onconnect} {onconnectend} {ondelete} onnodedragstop={ondragstop}
                    onnodeclick={({ node, event }) => { selected = node.id; tab = "node"; if (event.detail === 2) enter(node.id); }} onpaneclick={() => (selected = "")}
                    defaultEdgeOptions={{ type: "default" }} proOptions={{ hideAttribution: true }}>
          <FitOnce />
          <Background gap={24} />
          <Controls showLock={false} />
          <MiniMap pannable zoomable bgColor="#15171c" nodeColor="#2a2e37" maskColor="rgba(0, 0, 0, 0.5)" />
          <Panel position="top-left">
            {#if editable}<button class="btn" onclick={(e) => (menu = { x: e.clientX, y: e.clientY + 30, from: null })}>+ Нода</button>{/if}
            <span class="tip muted">Shift+A — добавить · Ctrl+G — в группу · Tab — войти/выйти · M — выключить · Ctrl+H — свернуть · Ctrl+D — копия · Delete — убрать</span>
          </Panel>
          {#if menu}
            <AddMenu at={menu} {catalog} filter={menu.from ? (k) => insOf(k, {}).length > 0 && !k.start_only : null}
                     onpick={(kind, position) => addNode(kind, position, menu?.from ?? null)} onclose={() => (menu = null)} />
          {/if}
        </SvelteFlow>
        {/key}
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
                         stat={stats?.nodes[statPrefix + current.id] ?? null} statKey={statPrefix + current.id} graphId={id} {editable} onchange={(patch) => patchNode(current.id, patch)}
                         onremove={() => removeNodes([current.id])} onstarted={load}
                         groupTitle={current.type === "group" ? doc.groups?.[String(current.data.group ?? "")]?.title ?? "" : null}
                         ongrouptitle={(title) => setGroupTitle(String(current.data.group ?? ""), title)} onenter={() => enter(current.id)} />
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
                <button class="problem" class:error={p.level === "error"} onclick={() => showProblem(p.node)}>
                  {#if p.node}<span class="mono">{problemPlace(p.node).text}</span>{/if}<span>{p.text}</span>
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
  .crumbs { display: flex; align-items: center; gap: 6px; font-size: 13px; }
  .crumb { border: 0; background: none; color: var(--accent); cursor: pointer; font: inherit; padding: 0; }
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
