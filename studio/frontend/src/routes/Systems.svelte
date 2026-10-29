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
    { key: "disk", label: "Диск" },
    { key: "groups", label: "Группы и политики" },
    { key: "scenes", label: "Сцены событий" },
    { key: "screen", label: "Смена экрана" },
    { key: "style", label: "Стиль" },
  ];
  const SHOWN = 8;
  let showMachines = $state(false);

  type Blackout = Schemas["BlackoutValues"];
  let blackouts = $state<Record<string, Blackout>>({});
  let blackoutsSaved = $state("");
  const TONES: Record<string, string> = { "": "как у движка", success: "зелёный", warning: "жёлтый", error: "красный", dim: "серый" };
  const TONE_COLOR: Record<string, string> = { success: "var(--ok)", warning: "var(--warn)", error: "var(--danger)", dim: "var(--faint)" };

  const blackoutDirty = (event: string) => JSON.stringify(blackouts[event]) !== JSON.stringify(blackoutsSaved ? JSON.parse(blackoutsSaved)[event] : null);

  async function saveBlackout(event: string) {
    if (!system) return;
    const { data, error } = await api.PUT("/studio/api/systems/{code}/blackouts/{event}", { params: { path: { code: system.code, event } }, body: blackouts[event] });
    done(data, error, "Чёрный экран сохранён.");
  }

  async function resetBlackout(event: string) {
    if (!system) return;
    const { data, error } = await api.DELETE("/studio/api/systems/{code}/blackouts/{event}", { params: { path: { code: system.code, event } } });
    done(data, error, "Сброшено до умолчаний движка.");
  }

  async function chooseScene(slot: string, script: string) {
    if (!system) return;
    const { data, error } = await api.PUT("/studio/api/systems/{code}/scenes/{slot}", { params: { path: { code: system.code, slot } }, body: { script: script || null } });
    done(data, error, script ? "Сцена назначена." : "Играет встроенная сцена.");
  }

  const number = (value: string) => (value === "" ? null : Math.max(0, Math.round(+value)));

  let treePath = $state("/");
  let listing = $state<Schemas["ImageListing"] | null>(null);
  let picking = $state<string | null>(null);

  async function loadTree(path: string) {
    if (!system) return;
    treePath = path;
    listing = (await api.GET("/studio/api/systems/{code}/tree", { params: { path: { code: system.code }, query: { path } } })).data ?? null;
  }

  // дерево обновляется, когда меняется образ (тома, точки, порядок) или открывается вкладка
  $effect(() => {
    if ((tab === "disk" || tab === "paths") && system) {
      JSON.stringify(system.image);
      loadTree(treePath);
    }
  });

  const crumbs = $derived.by(() => {
    const parts = treePath.split("/").filter(Boolean);
    return [{ name: "/", path: "/" }, ...parts.map((name, i) => ({ name, path: "/" + parts.slice(0, i + 1).join("/") }))];
  });

  // шаблон места -> регулярное выражение: {home} раскрывается шаблоном home, {login} любым именем
  function template(name: string) {
    return places[name] || system?.places.find((row) => row.name === name)?.default || "";
  }

  function pattern(text: string, depth = 0): string {
    if (depth > 5) return "";
    return text.split(/(\{home\}|\{login\})/).map((part) =>
      part === "{login}" ? "[^/]+" : part === "{home}" ? pattern(template("home"), depth + 1) : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    ).join("");
  }

  const matchers = $derived(system ? system.places.map((row) => ({ name: row.name, re: new RegExp("^" + pattern(template(row.name)) + "$") })) : []);
  const placesAt = (path: string) => matchers.filter((m) => m.re.test(path)).map((m) => m.name);

  function pickFolder(path: string) {
    if (picking === null) return;
    places = { ...places, [picking]: path };
    picking = null;
  }

  let look = $state({ style: "aether", tokens: {} as Record<string, string> });
  let lookSaved = $state("");
  const lookDirty = $derived(JSON.stringify(look) !== lookSaved);
  const groups = $derived(system ? [...new Set(system.token_info.map((t) => t.group))] : []);
  const HEX6 = /^#[0-9a-fA-F]{6}$/;

  async function saveLook() {
    if (!system) return;
    const { data, error } = await api.PUT("/studio/api/systems/{code}/style", { params: { path: { code: system.code } }, body: look });
    done(data, error, "Стиль сохранён.");
  }

  function setToken(name: string, value: string) {
    look.tokens = value.trim() ? { ...look.tokens, [name]: value } : Object.fromEntries(Object.entries(look.tokens).filter(([key]) => key !== name));
  }

  const pickerValue = (token: Schemas["TokenInfo"]) => (HEX6.test(look.tokens[token.name] ?? "") ? look.tokens[token.name] : HEX6.test(token.default) ? token.default : "#000000");
  const desktopUrl = $derived(system ? `${(window as unknown as { STUDIO: { site: string } }).STUDIO.site}?preview_os=${system.code}` : "#");

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
    look = { style: data.style, tokens: { ...data.style_tokens } };
    lookSaved = JSON.stringify(look);
    blackouts = Object.fromEntries(data.blackouts.map((row) => [row.event, { ...row.own }]));
    blackoutsSaved = JSON.stringify(blackouts);
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

      {#if tab === "disk" || tab === "paths"}
      <div class="diskgrid">
        <div class="col">
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

      <div class="block">
        <h3>Системные пути <button class="btn ghost" onclick={() => (dialog = "place")}>+ Путь</button></h3>
        <p class="muted small">Шаблоны путей для машин ОС: {"{login}"} — логин учётки, {"{home}"} — место home. Пусто: как у движка. «Выбрать» подставляет папку, на которую нажмёте в дереве диска; {"{login}"} дописывается руками.</p>
        <div class="places">
          {#each system.places as row (row.name)}
            <span class="mono pname">{row.name}</span>
            <input class="field mono" bind:value={places[row.name]} placeholder={row.default || "—"} class:bad={errors[row.name]} class:picking={picking === row.name} />
            <button class="btn ghost" class:on={picking === row.name} onclick={() => (picking = picking === row.name ? null : row.name)} title="Выбрать папку на диске справа">Выбрать</button>
            <span class="muted small">{row.machines.length ? `своё у ${row.machines.join(", ")}` : ""}{errors[row.name] ? errors[row.name].join(" ") : ""}</span>
          {/each}
        </div>
        <div><button class="btn primary" disabled={!placesDirty} onclick={savePlaces}>Сохранить пути</button></div>
      </div>
        </div>
      <div class="block tree">
        <h3>Дисковое пространство ОС</h3>
        <p class="muted small">Как сложится файловая система машины ОС без её собственных монтирований: тома образа слоями. Папки, совпавшие с системными путями, подписаны.</p>
        {#if picking}<div class="banner">Выберите папку для «{picking}» <button class="btn ghost" onclick={() => (picking = null)}>Отмена</button></div>{/if}
        <nav class="crumbs">
          {#each crumbs as crumb, i}{#if i > 1}<span class="sep">/</span>{/if}<button onclick={() => loadTree(crumb.path)}>{crumb.name}</button>{/each}
          {#if picking}<button class="btn ghost" onclick={() => pickFolder(treePath)}>Выбрать эту папку</button>{/if}
        </nav>
        <div class="nodes">
          {#each listing?.nodes ?? [] as node (node.path)}
            <div class="node" class:dir={node.is_dir}>
              {#if node.is_dir}
                <button class="nodename" onclick={() => loadTree(node.path)}>▸ {node.name}</button>
              {:else}
                <span class="nodename file">{node.name}</span>
              {/if}
              {#each placesAt(node.path) as name}<span class="chip mono">{name}</span>{/each}
              {#if node.mount}<span class="chip">монтирование</span>{/if}
              <span class="spacer"></span>
              {#if picking && node.is_dir}<button class="btn ghost" onclick={() => pickFolder(node.path)}>Выбрать</button>{/if}
            </div>
          {:else}
            <p class="muted small">{system.image.length ? "Папка пуста." : "Образа нет: добавьте тома слева, и здесь появится дерево."}</p>
          {/each}
        </div>
      </div>
      </div>
      {:else if tab === "scenes"}
        <div class="block">
          <h3>Сцены событий <a class="more" href="#/scenes">библиотека →</a></h3>
          <p class="muted small">Что играет в терминале на событии этой ОС. «Встроенная»: сцена движка. Свою пишут в разделе «Сцены».</p>
          {#each system.scenes as row (row.slot)}
            <div class="slotrow" class:own={row.script}>
              <div class="slotinfo">
                <b>{row.label}</b>
                <span class="mono muted small">{row.slot}</span>
                <span class="params">{#each row.params as name}<code>{"{"}{name}{"}"}</code>{/each}</span>
              </div>
              <div class="slotpick">
                <select class="field" value={row.script ?? ""} onchange={(e) => chooseScene(row.slot, e.currentTarget.value)}>
                  <option value="">Встроенная (движок)</option>
                  {#each system.scene_library as item}<option value={item.slug}>{item.title ? `${item.title} · ${item.slug}` : item.slug}</option>{/each}
                </select>
                {#if row.script}<a class="btn ghost" href="#/scenes/{row.script}">Открыть</a>{/if}
              </div>
            </div>
          {/each}
        </div>
      {:else if tab === "style"}
        <div class="block">
          <h3>Стиль рабочего стола и окон <a class="more" href={desktopUrl} target="_blank" rel="noopener">посмотреть на рабочем столе →</a></h3>
          <p class="muted small">Стиль задаёт раскладку и вид элементов: панель, окна, кнопки, иконки. Стили готовятся в коде, здесь выбирается один из них. Токены ниже переназначают цвета, шрифты и форму поверх выбранного стиля.</p>
          <div class="styles">
            {#each system.styles as item}
              <label class="stylecard" class:on={look.style === item.slug}>
                <input type="radio" name="style" value={item.slug} bind:group={look.style} />
                <b>{item.label}</b>
                <span class="muted small">{item.description}</span>
              </label>
            {/each}
          </div>
        </div>

        {#each groups as group}
          <div class="block">
            <h3>{group}</h3>
            <div class="tokens">
              {#each system.token_info.filter((t) => t.group === group) as token (token.name)}
                <div class="token" class:own={look.tokens[token.name]}>
                  <span>{token.label}<span class="mono muted small"> {token.name}</span></span>
                  {#if token.kind === "font"}
                    <select class="field" value={look.tokens[token.name] ?? ""} onchange={(e) => setToken(token.name, e.currentTarget.value)}>
                      <option value="">как в стиле ({token.default})</option>
                      {#each system.fonts as font}<option value={font.value}>{font.label}</option>{/each}
                    </select>
                  {:else}
                    <div class="tokeninput">
                      {#if token.kind === "color"}
                        <input class="picker" type="color" value={pickerValue(token)} oninput={(e) => setToken(token.name, e.currentTarget.value)} />
                      {/if}
                      <input class="field mono" placeholder={token.default} value={look.tokens[token.name] ?? ""} oninput={(e) => setToken(token.name, e.currentTarget.value)} class:bad={errors.style} />
                    </div>
                  {/if}
                  <button class="btn ghost" disabled={!look.tokens[token.name]} onclick={() => setToken(token.name, "")} title="Как в стиле">×</button>
                </div>
              {/each}
            </div>
          </div>
        {/each}
        {#if errors.style}{#each errors.style as text}<p class="warn small">{text}</p>{/each}{/if}
        <div><button class="btn primary" disabled={!lookDirty} onclick={saveLook}>Сохранить стиль</button></div>
      {:else if tab === "screen"}
        <div class="block">
          <h3>Чёрный экран рабочего стола</h3>
          <p class="muted small">Что показывается, когда рабочий стол меняется. Пустое поле: как у движка (серым в подсказке). Подстановки:
            {#each system.blackout_params as param}<code title={param.label}>{"{"}{param.name}{"}"}</code>{" "}{/each}. Цвет окна один на всё окно. У учётки может
            быть свой текст обрыва: он важнее текста здесь.</p>
          {#each system.blackouts as row (row.event)}
            {@const own = blackouts[row.event]}
            {#if own}
              <div class="bo">
                <div class="bo-head"><b>{row.label}</b>
                  <span class="spacer"></span>
                  <button class="btn ghost" disabled={!blackoutDirty(row.event)} onclick={() => saveBlackout(row.event)}>Сохранить</button>
                  <button class="btn ghost danger" onclick={() => resetBlackout(row.event)}>Сбросить</button>
                </div>
                <div class="bo-grid">
                  <div class="col">
                    <input class="field" placeholder={row.default.title} bind:value={own.title} />
                    <textarea class="field mono" rows="3" spellcheck="false" placeholder={row.default.text} bind:value={own.text}></textarea>
                    {#if errors.text}<p class="warn small">{errors.text.join(" ")}</p>{/if}
                  </div>
                  <div class="col">
                    <select class="field" bind:value={own.tone}>
                      {#each Object.entries(TONES) as [value, label]}<option {value}>{label}{value === "" ? ` (${TONES[row.default.tone]})` : ""}</option>{/each}
                    </select>
                    <div class="three">
                      <label><span class="label">Пауза до окна, мс</span><input class="field" type="number" min="0" placeholder={String(row.default.delay_ms)} value={own.delay_ms ?? ""} oninput={(e) => (own.delay_ms = number(e.currentTarget.value))} /></label>
                      <label><span class="label">Печать, мс/буква</span><input class="field" type="number" min="0" placeholder={String(row.default.speed_ms)} value={own.speed_ms ?? ""} oninput={(e) => (own.speed_ms = number(e.currentTarget.value))} /></label>
                      <label><span class="label">Пауза после, мс</span><input class="field" type="number" min="0" placeholder={String(row.default.hold_ms)} value={own.hold_ms ?? ""} oninput={(e) => (own.hold_ms = number(e.currentTarget.value))} /></label>
                    </div>
                  </div>
                  <div class="bo-mock" style:--tone={TONE_COLOR[own.tone || row.default.tone]}>
                    <div class="bo-title">{own.title || row.default.title}</div>
                    <pre class="bo-body">{own.text || row.default.text}</pre>
                  </div>
                </div>
              </div>
            {/if}
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
          <p class="muted small">Что видит игрок, когда открывается оболочка этой ОС. Пусто: общее приветствие движка. Цвета: <code>&lt;dim&gt;</code>, <code>&lt;success&gt;</code>, <code>&lt;warning&gt;</code>, <code>&lt;error&gt;</code> (закрываются в той же строке). Случайное число: <code>&lt;rand&gt;21-41&lt;/rand&gt;</code>. Время с даты: <code>&lt;since&gt;2027-10-29 | days&lt;/since&gt;</code> (форматы: days, hours, minutes, years, ymd, ago; считается от «сейчас» в мире). Колонки: <code>&lt;table&gt;</code> … <code>&lt;/table&gt;</code>, ячейки через <code>|</code>, ширина считается сама (<code>&lt;table gap=4&gt;</code> — пробелов между колонками; сам знак: <code>&amp;pipe;</code>). Скобки: <code>{"{{"}</code> и <code>{"}}"}</code>.</p>
          <div class="greet">
            <div class="col">
              <textarea class="field mono greeting" rows="22" wrap="off" spellcheck="false" bind:value={props_.greeting} class:bad={errors.greeting}></textarea>
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
  .places { display: grid; grid-template-columns: 100px minmax(200px, 1fr) max-content minmax(60px, auto); gap: 8px 10px; align-items: center; }
  .diskgrid { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(300px, 1fr); gap: 14px; align-items: start; }
  .diskgrid > .col { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
  .tree { position: sticky; top: 8px; max-height: calc(100vh - 140px); overflow: auto; }
  .banner { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: var(--radius-s); background: var(--accent-soft); color: var(--accent); font-size: 13px; }
  .crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 2px; }
  .crumbs button { border: 0; background: none; color: var(--accent); cursor: pointer; padding: 2px 4px; }
  .crumbs .sep { color: var(--faint); }
  .nodes { display: flex; flex-direction: column; }
  .node { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-bottom: 1px solid var(--line-soft); }
  .node:hover { background: var(--panel-2); }
  .nodename { border: 0; background: none; color: var(--text); cursor: pointer; text-align: left; padding: 0; }
  .nodename.file { color: var(--muted); cursor: default; }
  .field.picking { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .btn.on { background: var(--accent-soft); color: var(--accent); }
  .pname { color: var(--muted); }
  .field.bad { border-color: var(--danger); }
  .empty { padding: 24px; }
  .layer { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--line-soft); }
  .point { min-width: 90px; }
  .greet { display: flex; flex-direction: column; gap: 12px; }
  .greet textarea { width: 100%; white-space: pre; overflow: auto; box-sizing: border-box; resize: vertical; }
  .col { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; }
  .chips .chip { cursor: pointer; }
  .term { margin: 0; min-height: 200px; padding: 10px 12px; border-radius: var(--radius-s); background: #0b0d10; color: #cfd6dd; font-size: 12px; line-height: 1.4; overflow: auto; }
  .slotrow { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(260px, 420px); gap: 16px; align-items: center; padding: 10px 12px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); }
  .slotrow.own { border-color: var(--accent); background: var(--accent-soft); }
  .slotinfo { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .params { display: flex; flex-wrap: wrap; gap: 4px; }
  .params code { padding: 0 5px; border-radius: 4px; background: var(--raise); color: var(--muted); font-size: 11px; }
  .slotpick { display: flex; gap: 8px; align-items: center; }
  .slotpick select { flex: 1; min-width: 0; }
  .more { margin-left: auto; font-size: 12px; text-transform: none; letter-spacing: 0; }
  .styles { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px; }
  .stylecard { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border: 1px solid var(--line-soft); border-radius: var(--radius-s); cursor: pointer; }
  .stylecard.on { border-color: var(--accent); background: var(--accent-soft); }
  .stylecard input { display: none; }
  .tokens { display: flex; flex-direction: column; gap: 6px; }
  .token { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(220px, 340px) max-content; gap: 12px; align-items: center; padding: 4px 0; }
  .token.own > span:first-child { color: var(--accent); }
  .tokeninput { display: flex; gap: 6px; align-items: center; }
  .picker { width: 34px; height: 32px; padding: 0; border: 1px solid var(--line); border-radius: var(--radius-s); background: none; cursor: pointer; }
  .bo { display: flex; flex-direction: column; gap: 8px; padding: 10px 0; border-top: 1px solid var(--line-soft); }
  .bo-head { display: flex; align-items: center; gap: 8px; }
  .bo-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 0.9fr); gap: 12px; align-items: start; }
  .bo-mock { border: 1px solid var(--tone); background: #0b0d10; font-size: 12px; }
  .bo-title { padding: 3px 8px; background: var(--tone); color: black; }
  .bo-body { margin: 0; padding: 10px 12px; min-height: 5em; color: var(--tone); white-space: pre-wrap; font-family: inherit; }
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
