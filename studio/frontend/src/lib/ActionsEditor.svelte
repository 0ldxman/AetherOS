<script lang="ts">
  // Редактор списка действий по словарю движка: одно место для почты, ответчиков эфира, триггеров мира и кукловода.
  // provides — что даёт место (world, user, account, session); host — свои действия места (goto, bounce у почты);
  // compose — письмо можно написать прямо здесь (почта сама создаст объект письма при сохранении).
  import { engine, type Act, type ActionSpec } from "./engine.svelte";

  let { actions = $bindable([]), provides = ["world"], host = [], steps = [], compose = false, addLabel = "+ действие" }: {
    actions: Act[]; provides?: string[]; host?: string[]; steps?: string[]; compose?: boolean; addLabel?: string;
  } = $props();

  const store = engine();
  const allowed = $derived((store.catalog?.actions ?? []).filter((a) => (a.needs === "host" ? host.includes(a.name) : provides.includes(a.needs))));
  const groups = $derived([...new Set(allowed.map((a) => a.group))]);
  const specOf = (name: string): ActionSpec | undefined => store.catalog?.actions.find((a) => a.name === name);
  const picks = (kind: string) => store.catalog?.picks[kind] ?? [];
  const uid = Math.random().toString(36).slice(2, 8);

  function set(index: number, patch: Record<string, unknown>) {
    actions = actions.map((a, i) => (i === index ? { ...a, ...patch } : a));
  }
  function change(index: number, kind: string) {
    actions = actions.map((a, i) => (i === index ? { do: kind } : a));
  }
  function add() {
    if (allowed.length) actions = [...actions, { do: allowed[0].name }];
  }
  const value = (a: Act, name: string) => (a[name] === undefined || a[name] === null ? "" : String(a[name]));
  const PICKED = ["key", "letter", "item", "section", "character", "station"];
  const LISTED = ["flag", "world_flag", "counter"];
</script>

