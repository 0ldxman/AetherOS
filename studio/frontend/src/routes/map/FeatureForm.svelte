<script lang="ts">
  // Свойства одной пометки сцены: поля зависят от типа. Условие по ключам собирает общий конструктор.
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import Hint from "../../lib/Hint.svelte";
  import type { Schemas } from "../../lib/api";
  import { COLOR_HEX, COLOR_NAME, TYPE_LABEL, hex, pointOf, type Feature } from "../../lib/sceneGeo";

  let { f = $bindable(), options, unknown = false, onduplicate, onremove }: {
    f: Feature;
    options: Schemas["MapSceneOptions"];
    unknown?: boolean;           // выделение не нашло провинций
    onduplicate: () => void;
    onremove: () => void;
  } = $props();

  const filled = $derived(["polygon", "circle", "region"].includes(f.type));
  const path = $derived(["line", "arrow"].includes(f.type));
  let timeOpen = $state(false);
  $effect(() => { if (f.from || f.to || f.key) timeOpen = true; });

  function setRadius(value: number) { f.radius_km = value; }
  function offset(i: 0 | 1, value: number) { const o = f.offset ?? [70, -50]; o[i] = value; f.offset = [o[0], o[1]]; }
</script>

<div class="form">
  <header>
    <b>{TYPE_LABEL[f.type]}</b>
    <span class="spacer"></span>
    <button class="btn ghost" onclick={onduplicate}>Копия</button>
    <button class="btn ghost danger" onclick={onremove}>Удалить</button>
  </header>

  {#if f.type === "region"}
    <label><span class="label">Что выделить<Hint text="Код провинции (RUS-32), код страны (POL) или её название. Провинции страны берутся по владению на дату сцены." /></span>
      <input class="field mono" class:bad={unknown} bind:value={f.token} /></label>
    {#if unknown}<p class="err">Такой провинции или страны на эту дату нет.</p>{/if}
    <label class="check"><input type="checkbox" checked={f.border === "outer"} onchange={(e) => (f.border = e.currentTarget.checked ? "outer" : undefined)} /> только внешняя граница<Hint text="Вместо границ каждой провинции рисуется одна линия вокруг всей области." /></label>
  {/if}

  {#if f.type === "text" || f.type === "callout"}
    <label><span class="label">Текст</span><textarea class="field area" rows="2" bind:value={f.text}></textarea></label>
  {:else if f.type !== "region"}
    <label><span class="label">Подпись</span><input class="field" bind:value={f.label} placeholder="необязательно" /></label>
  {/if}

  <div class="field-row">
    <span class="label">Цвет</span>
    <div class="swatches">
      {#each options.colors as name (name)}
        <button class="sw" class:on={f.color === name} style="background:{COLOR_HEX[name]}" title={COLOR_NAME[name] ?? name} aria-label={COLOR_NAME[name] ?? name} onclick={() => (f.color = name)}></button>
      {/each}
    </div>
  </div>

  {#if f.type === "marker"}
    <div class="icons">
      {#each options.icons as icon (icon.name)}
        <button class="ico" class:on={(f.icon ?? "pin") === icon.name} title={icon.label} aria-label={icon.label} onclick={() => (f.icon = icon.name === "pin" ? undefined : icon.name)}>
          <svg viewBox="0 0 24 24" width="20" height="20">
            {#if icon.name === "pin"}<path d="M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11Zm0-8.2a2.8 2.8 0 1 0 0-5.6 2.8 2.8 0 0 0 0 5.6Z" fill={hex(f.color)} />
            {:else}<path d={icon.d} fill={icon.closed || icon.solid ? hex(f.color) : "none"} fill-opacity={icon.solid ? 1 : 0.25} stroke={hex(f.color)} stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />{/if}
          </svg>
        </button>
      {/each}
    </div>
  {/if}

  {#if path}
    <div class="two">
      <label><span class="label">Толщина</span><input class="field" type="number" min="1" max="8" step="0.5" bind:value={f.width} placeholder="3" /></label>
      <label class="check low"><input type="checkbox" bind:checked={f.dash} /> пунктир</label>
    </div>
    <label class="check"><input type="checkbox" bind:checked={f.smooth} /> нарисована от руки<Hint text="Линия без вершин для правки: сглаженная, как от руки. Из панели её точки не двигаются." /></label>
  {/if}

  {#if f.type === "circle"}
    <label><span class="label">Радиус, км</span><input class="field" type="number" min="1" max="20000" value={f.radius_km ?? 100} oninput={(e) => setRadius(+e.currentTarget.value)} /></label>
  {/if}

  {#if f.type === "text"}
    <label><span class="label">Размер текста</span><input class="field" type="number" min="8" max="48" bind:value={f.size} placeholder="14" /></label>
  {/if}

  {#if f.type === "callout"}
    <div class="two">
      <label><span class="label">Сдвиг по X<Hint text="На сколько пикселей плашка отстоит от места, на которое указывает выноска." /></span><input class="field" type="number" value={f.offset?.[0] ?? 70} oninput={(e) => offset(0, +e.currentTarget.value)} /></label>
      <label><span class="label">Сдвиг по Y</span><input class="field" type="number" value={f.offset?.[1] ?? -50} oninput={(e) => offset(1, +e.currentTarget.value)} /></label>
    </div>
  {/if}

  {#if filled}
    <label class="check"><input type="checkbox" checked={f.fill !== false} onchange={(e) => (f.fill = e.currentTarget.checked)} /> заливка</label>
    {#if f.fill !== false}
      <div class="two">
        <label><span class="label">Цвет заливки</span>
          <select class="field" bind:value={f.fill_color}><option value={undefined}>как у линии</option>{#each options.colors as name (name)}<option value={name}>{COLOR_NAME[name] ?? name}</option>{/each}</select></label>
        <label><span class="label">Вид заливки<Hint text="Штриховка видна на странице карты; в редакторе заливка показана сплошной." /></span>
          <select class="field" bind:value={f.fill_style}><option value={undefined}>сплошная</option>{#each options.fill_styles.filter((s) => s !== "solid") as s (s)}<option value={s}>{s === "hatch" ? "штриховка" : s}</option>{/each}</select></label>
      </div>
    {/if}
  {/if}

  {#if f.type === "marker" || path || filled || f.type === "callout"}
    <label><span class="label">Ссылка<Hint text="Внутренний адрес: /wiki/… или путь записи вики (Technologies/First report). По клику игрок перейдёт туда." /></span>
      <input class="field" bind:value={f.url} placeholder="Technologies/First report" /></label>
  {/if}

  <details bind:open={timeOpen}>
    <summary>Когда видно и кому</summary>
    <div class="two">
      <label><span class="label">С даты<Hint text="Пометка видна на дату сцены, если дата не раньше этой. Пусто: без начала." /></span><input class="field" type="date" bind:value={f.from} /></label>
      <label><span class="label">По дату</span><input class="field" type="date" bind:value={f.to} /></label>
    </div>
    <span class="label">Условие по ключам<Hint text="Пометка не попадёт в страницу, пока у игрока нет нужных ключей. Пусто: видна всем." /></span>
    <AccessBuilder bind:value={() => f.key ?? "", (v) => (f.key = v || undefined)} />
  </details>

  {#if f.coords && f.type !== "region" && !Array.isArray(f.coords[0])}
    <p class="muted small mono">{pointOf(f)[0].toFixed(3)}, {pointOf(f)[1].toFixed(3)}</p>
  {/if}
</div>

<style>
  .form { display: flex; flex-direction: column; gap: 10px; }
  header { display: flex; align-items: center; gap: 4px; }
  .spacer { flex: 1; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-items: end; }
  .check { display: flex; align-items: center; gap: 6px; }
  .low { padding-bottom: 6px; }
  .swatches { display: flex; flex-wrap: wrap; gap: 6px; }
  .sw { width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; }
  .sw.on { border-color: #fff; box-shadow: 0 0 0 1px var(--bg) inset; }
  .icons { display: flex; flex-wrap: wrap; gap: 4px; }
  .ico { width: 30px; height: 30px; display: grid; place-items: center; border: 1px solid var(--line); border-radius: var(--radius-s); background: var(--panel-2); cursor: pointer; }
  .ico.on { border-color: var(--accent); background: var(--accent-soft); }
  .area { height: auto; padding: 6px 10px; resize: vertical; }
  .bad { border-color: var(--danger); }
  .err { color: var(--danger); margin: 0; font-size: 12px; }
  .mono { font-family: var(--mono); }
  summary { cursor: pointer; color: var(--muted); margin-bottom: 6px; }
  details { display: flex; flex-direction: column; gap: 8px; }
</style>
