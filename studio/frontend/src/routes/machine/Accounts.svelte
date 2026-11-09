<script lang="ts">
  import Hint from "../../lib/Hint.svelte";
  import { guardUnsaved } from "../../lib/guard.svelte";
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../../lib/api";
  import Dialog from "../../lib/Dialog.svelte";
  import { go } from "../../lib/router.svelte";
  import { ask } from "../../lib/confirm.svelte";
  import { ago, span, when } from "../../lib/time";
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
  let dialog = $state<null | "new" | "delete" | "token" | "bind">(null);
  let newLogin = $state("");
  let tokenForm = $state({ max_usage: "" as string, expires_at: "" });
  let fresh = $state("");
  let filter = $state("");
  let playersOpen = $state(false);
  let players = $state<Schemas["AccountPlayer"][]>([]);
  let newKind = $state<"shared" | "player">("shared");
  let playerQuery = $state("");
  let found = $state<string[]>([]);
  let chosenPlayer = $state("");

  function blank() {
    return { login: "", name: "", freq: "1", mail: "", groups: [] as string[], root: false, keys: "", entry_policy: null as number | null,
             ttl: null as number | null, cooldown: null as number | null, kick_message: "", login_scene: null as string | null };
  }

  const dirty = $derived(JSON.stringify(form) !== saved || password !== "" || clearPassword);
  guardUnsaved(() => saved !== "" && dirty);   // пока ничего не загружено, правок нет
  const current = $derived(selected ?? machine.accounts.find((row) => !row.owner)?.id ?? machine.accounts[0]?.id ?? null);

  // список: учётки автора сверху, рабочие учётки игроков отдельной группой (их столько, сколько игроков)
  const matches = (row: Schemas["AccountRow"]) => {
    const q = filter.trim().toLowerCase();
    return !q || [row.login, row.name, row.owner ?? "", row.freq].some((text) => text.toLowerCase().includes(q));
  };
  const authored = $derived(machine.accounts.filter((row) => !row.owner && matches(row)));
  const ofPlayers = $derived(machine.accounts.filter((row) => row.owner && matches(row)));
  const playerTotal = $derived(machine.accounts.filter((row) => row.owner).length);
  const showPlayers = $derived(playersOpen || !!filter.trim() || !!account?.owner);

  async function loadPlayers(id: number) {
    players = (await api.GET("/studio/api/machines/{machine_id}/accounts/{account_id}/players", { params: { path: { machine_id: machine.id, account_id: id } } })).data ?? [];
  }

  let findTimer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const q = playerQuery;
    clearTimeout(findTimer);
    if (!(dialog === "bind" || (dialog === "new" && newKind === "player"))) return;
    findTimer = setTimeout(async () => {
      found = (await api.GET("/studio/api/machines/players", { params: { query: { q } } })).data ?? [];
    }, 200);
  });

  const failure = (error: unknown, fallback: string) => {
    const fields = (error as { fields?: Record<string, string[]> } | undefined)?.fields;
    return fields ? Object.values(fields).flat().join(" ") : problem(error, fallback);
  };

  async function bindTo(player: string | null) {
    if (!account) return;
    const { data, error } = await api.POST("/studio/api/machines/{machine_id}/accounts/{account_id}/bind", {
      params: { path: { machine_id: machine.id, account_id: account.id } }, body: { player },
    });
    if (error || !data) return toast(failure(error, "Не получилось."), "error");
    dialog = null;
    toast(player ? `Учётка отдана игроку ${player}.` : "Учётка больше не принадлежит игроку.");
    await load(data.id);
    onchange();
  }

  async function unbind() {
    if (!account?.owner) return;
    if (!(await ask(`Отвязать учётку от игрока ${account.owner}?`, "Она станет общей. Игрок получит новую рабочую учётку при следующем входе на машину.", "Отвязать"))) return;
    bindTo(null);
  }

  async function act(kind: "unlock" | "kick", row: Schemas["AccountPlayer"]) {
    if (!account) return;
    const path = kind === "unlock" ? "/studio/api/machines/{machine_id}/unlock" : "/studio/api/machines/{machine_id}/kick";
    const { error } = await api.POST(path, { params: { path: { machine_id: machine.id } }, body: { account: account.id, player: row.player } });
    if (error) return toast(problem(error), "error");
    toast(kind === "unlock" ? `${row.player} разблокирован.` : `${row.player} будет выкинут при следующем действии.`);
    loadPlayers(account.id);
  }

  async function load(id: number | null) {
    account = null;
    password = "";
    clearPassword = false;
    errors = {};
    fresh = "";
    players = [];
    if (id === null) return;
    const { data } = await api.GET("/studio/api/machines/{machine_id}/accounts/{account_id}", {
      params: { path: { machine_id: machine.id, account_id: id } },
    });
    if (!data) return;
    account = data;
    form = { login: data.login, name: data.name, freq: data.freq, mail: data.mail, groups: [...data.groups], root: data.root, keys: data.keys,
             entry_policy: data.entry_policy ?? null, ttl: data.ttl ?? null, cooldown: data.cooldown ?? null, kick_message: data.kick_message, login_scene: data.login_scene ?? null };
    saved = JSON.stringify(form);
    if (!data.owner) loadPlayers(data.id);
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
      params: { path: { machine_id: machine.id } },
      body: { ...blank(), login: newLogin, clear_password: false, player: newKind === "player" ? chosenPlayer : null },
    });
    if (error || !data) return toast(failure(error, "Не создалась."), "error");
    dialog = null;
    newLogin = "";
    newKind = "shared";
    chosenPlayer = "";
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
    <input class="field" placeholder="Найти учётку или игрока…" bind:value={filter} aria-label="Поиск по учёткам" />
    {#snippet row(item: Schemas["AccountRow"])}
      <a class="item" class:on={item.id === current} href="#/machines/{machine.id}/accounts/{item.id}">
        <span class="login mono">{item.login}<span class="muted at">@{item.freq}</span></span>
        <span class="marks">
          {#if item.root}<span class="chip root">root</span>{/if}
          {#if item.has_password}<span class="chip">пароль</span>{/if}
          {#if item.has_key}<span class="chip">ключ</span>{/if}
          {#if !item.has_password && !item.has_key && !item.owner}<span class="chip warnchip" title="Ни пароля, ни ключа">открыта</span>{/if}
        </span>
        <span class="sub muted">{item.name && item.name !== item.login ? `${item.name} · ` : ""}{item.owner ? `игрок ${item.owner}` : item.groups.join(", ") || "без групп"}</span>
      </a>
    {/snippet}

    <h3 class="group">Учётки автора <span class="n">{authored.length}</span></h3>
    {#each authored as item (item.id)}{@render row(item)}{:else}<p class="muted small pad">{filter ? "Ничего не нашлось." : "Своих учёток нет."}</p>{/each}

    {#if playerTotal}
      <button class="group toggle" aria-expanded={showPlayers} onclick={() => (playersOpen = !playersOpen)} disabled={!!filter.trim() || !!account?.owner}>
        <span>{showPlayers ? "▾" : "▸"} Рабочие учётки игроков</span><span class="n">{ofPlayers.length}{filter.trim() ? ` из ${playerTotal}` : ""}</span>
      </button>
      {#if showPlayers}{#each ofPlayers as item (item.id)}{@render row(item)}{/each}{/if}
    {/if}
    <button class="btn add" onclick={() => { newKind = "shared"; chosenPlayer = ""; playerQuery = ""; dialog = "new"; }}>+ Учётка</button>
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
            <label><span class="label">Логин{#if account.owner}<Hint text="Логин рабочей учётки игрока менять нельзя: он совпадает с его логином на сайте." />{/if}</span><input class="field mono" bind:value={form.login} class:bad={errors.login} disabled={!!account.owner} /></label>
            <label><span class="label">Частота / порт<Hint text="Где слушает эта запись: у систем Aether частота в МГц (14.230), у остальных порт (22)." /></span><input class="field mono" bind:value={form.freq} class:bad={errors.freq} /></label>
          </div>
          <label><span class="label">Имя</span><input class="field" bind:value={form.name} /></label>
          <label><span class="label">Почта</span><input class="field mono" bind:value={form.mail} class:bad={errors.mail} placeholder="{form.login}@{machine.hostname}" /></label>
          {#each Object.entries(errors).filter(([key]) => ["login", "freq", "mail", "__all__"].includes(key)) as [, list]}<p class="err">{list.join(" ")}</p>{/each}

          <div class="ownerrow">
            <span class="label">Игрок</span>
            {#if account.owner}
              <span><b>{account.owner}</b> <span class="muted small">рабочая учётка: удаляется вместе с игроком</span></span>
              <button class="btn ghost" onclick={unbind}>Отвязать от игрока</button>
            {:else}
              <span class="muted">общая учётка (не принадлежит игроку)</span>
              <button class="btn ghost" onclick={() => { chosenPlayer = ""; playerQuery = ""; dialog = "bind"; }}>Отдать игроку…</button>
            {/if}
          </div>

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
          {#if account.owner && form.root}<p class="err">Игрок получит все привилегии и обход прав файлов на этой машине.</p>{/if}
        </div>

        <div class="block">
          <h3>Как войти</h3>
          {#if account.owner}
            <p class="muted small">Игрок входит через свой аккаунт на сайте, поэтому пароль, ключи, политика входа и токены у рабочей учётки не действуют. Здесь настраивается только то, что касается его сессии.</p>
          {:else}
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
              <option value={null}>как у машины</option>
              {#each machine.policies as policy}<option value={policy.id}>{policy.name}</option>{/each}
            </select>
          </label>
          {/if}
          <div class="pair">
            <label><span class="label">Срок подключения, секунд<Hint text="Через сколько секунд после входа сессия сама закончится. Пусто: берётся из политики входа." /></span><input class="field" type="number" min="0" bind:value={form.ttl} placeholder="из политики" /></label>
            <label><span class="label">Блок после обрыва, секунд<Hint text="Сколько секунд игроку нельзя войти снова после обрыва связи. Пусто: берётся из политики входа." /></span><input class="field" type="number" min="0" bind:value={form.cooldown} placeholder="из политики" /></label>
          </div>
          <label><span class="label">Сообщение при обрыве</span><input class="field" bind:value={form.kick_message} placeholder="стандартное для системы" /></label>
          <label><span class="label">Сцена после входа</span>
            <select class="field" bind:value={form.login_scene}>
              <option value={null}>общая сцена ОС (или никакой)</option>
              {#each account?.scene_library ?? [] as item}<option value={item.slug}>{item.title ? `${item.title} · ${item.slug}` : item.slug}</option>{/each}
            </select>
          </label>
        </div>
      </div>

      {#if !account.owner}
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

      {/if}

      {#if !account.owner}
        <div class="block players">
          <h3>Игроки на этой учётке<Hint text="Кто входил под этой учёткой. Блокировка действует на пару «игрок и учётка»: у разных игроков она своя." /></h3>
          {#each players as row (row.player)}
            <div class="pl">
              <span class="dot" class:on={row.online}></span>
              <b>{row.player}</b>
              <span class="muted small">{row.online && row.seen_at ? `сейчас на учётке · ${ago(row.seen_at)}` : row.last_login ? `входил ${ago(row.last_login)}` : "не входил"}</span>
              {#if row.locked}<span class="chip bad">блок {span(row.locked)}</span>{/if}
              {#if row.refusals}<span class="chip warnchip" title="Отказов за неделю">отказов {row.refusals}</span>{/if}
              <span class="spacer"></span>
              {#if row.locked}<button class="btn ghost" onclick={() => act("unlock", row)}>Разблокировать</button>{/if}
              {#if row.online}<button class="btn ghost danger" onclick={() => act("kick", row)}>Выкинуть</button>{/if}
            </div>
          {:else}
            <p class="muted">Никто ещё не входил под этой учёткой.</p>
          {/each}
        </div>
        <div class="danger-zone"><button class="btn ghost danger" onclick={() => (dialog = "delete")}>Удалить учётку</button></div>
      {:else}
        <p class="muted small ownernote">Рабочую учётку игрока нельзя удалить: она удалится вместе с ним. Чтобы освободить её, отвяжите от игрока.</p>
      {/if}
    </section>
  {:else}
    <p class="muted empty">{machine.accounts.length ? "Загрузка…" : "У машины ещё нет учёток."}</p>
  {/if}
</div>

{#if dialog === "new"}
  <Dialog title="Новая учётка" confirm="Создать" onsubmit={create} onclose={() => (dialog = null)} disabled={!newLogin.trim() || (newKind === "player" && !chosenPlayer)}>
    <input class="field mono" placeholder="логин" bind:value={newLogin} />
    <label class="radio"><input type="radio" bind:group={newKind} value="shared" /> общая: для загадок, в неё входят любые игроки</label>
    <label class="radio"><input type="radio" bind:group={newKind} value="player" /> для игрока: станет его рабочей учёткой</label>
    {#if newKind === "player"}
      <input class="field" placeholder="Найти игрока…" bind:value={playerQuery} />
      <div class="pickrow">{#each found as name (name)}<button class="pickbtn" class:on={chosenPlayer === name} onclick={() => (chosenPlayer = name)}>{name}</button>{:else}<span class="muted small">Игроков не найдено.</span>{/each}</div>
    {/if}
  </Dialog>
{:else if dialog === "bind" && account}
  <Dialog title="Отдать учётку {account.login} игроку" confirm="Отдать" onsubmit={() => bindTo(chosenPlayer)} onclose={() => (dialog = null)} disabled={!chosenPlayer}>
    <p class="muted small">Учётка станет рабочей учётки игрока на этой машине: пароль, ключи и токены у неё перестанут действовать. У игрока на машине может быть только одна рабочая учётка.</p>
    <input class="field" placeholder="Найти игрока…" bind:value={playerQuery} />
    <div class="pickrow">{#each found as name (name)}<button class="pickbtn" class:on={chosenPlayer === name} onclick={() => (chosenPlayer = name)}>{name}</button>{:else}<span class="muted small">Игроков не найдено.</span>{/each}</div>
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
  .group { display: flex; align-items: center; justify-content: space-between; margin: 10px 10px 2px; padding: 0; border: 0; background: none; color: var(--muted); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px; text-align: left; }
  button.group { cursor: pointer; width: calc(100% - 20px); }
  button.group:disabled { cursor: default; }
  .group .n { color: var(--faint); }
  .at { margin-left: 2px; font-weight: 400; }
  .pad { padding: 4px 10px; }
  .ownerrow { display: grid; grid-template-columns: 70px 1fr auto; gap: 8px; align-items: center; }
  .ownernote { margin: 4px 0 0; }
  .players { margin-top: 14px; }
  .pl { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .pl:last-child { border-bottom: 0; }
  .pl .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--faint); }
  .pl .dot.on { background: var(--ok); }
  .pl .spacer { flex: 1; }
  .chip.bad { background: var(--danger-soft); color: var(--danger); }
  .radio { display: flex; align-items: center; gap: 6px; }
  .pickrow { display: flex; flex-wrap: wrap; gap: 6px; max-height: 140px; overflow: auto; }
  .pickbtn { padding: 3px 12px; border: 1px solid var(--line); border-radius: 999px; background: var(--bg); cursor: pointer; }
  .pickbtn.on { border-color: var(--accent); background: var(--accent-soft); }
</style>
