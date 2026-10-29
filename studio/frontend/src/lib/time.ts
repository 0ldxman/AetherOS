// Даты и сроки для людей: «29.10 10:15», «2 мин назад», «4:12».
export function when(stamp: string | null | undefined): string {
  if (!stamp) return "—";
  return new Date(stamp).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ago(stamp: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(stamp).getTime()) / 1000));
  if (seconds < 60) return "только что";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} мин назад`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} ч назад`;
  return when(stamp);
}

export function span(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
