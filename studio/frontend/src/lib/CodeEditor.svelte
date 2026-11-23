<script lang="ts">
  // Ленивая обёртка над CodeMirror.svelte: редактор и его языки грузятся отдельным чанком, когда поле впервые на экране.
  import type * as Y from "yjs";
  import type { Problem } from "./scene/sceneLang";

  let { value = $bindable(""), markup = false, readonly = false, onsave, shared = null, field = "", scene = null }: {
    value?: string;
    markup?: boolean;
    readonly?: boolean;
    onsave?: () => void;
    shared?: Y.Text | null;
    field?: string;
    scene?: { problems: Problem[]; params: string[] } | null;
  } = $props();

  const load = import("./CodeMirror.svelte");
  let inner: { insertSnippet(t: string): void; insertText(t: string): void; goto(n: number): void } | undefined = $state();

  export function insertSnippet(template: string) { inner?.insertSnippet(template); }
  export function insertText(text: string) { inner?.insertText(text); }
  export function goto(number: number) { inner?.goto(number); }
</script>

{#await load}
  <div class="loading" aria-busy="true">Загрузка редактора…</div>
{:then loaded}
  <loaded.default bind:this={inner} bind:value {markup} {readonly} {onsave} {shared} {field} {scene} />
{:catch}
  <textarea class="fallback" bind:value {readonly} aria-label={field || "Текст"}></textarea>
{/await}

<style>
  .loading { min-height: 120px; padding: 12px; color: var(--muted); font-size: 12.5px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .fallback { width: 100%; min-height: 200px; font: 13px/1.5 var(--mono, monospace); }
</style>
