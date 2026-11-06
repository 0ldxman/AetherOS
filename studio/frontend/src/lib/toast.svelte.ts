// Короткие сообщения в углу: что сделано или что не получилось. С действием («Отменить») живут дольше.
export type ToastAction = { label: string; run: () => void };
export type Toast = { id: number; text: string; kind: "ok" | "error"; action?: ToastAction };

export const toasts = $state<Toast[]>([]);
let next = 1;

export function dismiss(id: number): void {
  const at = toasts.findIndex((item) => item.id === id);
  if (at >= 0) toasts.splice(at, 1);
}

export function toast(text: string, kind: Toast["kind"] = "ok", action?: ToastAction): void {
  const id = next++;
  toasts.push({ id, text, kind, action });
  setTimeout(() => dismiss(id), action ? 10000 : kind === "error" ? 6000 : 2500);
}
