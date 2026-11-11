<script lang="ts">
  import type { Snippet } from "svelte";

  /** Экран «список слева, редактор справа»: заголовок, список (list), кнопка добавления (add) и редактор (содержимое). */
  let { title, list, add, children, addOnTop = false }: { title: string; list: Snippet; add: Snippet; children?: Snippet; addOnTop?: boolean } = $props();
</script>

<div class="split">
  <aside class="list">
    {#if addOnTop}
      <h1 class="sr">{title}</h1>
      <div class="add top">{@render add()}</div>
    {:else}
      <h1>{title}</h1>
    {/if}
    {@render list()}
    {#if !addOnTop}<div class="add">{@render add()}</div>{/if}
  </aside>
  {@render children?.()}
</div>

<style>
  .split { display: grid; grid-template-columns: 260px 1fr; min-height: 100%; }
  .list { display: flex; flex-direction: column; gap: 2px; padding: 20px 8px; border-right: 1px solid var(--line-soft); position: sticky; top: 0; align-self: start; max-height: 100vh; overflow-y: auto; box-sizing: border-box; }
  h1 { margin: 0 10px 12px; font-size: 18px; }
  .list :global(.item) { display: flex; flex-direction: column; padding: 8px 10px; border-radius: var(--radius-s); color: var(--text); }
  .list :global(.item:hover) { background: var(--panel); text-decoration: none; }
  .list :global(.item.on) { background: var(--accent-soft); }
  .add { margin: 8px 4px 0; display: flex; }
  .add.top { margin: 0 4px 12px; }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .add :global(.btn) { flex: 1; justify-content: center; }
</style>
