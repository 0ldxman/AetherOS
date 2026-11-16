// Виды нод сценария (graph/nodes.py) и сокеты ноды с её данными: та же логика, что у сервера (nodes.sockets).
import type { Schemas } from "../../lib/api";

export type Kind = Schemas["GrKind"];
export type Catalog = Schemas["GrCatalog"];
export type Field = Schemas["GrField"];
export type GNode = { id: string; type: string; x: number; y: number; data: Record<string, unknown>; w?: number; h?: number; mute?: boolean; collapsed?: boolean };
export type GWire = { id: string; from: string; out: string; to: string; in: string };
export type Level = { nodes: GNode[]; wires: GWire[] };
export type Group = Level & { title: string };
export type Doc = Level & { groups?: Record<string, Group> };
export type Sock = { name: string; label: string; type?: string };
export type Iface = { inputs: Sock[]; outputs: Sock[] };
export const BOXES = ["group", "scenario"];

export const REF = "ref";
export const TIMEOUT = "timeout";
export const OFFER_USED = "on:offer.used";          // выходы — по сущности «Возможность» на проводе (graph/offers.used_outs)
export const COLORS: Record<string, string> = { entity: "#2f7d6d", noun: "#3f8f86", flow: "#a7793a", data: "#8a5d7a", action: "#4d6fc4", struct: "#7a5aa8", service: "#5b6170" };

// Типы сокетов: цвет у точки и провода. event — «случилось» (поток), остальные — вещи, которые едут по ◆-проводу.
export const TYPES: Record<string, { label: string; color: string; thing?: boolean }> = {
  event: { label: "Событие", color: "#e6e8ec" },
  bool: { label: "Да/нет", color: "#e58fc4" },
  text: { label: "Текст", color: "#6ec1e4" },
  number: { label: "Число", color: "#a1a7b0" },
  item: { label: "Объект", color: "#ed9e40", thing: true },
  placement: { label: "Размещение", color: "#a3d94f", thing: true },
  layer: { label: "Слой", color: "#d98a5a", thing: true },
  machine: { label: "Машина", color: "#3fc7b5", thing: true },
  account: { label: "Учётка", color: "#8fd8c4", thing: true },
  server: { label: "Сервер", color: "#4fa3d9", thing: true },
  character: { label: "Персонаж", color: "#c792ea", thing: true },
  section: { label: "Раздел", color: "#5fd07a", thing: true },
  player: { label: "Игрок", color: "#f0e6d2", thing: true },
  flag: { label: "Метка игрока", color: "#f2c66d", thing: true },
  world_flag: { label: "Метка мира", color: "#ff8f6b", thing: true },
  counter: { label: "Счётчик", color: "#8fb3ff", thing: true },
  moment: { label: "Момент", color: "#d4d27a", thing: true },
  offer: { label: "Возможность", color: "#e3b8f5", thing: true },
};
// списки: «list:<тип элемента>», «list:any» — вход, которому подходит любой список; @T и @list — по «Типу элементов» ноды.
// «many:<тип>» — одно значение или список; «a|b» — подходит любой из типов (сокет в цветах всех)
export const isList = (type: string | undefined) => !!type && type.startsWith("list:");
export const isMany = (type: string | undefined) => !!type && type.startsWith("many:");
export const elementOf = (type: string) => (isList(type) || isMany(type) ? type.slice(5) : type);
export const basesOf = (type: string) => elementOf(type).split("|");
export const takesEvent = (type: string | undefined) => !type || basesOf(type).includes("event");
export const typeColor = (type: string) => (type === "list:any" ? "#c9ccd2" : TYPES[basesOf(type)[0]]?.color ?? TYPES.event.color);
export const typeColors = (type: string) => (type === "list:any" ? ["#c9ccd2"] : basesOf(type).map((b) => TYPES[b]?.color ?? TYPES.event.color));
export function typeLabel(type: string | undefined): string {
  if (!type) return "";
  if (type === "list:any") return "Список";
  const one = basesOf(type).map((b) => TYPES[b]?.label ?? b).join(" или ");
  const elements = one.toLowerCase();
  return isList(type) ? `Список (${elements})` : isMany(type) ? `${one} или список (${elements})` : one;
}
export function resolveType(kind: Kind, data: Record<string, unknown>, type: string | undefined): string {
  if (type !== "@T" && type !== "@list" && type !== "many:@T") return type ?? "";
  const element = String((kind.typed && data[kind.typed]) || "text");
  return type === "@T" ? element : type === "@list" ? `list:${element}` : `many:${element}`;
}

