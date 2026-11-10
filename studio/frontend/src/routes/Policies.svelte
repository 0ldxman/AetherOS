<script lang="ts">
  import ListDetail from "../lib/ListDetail.svelte";
  import Hint from "../lib/Hint.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { onMount } from "svelte";
  import DraftState from "../lib/DraftState.svelte";
  import { SharedForm } from "../lib/shared.svelte";
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
  let base = $state<Form | null>(null);                    // сохранённое: им наполняется общий черновик
  let errors = $state<Record<string, string[]>>({});
  let week = $state<Schemas["Week"] | null>(null);
  let dialog = $state<null | "new" | "delete">(null);
  let newName = $state("");

  function blank(name: string): Form {
    return { name, description: "", mode: "all", sources: "", via: "", max_attempts: null, attempts_window: 600, lock_seconds: 300, ttl: null,
             windows: "", denied_text: "", locked_text: "", window_text: "", kick_text: "" };
  }

  const dirty = $derived(JSON.stringify(form) !== saved);
  guardUnsaved(() => saved !== "" && dirty && !share.ready);   // пока ничего не загружено, правок нет; черновик на сервере
  const current = $derived(id ?? rows[0]?.id ?? null);

  async function list() {
    rows = (await api.GET("/studio/api/policies")).data ?? [];
  }

  async function load(target: number | null) {
    policy = null;
    base = null;
    errors = {};
    if (target === null) return;
    const { data } = await api.GET("/studio/api/policies/{policy_id}", { params: { path: { policy_id: target } } });
    if (!data) return;
    policy = data;
    const { grid: _grid, used_by: _used, id: _id, ...fields } = data;
    form = fields;
    saved = JSON.stringify(form);
    base = JSON.parse(saved);
  }

  // общий черновик политики; кто-то сохранил: перечитать сохранённое, черновик не трогается
  const share = new SharedForm({
    room: () => `policies/${current}`,
    texts: ["description", "sources", "via", "windows", "denied_text", "locked_text", "window_text", "kick_text"],
    draft: () => form,
    base: () => base,
    onRemoteSave: async () => {
      if (current === null) return;
      const { data } = await api.GET("/studio/api/policies/{policy_id}", { params: { path: { policy_id: current } } });
      if (!data) return;
      policy = data;
      const { grid: _grid, used_by: _used, id: _id, ...fields } = data;
      saved = JSON.stringify(fields);
      base = JSON.parse(saved);
      list();
    },
  });

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
    share.markSaved();
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

  const KIND: Record<string, string> = { system: "ОС", machine: "машина", account: "учётка" };
</script>

<ListDetail title="Политики входа">
  {#snippet list()}
    {#each rows as row (row.id)}
      <a class="item" class:on={row.id === current} href="#/policies/{row.id}">
        <b>{row.name}</b>
        <span class="muted small">
          {[row.systems && `ОС ${row.systems}`, row.machines && `машин ${row.machines}`, row.accounts && `учёток ${row.accounts}`].filter(Boolean).join(" · ") || "не назначена"}
        </span>
      </a>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn add" onclick={() => (dialog = "new")}>+ Политика</button>
  {/snippet}

  {#if policy}
    <section class="editor">
      <header class="top">
        <input class="title" bind:value={form.name} class:bad={errors.name} />
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить</button>
        <DraftState {share} {dirty} saved="" />
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
          <label><span class="label">Откуда можно<Hint text="Какие хосты вправе подключаться, по одному в строке. «*» заменяет любые знаки: aether-* подходит для всех хостов, начинающихся с aether-. Пусто: откуда угодно." /></span>
            <textarea class="field area mono" bind:value={form.sources} placeholder={"aether-*\ngw-02"}></textarea></label>
          <label><span class="label">Только через<Hint text="Подключение должно идти через эти хосты-мосты, по одному в строке. Пусто: путь не важен." /></span>
            <textarea class="field area mono" bind:value={form.via}></textarea></label>
          <h3>Ошибки и срок</h3>
          <div class="three">
            <label><span class="label">Ошибок до блока<Hint text="Сколько неверных попыток подряд допускается, прежде чем вход заблокируется. Пусто: не блокировать." /></span><input class="field" type="number" min="1" bind:value={form.max_attempts} placeholder="не блокировать" /></label>
            <label><span class="label">За сколько секунд<Hint text="Окно, в котором считаются ошибки: например, 3 ошибки за 60 секунд." /></span><input class="field" type="number" min="1" bind:value={form.attempts_window} /></label>
            <label><span class="label">Блок на сколько секунд<Hint text="Как долго вход закрыт после блокировки." /></span><input class="field" type="number" min="1" bind:value={form.lock_seconds} /></label>
          </div>
          <label><span class="label">Срок подключения, секунд<Hint text="Через сколько секунд сессия сама закончится. Пусто: без ограничения." /></span><input class="field" type="number" min="1" bind:value={form.ttl} placeholder="без ограничения" /></label>
        </div>

        <div class="block">
          <h3>Когда</h3>
          <label><span class="label">Окна<Hint text="Когда можно входить, по строке на правило. «mon-fri: 9:00-13:00 14:00-18:00» — по будням с 9 до 13 и с 14 до 18. «except sun: *» — кроме воскресенья. Дни: mon tue wed thu fri sat sun." /></span>
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
    {#if rows.length}
      <p class="muted empty">Загрузка…</p>
    {:else}
      <div class="empty">
        <p class="muted">Политик пока нет. Политика входа задаёт, кто, откуда и когда может войти на машину.</p>
        <button class="btn primary" onclick={() => (dialog = "new")}>+ Политика</button>
      </div>
    {/if}
  {/if}
</ListDetail>

{#if dialog === "new"}
  <Dialog title="Новая политика" confirm="Создать" onsubmit={create} onclose={() => (dialog = null)}>
    <input class="field" placeholder="название" bind:value={newName} />
  </Dialog>
{:else if dialog === "delete" && policy}
  <Dialog title="Удалить «{policy.name}»?" confirm="Удалить" danger disabled={policy.used_by.length > 0} onsubmit={remove} onclose={() => (dialog = null)}>
    <p class="muted">{policy.used_by.length ? "Она назначена: сначала снимите её с ОС, машин и учёток." : "Политика нигде не назначена."}</p>
  </Dialog>
{/if}

<style>
  .small { font-size: 12px; margin: 0; }
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
