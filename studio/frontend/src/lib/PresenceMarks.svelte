<script lang="ts">
  // Где сейчас другие авторы: поле, в котором стоит его фокус, обведено его цветом с именем. Свой фокус сообщается
  // остальным (focusField) по ключу поля из подписи. CodeMirror показывает чужие курсоры сам.
  import { onMount } from "svelte";
  import { focusField, presence } from "./collab.svelte";
  import { fieldByKey, fieldKey, labelOfKey } from "./marks.svelte";

  type Box = { id: number; name: string; color: string; top: number; left: number; width: number; height: number };
  let boxes = $state<Box[]>([]);

  function place() {
    const next: Box[] = [];
    for (const peer of presence.peers) {
      if (!peer.field || !peer.field.includes("#")) continue;
      const element = fieldByKey(peer.field);
      if (!element || !element.offsetParent) continue;
      const rect = element.getBoundingClientRect();
      if (rect.width === 0) continue;
      next.push({ id: peer.id, name: peer.name, color: peer.color, top: rect.top, left: rect.left, width: rect.width, height: rect.height });
    }
    if (JSON.stringify(next) !== JSON.stringify(boxes)) boxes = next;
  }

  onMount(() => {
    const focusin = (event: FocusEvent) => {
      const target = event.target as Element | null;
      if (!target || target.closest(".cm-editor") || !target.closest("main") || !target.matches("input, select, textarea")) return;
      focusField(fieldKey(target));
    };
    const focusout = (event: FocusEvent) => {
      const target = event.target as Element | null;
      if (target && !target.closest(".cm-editor") && target.closest("main")) focusField("");
    };
    document.addEventListener("focusin", focusin);
    document.addEventListener("focusout", focusout);
    const timer = setInterval(place, 250);
    return () => {
      document.removeEventListener("focusin", focusin);
      document.removeEventListener("focusout", focusout);
      clearInterval(timer);
    };
  });
  $effect(() => { presence.peers; place(); });
</script>

<div class="marks" aria-hidden="true">
  {#each boxes as box (box.id)}
    <div class="box" style="--peer: {box.color}; top: {box.top - 3}px; left: {box.left - 3}px; width: {box.width + 6}px; height: {box.height + 6}px">
      <span class="tag">{box.name}</span>
    </div>
  {/each}
</div>

<style>
  .marks { position: fixed; inset: 0; pointer-events: none; z-index: 30; }
  .box { position: fixed; border: 2px solid var(--peer); border-radius: 7px; transition: top 0.15s, left 0.15s, width 0.15s, height 0.15s; }
  .tag { position: absolute; top: -9px; right: 6px; padding: 0 6px; border-radius: 4px; background: var(--peer); color: #111; font: 600 10.5px/16px var(--sans, system-ui); white-space: nowrap; }
  @media (prefers-reduced-motion: reduce) { .box { transition: none; } }
</style>
