<script lang="ts">
  // Неделя окон входа, которую рисуют мышью: нажать и вести закрашивает (или стирает, если начали с закрашенной клетки), Shift стирает.
  // Щелчок по названию дня открывает или закрывает день целиком. Клетка это полчаса.
  import { untrack } from "svelte";
  import { DAY_NAMES, cloneGrid, openHours, type Grid } from "./policy";

  let { grid, onchange }: { grid: Grid; onchange: (next: Grid) => void } = $props();

  let cells = $state<Grid>(untrack(() => cloneGrid(grid)));
  let drag = $state<{ value: boolean } | null>(null);
  let last: [number, number] | null = null;                 // последняя закрашенная клетка: быстрый ход мыши пропускает клетки, их дорисовываем

  $effect(() => {
    const next = grid;
    untrack(() => { if (!drag) cells = cloneGrid(next); });
  });

  function hit(event: PointerEvent): [number, number] | null {
    const node = document.elementFromPoint(event.clientX, event.clientY) as HTMLElement | null;
    if (!node?.dataset || node.dataset.d === undefined) return null;
    return [+node.dataset.d, +node.dataset.s!];
  }
  function down(event: PointerEvent) {
    const at = hit(event);
    if (!at || event.button !== 0) return;
    const value = event.shiftKey ? false : !cells[at[0]][at[1]];
    drag = { value };
    last = at;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    cells[at[0]][at[1]] = value;
    event.preventDefault();
  }
  function move(event: PointerEvent) {
    if (!drag) return;
    const at = hit(event);
    if (!at) return;
    const from = last ?? at;
    const steps = Math.max(Math.abs(at[0] - from[0]), Math.abs(at[1] - from[1]), 1);
    for (let i = 1; i <= steps; i++) {
      const d = Math.round(from[0] + ((at[0] - from[0]) * i) / steps);
      const s = Math.round(from[1] + ((at[1] - from[1]) * i) / steps);
      if (cells[d][s] !== drag.value) cells[d][s] = drag.value;
    }
    last = at;
  }
  function up() {
    if (!drag) return;
    drag = null;
    last = null;
    onchange(cloneGrid(cells));
  }
  function toggleDay(day: number) {
    const next = cloneGrid(cells);
    const open = !next[day].every(Boolean);
    next[day] = next[day].map(() => open);
    cells = next;
    onchange(cloneGrid(next));
  }
  const clock = (slot: number) => `${Math.floor(slot / 2)}:${slot % 2 ? "30" : "00"}`;
</script>

<div class="week">
  <span></span>
  <div class="hours" aria-hidden="true">{#each [0, 6, 12, 18, 24] as hour}<span style:left="{(hour / 24) * 100}%">{hour}</span>{/each}</div>
  {#each cells as day, d}
    <button class="day" onclick={() => toggleDay(d)} title="{DAY_NAMES[d]}: открыть или закрыть день целиком">{DAY_NAMES[d]}</button>
    <div class="slots" role="group" aria-label="{DAY_NAMES[d]}, окна входа" onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
      {#each day as open, s}
        <span class="slot" class:open class:hour={s % 2 === 0} data-d={d} data-s={s} title="{DAY_NAMES[d]} {clock(s)}–{clock(s + 1)}"></span>
      {/each}
    </div>
  {/each}
</div>
<p class="sum muted">Открыто {openHours(cells)} ч в неделю из 168. Рисуйте мышью, Shift стирает, щелчок по дню открывает или закрывает его целиком.</p>

<style>
  .week { display: grid; grid-template-columns: 30px 1fr; gap: 4px 8px; align-items: center; user-select: none; }
  .hours { position: relative; height: 14px; font-size: 10.5px; color: var(--faint); }
  .hours span { position: absolute; transform: translateX(-50%); }
  .hours span:first-child { transform: none; }
  .hours span:last-child { transform: translateX(-100%); }
  .day { padding: 0; border: 0; background: none; color: var(--muted); font: inherit; font-size: 12px; text-align: left; cursor: pointer; }
  .day:hover { color: var(--text); }
  .day:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
  .slots { display: grid; grid-template-columns: repeat(48, 1fr); gap: 1px; height: 24px; cursor: crosshair; touch-action: none; }
  .slot { background: var(--raise); border-radius: 2px; }
  .slot.open { background: rgba(95, 208, 160, 0.6); }
  .slot:hover { outline: 1px solid var(--accent); outline-offset: -1px; }
  .sum { margin: 8px 0 0; font-size: 12px; }
</style>
