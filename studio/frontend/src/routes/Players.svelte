<script lang="ts">
  // Игроки: кто играет, где был, что у него есть (учётки, ключи, изменённые файлы, журнал входов), и действия автора:
  // выбросить, разблокировать, выдать или забрать ключ, сбросить прогресс, отключить вход.
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { canAct, canEdit } from "../lib/me.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import { RoomPing } from "../lib/shared.svelte";

  let { id }: { id: number | null } = $props();

  let rows = $state<Schemas["PlRow"][]>([]);
  let card = $state<Schemas["PlCard"] | null>(null);
  let query = $state("");
  let onlyOnline = $state(false);
  let keys = $state<Schemas["Key"][]>([]);
  let dialog = $state<null | "key" | "reset">(null);
  let keyAccount = $state<number | null>(null);
  let keySlug = $state("");
  let resetMachine = $state<number | null>(null);
  let busy = $state(false);

  const edit = $derived(canEdit("players"));
  const why = (action: string) => !edit ? "У вашей роли нет права править раздел «Игроки»." : canAct(action) ? "" : "Ваша роль не разрешает это действие.";
  const allowed = (action: string) => !why(action);

  async function list() {
    rows = (await api.GET("/studio/api/players", { params: { query: { q: query.trim(), online: onlyOnline } } })).data ?? [];
  }
  async function open(playerId: number | null) {
    card = null;
    if (playerId === null) return;
    card = (await api.GET("/studio/api/players/{player_id}", { params: { path: { player_id: playerId } } })).data ?? null;
  }
  onMount(async () => {
    await list();
    keys = (await api.GET("/studio/api/keys")).data ?? [];
    if (id === null && rows.length) go(`/players/${rows[0].id}`);
  });
  $effect(() => { open(id); });
  // действие другого автора с этим игроком: карточка перечитывается
  new RoomPing({
    room: () => `players/${id}`,
    onPing: async () => {
      if (id === null) return;
      card = (await api.GET("/studio/api/players/{player_id}", { params: { path: { player_id: id } } })).data ?? card;
      await list();
    },
  });

  let timer: ReturnType<typeof setTimeout> | undefined;
  function search() {
    clearTimeout(timer);
    timer = setTimeout(list, 250);
  }

  type Done = { data?: Schemas["PlCard"]; error?: unknown };
  async function act(run: () => Promise<Done>, ok: string) {
    busy = true;
    const { data, error } = await run();
    busy = false;
    if (error || !data) return toast(problem(error, "Не получилось."), "error");
    card = data;
    toast(ok);
    await list();
  }
  const path = () => ({ path: { player_id: card!.id } });

  function kick(a: Schemas["PlAccount"]) {
    act(() => api.POST("/studio/api/players/{player_id}/kick", { params: path(), body: { account: a.id } }), `Подключение ${a.login}@${a.hostname} закроется при следующем запросе игрока.`);
  }
  function unlock(a: Schemas["PlAccount"]) {
    act(() => api.POST("/studio/api/players/{player_id}/unlock", { params: path(), body: { account: a.id } }), `Учётка ${a.login}@${a.hostname} снова принимает игрока.`);
  }
  async function takeKey(k: Schemas["PlKey"]) {
    if (!(await ask(`Забрать ключ ${k.slug}?`, `Файл ${k.name} пропадёт из папки секретов ${k.login}@${k.hostname} только у этого игрока.`, "Забрать ключ"))) return;
    act(() => api.POST("/studio/api/players/{player_id}/keys/take", { params: path(), body: { account: k.account, key: "", name: k.name } }), `Ключ ${k.slug} забран.`);
  }
  async function giveKey() {
    if (keyAccount === null || !keySlug) return;
    await act(() => api.POST("/studio/api/players/{player_id}/keys", { params: path(), body: { account: keyAccount!, key: keySlug, name: "" } }), `Ключ ${keySlug} выдан.`);
    dialog = null;
  }
  async function reset() {
    const where = resetMachine === null ? "на всех машинах" : `на ${card?.machines.find((m) => m.machine === resetMachine)?.hostname}`;
    if (!(await ask(`Сбросить прогресс ${card?.username} ${where}?`, "Пропадут его копии и правки файлов, удаления, корзина, снятые слои и сдвиги часов. Учётки и журнал входов останутся. Отменить нельзя.", "Сбросить прогресс"))) return;
    await act(() => api.POST("/studio/api/players/{player_id}/reset", { params: path(), body: { machine: resetMachine } }), "Прогресс сброшен.");
    dialog = null;
  }
  async function ban(banned: boolean) {
    if (banned && !(await ask(`Отключить вход ${card?.username}?`, "Игрок не сможет войти, открытые подключения закроются. Вход можно вернуть.", "Отключить вход"))) return;
    act(() => api.POST("/studio/api/players/{player_id}/ban", { params: path(), body: { banned } }), banned ? "Вход отключён." : "Вход возвращён.");
  }

  const when = (value: string | null | undefined) => value ? new Date(value).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";
  const minutes = (seconds: number) => seconds >= 60 ? `${Math.ceil(seconds / 60)} мин` : `${seconds} с`;
