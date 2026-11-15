<script lang="ts">
  // Вкладка «Вход» машины: граф попытки входа (тот же, что открывается из ноды «Машина: Попытка входа» в сценариях).
  import { onMount } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import Editor from "../graph/Editor.svelte";

  let { machine }: { machine: Schemas["Overview"] } = $props();
  let id = $state<number | null>(null);
  let failed = $state(false);

  onMount(async () => {
    const { data } = await api.GET("/studio/api/world/graphs/owned", { params: { query: { kind: "machine", key: machine.hostname, create: true } } });
    if (data?.id) id = data.id;
    else failed = true;
  });
</script>

{#if id}
  <div class="login"><Editor {id} embedded /></div>
{:else if failed}
  <p class="muted pad">У машины нет хоста: графу входа не к чему привязаться.</p>
{:else}
  <p class="muted pad">Загрузка…</p>
{/if}

<style>
  .login { height: 100%; min-height: 560px; display: flex; flex-direction: column; }
  .pad { padding: 24px; }
</style>
