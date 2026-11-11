<script lang="ts">
  // Экран сцены: терминал рядом с текстом. Сцена проигрывается сама после правки (переключатель «Авто»), «Заново» запускает с начала.
  import { onDestroy, onMount, untrack } from "svelte";
  import Icon from "../../lib/Icon.svelte";
  import type { Schemas } from "../../lib/api";

  type Step = Record<string, unknown>;
  type Term = { play: (steps: Step[], opts?: Record<string, unknown>) => Promise<unknown>; stop: () => void };

  let { steps, slots, slot = $bindable(""), failed = false }: {
    steps: Step[] | null; slots: Schemas["SlotInfo"][]; slot?: string; failed?: boolean;
  } = $props();

  const KEY = "studio.sceneStage";
  const SPEEDS = [{ key: "1", label: "1×", opts: { speed: 1 } }, { key: "2", label: "2×", opts: { speed: 0.5 } }, { key: "now", label: "Сразу", opts: { instant: true } }];
  function restore(): { auto: boolean; speed: string } {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) ?? "{}");
      return { auto: raw.auto !== false, speed: SPEEDS.some((item) => item.key === raw.speed) ? raw.speed : "1" };
    } catch { return { auto: true, speed: "1" }; }
  }
  const saved = restore();
  let auto = $state(saved.auto);
  let speed = $state(saved.speed);
  let screen: HTMLElement | undefined = $state();
  let term: Term | null = null;
  let running: Promise<unknown> = Promise.resolve();
  let generation = 0;
  let playing = $state(false);
  let timer: ReturnType<typeof setTimeout>;
  let lastKey = "";

  const remember = () => { try { localStorage.setItem(KEY, JSON.stringify({ auto, speed })); } catch { /* память браузера может быть закрыта */ } };

  async function start() {
    if (!screen || !steps?.length) return;
    const aether = (window as unknown as { Aether?: { console: { create: (el: HTMLElement, opts?: Record<string, unknown>) => Term } } }).Aether;
    if (!aether) return;
    term ??= aether.console.create(screen, { skipOnInput: false });
    const mine = ++generation;
    term.stop();
    await running;                                   // прежний показ дописывает последнее и останавливается
    if (mine !== generation) return;
    playing = true;
    const opts = SPEEDS.find((item) => item.key === speed)?.opts ?? {};
    running = term.play([{ op: "clear" }, ...steps], opts).finally(() => { if (mine === generation) playing = false; });
  }

  function stop() {
    generation++;
    term?.stop();
    playing = false;
  }

  // текст изменился: пауза в наборе, и сцена играет заново
  $effect(() => {
    const key = JSON.stringify(steps ?? []);
    if (steps === null) return;
    untrack(() => {
      if (key === lastKey) return;
      lastKey = key;
      if (auto) { clearTimeout(timer); timer = setTimeout(start, 450); }
    });
  });

  onMount(() => { if (auto && steps) start(); });
  onDestroy(() => { clearTimeout(timer); term?.stop(); });

  function toggleAuto() {
    auto = !auto;
    remember();
    if (auto) start();
  }
  function pick(key: string) {
    speed = key;
    remember();
    if (auto) start();
  }
</script>

<section class="stage" aria-label="Экран сцены">
  <header>
    <span class="title"><Icon name="terminal" size={15} />Экран</span>
    <button class="auto" class:on={auto} role="switch" aria-checked={auto} onclick={toggleAuto} title="Проигрывать сцену сама после правки текста">
      <span class="knob"></span>Авто
    </button>
    <span class="spacer"></span>
    {#if playing}
      <button class="btn replay" onclick={stop} title="Остановить показ"><Icon name="stop" size={14} />Стоп</button>
    {:else}
      <button class="btn replay" onclick={start} disabled={!steps?.length} title="Проиграть с начала"><Icon name="redo" size={14} />Заново</button>
    {/if}
  </header>
  <div class="slot">
    <div class="seg" role="group" aria-label="Скорость">
      {#each SPEEDS as item (item.key)}<button class:on={speed === item.key} aria-pressed={speed === item.key} onclick={() => pick(item.key)}>{item.label}</button>{/each}
    </div>
    <label><span class="muted">Событие:</span>
      <select class="field" bind:value={slot} aria-label="Событие для подстановок" title="Чьи подстановки брать в предпросмотре">
        <option value="">любое</option>
        {#each slots as item (item.slot)}<option value={item.slot}>{item.label}</option>{/each}
      </select>
    </label>
  </div>
  <div class="screen" bind:this={screen}></div>
  {#if !steps?.length}<p class="hint">{failed ? "Сцена не собралась: исправьте ошибки в тексте." : "Сцена пока пуста. Добавьте строку или шаг, и она появится здесь."}</p>{/if}
</section>

<style>
  .stage { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  header { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .title { display: inline-flex; align-items: center; gap: 6px; font-weight: 650; font-size: 13.5px; }
  .spacer { flex: 1; }
  .auto { display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px 3px 4px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .auto .knob { width: 22px; height: 12px; border-radius: 999px; background: var(--raise); position: relative; transition: background 0.15s; }
  .auto .knob::after { content: ""; position: absolute; top: 2px; left: 2px; width: 8px; height: 8px; border-radius: 50%; background: var(--muted); transition: transform 0.15s, background 0.15s; }
  .auto.on { color: var(--text); border-color: var(--accent); }
  .auto.on .knob { background: var(--accent-soft); }
  .auto.on .knob::after { transform: translateX(10px); background: var(--accent); }
  .seg { display: inline-flex; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 3px 10px; background: none; border: 0; color: var(--muted); cursor: pointer; font: inherit; font-size: 12.5px; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .replay { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; font-size: 12.5px; }
  .slot { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12.5px; }
  .slot label { display: flex; align-items: center; gap: 6px; }
  .slot select { width: 140px; min-width: 0; padding: 3px 8px; font-size: 12.5px; }
  .screen {
    --term-fg: #cccccc; --term-dim: #767676; --term-ok: #16c60c; --term-warn: #f9f1a5; --term-error: #e74856; --term-info: #61d6d6; --bg: #0b0d10;
    height: 340px; overflow: auto; padding: 10px 12px; background: #0b0d10; color: #cccccc; border: 1px solid var(--line-soft); border-radius: var(--radius-s);
    font: 14px/1.25 ui-monospace, "DejaVu Sans Mono", monospace; white-space: pre-wrap;
  }
  .hint { margin: 0; color: var(--muted); font-size: 12.5px; }
  .seg button:focus-visible, .auto:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
  @media (prefers-reduced-motion: reduce) { .auto .knob, .auto .knob::after { transition: none; } }
</style>
