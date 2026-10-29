<script lang="ts">
  // Модальное окно на <dialog>: Esc и клик мимо закрывают, Enter в форме подтверждает.
  import type { Snippet } from "svelte";

  let { title, confirm = "OK", danger = false, busy = false, onsubmit, onclose, children }: {
    title: string;
    confirm?: string;
    danger?: boolean;
    busy?: boolean;
    onsubmit: () => void;
    onclose: () => void;
    children?: Snippet;
  } = $props();

  let box: HTMLDialogElement;

  $effect(() => {
    box.showModal();
    box.querySelector<HTMLElement>("input, select, textarea")?.focus();
  });
</script>

<dialog bind:this={box} onclose={onclose} onclick={(event) => event.target === box && box.close()}>
  <form method="dialog" onsubmit={(event) => { event.preventDefault(); onsubmit(); }}>
    <h2>{title}</h2>
    {@render children?.()}
    <div class="actions">
      <button type="button" class="btn ghost" onclick={() => box.close()}>Отмена</button>
      <button type="submit" class="btn" class:primary={!danger} class:danger disabled={busy}>{confirm}</button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(440px, calc(100vw - 32px)); padding: 0; border: 1px solid var(--line); border-radius: 12px;
    background: var(--panel); color: var(--text); box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
  }
  dialog::backdrop { background: rgba(5, 6, 8, 0.6); backdrop-filter: blur(2px); }
  form { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; }
  h2 { margin: 0; font-size: 15px; font-weight: 600; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
</style>
