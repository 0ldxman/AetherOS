<script lang="ts">
  // Свойства пространства: название, описание, привязанные машины, кто читает и кто пишет.
  import { api, problem, type Schemas } from "../../lib/api";
  import AccessBuilder from "../../lib/AccessBuilder.svelte";
  import Hint from "../../lib/Hint.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { canAct } from "../../lib/me.svelte";
  import { toast } from "../../lib/toast.svelte";

  let { space, editable, onsaved, ondeleted }: {
    space: Schemas["FoSpaceOut"]; editable: boolean; onsaved: (s: Schemas["FoSpaceOut"]) => void; ondeleted: () => void;
  } = $props();

  const pick = (s: Schemas["FoSpaceOut"]) => ({ title: s.title, about: s.about, order: s.order, read_if: s.read_if, write: s.write, write_if: s.write_if, create: s.create, create_if: s.create_if, machines: [...s.machines] });
  // экран пересоздаётся при смене пространства ({#key}), поэтому начальное значение здесь верно
  // svelte-ignore state_referenced_locally
  let form = $state(pick(space));
  // svelte-ignore state_referenced_locally
  let saved = $state(JSON.stringify(pick(space)));
  let errors = $state<Record<string, string>>({});
  let busy = $state(false);
  const dirty = $derived(JSON.stringify(form) !== saved);

  function toggle(id: number) {
    form.machines = form.machines.includes(id) ? form.machines.filter((m) => m !== id) : [...form.machines, id];
  }

  async function save() {
    busy = true;
    const { data, error } = await api.PUT("/studio/api/forum/spaces/{slug}", { params: { path: { slug: space.slug } }, body: { ...form, slug: space.slug } });
    busy = false;
    if (error || !data) {
      errors = (error as { fields?: Record<string, string> } | undefined)?.fields ?? {};
      return toast(Object.values(errors)[0] ?? problem(error), "error");
    }
    errors = {};
    saved = JSON.stringify(pick(data));
    toast("Сохранено.");
    onsaved(data);
  }

  async function remove() {
    if (!(await ask(`Удалить пространство «${space.title}»?`, "Вместе со всеми разделами, темами и сообщениями. Это нельзя отменить.", "Удалить пространство"))) return;
    const { error } = await api.DELETE("/studio/api/forum/spaces/{slug}", { params: { path: { slug: space.slug } } });
    if (error) return toast(problem(error), "error");
    ondeleted();
  }
</script>

<div class="form">
  <label class="row"><span class="label">Название</span><input class="field" bind:value={form.title} maxlength="120" disabled={!editable} />
    {#if errors.title}<span class="error small">{errors.title}</span>{/if}</label>
  <label class="row"><span class="label">Описание<Hint text="Что это за место и для чего оно существует. Игрок видит это на первой странице пространства. Разметка: **жирный**, *курсив*, `код`." /></span>
    <textarea class="field" rows="3" bind:value={form.about} disabled={!editable}></textarea></label>

  <fieldset class="row">
    <legend class="label">Машины<Hint text="Пространство видно игроку на привязанных машинах, если на их столе есть приложение «форум» (файл приложения с путём /apps/forum/)." /></legend>
    <div class="machines">
      {#each space.machine_options as m (m.id)}
        <label class="check"><input type="checkbox" checked={form.machines.includes(m.id)} onchange={() => toggle(m.id)} disabled={!editable} />{m.label} <span class="muted small">{m.hostname}</span></label>
      {/each}
    </div>
  </fieldset>

  <div class="row"><span class="label">Кто читает<Hint text="Условие по ключам и меткам мира. Пусто: все, у кого машина привязана." /></span>
    <AccessBuilder bind:value={form.read_if} bad={!!errors.read_if} />{#if errors.read_if}<span class="error small">{errors.read_if}</span>{/if}</div>

  <label class="row"><span class="label">Кто пишет<Hint text="«Игроки»: любой, кто читает и выполнил условие записи. «Только авторы»: пишут персонажи из Студии. Разделы могут переопределить." /></span>
    <select class="field" bind:value={form.write} disabled={!editable}><option value="players">Игроки</option><option value="authors">Только авторы</option></select></label>
  <div class="row"><span class="label">Условие записи<Hint text="Дополнительное условие для игроков, поверх условия чтения. Пусто: без него." /></span>
    <AccessBuilder bind:value={form.write_if} bad={!!errors.write_if} />{#if errors.write_if}<span class="error small">{errors.write_if}</span>{/if}</div>

  <label class="row"><span class="label">Кто создаёт разделы<Hint text="«Игроки»: любой, кто читает пространство, может создать раздел первых двух уровней (не больше трёх живых разделов на игрока) и становится его модератором. «Только авторы»: разделы создаёте вы." /></span>
    <select class="field" bind:value={form.create} disabled={!editable}><option value="players">Игроки</option><option value="authors">Только авторы</option></select></label>
  <div class="row"><span class="label">Условие создания<Hint text="Дополнительное условие для игроков, создающих разделы. Пусто: без него." /></span>
    <AccessBuilder bind:value={form.create_if} bad={!!errors.create_if} />{#if errors.create_if}<span class="error small">{errors.create_if}</span>{/if}</div>

  <label class="row narrow"><span class="label">Порядок в списке</span><input class="field" type="number" bind:value={form.order} disabled={!editable} /></label>

  {#if editable}
    <div class="tools">
      <button class="btn primary" disabled={!dirty || busy || !form.title.trim()} onclick={save}>Сохранить</button>
      {#if canAct("delete")}<button class="btn ghost danger" onclick={remove}>Удалить пространство</button>{/if}
    </div>
  {/if}
</div>

<style>
  .form { display: flex; flex-direction: column; gap: 14px; max-width: 640px; }
  .row { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; border: 0; }
  .narrow { max-width: 160px; }
  .machines { display: flex; flex-direction: column; gap: 4px; max-height: 200px; overflow: auto; }
  .check { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; }
  .small { font-size: 12px; }
  .tools { display: flex; gap: 8px; }
</style>