</script>

<ListDetail title="Игроки">
  {#snippet list()}
    <input class="field find" placeholder="Поиск по имени" bind:value={query} oninput={search} aria-label="Поиск игрока" />
    <label class="only"><input type="checkbox" bind:checked={onlyOnline} onchange={list} /> только в мире</label>
    {#each rows as row (row.id)}
      <a class="item" class:on={row.id === id} href="#/players/{row.id}">
        <b>{#if row.online}<span class="dot" title="В мире"></span>{/if}{row.username}{#if row.staff}<span class="tag">автор</span>{/if}{#if row.banned}<span class="tag bad">вход отключён</span>{/if}</b>
        <span class="muted small">{row.discord ? `${row.discord} · ` : ""}{row.seen_at ? `был ${when(row.seen_at)}` : "не играл"}</span>
      </a>
    {:else}
      <p class="muted small pad">{query || onlyOnline ? "Никого не нашлось." : "Игроков пока нет: они появятся после первого входа в игру."}</p>
    {/each}
  {/snippet}
  {#snippet add()}{/snippet}

  {#if id === null}
    <p class="muted empty">Выберите игрока слева.</p>
  {:else if !card}
    <p class="muted empty">Загрузка…</p>
  {:else}
    <section class="editor">
      <header class="top">
        <div>
          <b class="big">{card.username}</b>
          <p class="muted small">
            {card.online ? "сейчас в мире" : "не в мире"}{card.discord ? ` · Discord: ${card.discord}` : ""} · в игре с {when(card.joined)}
          </p>
        </div>
        <span class="spacer"></span>
        <button class="btn ghost" disabled={busy || !allowed("reset") || !card.machines.length} title={why("reset") || (!card.machines.length ? "Прогресса пока нет." : "")}
                onclick={() => { resetMachine = null; dialog = "reset"; }}>Сбросить прогресс…</button>
        {#if card.banned}
          <button class="btn" disabled={busy || !allowed("ban")} title={why("ban")} onclick={() => ban(false)}>Вернуть вход</button>
        {:else}
          <button class="btn ghost danger" disabled={busy || !allowed("ban") || card.staff} title={why("ban") || (card.staff ? "Это автор: сначала уберите его из команды." : "")} onclick={() => ban(true)}>Отключить вход</button>
        {/if}
      </header>
      {#if card.banned}<p class="banner">Вход отключён: игрок не может войти в игру.</p>{/if}

      <div class="block">
        <b>Учётки</b>
        {#if !card.accounts.length}
          <p class="muted small">Игрок ещё ни под одной учёткой не работал.</p>
        {:else}
          <table class="grid">
            <thead><tr><th>Учётка</th><th>Был</th><th>Состояние</th><th></th></tr></thead>
            <tbody>
              {#each card.accounts as a (a.id)}
                <tr>
                  <td><a href="#/machines/{a.machine}/accounts/{a.id}" class="mono">{a.login}@{a.hostname}</a>{#if a.own}<span class="tag">рабочая</span>{/if}</td>
                  <td class="muted">{when(a.seen_at)}</td>
                  <td>{#if a.online}<span class="ok">в мире</span>{:else if a.locked}<span class="bad">заблокирован ещё {minutes(a.locked)}</span>{:else}<span class="muted">—</span>{/if}</td>
                  <td class="end">
                    {#if a.locked}<button class="btn ghost tiny" disabled={busy || !allowed("players")} title={why("players")} onclick={() => unlock(a)}>Разблокировать</button>{/if}
                    {#if a.online}<button class="btn ghost tiny" disabled={busy || !allowed("players")} title={why("players")} onclick={() => kick(a)}>Выбросить</button>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      <div class="block">
        <div class="row-head">
          <b>Ключи</b>
          <span class="spacer"></span>
          <button class="btn ghost tiny" disabled={!card.accounts.length || !allowed("keys")} title={why("keys") || (!card.accounts.length ? "У игрока нет учёток." : "")}
                  onclick={() => { keyAccount = card?.accounts[0]?.id ?? null; keySlug = ""; dialog = "key"; }}>+ Выдать ключ</button>
        </div>
        {#if !card.keys.length}
          <p class="muted small">В папках секретов его учёток ключей нет.</p>
        {:else}
          <table class="grid">
            <tbody>
              {#each card.keys as k (k.account + k.name)}
                <tr>
                  <td class="mono">{k.slug}</td>
                  <td class="muted">{k.login}@{k.hostname} · {k.name}</td>
                  <td class="end"><button class="btn ghost tiny danger" disabled={busy || !allowed("keys")} title={why("keys")} onclick={() => takeKey(k)}>Забрать</button></td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      <div class="block">
        <b>Изменённые файлы</b>
        {#if !card.machines.length}
          <p class="muted small">Игрок ничего не менял: видит мир как есть.</p>
        {:else}
          <p class="muted small">{card.machines.map((m) => `${m.hostname}: ${m.count}`).join(" · ")}</p>
          <table class="grid">
            <tbody>
              {#each card.files as f, i (i)}
                <tr><td class="mono">{f.hostname}:{f.path}</td><td class="muted">{f.kind}</td><td class="muted end">{when(f.at)}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      <div class="block">
        <b>Журнал игрока</b>
        {#if !card.journal.length}
          <p class="muted small">Пока ничего: здесь появятся ключи, файлы, слои, письма персонажам, эфир, форум и входы.</p>
        {:else}
          <table class="grid">
            <tbody>
              {#each card.journal as e, i (i)}
                <tr><td class="muted">{when(e.at)}</td><td>{e.text}</td><td class="mono">{e.where}</td><td class="muted">{e.source}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>

      <div class="block">
        <b>Журнал входов</b>
        {#if !card.events.length}
          <p class="muted small">Записей нет (журнал хранится 30 дней).</p>
        {:else}
          <table class="grid">
            <tbody>
              {#each card.events as e, i (i)}
                <tr><td class="muted">{when(e.at)}</td><td>{e.label}</td><td class="mono">{e.login}@{e.hostname}</td><td class="muted">{e.source}{e.detail ? ` · ${e.detail}` : ""}</td></tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    </section>
  {/if}
</ListDetail>

{#if dialog === "key" && card}
  <Dialog title="Выдать ключ" confirm="Выдать" {busy} disabled={keyAccount === null || !keySlug} onsubmit={giveKey} onclose={() => (dialog = null)}>
    <label><span class="label">Учётка (в её папку секретов)</span>
      <select class="field" bind:value={keyAccount}>
        {#each card.accounts as a (a.id)}<option value={a.id}>{a.login}@{a.hostname}</option>{/each}
      </select></label>
    <label><span class="label">Ключ</span>
      <select class="field" bind:value={keySlug}>
        <option value="" disabled>выберите ключ</option>
        {#each keys as k (k.slug)}<option value={k.slug}>{k.slug}{k.description ? ` — ${k.description}` : ""}</option>{/each}
      </select></label>
    <p class="muted small">Ключ появится только у этого игрока. Остальные его не увидят.</p>
  </Dialog>
{/if}

{#if dialog === "reset" && card}
  <Dialog title="Сбросить прогресс" confirm="Дальше" danger {busy} onsubmit={reset} onclose={() => (dialog = null)}>
    <label><span class="label">Где</span>
      <select class="field" bind:value={resetMachine}>
        <option value={null}>на всех машинах</option>
        {#each card.machines as m (m.machine)}<option value={m.machine}>{m.hostname} (файлов: {m.count})</option>{/each}
      </select></label>
  </Dialog>
{/if}

<style>
  .find { margin: 0 8px 6px; width: auto; }
  .only { display: flex; align-items: center; gap: 6px; margin: 0 10px 8px; font-size: 12.5px; color: var(--muted); }
  .small { font-size: 12px; margin: 0; }
  .pad { padding: 6px 10px; }
  .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--ok, #6fcf97); margin-right: 6px; vertical-align: middle; }
  .tag { margin-left: 6px; padding: 1px 6px; border-radius: 999px; background: var(--accent-soft); font-size: 11px; font-weight: 500; }
  .tag.bad { background: none; border: 1px solid var(--danger); color: var(--danger); }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; max-width: 860px; }
  .top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .big { font-size: 18px; }
  .spacer { flex: 1; }
  .banner { margin: 0; padding: 8px 12px; border: 1px solid var(--danger); border-radius: var(--radius-s); color: var(--danger); }
  .block { display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .row-head { display: flex; align-items: center; gap: 6px; }
  .tiny { padding: 2px 8px; font-size: 12px; }
  .grid { width: 100%; border-collapse: collapse; }
  .grid th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; padding: 5px 8px; border-bottom: 1px solid var(--line-soft); }
  .grid td { padding: 5px 8px; border-bottom: 1px solid var(--line-soft); overflow-wrap: anywhere; }
  .grid tr:last-child td { border-bottom: 0; }
  .grid .end { text-align: right; white-space: nowrap; }
  .ok { color: var(--ok, #6fcf97); }
  .bad { color: var(--danger); }
  .empty { padding: 20px; }
</style>
