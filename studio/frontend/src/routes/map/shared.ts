// Общее для вкладок карты: даты, подписи, чтение формы.
import type { Schemas } from "../../lib/api";

export type Country = Schemas["MapCountryRow"];

export const RANKS = [
  { value: 1, label: "Крупная" },
  { value: 2, label: "Средняя" },
  { value: 3, label: "Малая" },
  { value: 4, label: "Мелкая" },
];

export const NO_COLOR = "#26313c";

/** Сегодняшняя дата мира для подписи: ГГГГ-ММ-ДД. */
export function today(): string {
  return new Date().toISOString().slice(0, 10);
}

/** «1960-01-01» → «01.01.1960». */
export function showDate(value: string | null | undefined): string {
  if (!value) return "…";
  const [y, m, d] = value.split("-");
  return `${d}.${m}.${y}`;
}

/** Ошибки полей из ответа API. */
export function fieldErrors(error: unknown): Record<string, string[]> {
  return (error as { fields?: Record<string, string[]> })?.fields ?? {};
}
