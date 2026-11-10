// Уведомления автора (team.notify): число непрочитанных для кнопки «Главная», проверяется раз в 30 секунд и при возврате
// во вкладку; Главная перечитывает список, когда число меняется (stamp).
import { api } from "./api";

export const notes = $state({ unread: 0, stamp: 0 });

export async function checkNotes(): Promise<void> {
  const unread = (await api.GET("/studio/api/notifications")).data?.unread;
  if (unread === undefined) return;
  if (unread !== notes.unread) notes.stamp++;
  notes.unread = unread;
}

export function watchNotes(): () => void {
  checkNotes();
  const timer = setInterval(checkNotes, 30_000);
  const visible = () => { if (document.visibilityState === "visible") checkNotes(); };
  document.addEventListener("visibilitychange", visible);
  return () => { clearInterval(timer); document.removeEventListener("visibilitychange", visible); };
}
