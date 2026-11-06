<script lang="ts">
  import type { Snippet } from "svelte";

  /** Значок «?» с пояснением: по наведению, по фокусу и по касанию (кнопка переключает), Esc закрывает. */
  let { text, align = "left", children }: { text?: string; align?: "left" | "right"; children?: Snippet } = $props();
  let open = $state(false);
</script>

<button
  type="button" class="hint" class:open aria-label={text ?? "Пояснение"} aria-expanded={open}
  onclick={() => (open = !open)} onblur={() => (open = false)} onkeydown={(event) => event.key === "Escape" && (open = false)}
>
  ?
  <span class="bubble" class:right={align === "right"} role="tooltip">{#if children}{@render children()}{:else}{text}{/if}</span>
</button>

<style>
  .hint {
    position: relative; padding: 0; background: none; display: inline-flex; align-items: center; justify-content: center;
    width: 15px; height: 15px; margin-left: 5px; border: 1px solid var(--line); border-radius: 50%;
    color: var(--muted); font-size: 10px; font-weight: 600; cursor: help; vertical-align: middle; text-transform: none; letter-spacing: 0;
  }
  .hint:hover, .hint:focus-visible, .hint.open { border-color: var(--accent); color: var(--text); }
  .bubble {
    display: none; position: absolute; top: 120%; left: 0; z-index: 30; width: max-content; max-width: 280px;
    padding: 8px 10px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel);
    color: var(--text); font-size: 12px; font-weight: 400; line-height: 1.4; text-align: left; white-space: normal; box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
  }
  .bubble.right { left: auto; right: 0; }
  .hint:hover .bubble, .hint:focus-visible .bubble, .hint.open .bubble { display: block; }
</style>
