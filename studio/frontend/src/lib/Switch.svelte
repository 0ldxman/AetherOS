<script lang="ts">
  // Выключатель с подписью: «включено» значит, что у поля есть значение, «выключено» что поле пустое.
  let { checked, label, onchange }: { checked: boolean; label: string; onchange: (next: boolean) => void } = $props();
</script>

<label class="switch">
  <input type="checkbox" role="switch" {checked} onchange={(event) => onchange(event.currentTarget.checked)} />
  <span class="track" aria-hidden="true"></span>
  <span class="text">{label}</span>
</label>

<style>
  .switch { display: inline-flex; align-items: center; gap: 10px; cursor: pointer; font-size: 13.5px; }
  input { position: absolute; opacity: 0; width: 0; height: 0; }
  .track { flex: none; position: relative; width: 30px; height: 17px; border-radius: 999px; background: var(--raise); border: 1px solid var(--line); transition: background 0.15s; }
  .track::after { content: ""; position: absolute; top: 2px; left: 2px; width: 11px; height: 11px; border-radius: 50%; background: var(--muted); transition: transform 0.15s, background 0.15s; }
  input:checked + .track { background: var(--accent-soft); border-color: var(--accent); }
  input:checked + .track::after { transform: translateX(13px); background: var(--accent); }
  input:focus-visible + .track { outline: 2px solid var(--accent); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) { .track, .track::after { transition: none; } }
</style>
