<script lang="ts">
  import { getContext, type Snippet } from "svelte";

  /** Шапка экрана: заголовок, пояснение под ним (sub) и справа инструменты (содержимое). Одинаковая на всех страницах.
   *  Внутри вкладок (Embed) заголовок уже стоит над вкладками: остаются пояснение и инструменты. */
  let { title, sub, children }: { title: string; sub?: Snippet; children?: Snippet } = $props();
  const embedded = getContext<boolean | undefined>("embedded") === true;
</script>

{#if embedded}
  <header class="head inner">
    {#if sub}<p class="muted">{@render sub()}</p>{/if}
    {#if children}<div class="tools">{@render children()}</div>{/if}
  </header>
{:else}
  <header class="head">
    <div>
      <h1>{title}</h1>
      {#if sub}<p class="muted">{@render sub()}</p>{/if}
    </div>
    {#if children}<div class="tools">{@render children()}</div>{/if}
  </header>
{/if}

<style>
  .head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: flex-end; gap: 12px 24px; padding: 28px 32px 14px; }
  .head.inner { align-items: center; padding: 14px 32px 4px; }
  h1 { margin: 0; font-size: 22px; font-weight: 650; }
  p { margin: 4px 0 0; max-width: 640px; }
  .inner p { margin: 0; max-width: 720px; }
  .tools { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
</style>
