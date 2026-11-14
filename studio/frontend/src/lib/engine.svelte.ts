// Словарь действий движка (engine/actions.py): загружается один раз на сессию Студии и общий для всех редакторов действий.
import { api, type Schemas } from "./api";

export type Catalog = Schemas["EnCatalog"];
export type ActionSpec = Schemas["EnAction"];
export type Act = Record<string, unknown> & { do: string };

let catalog = $state<Catalog | null>(null);
let loading: Promise<void> | null = null;

export function engine() {
  if (!catalog && !loading) {
    loading = api.GET("/studio/api/engine/catalog").then(({ data }) => { if (data) catalog = data; loading = null; });
  }
  return { get catalog() { return catalog; } };
}

// Обновить подсказки полей (после создания ключа, раздела, станции).
export async function reloadEngine() {
  const { data } = await api.GET("/studio/api/engine/catalog");
  if (data) catalog = data;
}

// Как действие выглядит в списке: шаблон summary с подставленными полями.
export function summary(action: Act): string {
  engine();                                  // первый вызов запускает загрузку; когда словарь придёт, подписи пересчитаются
  const spec = catalog?.actions.find((a) => a.name === action.do);
  if (!spec) return action.do;
  return spec.summary.replace(/\{(\w+)\}/g, (_, name) => {
    const value = action[name];
    if (value === undefined || value === null || value === "") return name === "delta" ? "1" : "…";
    const field = spec.fields.find((f) => f.name === name);
    const pick = field && catalog?.picks[field.kind]?.find((o) => o.value === String(value));
    return pick && field.kind === "section" ? pick.label : String(value);
  });
}

export const summaries = (actions: Act[]) => actions.map(summary).join(", ");
