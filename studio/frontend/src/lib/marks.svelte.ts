// Следы совместной правки на экране, для всех форм сразу, без разметки полей: поле узнаётся по своей подписи.
// fieldKey: как назвать поле другим авторам (подпись и номер среди полей с той же подписью).
// flashAround: после чужой правки коротко подсвечивает поля, у которых сменилось значение.
import { tick } from "svelte";

const FIELDS = "main input, main select, main textarea";

function labelOf(element: Element): string {
  const own = element.getAttribute("aria-label");
  if (own) return own.trim();
  const label = element.closest("label");
  const text = label?.querySelector(".label")?.textContent ?? label?.textContent ?? "";
  if (text.trim()) return text.trim().split("\n")[0].trim();
  return (element as HTMLInputElement).placeholder?.trim() || (element as HTMLInputElement).name || "";
}

/** Ключ поля: «Название#0». Пусто: поле без подписи (такое не показывается другим). */
export function fieldKey(element: Element): string {
  const label = labelOf(element);
  if (!label) return "";
  const same = [...document.querySelectorAll(FIELDS)].filter((other) => labelOf(other) === label);
  return `${label}#${Math.max(0, same.indexOf(element))}`;
}

export function fieldByKey(key: string): HTMLElement | null {
  const at = key.lastIndexOf("#");
  if (at < 0) return null;
  const label = key.slice(0, at);
  const index = +key.slice(at + 1);
  const found = [...document.querySelectorAll(FIELDS)].filter((other) => labelOf(other) === label);
  return (found[index] as HTMLElement | undefined) ?? null;
}

export const labelOfKey = (key: string) => key.replace(/#\d+$/, "");

function valueOf(element: Element): string {
  const input = element as HTMLInputElement;
  return input.type === "checkbox" || input.type === "radio" ? String(input.checked) : input.value;
}

const TEXTS = "main td, main .cell, main li";

/** Выполнить чужую правку (или перечитать после неё) и подсветить поля и ячейки, которые от неё изменились. */
export async function flashAround(apply: () => void | Promise<void>) {
  const before = new Map([...document.querySelectorAll(FIELDS)].map((element) => [element, valueOf(element)]));
  const cells = new Map([...document.querySelectorAll(TEXTS)].map((element) => [element, element.textContent ?? ""]));
  await apply();
  await tick();
  for (const [element, text] of cells) {
    if (!element.isConnected || (element.textContent ?? "") === text) continue;
    element.classList.remove("remote-changed");
    void (element as HTMLElement).offsetWidth;
    element.classList.add("remote-changed");
    setTimeout(() => element.classList.remove("remote-changed"), 1400);
  }
  for (const [element, value] of before) {
    if (!element.isConnected || valueOf(element) === value || element === document.activeElement) continue;
    element.classList.remove("remote-changed");
    void (element as HTMLElement).offsetWidth;          // перезапуск анимации, если поле меняют часто
    element.classList.add("remote-changed");
    setTimeout(() => element.classList.remove("remote-changed"), 1400);
  }
}