<div class="actions">
  {#each actions as action, index (index)}
    {@const spec = specOf(action.do)}
    <div class="action">
      <div class="head">
        <select class="field kind" value={action.do} onchange={(e) => change(index, e.currentTarget.value)} aria-label="Действие">
          {#if !spec || !allowed.includes(spec)}<option value={action.do}>{spec?.label ?? action.do} (здесь недоступно)</option>{/if}
          {#each groups as group (group)}
            <optgroup label={group}>{#each allowed.filter((a) => a.group === group) as a (a.name)}<option value={a.name}>{a.label}</option>{/each}</optgroup>
          {/each}
        </select>
        <button type="button" class="x" onclick={() => (actions = actions.filter((_, i) => i !== index))} aria-label="Убрать действие" title="Убрать действие">✕</button>
      </div>
      {#if spec}
        <div class="fields">
          {#each spec.fields as f (f.name)}
            {#if f.kind === "bool"}
              <label class="check"><input type="checkbox" checked={!!action[f.name]} onchange={(e) => set(index, { [f.name]: e.currentTarget.checked })} />{f.label}</label>
            {:else if f.kind === "letter" && compose}
              <div class="wide letter">
                <select class="field" value={value(action, f.name)} aria-label={f.label}
                        onchange={(e) => set(index, { item: e.currentTarget.value || undefined, subject: "", text: "" })}>
                  <option value="">новое письмо</option>
                  {#if action.item && !picks("letter").some((o) => o.value === action.item)}<option value={String(action.item)}>{action.item}</option>{/if}
                  {#each picks("letter") as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
                </select>
                {#if !action.item}
                  <input class="field" value={value(action, "subject")} oninput={(e) => set(index, { subject: e.currentTarget.value })} placeholder="Тема" aria-label="Тема письма" />
                  <textarea class="field" rows="3" value={value(action, "text")} oninput={(e) => set(index, { text: e.currentTarget.value })}
                            placeholder="Текст письма. {'{player}'}, {'{login}'}, {'{date}'} подставятся." aria-label="Текст письма"></textarea>
                {/if}
              </div>
            {:else if PICKED.includes(f.kind)}
              <label class="cell"><span class="label">{f.label}</span>
                <select class="field" value={value(action, f.name)} aria-label={f.label}
                        onchange={(e) => set(index, { [f.name]: f.kind === "section" ? Number(e.currentTarget.value) || undefined : e.currentTarget.value || undefined })}>
                  <option value="">{f.kind === "character" ? f.placeholder || "—" : "— выбрать —"}</option>
                  {#if action[f.name] && !picks(f.kind).some((o) => o.value === value(action, f.name))}<option value={value(action, f.name)}>{action[f.name]}</option>{/if}
                  {#each picks(f.kind) as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
                </select></label>
            {:else if f.kind === "select"}
              <label class="cell"><span class="label">{f.label}</span>
                <select class="field" value={value(action, f.name) || f.options[0]?.value} onchange={(e) => set(index, { [f.name]: e.currentTarget.value })} aria-label={f.label}>
                  {#each f.options as o (o.value)}<option value={o.value}>{o.label}</option>{/each}
                </select></label>
            {:else if f.kind === "step"}
              <label class="cell"><span class="label">{f.label}</span>
                <select class="field" value={value(action, f.name)} onchange={(e) => set(index, { [f.name]: e.currentTarget.value })} aria-label={f.label}>
                  <option value="">— шаг —</option>
                  {#each steps as name (name)}<option value={name}>{name}</option>{/each}
                </select></label>
            {:else if f.kind === "number"}
              <label class="cell num"><span class="label">{f.label}</span>
                <input class="field" type="number" value={value(action, f.name)} placeholder={f.placeholder} aria-label={f.label}
                       oninput={(e) => set(index, { [f.name]: e.currentTarget.value === "" ? undefined : +e.currentTarget.value })} /></label>
            {:else if f.kind === "textarea"}
              <label class="cell wide"><span class="label">{f.label}</span>
                <textarea class="field" rows="2" value={value(action, f.name)} placeholder={f.placeholder} aria-label={f.label}
                          oninput={(e) => set(index, { [f.name]: e.currentTarget.value })}></textarea></label>
            {:else}
              <label class="cell" class:wide={f.kind === "path"}><span class="label">{f.label}</span>
                <input class="field" class:mono={LISTED.includes(f.kind) || f.kind === "path"} value={value(action, f.name)} placeholder={f.placeholder} aria-label={f.label}
                       list={LISTED.includes(f.kind) ? `act-${uid}-${f.kind}` : undefined}
                       oninput={(e) => set(index, { [f.name]: LISTED.includes(f.kind) ? e.currentTarget.value.trim() : e.currentTarget.value })} /></label>
            {/if}
          {/each}
        </div>
      {/if}
    </div>
  {/each}
  {#if allowed.length}<button type="button" class="btn ghost tiny" onclick={add}>{addLabel}</button>{/if}
  {#each LISTED as kind (kind)}<datalist id={`act-${uid}-${kind}`}>{#each picks(kind) as o (o.value)}<option value={o.value}></option>{/each}</datalist>{/each}
</div>

<style>
  .actions { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .action { display: flex; flex-direction: column; gap: 6px; padding: 8px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--bg); min-width: 0; }
  .head { display: flex; gap: 6px; align-items: center; }
  .kind { flex: 1; min-width: 0; }
  .fields { display: flex; flex-wrap: wrap; gap: 6px 8px; }
  .cell { display: flex; flex-direction: column; gap: 2px; flex: 1 1 160px; min-width: 0; }
  .cell.num { flex: 0 0 100px; }
  .wide { flex-basis: 100%; }
  .letter { display: flex; flex-direction: column; gap: 5px; }
  .label { font-size: 11px; color: var(--muted); }
  .check { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; flex-basis: 100%; }
  textarea { resize: vertical; font: inherit; }
  .mono { font-family: var(--mono); font-size: 12px; }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; padding: 0 4px; }
  .x:hover { color: var(--danger); }
  .tiny { padding: 2px 8px; font-size: 12px; align-self: flex-start; }
</style>
