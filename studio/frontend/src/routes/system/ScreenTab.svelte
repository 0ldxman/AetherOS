<script lang="ts">
  import { untrack } from "svelte";
  import { api, type Schemas } from "../../lib/api";
  import { ask } from "../../lib/confirm.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { SharedForm } from "../../lib/shared.svelte";

  type System = Schemas["SystemOut"];
  type Done = (data: System | undefined, error: unknown, text: string) => void;

  let { system, errors, done }: { system: System; errors: Record<string, string[]>; done: Done } = $props();

  type Blackout = Schemas["BlackoutValues"];
  let blackouts = $state<Record<string, Blackout>>({});
  let blackoutsSaved = $state("");
  let base = $state<Record<string, Blackout> | null>(null);      // сохранённое: им наполняется общий черновик
  // общий черновик чёрных экранов ОС (каждое событие общим значением)
  const share = new SharedForm({ room: () => `systems/${system.code}`, scope: () => "blackouts", draft: () => blackouts, base: () => base });
  const TONES: Record<string, string> = { "": "как у движка", success: "зелёный", warning: "жёлтый", error: "красный", dim: "серый" };
  const TONE_COLOR: Record<string, string> = { success: "var(--ok)", warning: "var(--warn)", error: "var(--danger)", dim: "var(--faint)" };

  const blackoutDirty = (event: string) => JSON.stringify(blackouts[event]) !== JSON.stringify(blackoutsSaved ? JSON.parse(blackoutsSaved)[event] : null);

  async function saveBlackout(event: string) {
    const { data, error } = await api.PUT("/studio/api/systems/{code}/blackouts/{event}", { params: { path: { code: system.code, event } }, body: blackouts[event] });
    if (data && !Object.keys(blackouts).some((other) => other !== event && blackoutDirty(other))) share.markSaved();
    done(data, error, "Чёрный экран сохранён.");
  }

  async function resetBlackout(event: string) {
    if (!(await ask("Сбросить к умолчаниям движка?", "Свои настройки этого события пропадут.", "Сбросить"))) return;
    const { data, error } = await api.DELETE("/studio/api/systems/{code}/blackouts/{event}", { params: { path: { code: system.code, event } } });
    done(data, error, "Сброшено до умолчаний движка.");
  }

  const number = (value: string) => (value === "" ? null : Math.max(0, Math.round(+value)));

  // сервер вернул ОС заново (после сохранения): берём значения оттуда
  $effect(() => {
    const rows = system.blackouts;
    untrack(() => {
      const next = Object.fromEntries(rows.map((row) => [row.event, { ...row.own }]));
      if (!share.ready) blackouts = JSON.parse(JSON.stringify(next));
      blackoutsSaved = JSON.stringify(next);
      base = next;
    });
  });

  guardUnsaved(() => !share.ready && blackoutsSaved !== "" && Object.keys(blackouts).some(blackoutDirty));
</script>

  <div class="block">
    <h3>Чёрный экран рабочего стола</h3>
    <p class="muted small">Что показывается, когда рабочий стол меняется. Пустое поле: как у движка (серым в подсказке). Подстановки:
      {#each system.blackout_params as param}<code title={param.label}>{"{"}{param.name}{"}"}</code>{" "}{/each}. Цвет окна один на всё окно. У учётки может
      быть свой текст обрыва: он важнее текста здесь.</p>
    {#each system.blackouts as row (row.event)}
      {@const own = blackouts[row.event]}
      {#if own}
        <div class="bo">
          <div class="bo-head"><b>{row.label}</b>
            <span class="spacer"></span>
            <button class="btn ghost" disabled={!blackoutDirty(row.event)} onclick={() => saveBlackout(row.event)}>Сохранить</button>
            <button class="btn ghost danger" onclick={() => resetBlackout(row.event)}>Сбросить</button>
          </div>
          <div class="bo-grid">
            <div class="col">
              <input class="field" placeholder={row.default.title} bind:value={own.title} />
              <textarea class="field mono" rows="3" spellcheck="false" placeholder={row.default.text} bind:value={own.text}></textarea>
              {#if errors.text}<p class="warn small">{errors.text.join(" ")}</p>{/if}
            </div>
            <div class="col">
              <select class="field" bind:value={own.tone}>
                {#each Object.entries(TONES) as [value, label]}<option {value}>{label}{value === "" ? ` (${TONES[row.default.tone]})` : ""}</option>{/each}
              </select>
              <div class="three">
                <label><span class="label">Пауза до окна, мс</span><input class="field" type="number" min="0" placeholder={String(row.default.delay_ms)} value={own.delay_ms ?? ""} oninput={(e) => (own.delay_ms = number(e.currentTarget.value))} /></label>
                <label><span class="label">Печать, мс/буква</span><input class="field" type="number" min="0" placeholder={String(row.default.speed_ms)} value={own.speed_ms ?? ""} oninput={(e) => (own.speed_ms = number(e.currentTarget.value))} /></label>
                <label><span class="label">Пауза после, мс</span><input class="field" type="number" min="0" placeholder={String(row.default.hold_ms)} value={own.hold_ms ?? ""} oninput={(e) => (own.hold_ms = number(e.currentTarget.value))} /></label>
              </div>
            </div>
            <div class="bo-mock" style:--tone={TONE_COLOR[own.tone || row.default.tone]}>
              <div class="bo-title">{own.title || row.default.title}</div>
              <pre class="bo-body">{own.text || row.default.text}</pre>
            </div>
          </div>
        </div>
      {/if}
    {/each}
  </div>

<style>
  .small { font-size: 12px; margin: 0; }
  .warn { color: var(--warn); margin: 0; }
  .col { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .spacer { flex: 1; }
  .three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .bo { display: flex; flex-direction: column; gap: 8px; padding: 10px 0; border-top: 1px solid var(--line-soft); }
  .bo-head { display: flex; align-items: center; gap: 8px; }
  .bo-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.9fr); gap: 12px; align-items: start; }
  .bo-mock { border: 1px solid var(--tone); background: #0b0d10; font-size: 12px; }
  .bo-title { padding: 3px 8px; background: var(--tone); color: black; }
  .bo-body { margin: 0; padding: 10px 12px; min-height: 5em; color: var(--tone); white-space: pre-wrap; font-family: inherit; }
</style>
