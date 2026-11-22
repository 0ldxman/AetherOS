// Карта сценария (graph/flowmap.py): типы, раскладка в пиксели, маршруты стрелок и расстановка подписей без наложений.
export type WaitRow = { id: number; run: number; owner: string; since: string; since_game: string | null; until: string | null; until_game: string | null; kind: string; what: string; free: boolean };
export type WaitItem = { kind: string; what: string; until: string | null; until_game: string | null };
export type WaitInfo = { count: number; items: WaitItem[]; more: number; waits: WaitRow[] };
export type FlowNode = { id: string; title: string; hint: string; role: "start" | "stage" | "fork" | "lane"; col: number; row: number; branch: string; state: "done" | "ahead"; hits: number; last_at: string | null; here: boolean };
export type FlowEdge = { src: string; to: string; label: string; lane: boolean; back: boolean; wait: WaitInfo | null };
export type FlowTail = { node: string } & WaitInfo;
export type FlowBranch = { run: number; state: "free" | "taken" | "done"; owner: string; at: string; outcome: string };
export type FlowFork = { node: string; title: string; repeat: boolean; open: boolean; taken: number; total: number; done: number; branches: FlowBranch[] };
export type Pt = { x: number; y: number };

export const COLW = 196, ROWH = 92, PADX = 70, PADY = 44, BAND = 56, R = 9;

/** Центры узлов в пикселях: над первой строкой каждой дорожки остаётся место под шапку. */
export function place(nodes: FlowNode[]) {
  const starts = [...new Set(nodes.filter((n) => n.branch).map((n) => n.branch))]
    .map((g) => Math.min(...nodes.filter((n) => n.branch === g).map((n) => n.row)))
    .sort((a, b) => a - b);
  const at = new Map<string, Pt>();
  for (const n of nodes) at.set(n.id, { x: PADX + n.col * COLW, y: PADY + n.row * ROWH + BAND * starts.filter((s) => s <= n.row).length });
  return at;
}

export type Route = { d: string; at: (t: number) => Pt };

/** Маршрут стрелки. Дорожка ветвления: вниз от ромба и вправо в первую точку; цикл: дугой под узлами; остальные: плавной кривой. */
export function route(a: Pt, b: Pt, e: { lane: boolean; back: boolean }): Route {
  if (e.lane) {                                                   // вправо из ромба, вниз по просвету между колонками и вправо в первую точку ветки
    const x1 = a.x + R + 2, y1 = a.y, gx = a.x + COLW / 2, x2 = b.x - R - 5, y2 = b.y;
    return { d: `M${x1} ${y1} H${gx - 14} Q${gx} ${y1} ${gx} ${y1 + 14} V${y2 - 14} Q${gx} ${y2} ${gx + 14} ${y2} H${x2}`, at: (t) => ({ x: gx, y: y1 + 22 + t * Math.max(10, y2 - y1 - 44) }) };
  }
  const x1 = a.x + R + 2, y1 = a.y, x2 = b.x - R - 5, y2 = b.y;
  if (e.back) {
    const low = Math.max(y1, y2) + 104;
    const c = [x1 + 50, low, x2 - 50, low] as const;
    return { d: `M${x1} ${y1} C${c[0]} ${c[1]} ${c[2]} ${c[3]} ${x2} ${y2}`, at: (t) => cubic(x1, y1, c[0], c[1], c[2], c[3], x2, y2, t) };
  }
  const dx = Math.max(40, (x2 - x1) / 2);
  return { d: `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`, at: (t) => cubic(x1, y1, x1 + dx, y1, x2 - dx, y2, x2, y2, t) };
}

function cubic(x1: number, y1: number, cx1: number, cy1: number, cx2: number, cy2: number, x2: number, y2: number, t: number): Pt {
  const u = 1 - t;
  return { x: u * u * u * x1 + 3 * u * u * t * cx1 + 3 * u * t * t * cx2 + t * t * t * x2, y: u * u * u * y1 + 3 * u * u * t * cy1 + 3 * u * t * t * cy2 + t * t * t * y2 };
}

