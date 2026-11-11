<script lang="ts">
  // Фильтр-чип: кнопка с названием и выбранным значением, по щелчку открывается панель с самим фильтром.
  import type { Snippet } from "svelte";
  import { onMount } from "svelte";
  import Icon from "../../lib/Icon.svelte";

  let { label, value = "", children }: { label: string; value?: string; children: Snippet } = $props();
  let open = $state(false);
  let root: HTMLElement | undefined = $state();

  onMount(() => {
    const outside = (event: MouseEvent) => { if (open && !root?.contains(event.target as Node)) open = false; };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  });
</script>

<div class="fchip" bind:this={root} onkeydown={(event) => event.key === "Escape" && (open = false)} role="presentation">
  <button class:on={!!value} aria-expanded={open} aria-haspopup="dialog" onclick={() => (open = !open)}>
    <span>{label}{#if value}<span class="v">: <b>{value}</b></span>{/if}</span><Icon name="chevron" size={12} />
  </button>
  {#if open}<div class="pop" role="dialog" aria-label={label}>{@render children()}</div>{/if}
</div>

<style>
  .fchip { position: relative; }
  button { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: 999px; background: var(--panel); color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
  button:hover, button[aria-expanded="true"] { border-color: var(--line); color: var(--text); }
  button.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .v b { font-weight: 600; }
  .pop { position: absolute; z-index: 30; top: calc(100% + 6px); left: 0; display: flex; flex-direction: column; gap: 8px; min-width: 240px; padding: 12px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--raise); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
</style>
