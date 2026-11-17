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

  // Порядок: тип ноды (назначение), внутри — пространство «Машина: …», «Размещение: …»; без пространства — первыми.
  const ORDER = ["noun", "happen", "action", "flow", "data", "entity", "attr", "struct", "service"];
  const groupLabel = (name: string) => catalog.groups.find((g) => g.name === name)?.label ?? name;
  const split = (kind: Kind) => {
    const at = kind.label.indexOf(": ");
    return at > 0 ? { space: kind.label.slice(0, at), short: kind.label.slice(at + 2) } : { space: kind.subgroup ?? "", short: kind.label };
  };
  const found = $derived.by(() => {
    const q = query.trim().toLowerCase();
    const seen = new Set<string>();                  // семейство — одной строкой: первая его нода, режим выбирается на ноде
    return catalog.kinds.filter((k) => !k.hidden && (!filter || filter(k)) && (!q || `${k.label} ${k.family ?? ""} ${k.subgroup} ${groupLabel(k.group)}`.toLowerCase().includes(q)))
      .filter((k) => !k.family || (!seen.has(k.family) && !!seen.add(k.family)))
      .map((k) => (k.family ? { ...k, label: k.family } : k));      // найденный режим и добавится (поиск «случ» — «Случайно»)
  });
  type Space = { name: string; kinds: Kind[] };
  const sections = $derived.by(() => {
    const out: { group: string; title: string; spaces: Space[] }[] = [];
    for (const kind of found) {
      let section = out.find((s) => s.group === kind.group);
      if (!section) out.push((section = { group: kind.group, title: groupLabel(kind.group), spaces: [] }));
      const name = split(kind).space;
      let space = section.spaces.find((s) => s.name === name);
      if (!space) section.spaces.push((space = { name, kinds: [] }));
      space.kinds.push(kind);
    }
    const rank = (group: string) => (ORDER.indexOf(group) + ORDER.length + 1) % (ORDER.length + 1);
    out.sort((a, b) => rank(a.group) - rank(b.group));
    for (const section of out) section.spaces.sort((a, b) => (a.name ? 1 : 0) - (b.name ? 1 : 0) || a.name.localeCompare(b.name, "ru"));
    return out;
  });
  const flat = $derived(sections.flatMap((s) => s.spaces.flatMap((space) => space.kinds)));
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
  const top = $derived(Math.min(at.y, window.innerHeight - 460));
</script>

<button class="shade" aria-label="Закрыть меню" onclick={onclose}></button>
<div class="menu" style="left: {left}px; top: {top}px" role="dialog" aria-label="Добавить ноду">
  <input class="field" bind:this={input} bind:value={query} {onkeydown} placeholder="Поиск ноды…" aria-label="Поиск ноды" />
  <div class="list">
    {#each sections as section (section.group)}
      <div class="group" style="--c: {COLORS[section.group]}">{section.title}</div>
      {#each section.spaces as space (space.name)}
        {#each space.kinds as kind (kind.name)}
          <button class="kind" class:on={flat[active] === kind} style="--c: {COLORS[kind.group]}" onclick={() => pick(kind)}
                  onmouseenter={() => (active = flat.indexOf(kind))} title={kind.label}>
            {#if space.name}<span class="space">{space.name}</span>{/if}<span class="name">{split(kind).short}</span>
          </button>
        {/each}
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
  .list { max-height: 400px; overflow-y: auto; display: flex; flex-direction: column; }
  .group { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px; margin-top: 4px; padding: 5px 6px 4px; background: var(--panel);
           border-bottom: 1px solid var(--line); color: var(--text); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
  .group:first-child { margin-top: 0; }
  .group::before { content: ""; width: 3px; height: 11px; border-radius: 1px; background: var(--c); flex: none; }
  .space { flex: none; color: var(--muted); }
  .name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kind { display: flex; align-items: center; gap: 8px; padding: 5px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit;
          font-size: 13px; text-align: left; cursor: pointer; }
  .kind::before { content: ""; width: 8px; height: 8px; border-radius: 2px; background: var(--c); flex: none; }
  .kind.on { background: var(--accent-soft); }
  .none { padding: 6px; font-size: 12px; margin: 0; }
</style>
