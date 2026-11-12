<script lang="ts">
  // Действия одного исхода варианта: список строк «что сделать» с параметрами. Письмо пишется прямо здесь (тема и текст).
  import type { Schemas } from "../../lib/api";
  import { ACTIONS, type Action } from "./doc";

  // kinds: какие действия можно выбрать (эфир: без шагов и писем); по умолчанию все
  let { actions = $bindable([]), steps, picks, kinds = null }: { actions: Action[]; steps: string[]; picks: Schemas["MlPicks"] | null; kinds?: string[] | null } = $props();
  const allowed = $derived(kinds ? ACTIONS.filter((a) => kinds.includes(a.value)) : ACTIONS);

  const letters = $derived((picks?.items ?? []).filter((i) => i.format === "msg"));
  const keys = $derived((picks?.items ?? []).filter((i) => i.format === "key"));

  function set(index: number, patch: Partial<Action>) {
    actions = actions.map((a, i) => (i === index ? { ...a, ...patch } : a));
  }
  function change(index: number, kind: string) {
    actions = actions.map((a, i) => (i === index ? { do: kind } : a));
  }
  function add() {
    actions = [...actions, allowed[0]?.value === "goto" ? { do: "goto", step: "" } : { do: allowed[0]?.value ?? "flag" }];
  }
  function remove(index: number) {
    actions = actions.filter((_, i) => i !== index);
  }
</script>

<div class="actions">
  {#each actions as action, index (index)}
    <div class="action">
      <div class="row">
        <select class="field kind" value={action.do} onchange={(e) => change(index, e.currentTarget.value)} aria-label="Действие">
          {#each allowed as a (a.value)}<option value={a.value}>{a.label}</option>{/each}
        </select>
        {#if action.do === "goto"}
          <select class="field" value={action.step ?? ""} onchange={(e) => set(index, { step: e.currentTarget.value })} aria-label="Шаг">
            <option value="">— шаг —</option>
            {#each steps as name (name)}<option value={name}>{name}</option>{/each}
          </select>
        {:else if action.do === "flag" || action.do === "unflag"}
          <input class="field" list="mail-flags" value={action.name ?? ""} oninput={(e) => set(index, { name: e.currentTarget.value.trim() })} placeholder="имя метки" aria-label="Метка" />
        {:else if action.do === "key"}
          <select class="field" value={action.slug ?? ""} onchange={(e) => set(index, { slug: e.currentTarget.value })} aria-label="Ключ">
            <option value="">— ключ —</option>
            {#if action.slug && !keys.some((k) => k.slug === action.slug)}<option value={action.slug}>{action.slug}</option>{/if}
            {#each keys as k (k.slug)}<option value={k.slug}>{k.slug}</option>{/each}
          </select>
        {/if}
        {#if action.do === "goto" || action.do === "letter"}
          <input class="field delay" type="number" min="0" value={action.delay ?? 0} oninput={(e) => set(index, { delay: Math.max(0, +e.currentTarget.value || 0) })} aria-label="Задержка, секунд" title="Задержка, секунд" />
          <span class="muted unit">с</span>
        {/if}
        <button class="x" onclick={() => remove(index)} aria-label="Убрать действие" title="Убрать действие">✕</button>
      </div>
      {#if action.do === "letter"}
        <div class="letter">
          <div class="row">
            <select class="field" value={action.item ?? ""} onchange={(e) => { const found = letters.find((l) => l.slug === e.currentTarget.value); set(index, { item: found?.slug, subject: found?.subject ?? "", text: found?.text ?? "" }); }} aria-label="Письмо">
              <option value="">новое письмо</option>
              {#if action.item && !letters.some((l) => l.slug === action.item)}<option value={action.item}>{action.item}</option>{/if}
              {#each letters as l (l.slug)}<option value={l.slug}>{l.slug}</option>{/each}
            </select>
          </div>
          <input class="field" value={action.subject ?? ""} oninput={(e) => set(index, { subject: e.currentTarget.value })} placeholder="Тема" aria-label="Тема письма" />
          <textarea class="field" rows="3" value={action.text ?? ""} oninput={(e) => set(index, { text: e.currentTarget.value })} placeholder="Текст письма. {'{player}'}, {'{login}'}, {'{date}'} подставятся." aria-label="Текст письма"></textarea>
          {#if action.item}<span class="muted small">Правка темы и текста меняет письмо «{action.item}» везде, где оно используется.</span>{/if}
        </div>
      {:else if action.do === "file"}
        <div class="row">
          <input class="field" value={action.item ?? ""} oninput={(e) => set(index, { item: e.currentTarget.value.trim() })} placeholder="слаг объекта" aria-label="Объект" />
          <input class="field" value={action.path ?? ""} oninput={(e) => set(index, { path: e.currentTarget.value.trim() })} placeholder="/home/{'{login}'}/file.txt" aria-label="Путь" />
        </div>
      {:else if action.do === "hook"}
        <textarea class="field mono" rows="2" value={action.text ?? ""} oninput={(e) => set(index, { text: e.currentTarget.value })} placeholder={'alert "Intrusion detected"\nkick'} aria-label="Хук"></textarea>
      {/if}
    </div>
  {/each}
  <button class="btn ghost tiny" onclick={add}>+ действие</button>
</div>

<style>
  .actions { display: flex; flex-direction: column; gap: 6px; }
  .action { display: flex; flex-direction: column; gap: 5px; padding: 6px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); }
  .row { display: flex; gap: 5px; align-items: center; min-width: 0; }
  .row .field { flex: 1; min-width: 0; }
  .kind { flex: 0 0 auto !important; width: 150px; }
  .delay { flex: 0 0 56px !important; width: 56px; }
  .unit { font-size: 12px; }
  .letter { display: flex; flex-direction: column; gap: 5px; }
  textarea { resize: vertical; font: inherit; }
  .mono { font-family: var(--mono); font-size: 12px; }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 0 4px; }
  .x:hover { color: var(--danger); }
  .tiny { padding: 2px 8px; font-size: 12px; align-self: flex-start; }
  .small { font-size: 11.5px; }
</style>
