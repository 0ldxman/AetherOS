<script lang="ts">
  import { onMount } from "svelte";
  import { api, problem, type Schemas } from "../lib/api";
  import Dialog from "../lib/Dialog.svelte";
  import { go } from "../lib/router.svelte";
  import { toast } from "../lib/toast.svelte";

  type System = Schemas["SystemOut"];
  type Row = Schemas["TypeGroup"];

  let { code, tab }: { code: string | null; tab: string } = $props();

  let rows = $state<Schemas["SystemRow"][]>([]);
  let system = $state<System | null>(null);
  let props_ = $state({ code: "", greeting: "", name: "", path_style: "unix", entry_policy: null as number | null });
  let places = $state<Record<string, string>>({});
  let placesSaved = $state("");
  let propsSaved = $state("");
  let dialog = $state<null | "type" | "group" | "place">(null);
  let layer = $state<null | { id: number | null; volume: number | null; volume_path: string; mount_path: string; order: number }>(null);
  let draft = $state({ code: "", name: "", group: "", place: "" });
  let errors = $state<Record<string, string[]>>({});

  const TABS = [
    { key: "overview", label: "Обзор" },
    { key: "paths", label: "Системные пути" },
    { key: "disk", label: "Образ системного диска" },
    { key: "groups", label: "Группы и политики" },
  ];
  const SHOWN = 8;
  let showMachines = $state(false);

  let preview = $state<Schemas["GreetingPreview"] | null>(null);
  let previewTimer: ReturnType<typeof setTimeout>;
  const STYLE_COLOR: Record<string, string> = { dim: "var(--faint)", success: "var(--ok)", warning: "var(--warn)", error: "var(--danger)" };

  async function showPreview() {
    if (!system) return;
    const { data } = await api.POST("/studio/api/systems/{code}/greeting/preview", { params: { path: { code: system.code } }, body: { greeting: props_.greeting } });
    preview = data ?? null;
  }

  $effect(() => {
    props_.greeting;
    clearTimeout(previewTimer);
    previewTimer = setTimeout(showPreview, 300);
    return () => clearTimeout(previewTimer);
  });

  function insert(name: string) {
    props_.greeting += `{${name}}`;
  }

  const current = $derived(code ?? rows[0]?.code ?? null);
  const placesDirty = $derived(JSON.stringify(places) !== placesSaved);
  const propsDirty = $derived(JSON.stringify(props_) !== propsSaved);

  async function list() {
    rows = (await api.GET("/studio/api/systems")).data ?? [];
  }

  function fill(data: System) {
    system = data;
    props_ = { code: data.code, greeting: data.greeting, name: data.name, path_style: data.path_style, entry_policy: data.entry_policy ?? null };
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
    const before = system.code;
    const { data, error } = await api.PUT("/studio/api/systems/{code}", { params: { path: { code: before } }, body: props_ });
    done(data, error, "ОС сохранена.");
    if (data && data.code !== before) go(`/systems/${data.code}/${tab}`);
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

  function editLayer(row: Schemas["ImageRow"] | null) {
    errors = {};
    layer = row
      ? { id: row.id, volume: row.volume.id, volume_path: row.volume_path, mount_path: row.mount_path, order: row.order }
      : { id: null, volume: null, volume_path: "", mount_path: "/", order: 0 };
  }

  async function saveLayer() {
    if (!system || !layer || layer.volume === null) return;
    const { id, ...body } = layer;
    const params = { path: { code: system.code } };
    const { data, error } = id === null
      ? await api.POST("/studio/api/systems/{code}/image", { params, body: { ...body, volume: layer.volume } })
      : await api.PUT("/studio/api/systems/{code}/image/{row_id}", { params: { path: { ...params.path, row_id: id } }, body: { ...body, volume: layer.volume } });
    done(data, error, "Образ сохранён.");
    if (data) layer = null;
  }

  async function dropLayer(row: Schemas["ImageRow"]) {
    if (!system) return;
    const { data, error } = await api.DELETE("/studio/api/systems/{code}/image/{row_id}", { params: { path: { code: system.code, row_id: row.id } } });
    done(data, error, "Том убран из образа.");
  }

  async function createType() {
    const { data, error } = await api.POST("/studio/api/systems", { body: { code: draft.code, name: draft.name } });
    if (error || !data) return toast(problem(error, "ОС не создалась."), "error");
    dialog = null;
    await list();
    go(`/systems/${data.code}/overview`);
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
    <h1>Операционные системы</h1>
    {#each rows as row (row.code)}
      <a class="item" class:on={row.code === current} href="#/systems/{row.code}/{tab}">
        <b class="mono">{row.code}</b>
        <span class="muted small">{row.name} · машин {row.machines}</span>
      </a>
    {/each}
    <button class="btn add" onclick={() => (dialog = "type")}>+ Операционная система</button>
  </aside>

  {#if system}
    <section class="editor">
      <header class="top">
        <h2 class="mono">{system.code}</h2>
        <span class="muted">{system.name}</span>
        <span class="spacer"></span>
        <span class="machines" role="group" onmouseenter={() => (showMachines = true)} onmouseleave={() => (showMachines = false)}>
          <span class="chip">{system.machines.length} {system.machines.length === 1 ? "машина" : "машин"}</span>
          {#if showMachines && system.machines.length}
            <div class="pop">
              {#each system.machines.slice(0, SHOWN) as host}<span class="mono">{host || "без хоста"}</span>{/each}
              {#if system.machines.length > SHOWN}<span class="muted small">и ещё {system.machines.length - SHOWN} машин</span>{/if}
            </div>
          {/if}
        </span>
      </header>

      <nav class="tabs">
        {#each TABS as item}
          <a class="tab" class:on={tab === item.key} href="#/systems/{system.code}/{item.key}">{item.label}</a>
        {/each}
      </nav>

      {#if tab === "paths"}
      <div class="block">
        <h3>Системные пути <button class="btn ghost" onclick={() => (dialog = "place")}>+ Путь</button></h3>
        <p class="muted small">Шаблоны путей для машин ОС: {"{login}"} — логин учётки, {"{home}"} — место home. Пусто: как у движка.</p>
        <div class="places">
          {#each system.places as row (row.name)}
            <span class="mono pname">{row.name}</span>
            <input class="field mono" bind:value={places[row.name]} placeholder={row.default || "—"} class:bad={errors[row.name]} />
            <span class="muted small">{row.machines.length ? `своё у ${row.machines.join(", ")}` : ""}{errors[row.name] ? errors[row.name].join(" ") : ""}</span>
          {/each}
        </div>
        <div><button class="btn primary" disabled={!placesDirty} onclick={savePlaces}>Сохранить пути</button></div>
      </div>
      {:else if tab === "disk"}
        <div class="block">
          <h3>Образ системного диска <button class="btn ghost" onclick={() => editLayer(null)}>+ Том</button></h3>
          <p class="muted small">Тома, которые получают все машины ОС ({system.machines.length}). Лежат под монтированиями самой машины: на одну точку они складываются стопкой, файлы машины перекрывают файлы образа.</p>
          {#each system.image as row (row.id)}
            <div class="layer">
              <span class="mono point">{row.mount_path}</span><span class="muted">←</span>
              <span>{row.volume.label}{#if row.volume_path}<span class="mono muted"> /{row.volume_path}</span>{/if}</span>
              {#if row.order}<span class="chip">слой {row.order}</span>{/if}
              <span class="spacer"></span>
              <button class="btn ghost" onclick={() => editLayer(row)}>Изменить</button>
              <button class="btn ghost danger" onclick={() => dropLayer(row)}>Убрать</button>
            </div>
          {:else}
            <p class="muted">Образа нет: у машин только их собственные тома.</p>
          {/each}
        </div>
      {:else if tab === "groups"}
      <div class="block">
        <h3>Политика входа</h3>
        <label><span class="label">Политика входа</span>
            <select class="field" bind:value={props_.entry_policy}>
              <option value={null}>без ограничений</option>
              {#each system.policies as policy}<option value={policy.id}>{policy.name}</option>{/each}
            </select>
          </label>
        <div><button class="btn primary" disabled={!propsDirty} onclick={saveProps}>Сохранить</button></div>
      </div>

      <div class="block">
        <h3>Группы ОС <button class="btn ghost" onclick={() => (dialog = "group")}>+ Группа</button></h3>
        {#if system.groups.some((row) => row.source === "default")}
          <p class="muted small">Своих групп у ОС нет: действуют группы движка по умолчанию. Первая правка запишет их в ОС.</p>
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
      {:else}
      <div class="block">
        <h3>Свойства</h3>
        <div class="three">
          <label><span class="label">Код</span><input class="field mono" bind:value={props_.code} /></label>
          <label><span class="label">Название</span><input class="field" bind:value={props_.name} /></label>
          <label><span class="label">Диалект путей</span>
            <select class="field" bind:value={props_.path_style}>
              <option value="unix">Unix (/home/ivan)</option><option value="windows">Windows (C:\Users\ivan)</option>
            </select>
          </label>
        </div>
        {#if props_.code.trim().toUpperCase() !== system.code}
          <p class="warn small">Код выбирает сцены и команды в Python. Машины ({system.machines.length}) переедут на новый код, но без сцен под него в движке будет поведение по умолчанию.</p>
        {/if}
        <div><button class="btn primary" disabled={!propsDirty} onclick={saveProps}>Сохранить</button></div>
      </div>
        <div class="block">
          <h3>Приветствие при подключении</h3>
          <p class="muted small">Что видит игрок, когда открывается оболочка этой ОС. Пусто: общее приветствие движка. Цвета: <code>&lt;dim&gt;</code>, <code>&lt;success&gt;</code>, <code>&lt;warning&gt;</code>, <code>&lt;error&gt;</code> (закрываются в той же строке). Случайное число: <code>&lt;random&gt;21-41&lt;/random&gt;</code>. Скобки: <code>{"{{"}</code> и <code>{"}}"}</code>.</p>
          <div class="greet">
            <div class="col">
              <textarea class="field mono" rows="14" spellcheck="false" bind:value={props_.greeting} class:bad={errors.greeting}></textarea>
              <div class="chips">
                {#each system.greeting_params as param}
                  <button class="chip mono" title={param.label} onclick={() => insert(param.name)}>{"{"}{param.name}{"}"}</button>
                {/each}
              </div>
            </div>
            <div class="col">
              <pre class="term">{#each preview?.lines ?? [] as line}{#each line as part}<span style:color={part.style ? STYLE_COLOR[part.style] : null}>{part.text}</span>{/each}
{/each}</pre>
              <p class="muted small">{preview?.machine ? `Значения с машины ${preview.machine}.` : "Машин у ОС нет: значения условные."}</p>
              {#each preview?.errors ?? [] as error}<p class="warn small">Строка {error.line}: {error.text}</p>{/each}
            </div>
          </div>
          <div><button class="btn primary" disabled={!propsDirty} onclick={saveProps}>Сохранить</button></div>
        </div>
      {/if}
    </section>
  {:else}
    <p class="muted empty">{rows.length ? "Загрузка…" : "Типов пока нет."}</p>
  {/if}
</div>

{#if layer}
  <Dialog title={layer.id === null ? "Том в образе" : "Изменить том образа"} confirm="Сохранить" onsubmit={saveLayer} onclose={() => (layer = null)}>
    <select class="field" bind:value={layer.volume}>
      <option value={null}>— том —</option>
      {#each system?.volumes ?? [] as volume}<option value={volume.id}>{volume.label}</option>{/each}
    </select>
    <input class="field mono" placeholder="папка тома (пусто: весь том)" bind:value={layer.volume_path} />
    <input class="field mono" placeholder="точка монтирования: /" bind:value={layer.mount_path} />
    <input class="field" type="number" min="0" placeholder="порядок" bind:value={layer.order} />
    {#each Object.values(errors).flat() as text}<p class="warn small">{text}</p>{/each}
  </Dialog>
{/if}
{#if dialog === "type"}
  <Dialog title="Новая операционная система" confirm="Создать" onsubmit={createType} onclose={() => (dialog = null)}>
    <input class="field mono" placeholder="КОД (латиницей, по нему выбираются сцены и команды)" bind:value={draft.code} />
    <input class="field" placeholder="название" bind:value={draft.name} />
  </Dialog>
{:else if dialog === "group"}
  <Dialog title="Новая группа ОС" confirm="Создать" onsubmit={addGroup} onclose={() => (dialog = null)}>
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
  .layer { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .point { min-width: 90px; }
  .greet { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
  .greet textarea { width: 100%; box-sizing: border-box; resize: vertical; }
  .col { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; }
  .chips .chip { cursor: pointer; }
  .term { margin: 0; min-height: 200px; padding: 10px 12px; border-radius: var(--radius-s); background: #0b0d10; color: #cfd6dd; font-size: 12px; line-height: 1.4; overflow: auto; }
  .spacer { flex: 1; }
  .warn { color: var(--warn); margin: 0; }
  .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line-soft); }
  .tab { padding: 9px 12px; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab:hover { color: var(--text); text-decoration: none; }
  .tab.on { color: var(--text); border-bottom-color: var(--accent); }
  .machines { position: relative; }
  .machines .chip { cursor: default; }
  .pop { position: absolute; right: 0; top: 100%; z-index: 5; display: flex; flex-direction: column; gap: 4px; min-width: 180px; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); background: var(--panel-2); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35); }
</style>
