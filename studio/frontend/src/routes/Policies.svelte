<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import WeekGrid from "../lib/WeekGrid.svelte";

  type Form = Schemas["PolicyIn"];

  let { id }: { id: number | null } = $props();

  let rows = $state<Schemas["PolicyRow"][]>([]);
  let policy = $state<Schemas["PolicyOut"] | null>(null);
  let form = $state<Form>(blank(""));
  let saved = $state("");
  let errors = $state<Record<string, string[]>>({});
  let week = $state<Schemas["Week"] | null>(null);
  let dialog = $state<null | "new" | "delete">(null);
  let newName = $state("");

  function blank(name: string): Form {
    return { name, description: "", mode: "all", sources: "", via: "", max_attempts: null, attempts_window: 600, lock_seconds: 300, ttl: null,
             windows: "", denied_text: "", locked_text: "", window_text: "", kick_text: "" };
  }

  const dirty = $derived(JSON.stringify(form) !== saved);
  const current = $derived(id ?? rows[0]?.id ?? null);

  async function list() {
    rows = (await api.GET("/studio/api/policies")).data ?? [];
  }

  async function load(target: number | null) {
    policy = null;
    errors = {};
    if (target === null) return;
    const { data } = await api.GET("/studio/api/policies/{policy_id}", { params: { path: { policy_id: target } } });
    if (!data) return;
    policy = data;
    const { grid: _grid, used_by: _used, id: _id, ...fields } = data;
    form = fields;
    saved = JSON.stringify(form);
  }

  onMount(list);
  $effect(() => { load(current); });

  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const text = form.windows;
    clearTimeout(timer);
    timer = setTimeout(async () => {
      week = (await api.POST("/studio/api/policies/week", { body: { windows: text } })).data ?? null;
    }, 250);
  });

  async function save() {
    if (!policy) return;
    errors = {};
    const { data, error } = await api.PUT("/studio/api/policies/{policy_id}", { params: { path: { policy_id: policy.id } }, body: form });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    toast("Политика сохранена.");
    await load(data.id);
    list();
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/policies", { body: blank(newName.trim()) });
    if (error || !data) return toast(problem(error, "Не создалась."), "error");
    dialog = null;
    newName = "";
    await list();
    go(`/policies/${data.id}`);
  }

  async function remove() {
    if (!policy) return;
    const { error } = await api.DELETE("/studio/api/policies/{policy_id}", { params: { path: { policy_id: policy.id } } });
    dialog = null;
    if (error) return toast(problem(error), "error");
    toast("Политика удалена.");
    await list();
    go("/policies");
  }

  const KIND: Record<string, string> = { system: "тип", machine: "машина", account: "учётка" };
</script>

