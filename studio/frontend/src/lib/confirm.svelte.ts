// Подтверждение опасного действия: `if (!(await ask("Удалить сцену?", "Привязки пропадут."))) return;`
type Pending = { title: string; text: string; confirm: string; resolve: (ok: boolean) => void };

export const pending = $state<{ current: Pending | null }>({ current: null });

export function ask(title: string, text = "", confirm = "Удалить"): Promise<boolean> {
  return new Promise((resolve) => {
    pending.current?.resolve(false);
    pending.current = { title, text, confirm, resolve };
  });
}

export function settle(ok: boolean): void {
  const current = pending.current;
  if (!current) return;
  pending.current = null;
  current.resolve(ok);
}
