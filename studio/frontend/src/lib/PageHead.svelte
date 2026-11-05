<script lang="ts">
  import type { Snippet } from "svelte";

  /** Шапка экрана: заголовок, пояснение под ним (sub) и справа инструменты (содержимое). Одинаковая на всех страницах. */
  let { title, sub, children }: { title: string; sub?: Snippet; children?: Snippet } = $props();
</script>

<header class="head">
  <div>
    <h1>{title}</h1>
    {#if sub}<p class="muted">{@render sub()}</p>{/if}
  </div>
  {#if children}<div class="tools">{@render children()}</div>{/if}
</header>

<style>
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 12px 24px; padding: 28px 32px 14px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  p { margin: 4px 0 0; max-width: 640px; }
  .tools { display: flex; flex-wrap: wrap; gap: 8px; }
</style>
