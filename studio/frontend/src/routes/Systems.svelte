<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  type System = Schemas["SystemOut"];
  type Row = Schemas["TypeGroup"];

  let { code }: { code: string | null } = $props();

  let rows = $state<Schemas["SystemRow"][]>([]);
  let system = $state<System | null>(null);
  let props_ = $state({ name: "", path_style: "unix", entry_policy: null as number | null });
  let places = $state<Record<string, string>>({});
  let placesSaved = $state("");
  let propsSaved = $state("");
  let dialog = $state<null | "type" | "group" | "place">(null);
  let draft = $state({ code: "", name: "", group: "", place: "" });
  let errors = $state<Record<string, string[]>>({});

  const current = $derived(code ?? rows[0]?.code ?? null);
  const placesDirty = $derived(JSON.stringify(places) !== placesSaved);
  const propsDirty = $derived(JSON.stringify(props_) !== propsSaved);

  async function list() {
    rows = (await api.GET("/studio/api/systems")).data ?? [];
  }

  function fill(data: System) {
    system = data;
    props_ = { name: data.name, path_style: data.path_style, entry_policy: data.entry_policy ?? null };
    propsSaved = JSON.stringify(props_);
    places = Object.fromEntries(data.places.map((row) => [row.name, row.path]));
    placesSaved = JSON.stringify(places);
    errors = {};
  }

  async function load(target: string | null) {
    system = null;
    if (target === null) return;
    const { data } = await api.GET("/studio/api/systems/{code}", { params: { path: { code: target } } });
    if (data) fill(data);
  }

  onMount(list);
  $effect(() => { load(current); });

  function done(data: System | undefined, error: unknown, text: string) {
    if (error || !data) {
      errors = (error as { fields?: Record<string, string[]> } | undefined)?.fields ?? {};
      return toast(problem(error, "Не сохранилось."), "error");
    }
    fill(data);
    toast(text);
    list();
  }

  async function saveProps() {
    if (!system) return;
    const { data, error } = await api.PUT("/studio/api/systems/{code}", { params: { path: { code: system.code } }, body: props_ });
    done(data, error, "Тип сохранён.");
  }

  async function savePlaces() {
    if (!system) return;
    const { data, error } = await api.PUT("/studio/api/systems/{code}/places", { params: { path: { code: system.code } }, body: { places } });
    done(data, error, "Пути сохранены.");
  }

  async function putGroup(row: { name: string }, privileges: string[], everyone: boolean) {
    if (!system) return;
    const { data, error } = await api.PUT("/studio/api/systems/{code}/groups/{name}", {
      params: { path: { code: system.code, name: row.name } }, body: { privileges, everyone },
    });
    done(data, error, "Группа сохранена.");
  }

  function toggle(row: Row, privilege: string) {
    putGroup(row, row.privileges.includes(privilege) ? row.privileges.filter((p) => p !== privilege) : [...row.privileges, privilege], row.everyone);
  }

  async function dropGroup(row: Row) {
    if (!system) return;
    const { data, error } = await api.DELETE("/studio/api/systems/{code}/groups/{name}", { params: { path: { code: system.code, name: row.name } } });
    done(data, error, `Группа ${row.name} удалена.`);
  }

  async function createType() {
    const { data, error } = await api.POST("/studio/api/systems", { body: { code: draft.code, name: draft.name } });
    if (error || !data) return toast(problem(error, "Тип не создался."), "error");
    dialog = null;
    await list();
    go(`/systems/${data.code}`);
  }

  function addGroup() {
    putGroup({ name: draft.group.trim() }, [], false);
    dialog = null;
    draft.group = "";
  }

  function addPlace() {
    places = { ...places, [draft.place.trim()]: "" };
    if (system) system.places = [...system.places, { name: draft.place.trim(), path: "", default: "", machines: [] }];
    dialog = null;
    draft.place = "";
  }
</script>

