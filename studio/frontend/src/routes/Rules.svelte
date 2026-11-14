<script lang="ts">
  // Правила на события (engine/rules.py): когда игрок сделал X (и выполнено условие) — действия. Кратность: один раз в мире
  // (кто первым), раз на игрока, каждый раз. Логика на сервере; здесь список, форма и кто сработал.
  import { onMount } from "svelte";
  import ActionsEditor from "../lib/ActionsEditor.svelte";
  import AccessBuilder from "../lib/AccessBuilder.svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import Hint from "../lib/Hint.svelte";
  import PageHead from "../lib/PageHead.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { summaries, type Act } from "../lib/engine.svelte";
  import { canEdit } from "../lib/me.svelte";
  import { toast } from "../lib/toast.svelte";

  type Rule = Schemas["RuRule"];
  type Form = { id: number | null; name: string; label: string; on: string; match: { key: string; value: string }[]; condition_text: string; actions: Act[]; once: string; active: boolean };

  let data = $state<Schemas["RuList"] | null>(null);
  let form = $state<Form | null>(null);
  let busy = $state(false);
  let fires = $state<{ rule: Rule; rows: Schemas["RuFire"][] } | null>(null);
  const editable = canEdit("world");

  const ONCE: Record<string, string> = { world: "один раз в мире", player: "раз на игрока", always: "каждый раз" };
  const MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
  const when = (iso: string | null | undefined) => { if (!iso) return ""; const d = new Date(iso); return `${d.getDate()} ${MONTHS[d.getMonth()]}, ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const eventLabel = (name: string) => data?.events.find((e) => e.name === name)?.label ?? name;
  const fieldsOf = (name: string) => data?.events.find((e) => e.name === name)?.fields ?? [];

  function take(next: Schemas["RuList"] | undefined, error?: unknown) {
    if (error || !next) { toast(problem(error), "error"); return false; }
    data = next;
    return true;
  }
  onMount(async () => { const { data: next } = await api.GET("/studio/api/world/rules"); if (next) data = next; });

  function edit(rule: Rule | null) {
    form = rule
      ? { id: rule.id, name: rule.name, label: rule.label, on: rule.on, match: Object.entries(rule.match).map(([key, value]) => ({ key, value })),
          condition_text: rule.condition_text, actions: (rule.actions as Act[]).map((a) => ({ ...a })), once: rule.once, active: rule.active }
      : { id: null, name: "", label: "", on: "key.got", match: [], condition_text: "", actions: [], once: "player", active: true };
  }
  async function save() {
    if (!form) return;
    busy = true;
    const body = { name: form.name, label: form.label, on: form.on, match: Object.fromEntries(form.match.filter((m) => m.key && m.value).map((m) => [m.key, m.value])),
                   condition_text: form.condition_text, actions: form.actions as Record<string, unknown>[], once: form.once, active: form.active };
    const result = form.id !== null
      ? await api.PUT("/studio/api/world/rules/{rule_id}", { params: { path: { rule_id: form.id } }, body })
      : await api.POST("/studio/api/world/rules", { body });
    busy = false;
    if (take(result.data, result.error)) { toast("Правило сохранено."); form = null; }
  }
  async function remove(rule: Rule) {
    if (!(await ask(`Удалить правило ${rule.name}?`, "Вместе с записями, кто и когда его сработал."))) return;
    const { data: next, error } = await api.DELETE("/studio/api/world/rules/{rule_id}", { params: { path: { rule_id: rule.id } } });
    take(next, error);
  }
  async function reset(rule: Rule) {
    if (!(await ask(`Сбросить ${rule.name}?`, "Правило забудет, кто его уже сработал: снова сработает для всех, «первым» станет следующий."))) return;
    const { data: next, error } = await api.POST("/studio/api/world/rules/{rule_id}/reset", { params: { path: { rule_id: rule.id } } });
    if (take(next, error)) toast(`${rule.name} сброшено.`);
  }
  async function showFires(rule: Rule) {
    const { data: rows } = await api.GET("/studio/api/world/rules/{rule_id}/fires", { params: { path: { rule_id: rule.id } } });
    fires = { rule, rows: rows ?? [] };
  }
  const matchText = (rule: Rule) => Object.entries(rule.match).map(([k, v]) => `${k} = ${v}`).join(", ");
</script>

<PageHead title="Правила">
  {#snippet sub()}Когда игрок что-то сделал (получил ключ, снял слой, написал персонажу…) и у него выполнено условие, мир отвечает действиями. «Один раз в мире» запоминает, кто был первым.{/snippet}
  {#if editable}<button class="btn primary" onclick={() => edit(null)}>+ Правило</button>{/if}
</PageHead>

{#if data}
  <div class="list">
    {#each data.rules as rule (rule.id)}
      <article class="card" class:off={!rule.active}>
        <div class="main">
          <div class="title"><b class="mono">{rule.name}</b>{#if rule.label}<span class="muted"> · {rule.label}</span>{/if}
            <span class="chip">{ONCE[rule.once]}</span>{#if !rule.active}<span class="chip">выключено</span>{/if}</div>
          <div class="line">когда <b>{eventLabel(rule.on)}</b>{#if Object.keys(rule.match).length}<span class="mono"> ({matchText(rule)})</span>{/if}
            {#if rule.condition_text} и <span class="mono">{rule.condition_text}</span>{/if}</div>
          <div class="muted small">→ {rule.actions.length ? summaries(rule.actions as Act[]) : "без действий (только отметка)"}</div>
          {#if rule.fires}
            <div class="small">сработало {rule.fires} раз{#if rule.first_player} · первым <b>{rule.first_player}</b> {when(rule.first_at)}{/if}
              · <button class="link" onclick={() => showFires(rule)}>кто</button></div>
          {/if}
        </div>
        {#if editable}
          <div class="tools">
            <button class="btn ghost small" onclick={() => edit(rule)}>Изменить</button>
            {#if rule.fires}<button class="btn ghost small" onclick={() => reset(rule)}>Сбросить</button>{/if}
            <button class="btn ghost small danger" onclick={() => remove(rule)}>Удалить</button>
          </div>
        {/if}
      </article>
    {:else}
      <p class="muted empty">Правил пока нет. Пример: «когда игрок получил ключ boreas — один раз в мире — запись в хронику “{"{player}"} first decoded BOREAS”».</p>
    {/each}
  </div>
{/if}

{#if form && data}
  <Dialog wide title={form.id !== null ? `Правило ${form.name}` : "Новое правило"} confirm="Сохранить" {busy} disabled={!form.name.trim()} onsubmit={save} onclose={() => (form = null)}>
    <div class="form">
      <div class="two">
        <label><span class="label">Имя</span><input class="field mono" bind:value={form.name} placeholder="first-boreas" /></label>
        <label><span class="label">Подпись для авторов</span><input class="field" bind:value={form.label} placeholder="кто первым собрал ключ BOREAS" /></label>
      </div>
      <div class="two">
        <label><span class="label">Когда</span>
          <select class="field" bind:value={form.on} onchange={() => (form!.match = [])}>
            {#each data.events as e (e.name)}<option value={e.name}>{e.label}</option>{/each}
          </select></label>
        <label><span class="label">Сколько раз<Hint text="«Один раз в мире» — только первый игрок (кто первым, видно в списке). «Раз на игрока» — каждому по разу. «Каждый раз» — на каждое событие." /></span>
          <select class="field" bind:value={form.once}>{#each Object.entries(ONCE) as [value, label] (value)}<option {value}>{label}</option>{/each}</select></label>
      </div>
      <div><span class="label">Подробности события<Hint text="Только такие события: поле = значение. В значении * — любые знаки, например /home/*/door.bin. Пусто: любые." /></span>
        <div class="match">
          {#each form.match as m, i (i)}
            <div class="mrow">
              <select class="field" bind:value={m.key} aria-label="Поле">{#each fieldsOf(form.on) as f (f)}<option value={f}>{f}</option>{/each}</select>
              <input class="field mono" bind:value={m.value} placeholder="значение" aria-label="Значение" />
              <button type="button" class="x" onclick={() => (form!.match = form!.match.filter((_, j) => j !== i))} aria-label="Убрать">✕</button>
            </div>
          {/each}
          {#if fieldsOf(form.on).length}<button type="button" class="btn ghost tiny" onclick={() => form!.match.push({ key: fieldsOf(form!.on)[0], value: "" })}>+ поле</button>{/if}
        </div>
      </div>
      <div><span class="label">Если у игрока<Hint text="Условие на факты игрока: ключи его учётки, flag:метка, world:метка. Пусто: всегда." /></span>
        <AccessBuilder bind:value={form.condition_text} /></div>
      <div><span class="label">Что сделать<Hint text="Действия от имени игрока: мир, его метки, его учётка (если событие было на машине). {'{player}'} в текстах — его позывной." /></span>
        <ActionsEditor bind:actions={form.actions} provides={["world", "user", "account"]} /></div>
      <label class="check"><input type="checkbox" bind:checked={form.active} /> Включено</label>
    </div>
  </Dialog>
{/if}

{#if fires}
  <Dialog title={`Кто сработал ${fires.rule.name}`} confirm="Закрыть" onsubmit={() => (fires = null)} onclose={() => (fires = null)}>
    {#if !fires.rows.length}<p class="muted">Никто.</p>{:else}
      <ul class="fires">{#each fires.rows as row, i (i)}<li><span class="muted">{when(row.at)}</span> <b>{row.player || "—"}</b></li>{/each}</ul>
    {/if}
  </Dialog>
{/if}

<style>
  .list { display: flex; flex-direction: column; gap: 8px; max-width: 1000px; margin: 12px 32px; }
  .card { display: flex; gap: 16px; justify-content: space-between; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .card.off { opacity: 0.6; }
  .main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .title { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .chip { padding: 0 6px; border-radius: 999px; background: var(--accent-soft); font-size: 11.5px; }
  .line { font-size: 13px; }
  .tools { display: flex; gap: 4px; align-items: flex-start; flex-wrap: wrap; justify-content: flex-end; }
  .small { font-size: 12px; }
  .form { display: flex; flex-direction: column; gap: 12px; }
  .form label { display: flex; flex-direction: column; gap: 4px; }
  .label { font-size: 12px; color: var(--muted); display: inline-flex; gap: 4px; align-items: center; margin-bottom: 4px; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .check { flex-direction: row !important; align-items: center; gap: 8px !important; font-size: 13px; }
  .check input { width: auto; }
  .match { display: flex; flex-direction: column; gap: 6px; }
  .mrow { display: grid; grid-template-columns: 160px minmax(0, 1fr) auto; gap: 6px; align-items: center; }
  .x { border: 0; background: none; color: var(--faint); cursor: pointer; }
  .tiny { padding: 2px 8px; font-size: 12px; align-self: flex-start; }
  .link { padding: 0; border: 0; background: none; color: var(--accent); font: inherit; cursor: pointer; }
  .fires { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 400px; overflow: auto; }
</style>
