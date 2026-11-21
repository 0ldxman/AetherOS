<script lang="ts">
  import { setContext, type Snippet } from "svelte";

  /** Экран внутри вкладки: его PageHead не рисует заголовок (он уже над вкладками). */
  let { children }: { children: Snippet } = $props();
  setContext("embedded", true);
</script>

{@render children()}