// вид поля без кратности: «many:object» -> «object»; поле нескольких типов («player|machine») — только провод, без редактора
export const plainKind = (kind: string) => (kind.startsWith("many:") ? kind.slice(5) : kind);
export const wireOnly = (kind: string) => plainKind(kind).includes("|");

// тип провода задаёт поля ноды (kind.infers): машина в «Владелец» — владелец «машина»
export function inferred(kind: Kind, data: Record<string, unknown>, fed: Record<string, string>): Record<string, unknown> {
  const rules = Object.entries(kind.infers ?? {});
  if (!rules.length) return data;
  const out = { ...data };
  for (const [name, rule] of rules) {
    const type = fed[`f:${name}`];
    const found = type ? rule.by[basesOf(type)[0]] : undefined;
    if (found) out[rule.mode] = found.value;
  }
  return out;
}

// Можно ли вести провод из выхода типа src во вход типа dst (та же логика, что graph/nodes.compatible)
export function compatible(src: string, dst: string): boolean {
  if (src === dst) return true;
  const bases = basesOf(dst);
  if (bases.includes("event") && bases.length > 1) return src === "event" || compatible(src, bases.filter((b) => b !== "event").join("|"));
  if (src === "event" || dst === "event") return false;
  if (dst === "list:any") return isList(src) || isMany(src);
  if (isList(src) && !isList(dst) && !isMany(dst)) return dst === "text";
  const [from, to] = [basesOf(src), basesOf(dst)];
  if (from.length > 1 || to.length > 1 || from[0] !== src || to[0] !== dst) return from.every((s) => to.some((d) => one(s, d)));
  return one(src, dst);
}

function one(src: string, dst: string): boolean {
  if (src === dst) return true;
  if (dst === "text") return true;
  if (dst === "number") return src === "bool";
  if (dst === "bool") return src === "number";
  if (TYPES[dst]?.thing) return src === "text";
  return false;
}

function items(data: Record<string, unknown>, field: string): unknown[] {
  const value = data[field];
  if (Array.isArray(value)) return value;
  const n = value === undefined || value === null || value === "" ? 2 : Math.max(0, Math.min(Math.trunc(Number(value)) || 2, 12));
  return Array.from({ length: n }, () => null);
}

// сокеты «Входа» и «Выхода» группы: имена хранятся в списке, чтобы не сдвигаться при удалении
export function named(data: Record<string, unknown>): Sock[] {
  const list = Array.isArray(data.sockets) ? (data.sockets as { name?: string; label?: string; type?: string }[]) : [];
  return list.filter((s) => s && String(s.name ?? "").trim()).map((s) => ({ name: String(s.name).trim(), label: String(s.label || s.name), type: s.type || "event" }));
}

function many(kind: Kind, data: Record<string, unknown>, side: string): Sock[] {
  return kind.many.filter((m) => m.side === side).flatMap((m) => (!m.prefix ? named(data) : items(data, m.field).map((item, i) => {
    const label = item && typeof item === "object" && "label" in item ? String((item as { label: unknown }).label ?? "") : "";
    return { name: `${m.prefix}${i + 1}`, label: m.label.includes("{label}") ? label || `Если ${i + 1}` : m.label.replace("{n}", String(i + 1)) };
  })));
}

