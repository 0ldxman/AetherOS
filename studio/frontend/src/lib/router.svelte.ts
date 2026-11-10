import { LEAVE_TEXT, unsavedFor } from "./guard.svelte";

// Маршруты по hash (#/volumes/3): страницу /studio/ отдаёт Django, всё остальное решается здесь.
export const route = $state({ path: read() });

function read(): string {
  return decodeURIComponent(location.hash.replace(/^#/, "")) || "/volumes";
}

let shown = location.hash;

window.addEventListener("hashchange", () => {
  const next = read();
  if (next !== route.path && unsavedFor(next) && !window.confirm(LEAVE_TEXT)) {
    history.replaceState(null, "", location.pathname + location.search + shown);
    return;
  }
  shown = location.hash;
  route.path = next;
});

export function go(path: string): void {
  location.hash = path;
}

/** Параметры пути по шаблону «/volumes/:id» или null. */
export function match(pattern: string, path: string): Record<string, string> | null {
  const want = pattern.split("/").filter(Boolean);
  const got = path.split("?")[0].split("/").filter(Boolean);
  if (want.length !== got.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < want.length; i++) {
    if (want[i].startsWith(":")) params[want[i].slice(1)] = got[i];
    else if (want[i] !== got[i]) return null;
  }
  return params;
}

/** Откуда пришли в редактор: его стрелка «назад» возвращает туда. Редактор забирает значение при открытии и сбрасывает его. */
const from = { path: "", label: "" };

export function comeFrom(path: string, label: string): void {
  from.path = path;
  from.label = label;
}

export function takeOrigin(): { path: string; label: string } {
  const taken = { ...from };
  from.path = from.label = "";
  return taken;
}
