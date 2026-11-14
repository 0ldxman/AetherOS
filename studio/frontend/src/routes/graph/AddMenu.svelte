<script lang="ts">
  // Меню «Добавить ноду» (Shift+A, как в Blender): поиск по названию и группе, стрелки и Enter, Esc закрывает.
  import { useSvelteFlow } from "@xyflow/svelte";
  import { COLORS, type Catalog, type Kind } from "./kinds";

  let { at, catalog, filter = null, onpick, onclose }: {
    at: { x: number; y: number }; catalog: Catalog; filter?: ((kind: Kind) => boolean) | null;
    onpick: (kind: Kind, position: { x: number; y: number }) => void; onclose: () => void;
  } = $props();

  const flow = useSvelteFlow();
  let query = $state("");
  let active = $state(0);
  let input: HTMLInputElement | undefined = $state();
  $effect(() => { input?.focus(); });

  const groupLabel = (name: string) => catalog.groups.find((g) => g.name === name)?.label ?? name;
  const found = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return catalog.kinds.filter((k) => !k.hidden && (!filter || filter(k)) && (!q || `${k.label} ${k.subgroup} ${groupLabel(k.group)}`.toLowerCase().includes(q)));
  });
  const sections = $derived.by(() => {
    const out: { title: string; kinds: Kind[] }[] = [];
    for (const kind of found) {
      const title = kind.subgroup ? `${groupLabel(kind.group)} · ${kind.subgroup}` : groupLabel(kind.group);
      let section = out.find((s) => s.title === title);
      if (!section) out.push((section = { title, kinds: [] }));
      section.kinds.push(kind);
    }
    return out;
  });
  const flat = $derived(sections.flatMap((s) => s.kinds));
  $effect(() => { query; active = 0; });

  function pick(kind: Kind) {
    onpick(kind, flow.screenToFlowPosition({ x: at.x, y: at.y }));
  }
  function onkeydown(event: KeyboardEvent) {
    if (event.key === "Escape") { event.preventDefault(); onclose(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); active = Math.min(active + 1, flat.length - 1); }
    else if (event.key === "ArrowUp") { event.preventDefault(); active = Math.max(active - 1, 0); }
    else if (event.key === "Enter" && flat[active]) { event.preventDefault(); pick(flat[active]); }
  }
  const left = $derived(Math.min(at.x, window.innerWidth - 300));
  const top = $derived(Math.min(at.y, window.innerHeight - 420));
</script>

<button class="shade" aria-label="Закрыть меню" onclick={onclose}></button>
<div class="menu" style="left: {left}px; top: {top}px" role="dialog" aria-label="Добавить ноду">
  <input class="field" bind:this={input} bind:value={query} {onkeydown} placeholder="Поиск ноды…" aria-label="Поиск ноды" />
  <div class="list">
    {#each sections as section (section.title)}
      <div class="group">{section.title}</div>
      {#each section.kinds as kind (kind.name)}
        <button class="kind" class:on={flat[active] === kind} style="--c: {COLORS[kind.group]}" onclick={() => pick(kind)}
                onmouseenter={() => (active = flat.indexOf(kind))}>{kind.label}</button>
      {/each}
    {:else}
      <p class="muted none">Ничего не нашлось.</p>
    {/each}
  </div>
</div>

<style>
  .shade { position: fixed; inset: 0; z-index: 40; border: 0; background: transparent; cursor: default; }
  .menu { position: fixed; z-index: 41; width: 280px; display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--line); border-radius: var(--radius);
          background: var(--panel); box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5); }
  .list { max-height: 360px; overflow-y: auto; display: flex; flex-direction: column; }
  .group { padding: 6px 6px 2px; color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
  .kind { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit;
          font-size: 13px; text-align: left; cursor: pointer; }
  .kind::before { content: ""; width: 8px; height: 8px; border-radius: 2px; background: var(--c); flex: none; }
  .kind.on { background: var(--accent-soft); }
  .none { padding: 6px; font-size: 12px; margin: 0; }
</style>
