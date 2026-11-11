// Песочница автора (users/sandbox.py): одно окно на всю Студию. Пока она включена, игровые страницы в этом браузере идут
// от имени песочного игрока автора, а Студия остаётся за автором. Окно поверх экрана: «Свернуть» оставляет плашку в углу.
import { api, problem } from "./api";
import { ask } from "./confirm.svelte";
import { toast } from "./toast.svelte";

export const sandbox = $state({ open: false, shown: false, player: "", title: "", hint: "", nonce: 0 });

/** Адрес настоящего рабочего стола (nonce заставляет рамку перезагрузиться). */
export function sandboxUrl(): string {
  return `${window.STUDIO.site}?sandbox=${sandbox.nonce}`;
}

export async function loadSandbox() {
  const { data } = await api.GET("/studio/api/sandbox");
  if (!data) return;
  sandbox.open = data.open;
  sandbox.player = data.player;
}

/** Открыть песочницу: title говорит, что проверяем, hint это что ввести руками (команда, логин). */
export async function openSandbox(title = "", hint = "") {
  const { data, error } = await api.POST("/studio/api/sandbox/open");
  if (error || !data) return toast(problem(error, "Песочница не открылась."), "error");
  Object.assign(sandbox, { open: true, shown: true, player: data.player, title, hint, nonce: sandbox.nonce + 1 });
}

export function showSandbox(shown: boolean) {
  sandbox.shown = shown;
}

export async function closeSandbox() {
  await api.POST("/studio/api/sandbox/close");
  Object.assign(sandbox, { open: false, shown: false, title: "", hint: "" });
}

export async function resetSandbox() {
  if (!(await ask("Начать заново?", "Песочный игрок со всем, что он сделал (входы и блокировки, файлы, письма, метки, часы машин), будет стёрт. Мир и настоящие игроки не затрагиваются.", "Начать заново"))) return;
  const { data, error } = await api.POST("/studio/api/sandbox/reset");
  if (error || !data) return toast(problem(error), "error");
  sandbox.player = data.player;
  sandbox.nonce += 1;
  toast("Песочница начата заново.");
}