// iface: сокеты группы или вложенного сценария (из определения группы или списка сценариев)
export function insOf(kind: Kind, data: Record<string, unknown>, iface: Iface | null = null): Sock[] {
  if (BOXES.includes(kind.name)) return iface?.inputs ?? [];
  return [...kind.ins.map((name) => ({ name, label: "", type: kind.in_types?.[name] ?? "event" })), ...many(kind, data, "in")];
}

// поля ноды, у которых есть вход (тип), и поля-параметры (выбор режима) — как в Blender
export const socketFields = (kind: Kind) => kind.fields.filter((f) => f.socket);
export const isChoice = (f: Field) => f.kind === "select" || f.kind === "switch";        // переключатель — выбор кнопками [а | б]
export const propFields = (kind: Kind) => kind.fields.filter((f) => !f.socket && isChoice(f));

// тип сокета ноды: name "f:поле" — вход-поле
export function sockType(kind: Kind, data: Record<string, unknown>, side: "in" | "out", name: string, iface: Iface | null = null): string {
  if (BOXES.includes(kind.name)) return ((side === "in" ? iface?.inputs : iface?.outputs) ?? []).find((s) => s.name === name)?.type ?? "event";
  if (kind.name === "group_in" || kind.name === "group_out") return named(data).find((s) => s.name === name)?.type ?? "event";
  if (side === "in") {
    if (!name.startsWith("f:")) return kind.in_types?.[name] ?? "event";
    const field = kind.fields.find((f) => f.name === name.slice(2));
    return resolveType(kind, data, field ? field.socket : isRow(kind, name.slice(2)) ? kind.grow!.type : "");
  }
  if (kind.owned || kind.name === OFFER_USED) {
    const own = iface?.outputs.find((s) => s.name === name);
    if (own) return own.type ?? "event";
  }
  if (kind.name === OFFER_USED && name.startsWith("fork:")) return "text";
  return resolveType(kind, data, kind.outs.find((s) => s.name === name)?.type ?? "event");
}

// waiting: у ноды есть входящий провод (существительное ждёт, а не стартует)
export function outsOf(kind: Kind, data: Record<string, unknown>, waiting: boolean, iface: Iface | null = null): Sock[] {
  if (BOXES.includes(kind.name)) return iface?.outputs ?? [];
  if (kind.name === OFFER_USED && iface) {
    const own = iface.outputs.filter((s) => (s.type ?? "event") === "event");
    if (!kind.start_only && waiting) own.push({ name: TIMEOUT, label: "Таймаут", type: "event" });
    return [...own, ...iface.outputs.filter((s) => s.type && s.type !== "event"), ...kind.outs.filter((s) => s.type && s.type !== "event")];
  }
  const events = kind.outs.filter((s) => (s.type ?? "event") === "event" && inWhen(kind, data, s.name));
  const values = kind.outs.filter((s) => s.type && s.type !== "event").map((s) => ({ ...s, type: resolveType(kind, data, s.type) }));
  const out: Sock[] = [...events, ...(kind.owned ? iface?.outputs ?? [] : []), ...many(kind, data, "out"), ...kind.tail];
  if (kind.group === "noun" && !kind.start_only && waiting) out.push({ name: TIMEOUT, label: "Таймаут", type: "event" });
  return [...out, ...values];
}

