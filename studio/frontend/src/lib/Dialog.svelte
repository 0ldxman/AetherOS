<script lang="ts" module>
  let counter = 0;
</script>

<script lang="ts">
  // Модальное окно на <dialog>: Esc и клик мимо закрывают (если уже что-то введено, сначала спросят), Enter в форме подтверждает.
  // Опасное (danger): фокус на «Отмене», а не на подтверждении.
  import type { Snippet } from "svelte";

  let { title, confirm = "Готово", danger = false, busy = false, disabled = false, wide = false, onsubmit, onclose, children }: {
    title: string;
    confirm?: string;
    danger?: boolean;
    busy?: boolean;
    wide?: boolean;       // шире и с прокруткой: для окон с конструкторами
    disabled?: boolean;   // подтвердить нельзя (причина написана в теле окна)
    onsubmit: () => void;
    onclose: () => void;
    children?: Snippet;
  } = $props();

  let box: HTMLDialogElement;
  let touched = false;
  const heading = `dialog-title-${++counter}`;

  function mayClose(): boolean {
    return !touched || window.confirm("Закрыть окно? Введённое не сохранится.");
  }

  $effect(() => {
    box.showModal();
    box.querySelector<HTMLElement>(danger ? ".cancel" : "input, select, textarea")?.focus();
  });
</script>

<dialog bind:this={box} class:wide aria-labelledby={heading} onclose={onclose} oncancel={(event) => { if (!mayClose()) event.preventDefault(); }}
  onclick={(event) => event.target === box && mayClose() && box.close()}>
  <form method="dialog" oninput={() => (touched = true)} onsubmit={(event) => { event.preventDefault(); onsubmit(); }}>
    <h2 id={heading}>{title}</h2>
    {@render children?.()}
    <div class="actions">
      <button type="button" class="btn ghost cancel" onclick={() => box.close()}>Отмена</button>
      <button type="submit" class="btn" class:primary={!danger} class:danger disabled={busy || disabled}>{confirm}</button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(440px, calc(100vw - 32px)); padding: 0; border: 1px solid var(--line); border-radius: 12px;
    background: var(--panel); color: var(--text); box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
  }
  dialog.wide { width: min(760px, calc(100vw - 32px)); max-height: calc(100vh - 48px); overflow-y: auto; }
  dialog::backdrop { background: rgba(5, 6, 8, 0.6); backdrop-filter: blur(2px); }
  form { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; }
  h2 { margin: 0; font-size: 15px; font-weight: 600; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
</style>
