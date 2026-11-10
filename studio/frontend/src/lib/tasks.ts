// Общее для экранов задач: цвет приоритета (1 спокойный серый … 10 красный).
export function priorityColor(priority: number): string {
  if (priority >= 9) return "var(--danger)";
  if (priority >= 7) return "#f76b15";
  if (priority >= 5) return "var(--warn)";
  if (priority >= 3) return "var(--accent)";
  return "var(--muted)";
}
