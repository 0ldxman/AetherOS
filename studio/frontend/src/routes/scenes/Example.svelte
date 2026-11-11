<script lang="ts">
  // Пример из справки по языку сцен: текст и его результат на мини-экране. Играет, когда попадает в поле зрения; «Заново» повторяет.
  import { onDestroy, onMount } from "svelte";
  import { api } from "../../lib/api";
  import Icon from "../../lib/Icon.svelte";

  type Step = Record<string, unknown>;
  type Term = { play: (steps: Step[], opts?: Record<string, unknown>) => Promise<unknown>; stop: () => void };

  let { code, play }: { code: string; play: "run" | "instant" | "none" } = $props();

  let host: HTMLElement | undefined = $state();
  let screen: HTMLElement | undefined = $state();
  let steps: Step[] | null = null;
  let term: Term | null = null;
  let running: Promise<unknown> = Promise.resolve();
  let generation = 0;
  let failed = $state(false);

  async function start() {
    if (!screen) return;
    if (!steps) {
      const { data } = await api.POST("/studio/api/scenes/preview", { body: { body: code, slot: "" } });
      if (!data || data.errors.length) { failed = true; return; }
      steps = data.steps as Step[];
    }
    const aether = (window as unknown as { Aether?: { console: { create: (el: HTMLElement, opts?: Record<string, unknown>) => Term } } }).Aether;
    if (!aether) return;
    term ??= aether.console.create(screen, { skipOnInput: false });
    const mine = ++generation;
    term.stop();
    await running;
    if (mine !== generation) return;
    running = term.play([{ op: "clear" }, ...steps], play === "instant" ? { instant: true } : { speed: 1 });
  }

  onMount(() => {
    if (play === "none" || !host) return;
    const seen = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) { seen.disconnect(); start(); }
    }, { threshold: 0.4 });
    seen.observe(host);
    return () => seen.disconnect();
  });
  onDestroy(() => { generation++; term?.stop(); });
</script>

<div class="example" bind:this={host}>
  <pre class="src">{code}</pre>
  {#if play === "none"}
    <p class="note">Результат зависит от вставляемой сцены.</p>
  {:else}
    <div class="out">
      <div class="screen" bind:this={screen}></div>
      {#if failed}<p class="note">Пример не собрался.</p>{/if}
      <button class="again" onclick={start} aria-label="Показать пример заново" title="Показать заново"><Icon name="redo" size={13} /></button>
    </div>
  {/if}
</div>

<style>
  .example { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 8px; align-items: stretch; }
  .src { margin: 0; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--text); font: 12.5px/1.5 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
  .out { position: relative; min-width: 0; }
  .screen {
    --term-fg: #cccccc; --term-dim: #767676; --term-ok: #16c60c; --term-warn: #f9f1a5; --term-error: #e74856; --term-info: #61d6d6; --bg: #0b0d10;
    height: 100%; min-height: 70px; max-height: 170px; overflow: auto; padding: 8px 10px; background: #0b0d10; color: #cccccc; border: 1px solid var(--line-soft); border-radius: var(--radius-s);
    font: 13px/1.25 ui-monospace, "DejaVu Sans Mono", monospace; white-space: pre-wrap;
  }
  .again { position: absolute; top: 4px; right: 4px; display: grid; place-items: center; width: 24px; height: 24px; border: 0; border-radius: 6px; background: rgba(255, 255, 255, 0.06); color: #9097a3; cursor: pointer; }
  .again:hover { background: rgba(255, 255, 255, 0.14); color: #fff; }
  .again:focus-visible { outline: 2px solid var(--accent); }
  .note { margin: 0; align-self: center; color: var(--muted); font-size: 12.5px; }
  @media (max-width: 700px) { .example { grid-template-columns: 1fr; } }
</style>