const hhmm = (stamp: string) => stamp.slice(11, 16);
const word = (n: number, f: [string, string, string]) => (n % 10 === 1 && n % 100 !== 11 ? f[0] : [2, 3, 4].includes(n % 10) && ![12, 13, 14].includes(n % 100) ? f[1] : f[2]);

/** Чего ждут, одним словом: игровое время важнее реального («до 14:20»), у событий — их значение («open»). */
export function waitText(item: WaitItem, clock: (iso: string) => string): string {
  if (item.kind === "time") return item.until_game ? `до ${hhmm(item.until_game)}` : item.until ? `до ${clock(item.until)}` : "время";
  if (item.kind === "condition") return "условие";
  return item.what ? `«${item.what}»` : "событие";
}

export function summary(w: WaitInfo, clock: (iso: string) => string): string {
  const names = w.items.slice(0, 2).map((i) => waitText(i, clock)).join(" или ");
  const rest = w.items.length - 2 + w.more;
  return names + (rest > 0 ? ` +${rest}` : "") + (w.count > 1 ? ` · ${w.count} ${word(w.count, ["поток", "потока", "потоков"])}` : "");
}

export type Mark = { key: string; kind: "chip" | "label" | "tail"; x: number; y: number; text: string; edge?: FlowEdge; w: number };
type Rect = { x: number; y: number; w: number; h: number };
const hit = (a: Rect, b: Rect) => Math.abs(a.x - b.x) * 2 < a.w + b.w && Math.abs(a.y - b.y) * 2 < a.h + b.h;
const width = (text: string, extra: number) => Math.min(200, text.length * 6.4 + extra);

/** Подписи на стрелках: каждая ищет место вдоль своей стрелки, где не задевает точки, названия и уже поставленные подписи. */
export function layoutMarks(nodes: FlowNode[], edges: FlowEdge[], tails: FlowTail[], spot: Map<string, Pt>, clock: (iso: string) => string): Mark[] {
  const blocked: Rect[] = nodes.flatMap((n) => {
    const p = spot.get(n.id)!;
    return [{ x: p.x, y: p.y, w: 30, h: 30 }, { x: p.x, y: p.y + 31, w: 152, h: 34 }];
  });
  const marks: Mark[] = [];
  const put = (mark: Omit<Mark, "x" | "y">, at: (t: number) => Pt, tries: number[]) => {
    const h = mark.kind === "label" ? 16 : 24;
    let chosen: Pt | null = null;
    for (const t of tries) {
      const p = at(t);
      if (!blocked.some((r) => hit({ x: p.x, y: p.y, w: mark.w, h }, r))) { chosen = p; break; }
    }
    const p = chosen ?? at(tries[0]);
    marks.push({ ...mark, x: p.x, y: p.y });
    blocked.push({ x: p.x, y: p.y, w: mark.w, h });
  };
  for (const t of tails) {
    const p = spot.get(t.node);
    if (!p) continue;
    const text = summary(t, clock);
    const w = width(text, 24);
    const x = p.x + 62 + w / 2;                                   // плашка стоит у конца короткой стрелки, а не поверх неё
    marks.push({ key: `tail:${t.node}`, kind: "tail", x, y: p.y, text, w });
    blocked.push({ x, y: p.y, w, h: 24 });
  }
  const routes = edges.map((e) => ({ e, r: spot.has(e.src) && spot.has(e.to) ? route(spot.get(e.src)!, spot.get(e.to)!, e) : null }));
  for (const { e, r } of routes) {
    if (r && e.label && !e.back) put({ key: `label:${e.src}>${e.to}`, kind: "label", text: e.label, edge: e, w: width(e.label, 8) }, r.at, [0.78, 0.68, 0.58]);
  }
  for (const { e, r } of routes) {
    if (r && e.wait) {
      const text = summary(e.wait, clock);
      put({ key: `chip:${e.src}>${e.to}`, kind: "chip", text, edge: e, w: width(text, 24) }, r.at, [0.5, 0.36, 0.64, 0.24, 0.76]);
    }
  }
  return marks;
}
