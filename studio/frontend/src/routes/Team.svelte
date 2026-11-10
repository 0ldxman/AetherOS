<script lang="ts">
  // Команда авторов: кто в ней и с какой ролью, и сами роли (уровень по разделам, опасные действия).
  // Смотрят все авторы, правит только суперадмин.
  import { onMount, untrack } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import ListDetail from "../lib/ListDetail.svelte";
  import { ask } from "../lib/confirm.svelte";
  import { guardUnsaved } from "../lib/guard.svelte";
  import { isSuper } from "../lib/me.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";
  import DraftState from "../lib/DraftState.svelte";
  import { SharedForm } from "../lib/shared.svelte";

  let { role: roleId }: { role: number | null } = $props();

  let team = $state<Schemas["TeamOut"] | null>(null);
  let form = $state<Schemas["TeamRoleIn"]>({ name: "", note: "", sections: {}, actions: [] });
  let saved = $state("");
  let busy = $state(false);
  let dialog = $state<null | "role" | "author">(null);
  let newName = $state("");
  let query = $state("");
  let found = $state<Schemas["TeamCandidate"][]>([]);
  let pickRole = $state<number | null>(null);

  const editable = $derived(isSuper());
  const role = $derived(team?.roles.find((r) => r.id === roleId) ?? null);
  const dirty = $derived(!!role && JSON.stringify(form) !== saved);
  guardUnsaved(() => dirty && !share.ready);                 // в совместном режиме черновик на сервере
  let base = $state<Schemas["TeamRoleIn"] | null>(null);
  // общий черновик роли (суперадмин правит, остальные видят его правки вживую)
  const share = new SharedForm({ room: () => `team/roles/${roleId}`, texts: ["name", "note"], draft: () => form, base: () => base, onRemoteSave: () => load() });
  const roleName = (id: number | null | undefined) => team?.roles.find((r) => r.id === id)?.name ?? "без роли";

  async function load() { team = (await api.GET("/studio/api/team")).data ?? null; }
  onMount(load);

  $effect(() => {
    if (role) {
      const next = { name: role.name, note: role.note, sections: { ...role.sections }, actions: [...role.actions] };
      if (!untrack(() => share.ready) || untrack(() => base?.name) === undefined) form = JSON.parse(JSON.stringify(next));
      saved = JSON.stringify(next);
      base = JSON.parse(saved);
    }
  });

  function toggleAction(name: string, on: boolean) {
    form.actions = on ? [...form.actions, name] : form.actions.filter((a) => a !== name);
  }

  function setAll(levelName: string) {
    for (const s of team?.sections ?? []) form.sections[s.name] = levelName;
  }

  async function saveRole() {
    if (!role) return;
    busy = true;
    const { error } = await api.PUT("/studio/api/team/roles/{role_id}", { params: { path: { role_id: role.id } }, body: $state.snapshot(form) });
    busy = false;
    if (error) return toast(problem(error, "Роль не сохранилась."), "error");
    share.markSaved();
    toast("Роль сохранена.");
    await load();
  }

  async function createRole() {
    busy = true;
    const sections = Object.fromEntries((team?.sections ?? []).map((s) => [s.name, "read"]));
    const { data, error } = await api.POST("/studio/api/team/roles", { body: { name: newName.trim(), note: "", sections, actions: [] } });
    busy = false;
    if (error || !data) return toast(problem(error, "Роль не создалась."), "error");
    dialog = null;
    newName = "";
    await load();
    go(`/team/roles/${data.id}`);
  }

  async function removeRole() {
    if (!role) return;
    const text = role.authors ? `Её авторы (${role.authors}) останутся без роли и смогут только смотреть.` : "У роли нет авторов.";
    if (!(await ask(`Удалить роль «${role.name}»?`, text, "Удалить роль"))) return;
    const { error } = await api.DELETE("/studio/api/team/roles/{role_id}", { params: { path: { role_id: role.id } } });
    if (error) return toast(problem(error), "error");
    toast("Роль удалена.");
    await load();
    go("/team");
  }

  async function setRole(user: Schemas["TeamAuthor"], value: string) {
    const { error } = await api.PUT("/studio/api/team/authors/{user_id}", { params: { path: { user_id: user.id } }, body: { role: value ? +value : null } });
    if (error) return toast(problem(error), "error");
    toast(`Роль ${user.username}: ${roleName(value ? +value : null)}.`);
    await load();
  }

  async function removeAuthor(user: Schemas["TeamAuthor"]) {
    if (!(await ask(`Убрать ${user.username} из команды?`, "Он останется игроком и потеряет доступ к Студии.", "Убрать из команды"))) return;
    const { error } = await api.DELETE("/studio/api/team/authors/{user_id}", { params: { path: { user_id: user.id } } });
    if (error) return toast(problem(error), "error");
    toast(`${user.username} больше не в команде.`);
    await load();
  }

  async function search() {
    found = (await api.GET("/studio/api/team/candidates", { params: { query: { q: query.trim() } } })).data ?? [];
  }
  $effect(() => { if (dialog === "author") { query; search(); } });

  async function addAuthor(user: Schemas["TeamCandidate"]) {
    const { error } = await api.PUT("/studio/api/team/authors/{user_id}", { params: { path: { user_id: user.id } }, body: { role: pickRole } });
    if (error) return toast(problem(error), "error");
    toast(`${user.username} теперь в команде.`);
    dialog = null;
    query = "";
    await load();
  }

  const when = (value: string | null | undefined) => value ? new Date(value).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" }) : "не входил";
