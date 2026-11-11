// Сценарий переписки в редакторе: черновик это шапка (title, slug, note, persona) и шаги по ключам «s:<ключ>», каждый шаг
// со своими вариантами. Так два автора правят разные шаги одновременно, не затирая друг друга. Удалённый шаг это null.
import type { Schemas } from "../../lib/api";

export type Action = { do: string; step?: string; item?: string; subject?: string; text?: string; delay?: number; name?: string; slug?: string; path?: string };
export type VariantDraft = Omit<Schemas["MlVariant"], "outcomes"> & { key: string; outcomes: Record<string, Action[]> };
export type StepDraft = Omit<Schemas["MlStep"], "variants"> & { key: string; order: number; variants: VariantDraft[] };
export type Head = { title: string; slug: string; note: string; persona: number };
export type Form = Head & Record<string, unknown>;

const PREFIX = "s:";
export const newKey = () => "n" + Math.random().toString(36).slice(2, 10);

export function toForm(doc: Schemas["MlDoc"]): Form {
  const form: Form = { title: doc.title, slug: doc.slug, note: doc.note ?? "", persona: doc.persona };
  (doc.steps ?? []).forEach((step, order) => {
    const key = `${step.id ?? newKey()}`;
    form[PREFIX + key] = {
      ...step, key, order, letter: { item: step.letter?.item ?? null, subject: step.letter?.subject ?? "", text: step.letter?.text ?? "" },
      variants: (step.variants ?? []).map((v) => ({ ...v, key: `${v.id ?? newKey()}`, outcomes: (v.outcomes ?? {}) as Record<string, Action[]> })),
    } satisfies StepDraft;
  });
  return form;
}

export function stepsOf(form: Form): StepDraft[] {
  return Object.keys(form)
    .filter((key) => key.startsWith(PREFIX) && form[key])
    .map((key) => form[key] as StepDraft)
    .sort((a, b) => a.order - b.order || a.key.localeCompare(b.key));
}

export const stepField = (key: string) => PREFIX + key;

export function toDoc(form: Form): Schemas["MlDoc"] {
  return {
    title: form.title, slug: form.slug, note: form.note, persona: form.persona,
    steps: stepsOf(form).map(({ key: _k, order: _o, variants, ...step }) => ({
      ...step, variants: variants.map(({ key: _vk, ...variant }) => variant),
    })),
  };
}

export function emptyVariant(): VariantDraft {
  return { key: newKey(), id: null, title: "", mode: "reply", text: "", forward_of: null, condition: "", need_flags: [], deny_flags: [],
           account: null, closed: "mystery", attachment: { kind: "", slug: "" }, max_attempts: 0, outcomes: {} };
}

export function emptyStep(name: string, order: number, x: number, y: number): StepDraft {
  return { key: newKey(), id: null, name, order, x, y, opening: false, letter: { item: null, subject: "", text: "" }, letter_delay: 0, variants: [] };
}

/** Свободное имя шага: step, step-2, … */
export function freeName(steps: StepDraft[], base = "step"): string {
  const names = new Set(steps.map((s) => s.name));
  if (!names.has(base)) return base;
  let n = 2;
  while (names.has(`${base}-${n}`)) n++;
  return `${base}-${n}`;
}

const TOKEN = /\{\{(.+?)\}\}|\[\[(.+?)\]\]/gs;

/** Выходы варианта, как mail.talk.sockets: ok, слова выбора, wrong (есть что угадать или приложить), exhausted (есть лимит). */
export function socketsOf(variant: VariantDraft): string[] {
  const out = ["ok"];
  let secret = !!variant.attachment?.kind;
  for (const found of (variant.text ?? "").matchAll(TOKEN)) {
    if (found[1] !== undefined) secret = true;
    else for (const option of found[2].split("|").map((o) => o.trim()).filter(Boolean)) if (!out.includes(`word:${option}`)) out.push(`word:${option}`);
  }
  if (secret || variant.max_attempts) out.push("wrong");
  if (variant.max_attempts) out.push("exhausted");
  for (const socket of Object.keys(variant.outcomes ?? {})) if (!out.includes(socket) && variant.outcomes[socket]?.length) out.push(socket);
  return out;
}

export function socketLabel(socket: string): string {
  if (socket === "ok") return "верно";
  if (socket === "wrong") return "неверно";
  if (socket === "exhausted") return "попытки кончились";
  if (socket.startsWith("word:")) return `«${socket.slice(5)}»`;
  return socket;
}

/** Все переходы goto: из какого шага, варианта и выхода в какое имя шага. */
export function gotos(steps: StepDraft[]) {
  const out: { from: StepDraft; variant: number; socket: string; target: string }[] = [];
  for (const step of steps)
    step.variants.forEach((variant, index) => {
      for (const [socket, actions] of Object.entries(variant.outcomes ?? {}))
        for (const action of actions ?? []) if (action.do === "goto" && action.step) out.push({ from: step, variant: index, socket, target: action.step });
    });
  return out;
}

/** Переименование шага: переходы на старое имя ведут на новое. */
export function renameRefs(step: StepDraft, from: string, to: string): StepDraft {
  let changed = false;
  const variants = step.variants.map((variant) => {
    const outcomes: Record<string, Action[]> = {};
    for (const [socket, actions] of Object.entries(variant.outcomes ?? {}))
      outcomes[socket] = (actions ?? []).map((a) => {
        if (a.do === "goto" && a.step === from) {
          changed = true;
          return { ...a, step: to };
        }
        return a;
      });
    return { ...variant, outcomes };
  });
  return changed ? { ...step, variants } : step;
}

export const ACTIONS: { value: string; label: string }[] = [
  { value: "goto", label: "Перейти на шаг" },
  { value: "letter", label: "Прислать письмо" },
  { value: "flag", label: "Поставить метку" },
  { value: "unflag", label: "Снять метку" },
  { value: "key", label: "Выдать ключ" },
  { value: "file", label: "Положить файл" },
  { value: "hook", label: "Хук (alert, open, kick)" },
  { value: "bounce", label: "Вернуть как недоставленное" },
];

export function describe(action: Action): string {
  switch (action.do) {
    case "goto": return `→ ${action.step || "?"}${action.delay ? ` через ${action.delay} с` : ""}`;
    case "letter": return `✉ ${action.subject || action.item || "письмо"}${action.delay ? ` через ${action.delay} с` : ""}`;
    case "flag": return `+ метка ${action.name || "?"}`;
    case "unflag": return `− метка ${action.name || "?"}`;
    case "key": return `ключ ${action.slug || "?"}`;
    case "file": return `файл ${action.item || "?"} → ${action.path || "?"}`;
    case "hook": return `хук: ${(action.text || "").split("\n")[0]}`;
    case "bounce": return "вернуть письмо";
    default: return action.do;
  }
}
