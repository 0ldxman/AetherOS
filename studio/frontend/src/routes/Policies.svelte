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
  import ChipList from "../lib/ChipList.svelte";
  import Duration from "../lib/Duration.svelte";
  import Icon from "../lib/Icon.svelte";
  import Switch from "../lib/Switch.svelte";
  import WeekPaint from "../lib/WeekPaint.svelte";
  import { PRESETS, duration, fullGrid, gridToText, windowsInWords } from "../lib/policy";

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

  const TEXTS = [
    { key: "denied_text", label: "Отказ", when: "Не тот хост или не тот путь через мосты." },
    { key: "locked_text", label: "Блокировка", when: "Слишком много ошибок подряд: вход закрыт на время блока." },
    { key: "window_text", label: "Вне окна", when: "Вход пробуют вне разрешённых часов." },
    { key: "kick_text", label: "Обрыв по сроку", when: "Сессия закончилась по сроку подключения." },
  ] as const;
  let textTab = $state<(typeof TEXTS)[number]["key"]>("denied_text");
  let textMode = $state(false);

  // неделя для сетки: сервер считает её по тексту; пустой текст значит «всегда открыто»
  const paintGrid = $derived(week?.grid ?? fullGrid());
  const list_ = (text: string) => text.split("\n").map((item) => item.trim()).filter(Boolean);
  const sourcesList = $derived(list_(form.sources));
  const viaList = $derived(list_(form.via));
  const firstMachine = $derived(policy?.used_by.find((where) => where.machine)?.machine ?? null);
  const plural = (n: number, one: string, few: string, many: string) => (n % 10 === 1 && n % 100 !== 11 ? one : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? few : many);
</script>

