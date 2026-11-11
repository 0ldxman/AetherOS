<script lang="ts">
  // Полоска жизни страны на общей оси времени: от «существует с» до «существовала по» (без даты: до края оси, с размытым концом).
  // Полоса выбранного периода фильтра подсвечена на той же оси.
  let { from, to, min, max, color, band = null, tall = false }: {
    from: string; to: string | null; min: number; max: number; color: string; band?: [number, number] | null; tall?: boolean;
  } = $props();

  const span = $derived(Math.max(1, max - min));
  const pct = (value: number) => Math.min(100, Math.max(0, ((value - min) / span) * 100));
  const left = $derived(pct(Date.parse(from)));
  const right = $derived(to ? pct(Date.parse(to)) : 100);
</script>

<div class="line" class:tall aria-hidden="true">
  {#if band}<span class="band" style="left:{pct(band[0])}%; width:{Math.max(0.6, pct(band[1]) - pct(band[0]))}%"></span>{/if}
  <span class="bar" class:open={!to} style="left:{left}%; width:{Math.max(0.8, right - left)}%; --c:{color}"></span>
</div>

<style>
  .line { position: relative; height: 5px; border-radius: 3px; background: var(--raise); overflow: hidden; }
  .line.tall { height: 10px; border-radius: 5px; }
  .bar { position: absolute; top: 0; bottom: 0; border-radius: inherit; background: var(--c); }
  .bar.open { background: linear-gradient(90deg, var(--c) 70%, transparent); }
  .band { position: absolute; top: 0; bottom: 0; background: rgba(122, 162, 255, 0.35); border-left: 1px solid var(--accent); border-right: 1px solid var(--accent); }
</style>
