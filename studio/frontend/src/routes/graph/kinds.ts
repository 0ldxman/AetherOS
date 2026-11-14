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
export const COLORS: Record<string, string> = { noun: "#3f8f86", flow: "#a7793a", data: "#8a5d7a", action: "#4d6fc4", struct: "#7a5aa8", service: "#5b6170" };

// Типы сокетов: цвет у точки и провода. event — «случилось» (поток), остальные — вещи, которые едут по ◆-проводу.
export const TYPES: Record<string, { label: string; color: string; thing?: boolean }> = {
  event: { label: "Событие", color: "#e6e8ec" },
  bool: { label: "Да/нет", color: "#e58fc4" },
  text: { label: "Текст", color: "#6ec1e4" },
  number: { label: "Число", color: "#a1a7b0" },
  item: { label: "Файл", color: "#ed9e40", thing: true },
  machine: { label: "Машина", color: "#3fc7b5", thing: true },
  character: { label: "Персонаж", color: "#c792ea", thing: true },
  section: { label: "Раздел", color: "#5fd07a", thing: true },
  flag: { label: "Метка игрока", color: "#f2c66d", thing: true },
  world_flag: { label: "Метка мира", color: "#ff8f6b", thing: true },
  counter: { label: "Счётчик", color: "#8fb3ff", thing: true },
  moment: { label: "Момент", color: "#d4d27a", thing: true },
};
export const typeColor = (type: string) => TYPES[type]?.color ?? TYPES.event.color;

// Можно ли вести провод из выхода типа src во вход типа dst (та же логика, что graph/nodes.compatible)
export function compatible(src: string, dst: string): boolean {
  if (src === dst) return true;
  if (src === "event" || dst === "event") return false;
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
  return [...kind.ins.map((name) => ({ name, label: "", type: "event" })), ...many(kind, data, "in")];
}

// поля ноды, у которых есть вход (тип), и поля-параметры (выбор режима) — как в Blender
export const socketFields = (kind: Kind) => kind.fields.filter((f) => f.socket);
export const propFields = (kind: Kind) => kind.fields.filter((f) => !f.socket && f.kind === "select");

// тип сокета ноды: name "f:поле" — вход-поле
export function sockType(kind: Kind, data: Record<string, unknown>, side: "in" | "out", name: string, iface: Iface | null = null): string {
  if (BOXES.includes(kind.name)) return ((side === "in" ? iface?.inputs : iface?.outputs) ?? []).find((s) => s.name === name)?.type ?? "event";
  if (kind.name === "group_in" || kind.name === "group_out") return named(data).find((s) => s.name === name)?.type ?? "event";
  if (side === "in") return name.startsWith("f:") ? kind.fields.find((f) => f.name === name.slice(2))?.socket ?? "" : "event";
  return kind.outs.find((s) => s.name === name)?.type ?? "event";
}

// waiting: у ноды есть входящий провод (существительное ждёт, а не стартует)
export function outsOf(kind: Kind, data: Record<string, unknown>, waiting: boolean, iface: Iface | null = null): Sock[] {
  if (BOXES.includes(kind.name)) return iface?.outputs ?? [];
  const events = kind.outs.filter((s) => (s.type ?? "event") === "event");
  const values = kind.outs.filter((s) => s.type && s.type !== "event");
  const out: Sock[] = [...events, ...many(kind, data, "out"), ...kind.tail];
  if (kind.group === "noun" && !kind.start_only && waiting) out.push({ name: TIMEOUT, label: "Таймаут", type: "event" });
  return [...out, ...values];
}

export const isThing = (type: string | undefined) => !!TYPES[type ?? ""]?.thing;

// Короткая подпись ноды: шаблон summary с подставленными полями; подсказки (picks) дают человеческие имена.
export function summaryOf(kind: Kind, data: Record<string, unknown>, picks: Record<string, { value: string; label: string }[]>): string {
  if (!kind.summary) return "";
  const text = kind.summary.replace(/\{(\w+)\}/g, (_, name) => {
    const value = data[name];
    if (value === undefined || value === null || value === "") return "";
    const field = kind.fields.find((f) => f.name === name);
    if (field?.kind === "select") return field.options.find((o) => o.value === String(value))?.label ?? String(value);
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
  for (const f of kind.fields) if (f.kind === "select" && f.options.length) data[f.name] = f.options[0].value;
  if (kind.name === "random") data.branches = [1, 1];
  if (kind.name === "choose") data.rows = [{ label: "", condition: "" }];
  for (const name of ["count"]) if (kind.fields.some((f) => f.name === name)) data[name] = kind.name === "first" ? 1 : 2;
  return data;
}
