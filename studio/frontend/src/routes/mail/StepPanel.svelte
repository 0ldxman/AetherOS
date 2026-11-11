<script lang="ts">
  // Шаг переписки в боковой панели: имя, «начало переписки», письмо персонажа и варианты ответа игрока.
  import type { Schemas } from "../../lib/api";
  import VariantEditor from "./VariantEditor.svelte";
  import { emptyVariant, type StepDraft } from "./doc";

  let { step, steps, picks, problems, onchange, onrename, onremove }: {
    step: StepDraft; steps: string[]; picks: Schemas["MlPicks"] | null; problems: Schemas["MlProblem"][];
    onchange: (next: StepDraft) => void; onrename: (from: string, to: string) => void; onremove: () => void;
  } = $props();

  const set = (patch: Partial<StepDraft>) => onchange({ ...step, ...patch });
  const letters = $derived((picks?.items ?? []).filter((i) => i.format === "msg"));
  let opened = $state<Record<string, boolean>>({});
  let nameAtFocus = "";

  function addVariant() {
    const variant = emptyVariant();
    opened = { ...opened, [variant.key]: true };
    set({ variants: [...step.variants, variant] });
  }
  function move(index: number, by: number) {
    const variants = [...step.variants];
    const [moved] = variants.splice(index, 1);
    variants.splice(index + by, 0, moved);
    set({ variants });
  }
  function pickLetter(slug: string) {
    const found = letters.find((l) => l.slug === slug);
    set({ letter: { item: found?.slug ?? null, subject: found?.subject ?? step.letter.subject, text: found?.text ?? step.letter.text } });
  }
</script>

<div class="panel">
  <div class="row">
    <label class="grow"><span class="label">Имя шага</span>
      <input class="field mono" value={step.name} onfocus={() => (nameAtFocus = step.name)}
             oninput={(e) => set({ name: e.currentTarget.value.replace(/\s+/g, "-") })}
             onchange={(e) => { if (nameAtFocus && nameAtFocus !== e.currentTarget.value) onrename(nameAtFocus, e.currentTarget.value); nameAtFocus = e.currentTarget.value; }} /></label>
    <button class="btn ghost danger" onclick={onremove}>Удалить шаг</button>
  </div>
  <label class="check"><input type="checkbox" checked={step.opening} onchange={(e) => set({ opening: e.currentTarget.checked })} />
    <span>Начало переписки <span class="muted">· варианты видны игроку, который сам пишет персонажу</span></span></label>

  {#each problems as p, i (i)}
    <p class="problem" class:error={p.level === "error"}>{p.text}</p>
  {/each}

  <section>
    <h3>Письмо персонажа</h3>
    <div class="row">
      <select class="field grow" value={step.letter.item ?? ""} onchange={(e) => pickLetter(e.currentTarget.value)} aria-label="Письмо">
        <option value="">{step.letter.subject || step.letter.text ? "новое письмо" : "без письма"}</option>
        {#if step.letter.item && !letters.some((l) => l.slug === step.letter.item)}<option value={step.letter.item}>{step.letter.item}</option>{/if}
        {#each letters as l (l.slug)}<option value={l.slug}>{l.slug} · {l.subject}</option>{/each}
      </select>
      <label class="inline"><input class="field num" type="number" min="0" value={step.letter_delay} oninput={(e) => set({ letter_delay: Math.max(0, +e.currentTarget.value || 0) })} aria-label="Задержка письма, секунд" /><span class="muted">с</span></label>
    </div>
    <input class="field" value={step.letter.subject} oninput={(e) => set({ letter: { ...step.letter, subject: e.currentTarget.value } })} placeholder="Тема" aria-label="Тема письма" />
    <textarea class="field" rows="4" value={step.letter.text} oninput={(e) => set({ letter: { ...step.letter, text: e.currentTarget.value } })}
              placeholder="Письмо приходит, когда игрок попадает на шаг. Пусто: шаг без письма." aria-label="Текст письма"></textarea>
    {#if step.letter.item}<span class="muted small">Письмо «{step.letter.item}»: правка меняет его везде, где оно используется.</span>{/if}
  </section>

  <section>
    <h3>Варианты ответа игрока</h3>
    {#each step.variants as variant, index (variant.key)}
      <VariantEditor {variant} {steps} {picks} {index} count={step.variants.length}
                     bind:open={() => !!opened[variant.key], (v) => (opened = { ...opened, [variant.key]: v })}
                     onchange={(next) => set({ variants: step.variants.map((v, i) => (i === index ? next : v)) })}
                     onremove={() => set({ variants: step.variants.filter((_, i) => i !== index) })}
                     onmove={(by) => move(index, by)} />
    {:else}
      <p class="muted small">Вариантов нет: игрок прочтёт письмо, но ответить ему нечем.</p>
    {/each}
    <button class="btn ghost tiny" onclick={addVariant}>+ вариант</button>
  </section>
</div>

<style>
  .panel { display: flex; flex-direction: column; gap: 12px; }
  .row { display: flex; gap: 8px; align-items: flex-end; }
  .grow { flex: 1; min-width: 0; }
  label { display: flex; flex-direction: column; gap: 4px; }
  label.inline { flex-direction: row; align-items: center; gap: 4px; }
  .check { flex-direction: row; align-items: center; gap: 8px; font-size: 13px; }
  .num { width: 64px; }
  .mono { font-family: var(--mono); }
  textarea { resize: vertical; font: inherit; }
  section { display: flex; flex-direction: column; gap: 6px; padding-top: 10px; border-top: 1px solid var(--line-soft); }
  h3 { margin: 0; font-size: 13px; color: var(--muted); font-weight: 600; }
  .small { font-size: 12px; margin: 0; }
  .tiny { padding: 3px 10px; font-size: 12.5px; align-self: flex-start; }
  .problem { margin: 0; padding: 6px 10px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); font-size: 12.5px; }
  .problem.error { background: var(--danger-soft); color: var(--danger); }
</style>
