// Короткие сообщения в углу: что сделано или что не получилось.
export type Toast = { id: number; text: string; kind: "ok" | "error" };

export const toasts = $state<Toast[]>([]);
let next = 1;

export function toast(text: string, kind: Toast["kind"] = "ok"): void {
  const id = next++;
  toasts.push({ id, text, kind });
  setTimeout(() => {
    const at = toasts.findIndex((item) => item.id === id);
    if (at >= 0) toasts.splice(at, 1);
  }, kind === "error" ? 6000 : 2500);
}