// выходы «Использована» по данным сущности «Возможность» (как graph/offers.used_outs): события канала, затем развилки текста
const FORK = /\[\[([\s\S]+?)\]\]/g;
const FORK_NAME = /^\s*([^|:\s][^|:]*?):\s+[\s\S]*$/;
export function offerIface(data: Record<string, unknown>): Iface {
  const channel = String(data.channel || "mail");
  let events: Sock[];
  if (channel === "choice") {
    const raw = Array.isArray(data.buttons) ? data.buttons : String(data.buttons ?? "").split(",");
    events = raw.map((b) => String(b ?? "").trim()).filter(Boolean).map((label, i) => ({ name: `b${i + 1}`, label, type: "event" }));
  } else if (channel === "file") events = [{ name: "ok", label: "Нажата", type: "event" }];
  else events = [{ name: "ok", label: "Верно", type: "event" }, { name: "wrong", label: "Неверно", type: "event" }];
  const forks: Sock[] = [];
  if (channel === "mail" || channel === "command") {
    let n = 0;
    for (const found of String(data.text ?? "").matchAll(FORK)) {
      n += 1;
      const name = FORK_NAME.exec(found[1])?.[1].trim() ?? "";
      forks.push({ name: `fork:${name || n}`, label: name || `Развилка ${n}`, type: "text" });
    }
  }
  return { inputs: [], outputs: [...events, ...forks] };
}

export const isThing = (type: string | undefined) => basesOf(type ?? "").some((b) => !!TYPES[b]?.thing);

// выход, который повторяет вход (kind.follows): пришёл список — список, одно — одно
export function followType(kind: Kind, name: string, type: string, fed: Record<string, string>): string {
  const field = kind.follows?.[name];
  const src = field ? fed[`f:${field}`] : "";
  if (!src || !isMany(type)) return type;
  return isList(src) ? `list:${elementOf(type)}` : isMany(src) ? type : elementOf(type);
}

// заголовок ноды: у «Математики» и «Логики» — выбранное действие (как в Blender)
const given = (value: unknown) => value !== undefined && value !== null && value !== "";

// поле задано: в него идёт провод или в нём что-то вписано
export const isSet = (data: Record<string, unknown>, usedIn: string[], name: string) => usedIn.includes(`f:${name}`) || given(data[name]);

export function titleOf(kind: Kind, data: Record<string, unknown>, usedIn: string[] = []): string {
  const named = Object.entries(kind.titled ?? {}).find(([name]) => isSet(data, usedIn, name));
  if (named) return named[1];                                    // «Размещение: Создать» с объектом — «Размещение: Добавить»
  if (!kind.title) return kind.label;
  const field = kind.fields.find((f) => f.name === kind.title);
  const value = String(data[kind.title] ?? field?.options[0]?.value ?? "");
  const chosen = field?.options.find((o) => o.value === value)?.label;
  if (!chosen) return kind.label;
  const space = kind.label.includes(": ") ? kind.label.split(": ")[0] : kind.group === "entity" ? kind.label : "";   // «Время: по дням недели», «Возможность: Письмо»
  return space ? `${space}: ${chosen}` : chosen;
}

// вход поля есть в выбранном режиме (kind.when); подключённые показываются всегда — это решает нода
export function inWhen(kind: Kind, data: Record<string, unknown>, name: string): boolean {
  return (kind.when ?? []).filter((w) => w.field === name).every((rule) => {
    const mode = kind.fields.find((f) => f.name === rule.mode);
    return rule.values.includes(String(data[rule.mode] ?? mode?.options[0]?.value ?? ""));
  });
}

// ---- растущий список входов (подстановки шаблона, входы «Логики») ----
export type Row = { id: string; name?: string; value?: unknown };
export const isRow = (kind: Kind, name: string) => !!kind.grow && name.startsWith(kind.grow.prefix) && /^\d+$/.test(name.slice(kind.grow.prefix.length));
export function rowsOf(kind: Kind, data: Record<string, unknown>): Row[] {
  const list = kind.grow ? data[kind.grow.field] : null;
  return Array.isArray(list) ? (list as Row[]).filter((r) => r && typeof r === "object" && r.id) : [];
}
const rowNum = (kind: Kind, id: string) => Number(id.slice(kind.grow!.prefix.length)) || 0;
const single = (kind: Kind, data: Record<string, unknown>) => !!kind.grow?.single.length && kind.grow.single.includes(String(data[kind.title || "op"] ?? ""));

