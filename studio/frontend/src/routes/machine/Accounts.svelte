<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { go } from "../../lib/router.svelte";
  import { when } from "../../lib/time";
  import { toast } from "../../lib/toast.svelte";

  type Account = Schemas["AccountOut"];

  let { machine, selected, onchange }: { machine: Schemas["Overview"]; selected: number | null; onchange: () => void } = $props();

  let account = $state<Account | null>(null);
  let form = $state(blank());
  let saved = $state("");
  let password = $state("");
  let clearPassword = $state(false);
  let errors = $state<Record<string, string[]>>({});
  let keys = $state<Schemas["Key"][]>([]);
  let dialog = $state<null | "new" | "delete" | "token">(null);
  let newLogin = $state("");
  let tokenForm = $state({ max_usage: "" as string, expires_at: "" });
  let fresh = $state("");

  function blank() {
    return { login: "", name: "", freq: "1", mail: "", groups: [] as string[], root: false, keys: "", entry_policy: null as number | null,
             ttl: null as number | null, cooldown: null as number | null, kick_message: "", login_scene: null as string | null };
  }

  const dirty = $derived(JSON.stringify(form) !== saved || password !== "" || clearPassword);
  const current = $derived(selected ?? machine.accounts[0]?.id ?? null);

  async function load(id: number | null) {
    account = null;
    password = "";
    clearPassword = false;
    errors = {};
    fresh = "";
    if (id === null) return;
    const { data } = await api.GET("/studio/api/machines/{machine_id}/accounts/{account_id}", {
      params: { path: { machine_id: machine.id, account_id: id } },
    });
    if (!data) return;
    account = data;
    form = { login: data.login, name: data.name, freq: data.freq, mail: data.mail, groups: [...data.groups], root: data.root, keys: data.keys,
             entry_policy: data.entry_policy ?? null, ttl: data.ttl ?? null, cooldown: data.cooldown ?? null, kick_message: data.kick_message, login_scene: data.login_scene ?? null };
    saved = JSON.stringify(form);
  }

  $effect(() => { load(current); });
  onMount(async () => { keys = (await api.GET("/studio/api/keys")).data ?? []; });

  async function save() {
    if (!account) return;
    errors = {};
    const { data, error } = await api.PUT("/studio/api/machines/{machine_id}/accounts/{account_id}", {
      params: { path: { machine_id: machine.id, account_id: account.id } },
      body: { ...form, password: password || null, clear_password: clearPassword },
    });
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> }).fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    toast("Учётка сохранена.");
    await load(data.id);
    onchange();
  }

  async function create() {
    const { data, error } = await api.POST("/studio/api/machines/{machine_id}/accounts", {
      params: { path: { machine_id: machine.id } }, body: { ...blank(), login: newLogin, clear_password: false },
    });
    if (error || !data) return toast(problem(error, "Не создалась."), "error");
    dialog = null;
    newLogin = "";
    onchange();
    go(`/machines/${machine.id}/accounts/${data.id}`);
  }

  async function remove() {
    if (!account) return;
    const { error } = await api.DELETE("/studio/api/machines/{machine_id}/accounts/{account_id}", {
      params: { path: { machine_id: machine.id, account_id: account.id } },
    });
    if (error) return toast(problem(error), "error");
    dialog = null;
    toast("Учётка удалена.");
    onchange();
    go(`/machines/${machine.id}/accounts`);
  }

  async function makeToken() {
    if (!account) return;
    const { data, error } = await api.POST("/studio/api/machines/{machine_id}/accounts/{account_id}/tokens", {
      params: { path: { machine_id: machine.id, account_id: account.id } },
      body: { max_usage: tokenForm.max_usage ? +tokenForm.max_usage : null, expires_at: tokenForm.expires_at || null },
    });
    if (error || !data) return toast(problem(error), "error");
    dialog = null;
    await load(account.id);
    fresh = data.token;
  }

  async function dropToken(token: Schemas["Token"]) {
    if (!account) return;
    await api.DELETE("/studio/api/machines/{machine_id}/accounts/{account_id}/tokens/{token_id}", {
      params: { path: { machine_id: machine.id, account_id: account.id, token_id: token.id } },
    });
    await load(account.id);
  }

  function toggleGroup(name: string) {
    form.groups = form.groups.includes(name) ? form.groups.filter((g) => g !== name) : [...form.groups, name].sort();
  }

  function addKey(slug: string) {
    form.keys = form.keys.trim() ? `${form.keys.trim()} and ${slug}` : slug;
  }

  const ORIGIN: Record<string, string> = { profile: "своя", machine: "от машины", system: "от типа системы" };
</script>

