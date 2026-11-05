<script lang="ts">
  import Dialog from "./Dialog.svelte";
  import { pending, settle } from "./confirm.svelte";
</script>

{#if pending.current}
  <Dialog title={pending.current.title} confirm={pending.current.confirm} danger onsubmit={() => settle(true)} onclose={() => settle(false)}>
    {#if pending.current.text}<p class="muted">{pending.current.text}</p>{/if}
  </Dialog>
{/if}