// строки на холсте: заполненные и пустые до нужного числа (одна пустая всегда, но не меньше min)
export function visibleRows(kind: Kind, data: Record<string, unknown>): (Row & { empty?: boolean })[] {
  if (!kind.grow) return [];
  const stored = rowsOf(kind, data);
  let next = Math.max(0, ...stored.map((r) => rowNum(kind, r.id))) + 1;
  const out: (Row & { empty?: boolean })[] = [...stored];
  const want = single(kind, data) ? 1 : Math.max(kind.grow.min, stored.length + 1);
  while (out.length < want) out.push({ id: `${kind.grow.prefix}${next++}`, empty: true });
  return single(kind, data) ? out.slice(0, Math.max(1, Math.min(out.length, 1))) : out;
}

const filled = (r: Row) => !!String(r.name ?? "").trim() || (r.value !== undefined && r.value !== null && r.value !== "" && r.value !== false);

// хранить только заполненные строки (имя, значение или провод); подключённые, но ещё не записанные — добавить
export function tidyRows(kind: Kind | undefined, node: GNode, wires: GWire[]): GNode {
  if (!kind?.grow) return node;
  const wired = wires.filter((w) => w.to === node.id && w.in.startsWith("f:") && isRow(kind, w.in.slice(2))).map((w) => w.in.slice(2));
  const stored = rowsOf(kind, node.data);
  const rows = [...stored, ...wired.filter((id) => !stored.some((r) => r.id === id)).map((id) => ({ id }))]
    .filter((r) => wired.includes(r.id) || filled(r));
  if (JSON.stringify(rows) === JSON.stringify(stored)) return node;
  return { ...node, data: { ...node.data, [kind.grow.field]: rows.length ? rows : undefined } };
}

// свободное имя подстановки по подписи выхода: «Игрок» -> «игрок», занято -> «игрок2»
export function rowName(kind: Kind, data: Record<string, unknown>, label: string): string {
  const base = label.trim().toLowerCase().replace(/[{}]/g, "") || "x";
  const taken = new Set(rowsOf(kind, data).map((r) => String(r.name ?? "").trim()));
  let name = base, n = 2;
  while (taken.has(name)) name = `${base}${n++}`;
  return name;
}

// Короткая подпись ноды: шаблон summary с подставленными полями; подсказки (picks) дают человеческие имена.
export function summaryOf(kind: Kind, data: Record<string, unknown>, picks: Record<string, { value: string; label: string }[]>): string {
  if (!kind.summary) return "";
  const text = kind.summary.replace(/\{(\w+)\}/g, (_, name) => {
    const value = data[name];
    if (value === undefined || value === null || value === "") return "";
    const field = kind.fields.find((f) => f.name === name);
    if (field && isChoice(field)) return field.options.find((o) => o.value === String(value))?.label ?? String(value);
    if (field?.kind === "section") return picks.section?.find((o) => o.value === String(value))?.label ?? String(value);
    return String(value);
  });
  return text.replace(/\s+/g, " ").trim();
}

export function ifaceOfLevel(level: Level | undefined): Iface {
  const find = (type: string) => level?.nodes.find((n) => n.type === type);
  return { inputs: find("group_in") ? named(find("group_in")!.data) : [], outputs: find("group_out") ? named(find("group_out")!.data) : [] };
}

export function freeId(doc: Level): string {
  const taken = new Set(doc.nodes.map((n) => n.id));
  let n = doc.nodes.length + 1;
  while (taken.has(`n${n}`)) n += 1;
  return `n${n}`;
}

export function defaults(kind: Kind): Record<string, unknown> {
  const data: Record<string, unknown> = {};
  for (const f of kind.fields) if (isChoice(f) && f.options.length) data[f.name] = f.options[0].value;
  if (kind.name === "random") data.branches = [1, 1];
  if (kind.name === "choose") data.rows = [{ label: "", condition: "" }];
  for (const name of ["count"]) if (kind.fields.some((f) => f.name === name)) data[name] = kind.name === "first" ? 1 : 2;
  return data;
}