<div class="split">
  <aside class="list">
    <h1>Политики входа</h1>
    {#each rows as row (row.id)}
      <a class="item" class:on={row.id === current} href="#/policies/{row.id}">
        <b>{row.name}</b>
        <span class="muted small">
          {[row.systems && `типов ${row.systems}`, row.machines && `машин ${row.machines}`, row.accounts && `учёток ${row.accounts}`].filter(Boolean).join(" · ") || "не назначена"}
        </span>
      </a>
    {/each}
    <button class="btn add" onclick={() => (dialog = "new")}>+ Политика</button>
  </aside>

  {#if policy}
    <section class="editor">
      <header class="top">
        <input class="title" bind:value={form.name} class:bad={errors.name} />
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить</button>
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
      </header>
      {#if errors.name}<p class="err">{errors.name.join(" ")}</p>{/if}
      <input class="field note" placeholder="Заметка для авторов (игрок её не видит)" bind:value={form.description} />

      <div class="cols">
        <div class="block">
          <h3>Кто и откуда</h3>
          <label><span class="label">Пароль и ключ</span>
            <select class="field" bind:value={form.mode}>
              <option value="all">нужны и пароль, и ключ</option>
              <option value="any">хватает пароля или ключа</option>
            </select>
          </label>
          <label><span class="label">Откуда можно (хост в строке, * заменяет любые знаки; пусто: откуда угодно)</span>
            <textarea class="field area mono" bind:value={form.sources} placeholder={"aether-*\ngw-02"}></textarea></label>
          <label><span class="label">Только через (хосты цепочки мостов)</span>
            <textarea class="field area mono" bind:value={form.via}></textarea></label>
          <h3>Ошибки и срок</h3>
          <div class="three">
            <label><span class="label">Ошибок до блока</span><input class="field" type="number" min="1" bind:value={form.max_attempts} placeholder="не блокировать" /></label>
            <label><span class="label">За, с</span><input class="field" type="number" min="1" bind:value={form.attempts_window} /></label>
            <label><span class="label">Блок на, с</span><input class="field" type="number" min="1" bind:value={form.lock_seconds} /></label>
          </div>
          <label><span class="label">Срок подключения, с</span><input class="field" type="number" min="1" bind:value={form.ttl} placeholder="без ограничения" /></label>
        </div>

        <div class="block">
          <h3>Когда</h3>
          <label><span class="label">Окна: «mon-fri: 9:00-13:00 14:00-18:00», «except sun: *», по строке на правило</span>
            <textarea class="field area mono" class:bad={errors.windows || week?.error} bind:value={form.windows} rows="4"></textarea></label>
          {#if week?.error}<p class="err">{week.error}</p>{:else if errors.windows}<p class="err">{errors.windows.join(" ")}</p>{/if}
          {#if week?.grid}<WeekGrid grid={week.grid} />{:else if !week?.error}<p class="muted small">Окон нет: входить можно в любое время.</p>{/if}

          <h3>Что видит игрок</h3>
          <label><span class="label">Отказ (не тот хост, не тот путь)</span><input class="field" bind:value={form.denied_text} placeholder="стандартный текст системы" /></label>
          <label><span class="label">Блокировка</span><input class="field" bind:value={form.locked_text} placeholder="стандартный текст системы" /></label>
          <label><span class="label">Вне окна</span><input class="field" bind:value={form.window_text} placeholder="стандартный текст системы" /></label>
          <label><span class="label">Обрыв по сроку</span><input class="field" bind:value={form.kick_text} placeholder="стандартный текст системы" /></label>
        </div>
      </div>

      <div class="block used">
        <h3>Где назначена</h3>
        {#each policy.used_by as where}
          {#if where.machine}<a href="#/machines/{where.machine}/access"><span class="chip">{KIND[where.kind]}</span> {where.label}</a>
          {:else}<span><span class="chip">{KIND[where.kind]}</span> {where.label}</span>{/if}
        {:else}
          <span class="muted">Нигде. Назначьте её машине (Обзор → Свойства) или учётке.</span>
        {/each}
      </div>
    </section>
  {:else}
    <p class="muted empty">{rows.length ? "Загрузка…" : "Политик пока нет."}</p>
  {/if}
</div>

{#if dialog === "new"}
  <Dialog title="Новая политика" confirm="Создать" onsubmit={create} onclose={() => (dialog = null)}>
    <input class="field" placeholder="название" bind:value={newName} />
  </Dialog>
{:else if dialog === "delete" && policy}
  <Dialog title="Удалить «{policy.name}»?" confirm="Удалить" danger onsubmit={remove} onclose={() => (dialog = null)}>
    <p class="muted">{policy.used_by.length ? "Она назначена: сначала снимите её с типов, машин и учёток." : "Политика нигде не назначена."}</p>
  </Dialog>
{/if}

<style>
  .split { display: grid; grid-template-columns: 260px 1fr; min-height: 100%; }
  .list { display: flex; flex-direction: column; gap: 2px; padding: 20px 8px; border-right: 1px solid var(--line-soft); }
  h1 { margin: 0 10px 12px; font-size: 18px; }
  .item { display: flex; flex-direction: column; padding: 8px 10px; border-radius: var(--radius-s); color: var(--text); }
  .item:hover { background: var(--panel); text-decoration: none; }
  .item.on { background: var(--accent-soft); }
  .small { font-size: 12px; margin: 0; }
  .add { margin: 8px 4px 0; justify-content: center; }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 10px; }
  .title { height: 36px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; font-size: 18px; font-weight: 600; outline: none; }
  .title:hover { border-color: var(--line); }
  .title:focus { border-color: var(--accent); background: var(--bg); }
  .title.bad { border-color: var(--danger); }
  .spacer { flex: 1; }
  .note { max-width: 640px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .block { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  h3 { margin: 6px 0 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3:first-child { margin-top: 0; }
  .area { height: auto; min-height: 64px; padding: 8px 10px; resize: vertical; }
  .three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .field.bad { border-color: var(--danger); }
  .err { margin: -4px 0 0; color: var(--danger); font-size: 12px; }
  .used { flex-direction: row; flex-wrap: wrap; align-items: center; gap: 12px; }
  .used h3 { margin: 0 8px 0 0; }
  .empty { padding: 24px; }
</style>
