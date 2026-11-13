<script lang="ts">
  // Дерево разделов пространства: слева дерево, справа свойства выбранного раздела. Правила записи наследуются вниз от родителя.
  import { api, problem, type Schemas } from "../../lib/api";
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { canAct } from "../../lib/me.svelte";
  import { toast } from "../../lib/toast.svelte";

  type Section = Schemas["FoSection"];
  let { space, editable, onchanged }: { space: Schemas["FoSpaceOut"]; editable: boolean; onchanged: () => void } = $props();

  type Form = { id: number | null; title: string; parent: number | null; about: string; order: number; read_if: string; write: string; write_if: string; archived: boolean };
  let form = $state<Form | null>(null);
  let errors = $state<Record<string, string>>({});
  let busy = $state(false);

  // раздел и его вложенные: плоский список с отступом
  const flat = $derived.by(() => {
    const out: { s: Section; depth: number }[] = [];
    const walk = (parent: number | null, depth: number) => {
      for (const s of space.sections.filter((x) => x.parent === parent)) { out.push({ s, depth }); walk(s.id, depth + 1); }
    };
    walk(null, 0);
    return out;
  });

  const blank = (parent: number | null): Form => ({ id: null, title: "", parent, about: "", order: 0, read_if: "", write: "inherit", write_if: "", archived: false });
  const open = (s: Section) => { form = { id: s.id, title: s.title, parent: s.parent, about: s.about, order: s.order, read_if: s.read_if, write: s.write, write_if: s.write_if, archived: s.archived }; errors = {}; };

  // варианты родителя: любой раздел, кроме самого и его потомков
  function descendants(id: number): Set<number> {
    const out = new Set<number>([id]);
    for (let grew = true; grew;) { grew = false; for (const s of space.sections) if (s.parent !== null && out.has(s.parent) && !out.has(s.id)) { out.add(s.id); grew = true; } }
    return out;
  }
  const parentOptions = $derived(form?.id ? flat.filter(({ s }) => !descendants(form!.id!).has(s.id)) : flat);

  async function save() {
    if (!form) return;
    busy = true;
    const body = { title: form.title, parent: form.parent, about: form.about, order: form.order, read_if: form.read_if, write: form.write, write_if: form.write_if, archived: form.archived };
    const result = form.id === null
      ? await api.POST("/studio/api/forum/spaces/{slug}/sections", { params: { path: { slug: space.slug } }, body })
      : await api.PUT("/studio/api/forum/sections/{section_id}", { params: { path: { section_id: form.id } }, body });
    busy = false;
    if (result.error || !result.data) {
      errors = (result.error as { fields?: Record<string, string> } | undefined)?.fields ?? {};
      return toast(Object.values(errors)[0] ?? problem(result.error), "error");
    }
    errors = {};
    toast("Сохранено.");
    await onchanged();
    open(result.data);
  }

  async function remove() {
    if (!form?.id) return;
    const s = space.sections.find((x) => x.id === form!.id);
    if (!(await ask(`Удалить раздел «${s?.title ?? ""}»?`, `Вместе с вложенными разделами, темами и сообщениями (в самом разделе тем: ${s?.topics ?? 0}). Это нельзя отменить.`, "Удалить раздел"))) return;
    const { error } = await api.DELETE("/studio/api/forum/sections/{section_id}", { params: { path: { section_id: form.id } } });
    if (error) return toast(problem(error), "error");
    form = null;
    await onchanged();
  }
</script>

<div class="split">
  <aside class="tree">
    {#each flat as { s, depth } (s.id)}
      <button class="node" class:on={form?.id === s.id} style:padding-left={`${8 + depth * 14}px`} onclick={() => open(s)}>
        <span>{s.title}</span>
        <span class="muted small">{s.topics}{s.write === "authors" ? " · авторы" : ""}{s.read_if ? " · закрыт" : ""}{s.archived ? " · архив" : ""}</span>
      </button>
    {:else}
      <p class="muted small">Разделов пока нет.</p>
    {/each}
    {#if editable}
      <button class="btn" onclick={() => { form = blank(null); errors = {}; }}>+ Раздел</button>
      {#if form?.id}<button class="btn ghost" onclick={() => { form = blank(form!.id); errors = {}; }}>+ Подраздел</button>{/if}
    {/if}
  </aside>

  {#if form}
    <div class="form">
      <h3>{form.id === null ? "Новый раздел" : "Раздел"}</h3>
      <label class="row"><span class="label">Название</span><input class="field" bind:value={form.title} maxlength="120" disabled={!editable} />{#if errors.title}<span class="error small">{errors.title}</span>{/if}</label>
      <label class="row"><span class="label">Описание</span><input class="field" bind:value={form.about} maxlength="240" disabled={!editable} /></label>
      <label class="row"><span class="label">Родитель</span>
        <select class="field" bind:value={form.parent} disabled={!editable}>
          <option value={null}>— корень —</option>
          {#each parentOptions as { s, depth } (s.id)}<option value={s.id}>{" ".repeat(depth)}{s.title}</option>{/each}
        </select>{#if errors.parent}<span class="error small">{errors.parent}</span>{/if}</label>
      <div class="row"><span class="label">Дополнительное условие чтения<Hint text="Поверх условий пространства и родителей. Пусто: как у родителя." /></span>
        <AccessBuilder bind:value={form.read_if} bad={!!errors.read_if} />{#if errors.read_if}<span class="error small">{errors.read_if}</span>{/if}</div>
      <label class="row"><span class="label">Кто пишет<Hint text="«Как у родителя» берёт режим ближайшего раздела выше, а в корне пространства — режим пространства." /></span>
        <select class="field" bind:value={form.write} disabled={!editable}><option value="inherit">Как у родителя</option><option value="players">Игроки</option><option value="authors">Только авторы</option></select></label>
      <div class="row"><span class="label">Дополнительное условие записи</span>
        <AccessBuilder bind:value={form.write_if} bad={!!errors.write_if} />{#if errors.write_if}<span class="error small">{errors.write_if}</span>{/if}</div>
      <div class="inline">
        <label class="row narrow"><span class="label">Порядок</span><input class="field" type="number" bind:value={form.order} disabled={!editable} /></label>
        <label class="check"><input type="checkbox" bind:checked={form.archived} disabled={!editable} />В архиве<Hint text="Раздел пропадает из списков игрока, записи остаются." /></label>
      </div>
      {#if editable}
        <div class="tools">
          <button class="btn primary" disabled={busy || !form.title.trim()} onclick={save}>Сохранить</button>
          {#if form.id && canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить</button>{/if}
        </div>
      {/if}
    </div>
  {:else}
    <p class="muted">Выберите раздел слева или создайте новый.</p>
  {/if}
</div>

<style>
  .split { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 24px; align-items: start; }
  .tree { display: flex; flex-direction: column; gap: 2px; }
  .node { display: flex; justify-content: space-between; gap: 8px; padding: 6px 8px; border: 0; border-radius: var(--radius-s); background: none; color: var(--text); font: inherit; text-align: left; cursor: pointer; }
  .node:hover { background: var(--panel); }
  .node.on { background: var(--accent-soft); }
  .tree > .btn { margin-top: 8px; }
  .form { display: flex; flex-direction: column; gap: 14px; max-width: 600px; }
  .form h3 { margin: 0; }
  .row { display: flex; flex-direction: column; gap: 4px; margin: 0; }
  .narrow { max-width: 140px; }
  .inline { display: flex; align-items: flex-end; gap: 24px; }
  .check { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
  .small { font-size: 12px; }
  .tools { display: flex; gap: 8px; }
</style>
