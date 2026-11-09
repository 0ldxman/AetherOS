<script lang="ts">
  import Territory from "./map/Territory.svelte";
  import Countries from "./map/Countries.svelte";
  import Provinces from "./map/Provinces.svelte";
  import Ownerships from "./map/Ownerships.svelte";
  import Labels from "./map/Labels.svelte";
  import Checks from "./map/Checks.svelte";
  import MapScenes from "./map/MapScenes.svelte";

  let { tab, id }: { tab: string; id: number | null } = $props();

  const TABS = [
    { key: "territory", label: "Территории", hint: "Карта на дату: кто чем владеет, покраска и передача провинций" },
    { key: "countries", label: "Страны", hint: "Страны, их годы жизни, цвета и подписи" },
    { key: "provinces", label: "Провинции", hint: "Таблица провинций с владельцем на дату" },
    { key: "ownerships", label: "Владения", hint: "Все записи «провинция → страна с даты»" },
    { key: "labels", label: "Подписи", hint: "Названия стран на карте" },
    { key: "scenes", label: "Сцены", hint: "Сохранённые карты с пометками" },
    { key: "checks", label: "Проверка", hint: "Что в данных карты выглядит неправильно" },
  ];
  const current = $derived(TABS.some((item) => item.key === tab) ? tab : "territory");
</script>

<div class="page">
  <nav class="tabs" aria-label="Разделы карты">
    <h1>Карта</h1>
    {#each TABS as item (item.key)}
      <a class="tab" class:on={current === item.key} href="#/map/{item.key}" title={item.hint}>{item.label}</a>
    {/each}
  </nav>
  <div class="body">
    {#if current === "territory"}<Territory />
    {:else if current === "countries"}{#key id}<Countries {id} />{/key}
    {:else if current === "provinces"}{#key id}<Provinces {id} />{/key}
    {:else if current === "ownerships"}<Ownerships />
    {:else if current === "labels"}{#key id}<Labels {id} />{/key}
    {:else if current === "scenes"}{#key id}<MapScenes {id} />{/key}
    {:else}<Checks />{/if}
  </div>
</div>

<style>
  .page { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .tabs { display: flex; align-items: center; gap: 2px; padding: 0 20px; border-bottom: 1px solid var(--line-soft); flex: none; }
  h1 { margin: 0 18px 0 0; font-size: 18px; }
  .tab { padding: 14px 12px 12px; color: var(--muted); border-bottom: 2px solid transparent; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .body { flex: 1; min-height: 0; overflow: auto; }
</style>
