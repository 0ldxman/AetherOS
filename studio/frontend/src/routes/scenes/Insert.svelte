<script lang="ts">
  // Кнопка «Вставить» со списком шагов и тегов по смыслу и кнопка «Подстановка»: шаблон встаёт на место курсора, поля заполняются по Tab.
  import { onMount } from "svelte";
  import Icon from "../../lib/Icon.svelte";
  import { GROUPS, SNIPPETS } from "../../lib/scene/catalog";

  let { params, samples, onsnippet, ontext }: {
    params: string[]; samples: Record<string, string>; onsnippet: (template: string) => void; ontext: (text: string) => void;
  } = $props();

  let open = $state<"" | "insert" | "params">("");
  let root: HTMLElement | undefined = $state();

  onMount(() => {
    const outside = (event: MouseEvent) => { if (open && !root?.contains(event.target as Node)) open = ""; };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  });
</script>

<div class="bar" bind:this={root} onkeydown={(event) => event.key === "Escape" && (open = "")} role="presentation">
  <div class="wrap">
    <button class="tool primary" aria-haspopup="menu" aria-expanded={open === "insert"} onclick={() => (open = open === "insert" ? "" : "insert")}>
      <Icon name="plus" size={14} />Вставить<Icon name="chevron" size={12} />
    </button>
    {#if open === "insert"}
      <div class="menu big" role="menu">
        {#each GROUPS as group}
          <h4>{group}</h4>
          {#each SNIPPETS.filter((item) => item.group === group) as item (item.title)}
            <button role="menuitem" onclick={() => { onsnippet(item.template); open = ""; }}>
              <span class="name">{item.title}</span><code>{item.code}</code>
            </button>
          {/each}
        {/each}
      </div>
    {/if}
  </div>
  <div class="wrap">
    <button class="tool" aria-haspopup="menu" aria-expanded={open === "params"} onclick={() => (open = open === "params" ? "" : "params")}>
      <Icon name="braces" size={14} />Подстановка<Icon name="chevron" size={12} />
    </button>
    {#if open === "params"}
      <div class="menu" role="menu">
        {#each params as name (name)}
          <button role="menuitem" onclick={() => { ontext(`{${name}}`); open = ""; }}>
            <code>{"{"}{name}{"}"}</code><span class="muted sample">{samples[name] ?? ""}</span>
          </button>
        {:else}
          <p class="muted none">У выбранного события нет подстановок.</p>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .bar { display: flex; align-items: center; gap: 8px; }
  .wrap { position: relative; }
  .tool { display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel); color: var(--text); font: inherit; font-size: 13px; cursor: pointer; }
  .tool:hover, .tool[aria-expanded="true"] { border-color: var(--line); background: var(--panel-2); }
  .tool.primary { border-color: var(--accent); }
  .tool:focus-visible, .menu button:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  .menu { position: absolute; z-index: 30; top: calc(100% + 4px); left: 0; display: flex; flex-direction: column; min-width: 220px; max-height: 420px; overflow-y: auto; padding: 4px; border: 1px solid var(--line); border-radius: var(--radius); background: var(--raise); box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35); }
  .menu.big { min-width: 320px; }
  .menu h4 { margin: 8px 8px 2px; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); }
  .menu h4:first-child { margin-top: 4px; }
  .menu button { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .menu button:hover { background: var(--accent-soft); }
  .menu code { font-family: var(--mono); font-size: 12px; color: var(--muted); }
  .sample { font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 150px; }
  .none { margin: 6px 8px; font-size: 12.5px; }
</style>
