<script lang="ts">
  // Кнопка «+ Шаг» на карте: новый шаг встаёт в середину того, что сейчас видно.
  import { useSvelteFlow } from "@xyflow/svelte";

  let { onadd }: { onadd: (x: number, y: number) => void } = $props();
  const flow = useSvelteFlow();
  let button: HTMLButtonElement;

  function add() {
    const box = button.closest(".svelte-flow")?.getBoundingClientRect();
    if (!box) return onadd(0, 0);
    const at = flow.screenToFlowPosition({ x: box.left + box.width / 2 - 120, y: box.top + box.height / 2 - 40 });
    onadd(Math.round(at.x), Math.round(at.y));
  }
</script>

<button class="btn" bind:this={button} onclick={add}>+ Шаг</button>
