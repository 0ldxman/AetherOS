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
export type Sock = { name: string; label: string };
export type Iface = { inputs: Sock[]; outputs: Sock[] };
export const BOXES = ["group", "scenario"];

export const REF = "ref";
export const TIMEOUT = "timeout";
export const COLORS: Record<string, string> = { noun: "#3f8f86", flow: "#a7793a", action: "#4d6fc4", service: "#5b6170" };

function items(data: Record<string, unknown>, field: string): unknown[] {
  const value = data[field];
  if (Array.isArray(value)) return value;
  const n = value === undefined || value === null || value === "" ? 2 : Math.max(0, Math.min(Math.trunc(Number(value)) || 2, 12));
  return Array.from({ length: n }, () => null);
}

// сокеты «Входа» и «Выхода» группы: имена хранятся в списке, чтобы не сдвигаться при удалении
export function named(data: Record<string, unknown>): Sock[] {
  const list = Array.isArray(data.sockets) ? (data.sockets as { name?: string; label?: string }[]) : [];
  return list.filter((s) => s && String(s.name ?? "").trim()).map((s) => ({ name: String(s.name).trim(), label: String(s.label || s.name) }));
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
  return [...kind.ins.map((name) => ({ name, label: "" })), ...many(kind, data, "in")];
}

// waiting: у ноды есть входящий провод (существительное ждёт, а не стартует)
export function outsOf(kind: Kind, data: Record<string, unknown>, waiting: boolean, iface: Iface | null = null): Sock[] {
  if (BOXES.includes(kind.name)) return iface?.outputs ?? [];
  const out = [...kind.outs.filter((s) => s.name !== REF), ...many(kind, data, "out"), ...kind.tail];
  if (kind.group === "noun" && !kind.start_only && waiting) out.push({ name: TIMEOUT, label: "Таймаут" });
  return out;
}

export function refOf(kind: Kind): Sock | null {
  return kind.outs.find((s) => s.name === REF) ?? null;
}

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