<div class="split">
  <aside class="list">
    <h1>Типы систем</h1>
    {#each rows as row (row.code)}
      <a class="item" class:on={row.code === current} href="#/systems/{row.code}">
        <b class="mono">{row.code}</b>
        <span class="muted small">{row.name} · машин {row.machines}</span>
      </a>
    {/each}
    <button class="btn add" onclick={() => (dialog = "type")}>+ Тип</button>
  </aside>

  {#if system}
    <section class="editor">
      <header class="top">
        <h2 class="mono">{system.code}</h2>
        <span class="muted">{system.machines.length ? `машины: ${system.machines.join(", ")}` : "машин этого типа нет"}</span>
      </header>

      <div class="block">
        <h3>Свойства</h3>
        <div class="three">
          <label><span class="label">Название</span><input class="field" bind:value={props_.name} /></label>
          <label><span class="label">Диалект путей</span>
            <select class="field" bind:value={props_.path_style}>
              <option value="unix">Unix (/home/ivan)</option><option value="windows">Windows (C:\Users\ivan)</option>
            </select>
          </label>
          <label><span class="label">Политика входа</span>
            <select class="field" bind:value={props_.entry_policy}>
              <option value={null}>без ограничений</option>
              {#each system.policies as policy}<option value={policy.id}>{policy.name}</option>{/each}
            </select>
          </label>
        </div>
        <div><button class="btn primary" disabled={!propsDirty} onclick={saveProps}>Сохранить</button></div>
      </div>

      <div class="block">
        <h3>Группы типа <button class="btn ghost" onclick={() => (dialog = "group")}>+ Группа</button></h3>
        {#if system.groups.some((row) => row.source === "default")}
          <p class="muted small">Своих групп у типа нет: действуют группы движка по умолчанию. Первая правка запишет их в тип.</p>
        {/if}
        <div class="matrix" style:--cols={system.privileges.length}>
          <div class="cell head">Группа</div>
          {#each system.privileges as privilege}<div class="cell head mono" title={privilege.label}>{privilege.code}</div>{/each}
          <div class="cell head">Все</div>
          <div class="cell head">Переопределена на</div>
          <div class="cell head"></div>
          {#each system.groups as row (row.name)}
            <div class="cell"><b class="mono">{row.name}</b>{#if row.source === "default"}<span class="chip">движок</span>{/if}</div>
            {#each system.privileges as privilege}
              <button class="cell tick" class:on={row.privileges.includes(privilege.code)} title={privilege.label} onclick={() => toggle(row, privilege.code)}>
                {row.privileges.includes(privilege.code) ? "●" : "·"}
              </button>
            {/each}
            <button class="cell tick" class:on={row.everyone} onclick={() => putGroup(row, row.privileges, !row.everyone)}>{row.everyone ? "да" : "—"}</button>
            <div class="cell muted small mono">{row.machines.join(", ") || "—"}</div>
            <div class="cell acts"><button class="btn ghost danger" onclick={() => dropGroup(row)}>Удалить</button></div>
          {/each}
        </div>
      </div>

      <div class="block">
        <h3>Системные пути <button class="btn ghost" onclick={() => (dialog = "place")}>+ Путь</button></h3>
        <p class="muted small">Шаблоны путей для машин типа: {"{login}"} — логин учётки, {"{home}"} — место home. Пусто: как у движка.</p>
        <div class="places">
          {#each system.places as row (row.name)}
            <span class="mono pname">{row.name}</span>
            <input class="field mono" bind:value={places[row.name]} placeholder={row.default || "—"} class:bad={errors[row.name]} />
            <span class="muted small">{row.machines.length ? `своё у ${row.machines.join(", ")}` : ""}{errors[row.name] ? errors[row.name].join(" ") : ""}</span>
          {/each}
        </div>
        <div><button class="btn primary" disabled={!placesDirty} onclick={savePlaces}>Сохранить пути</button></div>
      </div>
    </section>
  {:else}
    <p class="muted empty">{rows.length ? "Загрузка…" : "Типов пока нет."}</p>
  {/if}
</div>

{#if dialog === "type"}
  <Dialog title="Новый тип системы" confirm="Создать" onsubmit={createType} onclose={() => (dialog = null)}>
    <input class="field mono" placeholder="КОД (латиницей, по нему выбираются сцены и команды)" bind:value={draft.code} />
    <input class="field" placeholder="название" bind:value={draft.name} />
  </Dialog>
{:else if dialog === "group"}
  <Dialog title="Новая группа типа" confirm="Создать" onsubmit={addGroup} onclose={() => (dialog = null)}>
    <input class="field mono" placeholder="имя (латиницей)" bind:value={draft.group} />
  </Dialog>
{:else if dialog === "place"}
  <Dialog title="Новый системный путь" confirm="Добавить" onsubmit={addPlace} onclose={() => (dialog = null)}>
    <input class="field mono" placeholder="имя места (латиницей)" bind:value={draft.place} />
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
  .editor { display: flex; flex-direction: column; gap: 14px; padding: 16px 20px 32px; min-width: 0; }
  .top { display: flex; align-items: baseline; gap: 12px; }
  .top h2 { margin: 0; font-size: 20px; }
  .block { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line-soft); border-radius: var(--radius); background: var(--panel); }
  h3 { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }
  h3 .btn { margin-left: auto; text-transform: none; letter-spacing: 0; }
  .three { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .matrix { display: grid; grid-template-columns: 150px repeat(var(--cols), minmax(52px, 1fr)) 48px minmax(120px, 1fr) max-content; border: 1px solid var(--line-soft); border-radius: var(--radius-s); overflow: hidden; }
  .cell { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--line-soft); min-height: 38px; }
  .cell.head { color: var(--muted); font-size: 12px; background: var(--panel-2); }
  .tick { justify-content: center; border: 0; border-bottom: 1px solid var(--line-soft); background: none; cursor: pointer; color: var(--faint); }
  .tick:hover { background: var(--panel-2); }
  .tick.on { color: var(--ok); }
  .acts { justify-content: flex-end; }
  .places { display: grid; grid-template-columns: 120px minmax(240px, 420px) 1fr; gap: 8px 12px; align-items: center; }
  .pname { color: var(--muted); }
  .field.bad { border-color: var(--danger); }
  .empty { padding: 24px; }
</style>
