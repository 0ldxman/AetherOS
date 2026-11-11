<script lang="ts">
  // Список значений плашками. Наружу строка «по значению в строке», как хранит политика. Enter, запятая или пробел добавляют, Backspace убирает последнее.
  import Icon from "./Icon.svelte";

  let { value, placeholder = "", label, onchange }: { value: string; placeholder?: string; label: string; onchange: (next: string) => void } = $props();

  let draft = $state("");
  const items = $derived(value.split("\n").map((item) => item.trim()).filter(Boolean));

  function commit(extra = "") {
    const added = `${draft}${extra}`.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
    draft = "";
    if (!added.length) return;
    onchange([...items, ...added.filter((item) => !items.includes(item))].join("\n"));
  }
  function remove(index: number) {
    onchange(items.filter((_, i) => i !== index).join("\n"));
  }
  function key(event: KeyboardEvent) {
    if (event.key === "Enter" || event.key === "," || event.key === " " || event.key === ";") {
      if (draft.trim()) { event.preventDefault(); commit(); }
      else if (event.key === "Enter") event.preventDefault();
    } else if (event.key === "Backspace" && !draft && items.length) {
      remove(items.length - 1);
    }
  }
  function paste(event: ClipboardEvent) {
    const text = event.clipboardData?.getData("text") ?? "";
    if (/[\s,;]/.test(text.trim())) { event.preventDefault(); draft = text; commit(); }
  }
</script>

<div class="chips" role="group" aria-label={label}>
  {#each items as item, index (item)}
    <span class="chip"><code>{item}</code><button type="button" onclick={() => remove(index)} aria-label="Убрать {item}"><Icon name="close" size={12} /></button></span>
  {/each}
  <input bind:value={draft} onkeydown={key} onblur={() => commit()} onpaste={paste} placeholder={items.length ? "" : placeholder} aria-label="Добавить: {label}" />
</div>

<style>
  .chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-height: 36px; padding: 4px 8px; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--bg); }
  .chips:focus-within { border-color: var(--accent); }
  .chip { display: inline-flex; align-items: center; gap: 4px; padding: 1px 4px 1px 8px; border-radius: 999px; background: var(--accent-soft); }
  .chip code { font: 12.5px var(--mono); color: var(--text); }
  .chip button { display: grid; place-items: center; width: 18px; height: 18px; padding: 0; border: 0; border-radius: 50%; background: none; color: var(--muted); cursor: pointer; }
  .chip button:hover { background: rgba(255, 255, 255, 0.1); color: var(--text); }
  .chip button:focus-visible { outline: 2px solid var(--accent); }
  input { flex: 1; min-width: 120px; padding: 4px 0; border: 0; outline: 0; background: none; color: var(--text); font: 13px var(--mono); }
  input::placeholder { color: var(--faint); font-family: var(--font); }
</style>
