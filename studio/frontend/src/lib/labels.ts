// Общие подписи: так одно и то же называется на всех экранах Студии.

/** Статус машины: код из базы и подпись для автора. */
export const STATUS: Record<string, string> = { ONLINE: "в сети", OFFLINE: "не в сети", MAINTENANCE: "обслуживание" };

/** Склонение по числу: plural(2, "машина", "машины", "машин") → «машины». */
export function plural(count: number, one: string, few: string, many: string): string {
  const tail = count % 100;
  if (tail >= 11 && tail <= 14) return many;
  const last = count % 10;
  return last === 1 ? one : last >= 2 && last <= 4 ? few : many;
}
