// Карта сценария (graph/flowmap.py): типы, раскладка в пиксели и подписи ожиданий.
export type WaitRow = { owner: string; since: string; until: string | null; kind: string; what: string; free: boolean };
export type WaitInfo = { count: number; items: { kind: string; what: string; until: string | null }[]; more: number; waits: WaitRow[] };
export type FlowNode = { id: string; title: string; role: "start" | "stage" | "fork"; col: number; row: number; branch: string; state: "done" | "ahead"; hits: number; last_at: string | null; here: boolean };
export type FlowEdge = { src: string; to: string; label: string; lane: boolean; back: boolean; wait: WaitInfo | null };
export type FlowTail = { node: string } & WaitInfo;
export type FlowBranch = { run: number; state: "free" | "taken" | "done"; owner: string; at: string; outcome: string };
export type FlowFork = { node: string; title: string; repeat: boolean; open: boolean; taken: number; total: number; done: number; branches: FlowBranch[] };

export const COLW = 196, ROWH = 92, PADX = 70, PADY = 44, BAND = 40, R = 9;

/** Центры узлов в пикселях: у дорожек ветвлений над первой строкой остаётся место под шапку. */
export function place(nodes: FlowNode[]) {
  const starts = [...new Set(nodes.filter((n) => n.branch).map((n) => n.branch))]
    .map((g) => Math.min(...nodes.filter((n) => n.branch === g).map((n) => n.row)))
    .sort((a, b) => a - b);
  const at = new Map<string, { x: number; y: number }>();
  for (const n of nodes) at.set(n.id, { x: PADX + n.col * COLW, y: PADY + n.row * ROWH + BAND * starts.filter((s) => s <= n.row).length });
  return at;
}

export function curve(a: { x: number; y: number }, b: { x: number; y: number }, back: boolean) {
  const x1 = a.x + R + 2, y1 = a.y, x2 = b.x - R - 5, y2 = b.y;
  if (back) {
    const low = Math.max(y1, y2) + 46;
    return `M${x1} ${y1} C${x1 + 50} ${low} ${x2 - 50} ${low} ${x2} ${y2}`;
  }
  const dx = Math.max(40, (x2 - x1) / 2);
  return `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`;
}

export function middle(a: { x: number; y: number }, b: { x: number; y: number }, back: boolean) {
  return { x: (a.x + b.x) / 2, y: back ? Math.max(a.y, b.y) + 34 : (a.y + b.y) / 2 };
}

export function summary(w: WaitInfo, clock: (iso: string) => string): string {
  const one = w.items[0];
  const text = one.kind === "time" ? (one.until ? `до ${clock(one.until)}` : "время") : one.kind === "condition" ? "условие" : one.what ? `«${one.what}»` : "событие";
  const rest = w.items.length - 1 + w.more;
  return text + (rest > 0 ? ` +${rest}` : "") + (w.count > 1 ? ` ×${w.count}` : "");
}
