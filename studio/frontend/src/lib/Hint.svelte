<script lang="ts">
  import type { Snippet } from "svelte";

  /** Значок «?» с пояснением по наведению или фокусу. */
  let { text, children }: { text?: string; children?: Snippet } = $props();
</script>

<button type="button" class="hint" aria-label={text}>
  ?
  <span class="bubble">{#if children}{@render children()}{:else}{text}{/if}</span>
</button>

<style>
  .hint {
    position: relative; padding: 0; background: none; display: inline-flex; align-items: center; justify-content: center;
    width: 15px; height: 15px; margin-left: 5px; border: 1px solid var(--line); border-radius: 50%;
    color: var(--muted); font-size: 10px; font-weight: 600; cursor: help; vertical-align: middle; text-transform: none; letter-spacing: 0;
  }
  .hint:hover, .hint:focus { border-color: var(--accent); color: var(--text); outline: none; }
  .bubble {
    display: none; position: absolute; top: 120%; left: 0; z-index: 30; width: max-content; max-width: 280px;
    padding: 8px 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel);
    color: var(--text); font-size: 12px; font-weight: 400; line-height: 1.4; text-align: left; white-space: normal; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
  }
  .hint:hover .bubble, .hint:focus .bubble { display: block; }
</style>
