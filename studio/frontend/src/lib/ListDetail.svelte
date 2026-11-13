<script lang="ts">
  import type { Snippet } from "svelte";

  /** Экран «список слева, редактор справа»: заголовок, список (list), кнопка добавления (add) и редактор (содержимое). */
  let { title, list, add, children, addOnTop = false }: { title: string; list: Snippet; add: Snippet; children?: Snippet; addOnTop?: boolean } = $props();

  // свёрнутость помним по заголовку списка: у каждого экрана своя
  const key = () => `studio.list.collapsed.${title}`;
  let collapsed = $state(false);
  try { collapsed = localStorage.getItem(key()) === "1"; } catch { /* без хранилища список просто развёрнут */ }
  function toggle() {
    collapsed = !collapsed;
    try { localStorage.setItem(key(), collapsed ? "1" : "0"); } catch { /* не сохранилось: не страшно */ }
  }
</script>

<div class="split" class:collapsed>
  <aside class="list">
    <button class="fold" type="button" onclick={toggle} title={collapsed ? `Показать список: ${title}` : "Свернуть список"} aria-label={collapsed ? `Показать список: ${title}` : "Свернуть список"} aria-expanded={!collapsed}>{collapsed ? "»" : "«"}</button>
    {#if collapsed}
      <span class="vtitle" aria-hidden="true">{title}</span>
    {:else}
    {#if addOnTop}
      <h1 class="sr">{title}</h1>
      <div class="add top">{@render add()}</div>
    {:else}
      <h1>{title}</h1>
    {/if}
    {@render list()}
    {#if !addOnTop}<div class="add">{@render add()}</div>{/if}
    {/if}
  </aside>
  {@render children?.()}
</div>

<style>
  .split { display: grid; grid-template-columns: 260px 1fr; min-height: 100%; }
  .split.collapsed { grid-template-columns: 40px 1fr; }
  .split.collapsed .list { padding: 12px 4px; align-items: center; }
  .fold { align-self: flex-end; width: 28px; height: 28px; margin: -8px 2px 6px 0; border: 0; border-radius: var(--radius-s); background: none; color: var(--muted, var(--text)); font: inherit; cursor: pointer; }
  .fold:hover { background: var(--panel); color: var(--text); }
  .collapsed .fold { align-self: center; margin: 0 0 12px; }
  .vtitle { writing-mode: vertical-rl; color: var(--muted, var(--text)); font-size: 13px; letter-spacing: 0.04em; white-space: nowrap; }
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
