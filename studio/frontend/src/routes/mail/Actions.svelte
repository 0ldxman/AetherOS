<script lang="ts">
  // Действия одного исхода варианта: общий редактор движка, плюс шаги переписки и письмо, которое пишется прямо здесь.
  import ActionsEditor from "../../lib/ActionsEditor.svelte";
  import type { Act } from "../../lib/engine.svelte";

  let { actions = $bindable([]), steps }: { actions: Act[]; steps: string[] } = $props();
</script>

<ActionsEditor bind:actions provides={["world", "user", "account", "session"]} host={["goto", "bounce"]} {steps} compose />
