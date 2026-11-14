<script lang="ts">
  // Рамка: подпись и прямоугольник позади нод; размер тянется за угол. Заметка: текст на холсте. Обе не исполняются.
  import { NodeResizer } from "@xyflow/svelte";

  let { data, selected }: { data: { title: string; note: boolean; onresize: (w: number, h: number) => void }; selected?: boolean } = $props();
</script>

{#if data.note}
  <div class="note" class:selected>{data.title || "Заметка"}</div>
{:else}
  <NodeResizer minWidth={160} minHeight={100} isVisible={selected} lineStyle="border-color: var(--accent)" onResizeEnd={(_, p) => data.onresize(p.width, p.height)} />
  <div class="frame" class:selected><span>{data.title || "Рамка"}</span></div>
{/if}

<style>
  .frame { width: 100%; height: 100%; border: 1px dashed #3a3f4b; border-radius: var(--radius); background: rgba(122, 162, 255, 0.04); }
  .frame.selected { border-color: var(--accent); }
  .frame span { display: block; padding: 6px 10px; color: var(--muted); font-size: 13px; font-weight: 600; }
  .note { max-width: 260px; padding: 8px 10px; border-radius: var(--radius-s); background: #2b2a1f; color: #e8dfb5; font-size: 12px; white-space: pre-wrap; box-shadow: 0 3px 10px rgba(0, 0, 0, 0.3); }
  .note.selected { outline: 1px solid var(--accent); }
</style>