<div class="split">
  <aside class="list">
    {#each machine.accounts as row (row.id)}
      <a class="item" class:on={row.id === current} href="#/machines/{machine.id}/accounts/{row.id}">
        <span class="login mono">{row.login}</span>
        <span class="marks">
          {#if row.root}<span class="chip root">root</span>{/if}
          {#if row.has_password}<span class="chip">пароль</span>{/if}
          {#if row.has_key}<span class="chip">ключ</span>{/if}
          {#if !row.has_password && !row.has_key && !row.owner}<span class="chip warnchip" title="Ни пароля, ни ключа">открыта</span>{/if}
        </span>
        <span class="sub muted">{row.owner ? `игрок ${row.owner}` : row.groups.join(", ") || "без групп"}</span>
      </a>
    {/each}
    <button class="btn add" onclick={() => (dialog = "new")}>+ Учётка</button>
  </aside>

  {#if account}
    <section class="card-form">
      <header class="top">
        <h2 class="mono">{account.login}<span class="muted">@{machine.hostname}</span></h2>
        {#if account.owner}<span class="chip">рабочая учётка игрока {account.owner}</span>{/if}
        <span class="spacer"></span>
        <a class="btn ghost" href="#/machines/{machine.id}/access/{account.id}">Проверить вход</a>
        <a class="btn ghost" href="#/machines/{machine.id}/journal/{account.id}">Журнал</a>
        <button class="btn primary" disabled={!dirty} onclick={save}>Сохранить</button>
      </header>

      <div class="cols">
        <div class="block">
          <h3>Кто это</h3>
          <div class="pair">
            <label><span class="label">Логин</span><input class="field mono" bind:value={form.login} class:bad={errors.login} /></label>
            <label><span class="label">Частота / порт</span><input class="field mono" bind:value={form.freq} class:bad={errors.freq} /></label>
          </div>
          <label><span class="label">Имя</span><input class="field" bind:value={form.name} /></label>
          <label><span class="label">Почта</span><input class="field mono" bind:value={form.mail} class:bad={errors.mail} placeholder="{form.login}@{machine.hostname}" /></label>
          {#each Object.entries(errors).filter(([key]) => ["login", "freq", "mail", "__all__"].includes(key)) as [, list]}<p class="err">{list.join(" ")}</p>{/each}

          <h3>Группы и права</h3>
          <div class="chips">
            {#each machine.groups as name}
              <button class="pick" class:on={form.groups.includes(name)} onclick={() => toggleGroup(name)}>{name}</button>
            {/each}
            {#each form.groups.filter((g) => !machine.groups.includes(g)) as name}
              <button class="pick on unknown" title="Такой группы на машине нет" onclick={() => toggleGroup(name)}>{name} ✕</button>
            {/each}
          </div>
          <label class="check"><input type="checkbox" bind:checked={form.root} /> root: все привилегии и обход прав файлов</label>
        </div>

        <div class="block">
          <h3>Как войти</h3>
          <label>
            <span class="label">Пароль {account.has_password ? "(задан)" : "(не задан)"}</span>
            <input class="field" type="password" autocomplete="new-password" placeholder={account.has_password ? "новый пароль, чтобы сменить" : "задать пароль"}
                   bind:value={password} disabled={clearPassword} />
          </label>
          {#if account.has_password}<label class="check"><input type="checkbox" bind:checked={clearPassword} /> убрать пароль</label>{/if}

          <label>
            <span class="label">Ключи (выражение: a and (b or not c))</span>
            <input class="field mono" bind:value={form.keys} class:bad={errors.keys} placeholder="без ключей" />
          </label>
          {#if errors.keys}<p class="err">{errors.keys.join(" ")}</p>{/if}
          <div class="chips small">
            {#each keys.slice(0, 12) as key}<button class="pick" title={key.description} onclick={() => addKey(key.slug)}>+ {key.slug}</button>{/each}
          </div>

          <label>
            <span class="label">Политика входа · сейчас {account.policy ? `«${account.policy.name}», ${ORIGIN[account.policy.origin ?? ""]}` : "никакой"}</span>
            <select class="field" bind:value={form.entry_policy}>
              <option value={null}>наследовать</option>
              {#each machine.policies as policy}<option value={policy.id}>{policy.name}</option>{/each}
            </select>
          </label>
          <div class="pair">
            <label><span class="label">Срок подключения, с</span><input class="field" type="number" min="0" bind:value={form.ttl} placeholder="из политики" /></label>
            <label><span class="label">Блок после обрыва, с</span><input class="field" type="number" min="0" bind:value={form.cooldown} placeholder="из политики" /></label>
          </div>
          <label><span class="label">Сообщение при обрыве</span><input class="field" bind:value={form.kick_message} placeholder="стандартное для системы" /></label>
          <label><span class="label">Сцена после входа</span>
            <select class="field" bind:value={form.login_scene}>
              <option value={null}>общая сцена ОС (или никакой)</option>
              {#each account?.scene_library ?? [] as slug}<option value={slug}>{slug}</option>{/each}
            </select>
          </label>
        </div>
      </div>

      <div class="block tokens">
        <h3>Токены <button class="btn ghost" onclick={() => (dialog = "token")}>+ Токен</button></h3>
        {#if fresh}<p class="fresh">Новый токен: <code class="mono">{fresh}</code> — передайте его в мир (письмо, файл), токен пускает мимо пароля и ключей.</p>{/if}
        {#each account.tokens as token (token.id)}
          <div class="token">
            <code class="mono">{token.token}</code>
            <span class="muted">использован {token.usage}{token.max_usage != null ? ` из ${token.max_usage}` : ""}</span>
            <span class="muted">{token.expires_at ? `до ${when(token.expires_at)}` : "бессрочный"}</span>
            <button class="btn ghost danger" onclick={() => dropToken(token)}>Отозвать</button>
          </div>
        {:else}
          <p class="muted">Токенов нет.</p>
        {/each}
      </div>

      {#if !account.owner}
        <div class="danger-zone"><button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить учётку</button></div>
      {/if}
    </section>
  {:else}
    <p class="muted empty">{machine.accounts.length ? "Загрузка…" : "У машины ещё нет учёток."}</p>
  {/if}
</div>

{#if dialog === "new"}
  <Dialog title="Новая учётка" confirm="Создать" onsubmit={create} onclose={() => (dialog = null)}>
    <input class="field mono" placeholder="логин" bind:value={newLogin} />
  </Dialog>
{:else if dialog === "delete" && account}
  <Dialog title="Удалить учётку {account.login}?" confirm="Удалить" danger onsubmit={remove} onclose={() => (dialog = null)}>
    <p class="muted">Её сессии, события журнала и токены удалятся вместе с ней.</p>
  </Dialog>
{:else if dialog === "token"}
  <Dialog title="Новый токен" confirm="Создать" onsubmit={makeToken} onclose={() => (dialog = null)}>
    <label><span class="label">Сколько раз можно войти (пусто: без ограничения)</span><input class="field" type="number" min="1" bind:value={tokenForm.max_usage} /></label>
    <label><span class="label">Действует до (пусто: бессрочно)</span><input class="field" type="datetime-local" bind:value={tokenForm.expires_at} /></label>
  </Dialog>
{/if}

<style>
  .split { display: grid; grid-template-columns: 260px 1fr; min-height: 100%; }
  .list { display: flex; flex-direction: column; gap: 2px; padding: 12px 8px; border-right: 1px solid var(--line-soft); }
  .item { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; padding: 8px 10px; border-radius: var(--radius-s); color: var(--text); }
  .item:hover { background: var(--panel); text-decoration: none; }
  .item.on { background: var(--accent-soft); }
  .login { font-weight: 600; }
  .marks { display: flex; gap: 4px; align-items: center; font-size: 12px; }
  .sub { grid-column: 1 / -1; font-size: 12px; }
  .chip.root { background: rgba(255, 122, 122, 0.15); color: var(--danger); }
  .chip.warnchip { background: rgba(242, 198, 109, 0.15); color: var(--warn); }
  .add { margin: 8px 4px 0; justify-content: center; }
  .card-form { padding: 16px 20px 32px; min-width: 0; }
  .top { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
  .top h2 { margin: 0; font-size: 18px; }
  .spacer { flex: 1; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .block { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  h3 { display: flex; align-items: center; gap: 8px; margin: 6px 0 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3:first-child { margin-top: 0; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .pick { padding: 3px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); cursor: pointer; color: var(--muted); }
  .pick.on { border-color: var(--accent); background: var(--accent-soft); color: var(--text); }
  .pick.unknown { border-color: var(--warn); color: var(--warn); background: transparent; }
  .chips.small .pick { font-size: 12px; padding: 1px 8px; }
  .check { display: flex; align-items: center; gap: 8px; color: var(--muted); }
  .field.bad { border-color: var(--danger); }
  .err { margin: -4px 0 0; color: var(--danger); font-size: 12px; }
  .tokens { margin-top: 16px; }
  .token { display: grid; grid-template-columns: 1fr auto auto auto; gap: 14px; align-items: center; padding: 4px 0; }
  .fresh { margin: 0; padding: 8px 10px; border-radius: var(--radius-s); background: rgba(95, 208, 160, 0.1); border: 1px solid rgba(95, 208, 160, 0.3); }
  .danger-zone { margin-top: 16px; }
  .empty { padding: 24px; }
</style>
