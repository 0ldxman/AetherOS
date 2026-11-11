<script lang="ts">
  // Число секунд в удобных единицах: «5 мин» вместо 300. Значение наружу всегда в секундах.
  import { untrack } from "svelte";

  let { value, label, onchange }: { value: number; label: string; onchange: (seconds: number) => void } = $props();

  const UNITS = [{ key: "с", mult: 1 }, { key: "мин", mult: 60 }, { key: "ч", mult: 3600 }];
  const pick = (seconds: number) => [...UNITS].reverse().find((unit) => seconds >= unit.mult && seconds % unit.mult === 0) ?? UNITS[0];

  let unit = $state(untrack(() => pick(value)));
  let amount = $state(untrack(() => value / pick(value).mult));

  // значение пришло снаружи (другой автор, откат): пересчитать, пока оно не совпадает с введённым
  $effect(() => {
    const seconds = value;
    untrack(() => {
      if (Math.round(amount * unit.mult) !== seconds) { unit = pick(seconds); amount = seconds / unit.mult; }
    });
  });

  function set(next: number, mult: number) {
    amount = next;
    onchange(Math.max(1, Math.round(next * mult)));
  }
</script>

<span class="dur">
  <input class="field" type="number" min="1" step="any" value={amount} aria-label={label} oninput={(event) => set(+event.currentTarget.value || 0, unit.mult)} />
  <select class="field" aria-label="Единицы: {label}" value={unit.key} onchange={(event) => { unit = UNITS.find((u) => u.key === event.currentTarget.value)!; set(amount, unit.mult); }}>
    {#each UNITS as u (u.key)}<option value={u.key}>{u.key}</option>{/each}
  </select>
</span>

<style>
  .dur { display: inline-flex; gap: 4px; vertical-align: middle; }
  input { width: 60px; height: 30px; padding: 2px 8px; }
  select { width: auto; height: 30px; padding: 2px 6px; }
</style>
