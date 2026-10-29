// Маршруты по hash (#/volumes/3): страницу /studio/ отдаёт Django, всё остальное решается здесь.
export const route = $state({ path: read() });

function read(): string {
  return decodeURIComponent(location.hash.replace(/^#/, "")) || "/volumes";
}

window.addEventListener("hashchange", () => {
  route.path = read();
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
