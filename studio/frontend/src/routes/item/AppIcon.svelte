<script lang="ts">
  // Иконка приложения: выбор из каталога вместо текстового значка. Выбор пишется в строку «icon …» текста файла .app.
  import { onMount } from "svelte";
  import { api, type Schemas } from "../../lib/api";

  let { body = $bindable() }: { body: string } = $props();

  let catalog = $state<Schemas["AppIcons"] | null>(null);
  let style = $state("aether");
  onMount(async () => { catalog = (await api.GET("/studio/api/app-icons")).data ?? null; });

  const LINE = /^icon[ \t]+(\S+)[ \t]*$/im;
  const current = $derived((body.match(LINE)?.[1] ?? "").toLowerCase());
  const urls = $derived(catalog?.styles.find((s) => s.slug === style)?.urls ?? {});

  function pick(name: string) {
    if (LINE.test(body)) body = body.replace(LINE, `icon ${name}`);
    else if (/^glyph[ \t]+.*$/im.test(body)) body = body.replace(/^glyph[ \t]+.*$/im, `icon ${name}`);
    else body = `icon ${name}\n${body}`;
  }
</script>

{#if catalog}
  <section class="icons" aria-label="Иконка приложения">
    <header>
      <b>Иконка</b>
      <span class="muted small">{current ? catalog.icons.find((i) => i.name === current)?.title ?? `«${current}» нет в каталоге` : "не выбрана"}</span>
      <span class="spacer"></span>
      <label class="muted small">Как выглядит в стиле
        <select class="field" bind:value={style}>{#each catalog.styles as s}<option value={s.slug}>{s.label}</option>{/each}</select></label>
    </header>
    <div class="grid" role="radiogroup" aria-label="Иконки">
      {#each catalog.icons as icon (icon.name)}
        <button type="button" role="radio" aria-checked={current === icon.name} class:on={current === icon.name} title={icon.title} onclick={() => pick(icon.name)}>
          {#if urls[icon.name]}<i style="--icon:url('{urls[icon.name]}')"></i>{:else}<span class="mono ascii">{icon.ascii}</span>{/if}
          <span class="muted small">{icon.name}</span>
        </button>
      {/each}
    </div>
  </section>
{/if}

<style>
  .icons { padding: 10px 14px; border-bottom: 1px solid var(--line-soft); background: var(--panel); }
  header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
  .spacer { flex: 1; }
  .small { font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: 6px; }
  button { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 4px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); color: var(--text); cursor: pointer; }
  button:hover { background: var(--panel-2); }
  button.on { border-color: var(--accent); background: var(--accent-soft); }
  i { width: 26px; height: 26px; background: currentColor; -webkit-mask: var(--icon) center / contain no-repeat; mask: var(--icon) center / contain no-repeat; }
  .ascii { height: 26px; line-height: 26px; }
  select { width: auto; height: 26px; }
</style>
