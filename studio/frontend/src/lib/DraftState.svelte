<script lang="ts">
  // Состояние общего черновика формы: «Не сохранено · правили: …» и «Отменить правки» (вернуть всем сохранённое).
  import { ask } from "./confirm.svelte";
  import { presence } from "./collab.svelte";

  type Share = { editors: string[]; ready: boolean; discard(): void };
  let { share, dirty, saved = "Изменений нет" }: { share: Share; dirty: boolean; saved?: string } = $props();

  async function discard() {
    const others = share.editors.filter((name) => name !== presence.me);
    const text = others.length ? `В черновике есть правки ${others.join(", ")}: они тоже пропадут.` : "Поля вернутся к сохранённому.";
    if (await ask("Отменить правки черновика?", text, "Отменить правки")) share.discard();
  }
</script>

<span class="draft">
  {#if dirty}
    <span class="dot"></span>Не сохранено{#if share.editors.length}<span class="muted">&nbsp;· правили: {share.editors.join(", ")}</span>{/if}
    {#if share.ready}<button class="link" onclick={discard} title="Вернуть сохранённое: правки черновика пропадут у всех">Отменить правки</button>{/if}
  {:else}
    <span class="muted">{saved}</span>
  {/if}
</span>

<style>
  .draft { display: inline-flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  .dot { display: inline-block; width: 7px; height: 7px; margin-right: 4px; border-radius: 50%; background: var(--warn); }
  .link { margin-left: 8px; padding: 0; border: 0; background: none; color: var(--muted); cursor: pointer; font: inherit; text-decoration: underline; text-underline-offset: 2px; }
  .link:hover { color: var(--text); }
</style>
