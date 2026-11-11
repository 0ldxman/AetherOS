<script lang="ts">
  // Под экраном сцены: подстановки события, шпаргалка по языку (щелчок вставляет шаблон) и «Где играет».
  import Icon from "../../lib/Icon.svelte";
  import type { Schemas } from "../../lib/api";
  import { GROUPS, SNIPPETS } from "../../lib/scene/catalog";

  type Binding = Schemas["SceneBinding"];
  let { params, samples, bindings, onsnippet, ontext }: {
    params: string[]; samples: Record<string, string>; bindings: Binding[]; onsnippet: (template: string) => void; ontext: (text: string) => void;
  } = $props();

  let tab = $state<"help" | "params" | "used">("help");
  let query = $state("");
  const found = $derived(SNIPPETS.filter((item) => !query.trim() || `${item.title} ${item.code} ${item.doc} ${item.args}`.toLowerCase().includes(query.trim().toLowerCase())));
</script>

<section class="ref">
  <div class="tabs" role="tablist">
    <button role="tab" aria-selected={tab === "help"} class:on={tab === "help"} onclick={() => (tab = "help")}>Шпаргалка</button>
    <button role="tab" aria-selected={tab === "params"} class:on={tab === "params"} onclick={() => (tab = "params")}>Подстановки<span class="n">{params.length}</span></button>
    <button role="tab" aria-selected={tab === "used"} class:on={tab === "used"} onclick={() => (tab = "used")}>Где играет<span class="n" class:warn={!bindings.length}>{bindings.length}</span></button>
  </div>

  {#if tab === "help"}
    <label class="find"><Icon name="search" size={14} /><input placeholder="Найти шаг или тег" bind:value={query} aria-label="Поиск по шпаргалке" /></label>
    <div class="list">
      {#each GROUPS as group}
        {@const items = found.filter((item) => item.group === group)}
        {#if items.length}
          <h4>{group}</h4>
          {#each items as item (item.title)}
            <button class="row" onclick={() => onsnippet(item.template)} title="Вставить в текст">
              <span class="head"><b>{item.title}</b><code>{item.code}</code></span>
              {#if item.args}<span class="args">{item.args}</span>{/if}
              <span class="doc">{item.doc}</span>
            </button>
          {/each}
        {/if}
      {/each}
      {#if !found.length}<p class="muted none">Ничего не нашлось.</p>{/if}
    </div>
    <p class="note muted">Шаги пишутся с новой строки со знаком <code>@</code>. Части разделяются <code>|</code>, время можно задать диапазоном: <code>200-450</code>. Подробнее в «Справке», страница «Сцены».</p>
  {:else if tab === "params"}
    <div class="list">
      {#each params as name (name)}
        <button class="row line" onclick={() => ontext(`{${name}}`)} title="Вставить в текст"><code>{"{"}{name}{"}"}</code><span class="muted">{samples[name] ?? ""}</span></button>
      {:else}
        <p class="muted none">У выбранного события подстановок нет.</p>
      {/each}
    </div>
    <p class="note muted">Подставляются при показе игроку. Здесь видны условные значения. Подстановка, которой у события нет, считается ошибкой.</p>
  {:else}
    <div class="list">
      {#each bindings as item (item.system + item.slot)}
        <a class="row line" href="#/systems/{item.system}/scenes"><b>{item.system}</b><span class="muted">{item.label}</span></a>
      {:else}
        <p class="warnbox">Сцена не назначена ни одному событию, игрок её не увидит. Назначьте в «Операционные системы», вкладка «Сцены событий».</p>
      {/each}
    </div>
  {/if}
</section>

<style>
  .ref { display: flex; flex-direction: column; gap: 8px; padding: 6px 12px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); min-height: 0; }
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line-soft); }
  .tabs button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 8px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .tabs button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .n { padding: 0 6px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .n.warn { background: rgba(242, 198, 109, 0.16); color: var(--warn); }
  .find { display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--muted); }
  .find:focus-within { border-color: var(--accent); }
  .find input { flex: 1; min-width: 0; padding: 6px 0; border: 0; outline: 0; background: none; color: var(--text); font: inherit; font-size: 13px; }
  .list { display: flex; flex-direction: column; max-height: 300px; overflow-y: auto; }
  h4 { margin: 10px 4px 2px; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); }
  h4:first-child { margin-top: 2px; }
  .row { display: flex; flex-direction: column; gap: 1px; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; text-decoration: none; }
  .row:hover { background: var(--accent-soft); text-decoration: none; }
  .row:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .row.line { flex-direction: row; align-items: baseline; justify-content: space-between; gap: 12px; }
  .head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
  code { font-family: var(--mono); font-size: 12px; color: var(--muted); }
  .args { font-family: var(--mono); font-size: 11.5px; color: var(--accent); }
  .doc { font-size: 12.5px; color: var(--muted); }
  .note { margin: 0; font-size: 12px; }
  .none { margin: 8px 4px; font-size: 12.5px; }
  .warnbox { margin: 6px 4px; padding: 8px 10px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); font-size: 12.5px; }
</style>
