<script lang="ts">
  // Неделя окон входа: 7 дней × 48 получасов, закрашено то, когда войти можно. Сетку считает сервер теми же правилами, что и вход.
  let { grid, mark = null }: { grid: boolean[][]; mark?: { day: number; slot: number } | null } = $props();
  const DAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"];
</script>

<div class="week">
  <span></span>
  <div class="hours">{#each [0, 6, 12, 18] as hour}<span style:left="{(hour / 24) * 100}%">{hour}:00</span>{/each}</div>
  {#each grid as day, d}
    <span class="day">{DAYS[d]}</span>
    <div class="slots">
      {#each day as open, s}
        <span class="slot" class:open class:mark={mark?.day === d && mark?.slot === s} title="{DAYS[d]} {Math.floor(s / 2)}:{s % 2 ? '30' : '00'}"></span>
      {/each}
    </div>
  {/each}
</div>

<style>
  .week { display: grid; grid-template-columns: 26px 1fr; gap: 4px 8px; align-items: center; }
  .hours { position: relative; height: 14px; font-size: 10.5px; color: var(--faint); }
  .hours span { position: absolute; transform: translateX(-2px); }
  .day { font-size: 12px; color: var(--muted); }
  .slots { display: grid; grid-template-columns: repeat(48, 1fr); gap: 1px; height: 16px; }
  .slot { background: var(--raise); border-radius: 2px; }
  .slot:nth-child(2n) { margin-right: 0; }
  .slot.open { background: rgba(95, 208, 160, 0.55); }
  .slot.mark { outline: 2px solid var(--accent); outline-offset: 0; z-index: 1; }
</style>