<ListDetail title="Политики входа">
  {#snippet list()}
    {#each rows as row (row.id)}
      {@const used = [row.systems && `ОС ${row.systems}`, row.machines && `машин ${row.machines}`, row.accounts && `учёток ${row.accounts}`].filter(Boolean).join(" · ")}
      <a class="item" class:on={row.id === current} href="#/policies/{row.id}">
        <b>{row.name}</b>
        <span class="small" class:muted={used} class:idle={!used}>{used || "не назначена"}</span>
      </a>
    {/each}
  {/snippet}
  {#snippet add()}
    <button class="btn add" onclick={() => (dialog = "new")}>+ Политика</button>
  {/snippet}

  {#if policy}
    <section class="editor">
      <header class="top">
        <input class="title" bind:value={form.name} class:bad={errors.name} aria-label="Название политики" />
        <span class="spacer"></span>
        <button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить</button>
        <DraftState {share} {dirty} saved="" />
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
      </header>
      {#if errors.name}<p class="err">{errors.name.join(" ")}</p>{/if}
      <input class="field note" placeholder="Заметка для авторов (игрок её не видит)" bind:value={form.description} aria-label="Заметка" />

      <div class="work">
        <div class="main">
          <section class="card">
            <h3><span class="ico"><Icon name="key" size={16} /></span>Кому пускать</h3>
            <div class="seg" role="radiogroup" aria-label="Пароль и ключ">
              <button role="radio" aria-checked={form.mode === "all"} class:on={form.mode === "all"} onclick={() => (form.mode = "all")}>Нужны пароль и ключ</button>
              <button role="radio" aria-checked={form.mode === "any"} class:on={form.mode === "any"} onclick={() => (form.mode = "any")}>Хватает пароля или ключа</button>
            </div>
            <p class="muted small">Токен пускает мимо обоих. Что именно предъявлять, определяет учётка.</p>
            <div class="field-row">
              <span class="label">Откуда можно<Hint text="Какие хосты вправе подключаться. «*» заменяет любые знаки: aether-* подходит для всех хостов, чьё имя начинается с aether-. Пусто: откуда угодно." /></span>
              <ChipList label="Откуда можно" value={form.sources} placeholder="aether-*  gw-02 (пусто: откуда угодно)" onchange={(next) => (form.sources = next)} />
            </div>
            <div class="field-row">
              <span class="label">Только через<Hint text="Подключение должно пройти через эти хосты-мосты. Пусто: путь не важен." /></span>
              <ChipList label="Только через" value={form.via} placeholder="хост-мост (пусто: путь не важен)" onchange={(next) => (form.via = next)} />
            </div>
          </section>

          <section class="card">
            <h3><span class="ico"><Icon name="clock" size={16} /></span>Когда</h3>
            <div class="presets" role="group" aria-label="Готовые окна">
              {#each PRESETS as preset (preset.label)}
                <button class="preset" class:on={form.windows.trim() === preset.text} aria-pressed={form.windows.trim() === preset.text} title={preset.hint} onclick={() => (form.windows = preset.text)}>{preset.label}</button>
              {/each}
              <span class="spacer"></span>
              <button class="link" onclick={() => (textMode = !textMode)} aria-expanded={textMode}>{textMode ? "Скрыть текст" : "Править текстом"}</button>
            </div>
            {#if week?.error}
              <p class="err">Окна записаны с ошибкой: {week.error} Исправьте текст ниже.</p>
            {:else}
              <WeekPaint grid={paintGrid} onchange={(next) => (form.windows = gridToText(next))} />
            {/if}
            {#if textMode || week?.error}
              <label><span class="label">Правила<Hint text="По строке на правило: «mon-fri: 9:00-13:00 14:00-18:00» это будни с 9 до 13 и с 14 до 18, «except sun: *» исключает воскресенье, «*» вместо времени означает весь день. Дни: mon…sun, перечисление через запятую или диапазон mon-fri." /></span>
                <textarea class="field area mono" class:bad={errors.windows || week?.error} bind:value={form.windows} rows="4" placeholder={"mon-fri: 9:00-18:00"}></textarea></label>
              {#if errors.windows}<p class="err">{errors.windows.join(" ")}</p>{/if}
              {#if /#|except/i.test(form.windows)}<p class="muted small">Если нарисовать окна на сетке, правила запишутся заново равнозначным текстом: комментарии и «except» пропадут.</p>{/if}
            {/if}
          </section>

          <section class="card">
            <h3><span class="ico"><Icon name="lock" size={16} /></span>Ошибки и срок</h3>
            <div class="line">
              <Switch checked={form.max_attempts != null} label="Блокировать после неверных попыток" onchange={(on) => (form.max_attempts = on ? 3 : null)} />
            </div>
            {#if form.max_attempts != null}
              <p class="sentence">
                После <input class="field num" type="number" min="1" bind:value={form.max_attempts} aria-label="Ошибок до блока" /> {plural(form.max_attempts ?? 0, "ошибки", "ошибок", "ошибок")}
                за <Duration label="Окно подсчёта ошибок" value={form.attempts_window} onchange={(v) => (form.attempts_window = v)} />
                закрыть вход на <Duration label="Длительность блока" value={form.lock_seconds} onchange={(v) => (form.lock_seconds = v)} />
              </p>
            {:else}
              <p class="muted small">Сколько бы ни ошибались, вход не закрывается.</p>
            {/if}
            <div class="line">
              <Switch checked={form.ttl != null} label="Обрывать сессию по сроку" onchange={(on) => (form.ttl = on ? 1800 : null)} />
            </div>
            {#if form.ttl != null}
              <p class="sentence">Сессия обрывается через <Duration label="Срок подключения" value={form.ttl} onchange={(v) => (form.ttl = v)} /> после входа. Блок после обрыва задаётся блокировкой выше.</p>
            {:else}
              <p class="muted small">Подключение живёт, пока игрок сам не выйдет.</p>
            {/if}
          </section>

          <section class="card">
            <h3><span class="ico"><Icon name="eye" size={16} /></span>Что видит игрок</h3>
            <p class="muted small">Игрок не узнаёт, какое именно условие не выполнено. Свой текст заменяет стандартный текст системы.</p>
            <div class="tabs" role="tablist">
              {#each TEXTS as item (item.key)}
                <button role="tab" aria-selected={textTab === item.key} class:on={textTab === item.key} onclick={() => (textTab = item.key)}>{item.label}{#if form[item.key]}<span class="dot" title="Свой текст"></span>{/if}</button>
              {/each}
            </div>
            {#each TEXTS.filter((item) => item.key === textTab) as item (item.key)}
              <p class="muted small">{item.when}</p>
              <input class="field" bind:value={form[item.key]} placeholder="стандартный текст системы" aria-label={item.label} />
              <div class="screen" aria-label="Как это увидит игрок">
                <div class="dim">$ ssh ivan@aether-core</div>
                {#if form[item.key]}<div class="err-line">{form[item.key]}</div>{:else}<div class="dim">Покажется стандартный текст системы.</div>{/if}
              </div>
            {/each}
          </section>
        </div>

        <aside class="summary">
          <section class="card">
            <h3>Итог</h3>
            <ul>
              <li><span class="k">Вход</span>{form.mode === "all" ? "нужны и пароль, и ключ" : "хватает пароля или ключа"}</li>
              <li><span class="k">Откуда</span>{sourcesList.length ? sourcesList.join(", ") : "откуда угодно"}</li>
              {#if viaList.length}<li><span class="k">Через</span>{viaList.join(", ")}</li>{/if}
              <li><span class="k">Когда</span>{week?.error ? "окна записаны с ошибкой" : windowsInWords(paintGrid)}</li>
              <li><span class="k">Ошибки</span>{form.max_attempts != null ? `${form.max_attempts} за ${duration(form.attempts_window)}: блок на ${duration(form.lock_seconds)}` : "блокировки нет"}</li>
              <li><span class="k">Сессия</span>{form.ttl != null ? `до ${duration(form.ttl)}` : "без ограничения"}</li>
            </ul>
          </section>
          <section class="card">
            <h3>Где назначена</h3>
            {#each policy.used_by as where}
              <div class="where">
                <span class="chip">{KIND[where.kind]}</span>
                {#if where.machine}<a href="#/machines/{where.machine}/access">{where.label}</a>{:else}<span>{where.label}</span>{/if}
              </div>
            {:else}
              <p class="warnbox">Нигде. Политика не действует, пока её не назначат: машине (Обзор → Свойства), ОС или учётке.</p>
            {/each}
            {#if firstMachine}<a class="btn check" href="#/machines/{firstMachine}/access">Проверить вход</a>{/if}
          </section>
        </aside>
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
  .idle { color: var(--warn); }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 10px; }
  .top :global(.draft) { flex-wrap: nowrap; white-space: nowrap; }
  .title { height: 36px; min-width: 0; flex: 1 1 200px; max-width: 420px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--radius-s); background: none; color: var(--text); font-size: 18px; font-weight: 600; outline: none; }
  .title:hover { border-color: var(--line); }
  .title:focus { border-color: var(--accent); background: var(--bg); }
  .title.bad { border-color: var(--danger); }
  .spacer { flex: 1; }
  .note { max-width: 640px; }
  .work { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 16px; align-items: start; }
  .main { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .card { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); min-width: 0; }
  .card h3 { display: flex; align-items: center; gap: 8px; margin: 0 0 2px; font-size: 14px; font-weight: 650; }
  .ico { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 8px; background: var(--accent-soft); color: var(--accent); }
  .seg { display: inline-flex; align-self: flex-start; border: 1px solid var(--line-soft); border-radius: 999px; overflow: hidden; }
  .seg button { padding: 5px 14px; border: 0; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .seg button.on { background: var(--accent-soft); color: var(--text); }
  .field-row { display: flex; flex-direction: column; gap: 4px; }
  .presets { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .preset { padding: 4px 12px; border: 1px solid var(--line-soft); border-radius: 999px; background: none; color: var(--muted); font: inherit; font-size: 12.5px; cursor: pointer; }
  .preset:hover { border-color: var(--line); color: var(--text); }
  .preset.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .link { padding: 0; border: 0; background: none; color: var(--accent); font: inherit; font-size: 12.5px; cursor: pointer; }
  .link:hover { text-decoration: underline; }
  .area { height: auto; min-height: 64px; padding: 8px 10px; resize: vertical; }
  .line { margin-top: 2px; }
  .sentence { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 6px; margin: 0 0 4px 40px; font-size: 13.5px; }
  .num { width: 60px; height: 30px; padding: 2px 8px; }
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line-soft); }
  .tabs button { display: inline-flex; align-items: center; gap: 6px; padding: 7px 12px; margin-bottom: -1px; border: 0; border-bottom: 2px solid transparent; background: none; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
  .tabs button:hover { color: var(--text); }
  .tabs button.on { color: var(--text); border-bottom-color: var(--accent); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .screen { padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: #0b0d10; font: 13px/1.4 ui-monospace, "DejaVu Sans Mono", monospace; }
  .screen .dim { color: #767676; }
  .screen .err-line { color: #e74856; }
  .summary { position: sticky; top: 12px; display: flex; flex-direction: column; gap: 14px; }
  .summary ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
  .summary li { display: flex; flex-direction: column; gap: 1px; overflow-wrap: anywhere; }
  .k { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--faint); }
  .where { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .chip { padding: 0 8px; border-radius: 999px; background: var(--raise); color: var(--muted); font-size: 11.5px; }
  .warnbox { margin: 0; padding: 8px 10px; border-radius: var(--radius-s); background: rgba(242, 198, 109, 0.1); color: var(--warn); font-size: 12.5px; }
  .check { display: inline-flex; align-items: center; justify-content: center; gap: 6px; margin-top: 2px; text-decoration: none; }
  .field.bad { border-color: var(--danger); }
  .err { margin: 0; color: var(--danger); font-size: 12.5px; }
  .empty { padding: 24px; }
  @media (max-width: 1100px) { .work { grid-template-columns: 1fr; } .summary { position: static; } }
</style>
