<script lang="ts">
  // Страница сценария: вверху — состояние и действия (включить, править, сбросить), ниже три раздела:
  // «Поток» (карта этапов и ветвлений: что пройдено, где стоим, чего ждём), «Пульт» (управление, раскладку делает автор), «Журнал».
  // Прохождение одно на весь мир: игроков по отдельности здесь не отслеживают.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Icon from "../lib/Icon.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import Switch from "../lib/Switch.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { canEdit } from "../lib/me.svelte";
  import { toast } from "../lib/toast.svelte";
  import ScenarioFlow from "./scenario/Flow.svelte";
  import ScenarioJournal from "./scenario/Journal.svelte";
  import ScenarioPanel from "./scenario/Panel.svelte";

  type Page = Schemas["PnScenario"];
  let { id, tab }: { id: number; tab: string } = $props();

  const editable = canEdit("world");
  const TABS = [
    { key: "flow", label: "Поток" },
    { key: "panel", label: "Пульт" },
    { key: "journal", label: "Журнал" },
  ];
  const current = $derived(TABS.some((t) => t.key === tab) ? tab : "flow");

  let page = $state<Page | null>(null);
  let missing = $state(false);
  let failed = $state(false);
  let said = $state("");

  async function load() {
    const { data, response } = await api.GET("/studio/api/world/graphs/{graph_id}/scenario", { params: { path: { graph_id: id } } });
    missing = response?.status === 404;
    failed = !data && !missing;
    if (data) page = data;
  }

  onMount(() => {
    load();
    const tick = () => { if (!document.hidden) load(); };
    const timer = setInterval(tick, 5000);
    document.addEventListener("visibilitychange", tick);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", tick); };
  });

  const card = $derived(page?.card);
  const status = $derived(!card ? "" : !card.active ? "Выключен" : card.running ? "Идёт" : "Включён");

  async function setActive(active: boolean) {
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/active", { params: { path: { graph_id: id } }, body: { active } });
    if (error) toast(problem(error), "error");
    else said = `Сценарий ${active ? "включён" : "выключен"}`;
    await load();
  }

  async function reset() {
    if (!card) return;
    const sure = await ask(`Сбросить «${card.title}»?`, "Потоки, ветки, переменные, группы и счёт «По очереди» сотрутся, старты начнутся заново. Что сценарий уже сделал в мире (письма, экраны, теги) и журнал останутся.", "Сбросить");
    if (!sure) return;
    const { error } = await api.POST("/studio/api/world/graphs/{graph_id}/reset", { params: { path: { graph_id: id } } });
    if (error) return toast(problem(error), "error");
    toast(`«${card.title}» начат заново.`);
    said = "Сценарий начат заново";
    await load();
  }
</script>

<a class="crumb" href="#/world"><Icon name="chevron" size={14} />Сценарии</a>

{#if missing}
  <p class="pad">Такого сценария нет. <a href="#/world">К списку сценариев</a></p>
{:else if failed}
  <p class="pad">Не удалось загрузить сценарий. <button class="btn" onclick={load}>Повторить</button></p>
{:else if !page || !card}
  <p class="muted pad">Загрузка…</p>
{:else}
  <PageHead title={card.title}>
    {#snippet sub()}<span class="mono">{card.slug}</span> · {status}{#if card.errors} · <span class="bad">ошибок: {card.errors}</span>{/if}{/snippet}
    {#if editable}<Switch checked={card.active} label={card.active ? "Включён" : "Выключен"} onchange={setActive} />{/if}
    <a class="btn" href="#/graphs/{card.id}"><Icon name="pencil" size={14} />Редактировать</a>
    {#if editable}<button class="btn danger" onclick={reset}><Icon name="redo" size={14} />Сбросить</button>{/if}
  </PageHead>

  <nav class="tabs" aria-label="Разделы сценария">
    {#each TABS as t (t.key)}
      <a class="tab" class:on={current === t.key} href="#/world/scenario/{id}/{t.key}" aria-current={current === t.key ? "page" : undefined}>{t.label}</a>
    {/each}
  </nav>

  <p class="sr" aria-live="polite" role="status">{said}</p>

  {#if current === "flow"}
    <ScenarioFlow flow={page.flow} active={card.active} />
  {:else if current === "panel"}
    <ScenarioPanel {id} tiles={page.tiles} variables={page.variables} active={card.active} {editable} reload={load} />
  {:else}
    <ScenarioJournal {id} />
  {/if}
{/if}

<style>
  .crumb { display: inline-flex; align-items: center; gap: 4px; margin: 18px 32px 0; color: var(--muted); font-size: 12.5px; }
  .crumb :global(svg) { transform: rotate(90deg); }
  .crumb:hover { color: var(--text); text-decoration: none; }
  .bad { color: var(--danger); }
  .mono { font-family: var(--mono); font-size: 12px; }
  .pad { padding: 24px 32px; }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .tabs { display: flex; gap: 2px; padding: 0 32px; border-bottom: 1px solid var(--line-soft); overflow-x: auto; }
  .tab { display: inline-flex; align-items: center; padding: 10px 12px; color: var(--muted); border-bottom: 2px solid transparent; white-space: nowrap; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  @media (max-width: 720px) { .crumb { margin-left: 16px; } .tabs { padding: 0 16px; } }
</style>