</script>

<ListDetail title="Команда">
  {#snippet list()}
    <a class="item" class:on={roleId === null} href="#/team"><b>Авторы</b><span class="muted small">{team?.authors.length ?? "…"} в команде</span></a>
    <p class="group muted">Роли</p>
    {#each team?.roles ?? [] as item (item.id)}
      <a class="item" class:on={item.id === roleId} href="#/team/roles/{item.id}">
        <b>{item.name}</b><span class="muted small">{item.authors ? `авторов: ${item.authors}` : "без авторов"}</span>
      </a>
    {/each}
  {/snippet}
  {#snippet add()}
    {#if editable}<button class="btn add" onclick={() => (dialog = "role")}>+ Роль</button>{/if}
  {/snippet}

  {#if !team}
    <p class="muted empty">Загрузка…</p>
  {:else if roleId === null}
    <section class="editor wide">
      <header class="top">
        <b class="big">Авторы</b>
        <span class="spacer"></span>
        {#if editable}<button class="btn primary" onclick={() => { pickRole = team?.roles[0]?.id ?? null; dialog = "author"; }}>+ Автор</button>{/if}
      </header>
      {#if !editable}<p class="muted small">Состав команды и роли меняет только суперадмин.</p>{/if}
      <table class="grid">
        <thead><tr><th>Автор</th><th>Роль</th><th>Последний вход</th><th></th></tr></thead>
        <tbody>
          {#each team.authors as user (user.id)}
            <tr>
              <td><b>{user.username}</b></td>
              <td>
                {#if user.superuser}
                  <span class="badge">Суперадмин</span>
                {:else if editable}
                  <select class="field" value={user.role ?? ""} onchange={(e) => setRole(user, e.currentTarget.value)} aria-label="Роль {user.username}">
                    <option value="">без роли (только смотреть)</option>
                    {#each team.roles as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
                  </select>
                {:else}
                  {roleName(user.role)}
                {/if}
              </td>
              <td class="muted">{when(user.last_login)}</td>
              <td class="end">{#if editable && !user.superuser}<button class="btn ghost danger" onclick={() => removeAuthor(user)}>Убрать</button>{/if}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </section>
  {:else if role}
    <section class="editor wide">
      <header class="top">
        {#if editable}<input class="field big-field" bind:value={form.name} aria-label="Название роли" />{:else}<b class="big">{role.name}</b>{/if}
        <span class="spacer"></span>
        {#if editable}
          <button class="btn ghost danger" onclick={removeRole}>Удалить</button>
          <DraftState {share} {dirty} saved="" />
          <button class="btn primary" disabled={!dirty || busy || !form.name.trim()} onclick={saveRole}>Сохранить</button>
        {/if}
      </header>
      <label><span class="label">Заметка</span><textarea class="field" rows="2" bind:value={form.note} disabled={!editable} placeholder="Для кого эта роль"></textarea></label>

      <div class="block">
        <div class="row-head">
          <b>Разделы</b>
          <span class="spacer"></span>
          {#if editable}
            <span class="muted small">Всем:</span>
            {#each Object.entries(team.levels) as [code, label]}<button class="btn ghost tiny" onclick={() => setAll(code)}>{label}</button>{/each}
          {/if}
        </div>
        <table class="grid levels">
          <thead><tr><th>Раздел</th>{#each Object.values(team.levels) as label}<th class="c">{label}</th>{/each}</tr></thead>
          <tbody>
            {#each team.sections as section (section.name)}
              <tr>
                <td>{section.label}</td>
                {#each Object.keys(team.levels) as code}
                  <td class="c"><input type="radio" name="lvl-{section.name}" value={code} bind:group={form.sections[section.name]} disabled={!editable} aria-label="{section.label}: {team.levels[code]}" /></td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <div class="block">
        <b>Опасные действия</b>
        <p class="muted small">Нужны вдобавок к праву «править» в разделе.</p>
        {#each team.actions as action (action.name)}
          <label class="check"><input type="checkbox" checked={form.actions.includes(action.name)} disabled={!editable} onchange={(e) => toggleAction(action.name, e.currentTarget.checked)} /> {action.label}</label>
        {/each}
      </div>
    </section>
  {:else}
    <p class="muted empty">Такой роли нет.</p>
  {/if}
</ListDetail>

{#if dialog === "role"}
  <Dialog title="Новая роль" confirm="Создать" {busy} disabled={!newName.trim()} onsubmit={createRole} onclose={() => (dialog = null)}>
    <label><span class="label">Название</span><input class="field" placeholder="Сценарист" bind:value={newName} /></label>
    <p class="muted small">Новая роль видит все разделы, но ничего не правит. Права настроите после создания.</p>
  </Dialog>
{/if}

{#if dialog === "author"}
  <Dialog title="Добавить автора" confirm="Готово" onsubmit={() => (dialog = null)} onclose={() => (dialog = null)}>
    <label><span class="label">Роль</span>
      <select class="field" bind:value={pickRole}>
        <option value={null}>без роли (только смотреть)</option>
        {#each team?.roles ?? [] as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
      </select></label>
    <label><span class="label">Пользователь</span><input class="field" placeholder="Имя игрока" bind:value={query} /></label>
    <div class="found">
      {#each found as user (user.id)}
        <button type="button" class="pick" onclick={() => addAuthor(user)}><b>{user.username}</b><span class="muted small">добавить</span></button>
      {:else}
        <p class="muted small">Никого не нашлось. Автором становится тот, кто хоть раз входил в игру.</p>
      {/each}
    </div>
  </Dialog>
{/if}

<style>
  .small { font-size: 12px; margin: 0; }
  .group { margin: 14px 10px 4px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; }
  .editor { display: flex; flex-direction: column; gap: 12px; padding: 16px 20px 32px; min-width: 0; }
  .editor.wide { max-width: 820px; }
  .top { display: flex; align-items: center; gap: 12px; }
  .big { font-size: 18px; }
  .big-field { font-size: 16px; font-weight: 600; max-width: 360px; }
  .spacer { flex: 1; }
  .block { display: flex; flex-direction: column; gap: 8px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  .row-head { display: flex; align-items: center; gap: 6px; }
  .tiny { padding: 2px 8px; font-size: 12px; }
  .grid { width: 100%; border-collapse: collapse; }
  .grid th { text-align: left; font-weight: 500; color: var(--muted); font-size: 12px; padding: 6px 8px; border-bottom: 1px solid var(--line-soft); }
  .grid td { padding: 6px 8px; border-bottom: 1px solid var(--line-soft); }
  .grid .c { text-align: center; width: 90px; }
  .grid .end { text-align: right; }
  .levels td:first-child { width: auto; }
  .check { display: flex; align-items: center; gap: 8px; }
  .badge { padding: 2px 8px; border-radius: 999px; background: var(--accent-soft); font-size: 12px; }
  .found { display: flex; flex-direction: column; gap: 4px; max-height: 260px; overflow-y: auto; }
  .pick { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: none; color: var(--text); cursor: pointer; text-align: left; }
  .pick:hover { background: var(--panel-2); }
  .empty { padding: 20px; }
</style>
