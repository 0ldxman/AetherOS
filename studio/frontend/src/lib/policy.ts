// Окна входа: недельная сетка (7 дней × 48 получасов) и текст правил, который читает сервер (machines/access/windows.py).
export const DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export const DAY_NAMES = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"] as const;
export type Grid = boolean[][];
export type Span = [number, number];                 // слоты по полчаса: с включительно, по не включительно (48 это 24:00)
export type Group = { days: number[]; spans: Span[] };

export const fullGrid = (open = true): Grid => Array.from({ length: 7 }, () => Array<boolean>(48).fill(open));
export const cloneGrid = (grid: Grid): Grid => grid.map((day) => [...day]);

export function spansOf(day: boolean[]): Span[] {
  const out: Span[] = [];
  let start = -1;
  day.forEach((open, slot) => {
    if (open && start < 0) start = slot;
    if (!open && start >= 0) { out.push([start, slot]); start = -1; }
  });
  if (start >= 0) out.push([start, day.length]);
  return out;
}

/** Дни с одинаковыми интервалами складываются в одну группу: «пн–пт 9:00–18:00». */
export function groupsOf(grid: Grid): Group[] {
  const found = new Map<string, Group>();
  grid.forEach((day, d) => {
    const spans = spansOf(day);
    if (!spans.length) return;
    const key = JSON.stringify(spans);
    const group = found.get(key);
    if (group) group.days.push(d);
    else found.set(key, { days: [d], spans });
  });
  return [...found.values()];
}

const clock = (slot: number) => `${Math.floor(slot / 2)}:${slot % 2 ? "30" : "00"}`;

function runs(days: number[]): number[][] {
  const out: number[][] = [];
  for (const day of days) {
    const last = out.at(-1);
    if (last && last.at(-1) === day - 1) last.push(day);
    else out.push([day]);
  }
  return out;
}

/** Текст правил из сетки: пусто, если открыто всё; «except *: *», если закрыто всё. */
export function gridToText(grid: Grid): string {
  if (grid.every((day) => day.every(Boolean))) return "";
  const groups = groupsOf(grid);
  if (!groups.length) return "except *: *";
  return groups.map((group) => {
    const days = runs(group.days).flatMap((run) => (run.length >= 3 ? [`${DAY_KEYS[run[0]]}-${DAY_KEYS[run.at(-1)!]}`] : run.map((day) => DAY_KEYS[day]))).join(",");
    const whole = group.spans.length === 1 && group.spans[0][0] === 0 && group.spans[0][1] === 48;
    return `${days}: ${whole ? "*" : group.spans.map(([a, b]) => `${clock(a)}-${clock(b)}`).join(" ")}`;
  }).join("\n");
}

/** Те же окна словами для итога политики. */
export function windowsInWords(grid: Grid): string {
  if (grid.every((day) => day.every(Boolean))) return "в любое время";
  const groups = groupsOf(grid);
  if (!groups.length) return "вход закрыт всегда";
  return groups.map((group) => {
    const days = runs(group.days).map((run) => (run.length > 1 ? `${DAY_NAMES[run[0]]}–${DAY_NAMES[run.at(-1)!]}` : DAY_NAMES[run[0]])).join(", ");
    const whole = group.spans.length === 1 && group.spans[0][0] === 0 && group.spans[0][1] === 48;
    return `${days} ${whole ? "весь день" : group.spans.map(([a, b]) => `${clock(a)}–${clock(b)}`).join(", ")}`;
  }).join("; ");
}

export function openHours(grid: Grid): number {
  return grid.reduce((sum, day) => sum + day.filter(Boolean).length, 0) / 2;
}

/** 90 → «1 мин 30 с», 3600 → «1 ч». */
export function duration(seconds: number): string {
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return [h && `${h} ч`, m && `${m} мин`, (s || (!h && !m)) && `${s} с`].filter(Boolean).join(" ");
}

export const PRESETS: { label: string; text: string; hint: string }[] = [
  { label: "Всегда", text: "", hint: "Без ограничений по времени" },
  { label: "Будни 9–18", text: "mon-fri: 9:00-18:00", hint: "Пн–пт с 9:00 до 18:00" },
  { label: "Ночь", text: "*: 22:00-6:00", hint: "Каждый день с 22:00 до 6:00" },
  { label: "Выходные", text: "sat,sun: *", hint: "Суббота и воскресенье" },
  { label: "Нет входа", text: "except *: *", hint: "Вход закрыт всегда" },
];
