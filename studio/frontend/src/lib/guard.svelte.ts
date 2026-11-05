// Защита от потери несохранённых правок: экран регистрирует «есть ли правки», а роутер и браузер спрашивают перед уходом.
import { onDestroy } from "svelte";

type Entry = { dirty: () => boolean; stays?: (next: string) => boolean };
const entries = new Set<Entry>();

export const LEAVE_TEXT = "Есть несохранённые правки. Уйти без сохранения?";

/** Вызвать при создании экрана. stays: переход на этот путь правки не теряет (вкладки того же объекта). */
export function guardUnsaved(dirty: () => boolean, stays?: (next: string) => boolean): void {
  const entry: Entry = { dirty, stays };
  entries.add(entry);
  onDestroy(() => entries.delete(entry));
}

/** Пропадут ли чьи-то правки при переходе на путь next («» — уход со страницы). */
export function unsavedFor(next: string): boolean {
  for (const entry of entries) if (entry.dirty() && !entry.stays?.(next)) return true;
  return false;
}

window.addEventListener("beforeunload", (event) => {
  if (unsavedFor("")) event.preventDefault();
});
