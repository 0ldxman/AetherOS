<script lang="ts">
  // Карта при открытии показывает все шаги: один раз, когда узлы измерены (дальше вид держит автор).
  import { useNodesInitialized, useSvelteFlow } from "@xyflow/svelte";

  const ready = useNodesInitialized();
  const flow = useSvelteFlow();
  let done = false;
  $effect(() => {
    if (!ready.current || done) return;
    done = true;
    requestAnimationFrame(() => flow.fitView({ padding: 0.15, maxZoom: 1 }));
  });
</script>
