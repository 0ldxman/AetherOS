<script lang="ts">
  import Embed from "../lib/Embed.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import Links from "./Links.svelte";
  import Time from "./Time.svelte";
  import WorldScenarios from "./WorldScenarios.svelte";
  import WorldState from "./WorldState.svelte";

  // Мир: сценарии (пульт и вход в редактор), игровое время, переменные мира и связи между ключами
  let { tab }: { tab: string } = $props();

  const TABS = [
    { key: "scenarios", label: "Сценарии" },
    { key: "time", label: "Время" },
    { key: "state", label: "Переменные" },
    { key: "links", label: "Связи" },
  ];
  const current = $derived(TABS.some((t) => t.key === tab) ? tab : "scenarios");
</script>

<PageHead title="Мир" />

<nav class="tabs" aria-label="Разделы мира">
  {#each TABS as t (t.key)}
    <a class="tab" class:on={current === t.key} href={t.key === "scenarios" ? "#/world" : `#/world/${t.key}`} aria-current={current === t.key ? "page" : undefined}>{t.label}</a>
  {/each}
</nav>

<Embed>
  {#key current}
    {#if current === "scenarios"}<WorldScenarios />
    {:else if current === "time"}<Time />
    {:else if current === "state"}<WorldState />
    {:else}<Links />{/if}
  {/key}
</Embed>

<style>
  .tabs { display: flex; gap: 2px; padding: 0 32px; border-bottom: 1px solid var(--line-soft); overflow-x: auto; }
  .tab { display: inline-flex; align-items: center; padding: 10px 12px; color: var(--muted); border-bottom: 2px solid transparent; white-space: nowrap; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
</style>
