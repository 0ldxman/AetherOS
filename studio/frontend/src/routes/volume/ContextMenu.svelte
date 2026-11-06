<script lang="ts" module>
  export type MenuItem = { label: string; run: () => void; hint?: string; danger?: boolean; disabled?: boolean } | "sep";
</script>

<script lang="ts">
  // Контекстное меню по правой кнопке: позиция у курсора, закрывается по клику мимо, Esc и прокрутке.

  let { x, y, items, onclose }: { x: number; y: number; items: MenuItem[]; onclose: () => void } = $props();
  let box: HTMLDivElement;
  let at = $state({ left: 0, top: 0 });

  // не вылезать за край окна
  $effect(() => {
    const { width, height } = box.getBoundingClientRect();
    at = { left: Math.min(x, window.innerWidth - width - 8), top: Math.min(y, window.innerHeight - height - 8) };
    box.querySelector<HTMLElement>("button:not(:disabled)")?.focus();
  });

  function pick(item: Exclude<MenuItem, "sep">) {
    onclose();
    item.run();
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape") onclose();
    else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      const buttons = [...box.querySelectorAll<HTMLElement>("button:not(:disabled)")];
      const next = buttons.indexOf(document.activeElement as HTMLElement) + (event.key === "ArrowDown" ? 1 : -1);
      buttons[(next + buttons.length) % buttons.length]?.focus();
      event.preventDefault();
    }
  }
</script>

<svelte:window onkeydown={onKey} onscroll={onclose} onresize={onclose} />
<svelte:document onmousedown={(event) => { if (!box.contains(event.target as globalThis.Node)) onclose(); }} />

<div class="menu" role="menu" bind:this={box} style:left="{at.left}px" style:top="{at.top}px">
  {#each items as item}
    {#if item === "sep"}
      <div class="sep" role="separator"></div>
    {:else}
      <button type="button" role="menuitem" class:danger={item.danger} disabled={item.disabled} onclick={() => pick(item)}>{item.label}{#if item.hint}<span class="hint">{item.hint}</span>{/if}</button>
    {/if}
  {/each}
</div>

<style>
  .menu {
    position: fixed; z-index: 60; min-width: 200px; padding: 4px; border: 1px solid var(--line); border-radius: var(--radius);
    background: var(--panel); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  }
  button { display: block; width: 100%; padding: 6px 12px; border: 0; border-radius: var(--radius-s); background: none; text-align: left; cursor: pointer; }
  button:hover:not(:disabled), button:focus-visible { background: var(--accent-soft); outline: none; }
  button:disabled { color: var(--faint); cursor: default; }
  button.danger { color: var(--danger); }
  .hint { display: block; color: var(--muted); font-size: 12px; }
  .sep { height: 1px; margin: 4px 2px; background: var(--line-soft); }
</style>
