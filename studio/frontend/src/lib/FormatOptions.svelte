<script lang="ts">
  import type { Schemas } from "./api";

  /** Варианты для <select> формата: сначала форматы с разметкой (для статей и документов), ниже остальные. */
  let { formats, codeOnly = false }: { formats: Schemas["Format"][]; codeOnly?: boolean } = $props();

  const label = (found: Schemas["Format"]) => (codeOnly || !found.title ? found.name : `${found.name} — ${found.title}`);
  const marked = $derived(formats.filter((found) => found.markup));
  const plain = $derived(formats.filter((found) => !found.markup));
</script>

{#if marked.length}
  <optgroup label="✎ С разметкой: подходят для статей и документов">
    {#each marked as found}<option value={found.name}>{label(found)}</option>{/each}
  </optgroup>
  <optgroup label="Остальные">
    {#each plain as found}<option value={found.name}>{label(found)}</option>{/each}
  </optgroup>
{:else}
  {#each formats as found}<option value={found.name}>{label(found)}</option>{/each}
{/if}
